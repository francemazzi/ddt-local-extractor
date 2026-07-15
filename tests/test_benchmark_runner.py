"""Tests for benchmark runner with mocked extraction."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import pytest

from ddt_local.benchmark.runner import run_benchmark
from ddt_local.config import load_config
from ddt_local.database import Database
from ddt_local.models import (
    DatiDocumento,
    DocumentoDDT,
    ExtractionArtifacts,
    ExtractionMethod,
    ExtractionResult,
    ExecutionMetadata,
    RigaDDT,
    Soggetto,
)


@pytest.fixture
def mini_bench(tmp_path):
    docs = tmp_path / "docs"
    gt = tmp_path / "gt"
    cfg = tmp_path / "bench.yaml"
    docs.mkdir()
    gt.mkdir()

    pdf = docs / "mini.pdf"
    pdf.write_bytes(b"%PDF-1.4 mini")

    doc = DocumentoDDT(
        source_filename="mini.pdf",
        fornitore=Soggetto(ragione_sociale="F"),
        destinatario=Soggetto(ragione_sociale="C"),
        documento=DatiDocumento(numero_ddt="1", data_ddt=date(2026, 1, 1)),
        articoli=[RigaDDT(codice="A", quantita=Decimal("1"), unita_misura="PZ")],
    )
    (gt / "mini.json").write_text(doc.model_dump_json(), encoding="utf-8")
    cfg.write_text(
        """
runs:
  - name: native_only_baseline
    pipeline: native_only
    struct_model: qwen3.5:4b
repetitions: 1
""",
        encoding="utf-8",
    )
    return docs, gt, cfg


def test_runner_isolates_production_tables(mini_bench, monkeypatch, tmp_path):
    docs, gt, cfg = mini_bench
    monkeypatch.setenv("DDT_HOME", str(tmp_path / "DDT"))
    app_config = load_config()
    db = Database(tmp_path / "bench.sqlite3")
    db.initialize()

    fake_result = ExtractionResult(
        document=DocumentoDDT(
            source_filename="mini.pdf",
            fornitore=Soggetto(ragione_sociale="F"),
            destinatario=Soggetto(ragione_sociale="C"),
            documento=DatiDocumento(numero_ddt="1", data_ddt=date(2026, 1, 1)),
            articoli=[RigaDDT(codice="A", quantita=Decimal("1"), unita_misura="PZ")],
        ),
        metadata=ExecutionMetadata(
            pipeline="native_only",
            extraction_method=ExtractionMethod.NATIVE_TEXT,
        ),
        artifacts=ExtractionArtifacts(),
        success=True,
    )

    with patch("ddt_local.benchmark.runner.extract_document", return_value=fake_result):
        with patch("ddt_local.benchmark.runner.OllamaClient") as mock_client:
            mock_client.return_value.unload_model = lambda *a, **k: None
            summary = run_benchmark(
                documents_dir=docs,
                ground_truth_dir=gt,
                config_path=cfg,
                app_config=app_config,
                database=db,
            )

    assert len(summary.results) == 1
    assert summary.results[0].score.weighted_score == 1.0
    assert db.count_production_documents() == 0
    assert db.count_benchmark_results() == 1
