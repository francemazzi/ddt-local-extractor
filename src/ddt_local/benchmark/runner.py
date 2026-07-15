"""Benchmark runner — execute configs against ground truth."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from ddt_local.benchmark.ground_truth import COLLECTION_FILENAME, load_ground_truth_dir
from ddt_local.benchmark.scoring import ScoreResult, score_prediction
from ddt_local.config import AppConfig, settings_from_benchmark_run
from ddt_local.database import Database
from ddt_local.extractor import extract_document
from ddt_local.files import compute_sha256
from ddt_local.models import DocumentoDDT, ExtractionResult, SourceDocument
from ddt_local.ollama import OllamaClient

logger = logging.getLogger(__name__)


@dataclass
class BenchmarkConfig:
    runs: list[dict[str, Any]]
    repetitions: int = 1
    documents_filter: list[str] | None = None


@dataclass
class DocumentRunResult:
    run_name: str
    pipeline: str
    ocr_model: str | None
    struct_model: str | None
    vision_model: str | None
    document_filename: str
    repetition: int
    score: ScoreResult
    success: bool
    error_message: str | None = None
    total_latency_seconds: float = 0.0
    peak_memory_bytes: int | None = None
    phase_latency: dict[str, float] = field(default_factory=dict)
    retry_count: int = 0
    validation_passed: bool = False
    prediction: DocumentoDDT | None = None


@dataclass
class BenchmarkSummary:
    results: list[DocumentRunResult] = field(default_factory=list)
    ranking: list[tuple[str, float]] = field(default_factory=list)
    started_at: str = ""
    finished_at: str = ""

    def mean_scores_by_run(self) -> dict[str, float]:
        buckets: dict[str, list[float]] = {}
        for r in self.results:
            buckets.setdefault(r.run_name, []).append(r.score.weighted_score)
        return {name: sum(vals) / len(vals) for name, vals in buckets.items() if vals}


def load_benchmark_config(path: Path) -> BenchmarkConfig:
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return BenchmarkConfig(
        runs=list(data.get("runs") or []),
        repetitions=int(data.get("repetitions") or 1),
        documents_filter=data.get("documents_filter"),
    )


def _list_documents(documents_dir: Path, filter_names: list[str] | None) -> list[Path]:
    pdfs = sorted(
        p
        for p in documents_dir.glob("*.pdf")
        if p.name != COLLECTION_FILENAME and not p.name.startswith(".")
    )
    if filter_names:
        wanted = set(filter_names)
        pdfs = [p for p in pdfs if p.name in wanted]
    return pdfs


def run_benchmark(
    *,
    documents_dir: Path,
    ground_truth_dir: Path,
    config_path: Path,
    app_config: AppConfig,
    database: Database | None = None,
    runs_filter: str | None = None,
    repetitions: int | None = None,
    keep_artifacts: bool = False,
) -> BenchmarkSummary:
    """Run all benchmark configurations against documents and ground truth."""
    bench_cfg = load_benchmark_config(config_path)
    reps = repetitions if repetitions is not None else bench_cfg.repetitions
    runs = bench_cfg.runs
    if runs_filter:
        runs = [r for r in runs if r.get("name") == runs_filter]
    if not runs:
        raise ValueError("No benchmark runs to execute")

    gt_map = load_ground_truth_dir(ground_truth_dir)
    documents = _list_documents(documents_dir, bench_cfg.documents_filter)
    if not documents:
        raise ValueError(f"No PDF documents found in {documents_dir}")

    db = database or Database(app_config.database_path)
    db.initialize()
    client = OllamaClient(app_config)
    summary = BenchmarkSummary(started_at=datetime.now(timezone.utc).isoformat())
    previous_models: set[str] = set()

    for run in runs:
        run_name = run.get("name") or run.get("pipeline") or "unnamed"
        settings = settings_from_benchmark_run(app_config, run)

        # Unload previous models before loading new ones
        models_to_unload = previous_models - {
            m
            for m in (
                settings.ocr_model,
                settings.struct_model,
                settings.vision_model,
            )
            if m
        }
        for model in models_to_unload:
            client.unload_model(model)

        with db.transaction() as conn:
            run_id = db.insert_benchmark_run(
                conn,
                run_name=run_name,
                pipeline=settings.pipeline,
                ocr_model=settings.ocr_model if settings.pipeline != "vision_direct" else None,
                struct_model=settings.struct_model if settings.pipeline != "vision_direct" else None,
                vision_model=settings.vision_model if settings.pipeline == "vision_direct" else None,
                render_dpi=settings.render_dpi,
                seed=settings.seed,
            )

        for pdf_path in documents:
            gt = gt_map.get(pdf_path.name)
            if gt is None:
                stem = pdf_path.stem + ".json"
                alt = ground_truth_dir / stem
                if alt.exists():
                    from ddt_local.benchmark.ground_truth import load_ground_truth_file

                    gt = load_ground_truth_file(alt)
                else:
                    logger.warning("No ground truth for %s — skipping", pdf_path.name)
                    continue

            for rep in range(1, reps + 1):
                source = SourceDocument(
                    path=pdf_path,
                    filename=pdf_path.name,
                    sha256=compute_sha256(pdf_path),
                    size_bytes=pdf_path.stat().st_size,
                )
                try:
                    extraction = extract_document(source, app_config, settings)
                except Exception as exc:
                    logger.exception(
                        "extraction failed run=%s doc=%s: %s",
                        run_name,
                        pdf_path.name,
                        type(exc).__name__,
                    )
                    from ddt_local.models import ExtractionArtifacts, ExtractionMethod, ExecutionMetadata

                    extraction = ExtractionResult(
                        document=None,
                        metadata=ExecutionMetadata(
                            pipeline=settings.pipeline,
                            ocr_model=settings.ocr_model,
                            struct_model=settings.struct_model,
                            vision_model=settings.vision_model,
                            extraction_method=ExtractionMethod.NATIVE_TEXT,
                        ),
                        artifacts=ExtractionArtifacts(),
                        success=False,
                        error_message=f"{type(exc).__name__}: {exc}",
                    )

                prediction = extraction.document if extraction.success else None
                score = score_prediction(gt, prediction)

                phase_latency = {
                    p.phase: p.duration_seconds for p in extraction.metadata.phase_timings
                }
                doc_result = DocumentRunResult(
                    run_name=run_name,
                    pipeline=settings.pipeline,
                    ocr_model=settings.ocr_model,
                    struct_model=settings.struct_model,
                    vision_model=settings.vision_model,
                    document_filename=pdf_path.name,
                    repetition=rep,
                    score=score,
                    success=extraction.success,
                    error_message=extraction.error_message,
                    total_latency_seconds=extraction.metadata.total_duration_seconds,
                    peak_memory_bytes=extraction.metadata.peak_memory_bytes,
                    phase_latency=phase_latency,
                    retry_count=extraction.metadata.retries,
                    validation_passed=extraction.success,
                    prediction=prediction,
                )
                summary.results.append(doc_result)

                with db.transaction() as conn:
                    db.insert_benchmark_result(
                        conn,
                        benchmark_run_id=run_id,
                        document_filename=pdf_path.name,
                        repetition=rep,
                        metrics={
                            "field_metrics": score.field_metrics,
                            "lines_found": score.lines_found,
                            "lines_missing": score.lines_missing,
                            "lines_invented": score.lines_invented,
                            "wrong_quantities": score.wrong_quantities,
                            "total_latency_seconds": doc_result.total_latency_seconds,
                            "phase_latency": phase_latency,
                            "peak_memory_bytes": doc_result.peak_memory_bytes,
                            "validation_passed": doc_result.validation_passed,
                            "retry_count": doc_result.retry_count,
                            "weighted_score": score.weighted_score,
                        },
                    )

                if keep_artifacts and extraction.artifacts.raw_json_response:
                    art_dir = (
                        app_config.benchmark_dir
                        / "artifacts"
                        / run_name
                        / pdf_path.stem
                    )
                    art_dir.mkdir(parents=True, exist_ok=True)
                    (art_dir / f"rep{rep}_raw.json.txt").write_text(
                        extraction.artifacts.raw_json_response or "",
                        encoding="utf-8",
                    )

                logger.info(
                    "benchmark run=%s doc=%s score=%.3f success=%s",
                    run_name,
                    pdf_path.name,
                    score.weighted_score,
                    extraction.success,
                )

        previous_models = {
            m
            for m in (settings.ocr_model, settings.struct_model, settings.vision_model)
            if m
        }

    # Unload remaining models
    for model in previous_models:
        client.unload_model(model)

    means = summary.mean_scores_by_run()
    summary.ranking = sorted(means.items(), key=lambda x: x[1], reverse=True)
    summary.finished_at = datetime.now(timezone.utc).isoformat()
    return summary
