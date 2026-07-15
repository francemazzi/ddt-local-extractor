"""Shared pipeline base for interchangeable extraction strategies."""

from __future__ import annotations

import tempfile
import time
from dataclasses import replace
from pathlib import Path

from ddt_local.config import AppConfig, PipelineSettings
from ddt_local.models import (
    ExtractionArtifacts,
    ExtractionMethod,
    ExtractionResult,
    ExecutionMetadata,
    PhaseTiming,
    SourceDocument,
    ollama_documento_schema,
)
from ddt_local.ocr import OcrEngine
from ddt_local.ollama import OllamaClient
from ddt_local.pdf import PdfAnalysis, analyze_pdf, cleanup_render_dir, render_page_png
from ddt_local.quality import apply_quality
from ddt_local.validation import STRUCTURE_SYSTEM_PROMPT, parse_and_validate


class BasePipeline:
    name: str = "base"

    def __init__(
        self,
        settings: PipelineSettings,
        config: AppConfig,
        *,
        client: OllamaClient | None = None,
    ) -> None:
        self.settings = settings
        self.config = replace(
            config,
            pipeline=settings.pipeline,
            ocr_model=settings.ocr_model,
            struct_model=settings.struct_model,
            vision_model=settings.vision_model,
            render_dpi=settings.render_dpi,
            ocr_table_pass=settings.ocr_table_pass,
            min_native_text_chars=settings.min_native_text_chars,
            seed=settings.seed,
            max_retries=settings.max_retries,
            request_timeout_seconds=settings.request_timeout_seconds,
            unload_models=settings.unload_models,
        )
        self._client = client or OllamaClient(self.config)
        self._ocr = OcrEngine(self.config, client=self._client)

    def extract(self, document: SourceDocument) -> ExtractionResult:
        raise NotImplementedError

    def _analyze(self, document: SourceDocument) -> PdfAnalysis:
        return analyze_pdf(document.path, self.config)

    def _render_pages(
        self,
        document: SourceDocument,
        page_numbers: list[int],
        output_dir: Path,
    ) -> list[tuple[int, Path]]:
        rendered: list[tuple[int, Path]] = []
        for num in page_numbers:
            page = render_page_png(
                document.path,
                num,
                self.config,
                output_dir=output_dir,
            )
            rendered.append((page.page_number, page.image_path))
        return rendered

    def _structure_from_text(
        self,
        *,
        document: SourceDocument,
        text: str,
        table_markdown: str | None,
        page_count: int,
        extraction_method: ExtractionMethod,
        phase_timings: list[PhaseTiming],
        artifacts: ExtractionArtifacts,
        ocr_model: str | None = None,
    ) -> ExtractionResult:
        # Cap prompt size to avoid model hangs on very long native text
        max_chars = 12000
        truncated = text if len(text) <= max_chars else text[:max_chars] + "\n\n[TRUNCATED]"
        user_prompt = (
            f"source_filename: {document.filename}\n"
            f"page_count: {page_count}\n\n"
            f"--- Document text ---\n{truncated}\n"
        )
        if table_markdown:
            tables = table_markdown[:4000]
            user_prompt += f"\n--- Tables (Markdown) ---\n{tables}\n"

        schema = ollama_documento_schema()
        start = time.perf_counter()

        def _call(prompt: str) -> str:
            result = self._client.generate_text(
                model=self.settings.struct_model,
                prompt=prompt,
                system=STRUCTURE_SYSTEM_PROMPT,
                json_schema=schema,
                keep_alive="10m",
            )
            return result.text

        raw = _call(user_prompt)
        artifacts.raw_json_response = raw

        def repair_fn(repair_prompt: str) -> str:
            return _call(repair_prompt)

        doc, error, retries = parse_and_validate(
            raw,
            document.filename,
            repair_fn=repair_fn,
        )
        phase_timings.append(
            PhaseTiming(
                phase="structuring",
                duration_seconds=time.perf_counter() - start,
                model=self.settings.struct_model,
            )
        )

        if doc is None:
            return ExtractionResult(
                document=None,
                metadata=self._build_metadata(
                    page_count=page_count,
                    extraction_method=extraction_method,
                    phase_timings=phase_timings,
                    retries=retries,
                    ocr_model=ocr_model,
                ),
                artifacts=artifacts,
                success=False,
                error_message=error or "Validation failed",
            )

        apply_quality(doc)
        return ExtractionResult(
            document=doc,
            metadata=self._build_metadata(
                page_count=page_count,
                extraction_method=extraction_method,
                phase_timings=phase_timings,
                retries=retries,
                ocr_model=ocr_model,
            ),
            artifacts=artifacts,
            success=True,
        )

    def _build_metadata(
        self,
        *,
        page_count: int,
        extraction_method: ExtractionMethod,
        phase_timings: list[PhaseTiming],
        retries: int = 0,
        ocr_model: str | None = None,
        vision_model: str | None = None,
    ) -> ExecutionMetadata:
        total = sum(p.duration_seconds for p in phase_timings)
        return ExecutionMetadata(
            pipeline=self.name,
            ocr_model=ocr_model,
            struct_model=self.settings.struct_model,
            vision_model=vision_model,
            page_count=page_count,
            extraction_method=extraction_method,
            retries=retries,
            phase_timings=phase_timings,
            total_duration_seconds=total,
        )

    def _temp_render_dir(self) -> Path:
        return Path(tempfile.mkdtemp(prefix="ddt_pipeline_"))
