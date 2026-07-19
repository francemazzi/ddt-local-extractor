"""Unit and local integration tests for the one-shot production job."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest

from ddt_local.cli import main
from ddt_local.config import AppConfig
from ddt_local.database import Database
from ddt_local.files import acquire_job_lock, compute_sha256, release_job_lock
from ddt_local.models import (
    DatiDocumento,
    DocumentoDDT,
    ExecutionMetadata,
    ExtractionMethod,
    ExtractionResult,
    RigaDDT,
    Soggetto,
)
from ddt_local.production import requeue_document, run_once


def _result(filename: str, *, success: bool = True) -> ExtractionResult:
    if not success:
        return ExtractionResult(
            metadata=ExecutionMetadata(
                pipeline="ocr_struct", extraction_method=ExtractionMethod.OCR
            ),
            success=False,
            error_message="simulated model failure",
        )
    return ExtractionResult(
        document=DocumentoDDT(
            source_filename=filename,
            fornitore=Soggetto(ragione_sociale="Fornitore"),
            destinatario=Soggetto(ragione_sociale="Destinatario"),
            documento=DatiDocumento(numero_ddt="DDT-001", data_ddt=date(2026, 7, 18)),
            articoli=[RigaDDT(codice="ART-1", descrizione="Articolo", quantita="2", unita_misura="PZ")],
            quality_score=1.0,
        ),
        metadata=ExecutionMetadata(
            pipeline="ocr_struct",
            page_count=1,
            extraction_method=ExtractionMethod.NATIVE_TEXT,
        ),
        success=True,
    )


def _write_inbox_pdf(config: AppConfig, name: str = "test.pdf") -> Path:
    config.inbox_dir.mkdir(parents=True, exist_ok=True)
    document = config.inbox_dir / name
    document.write_bytes(b"%PDF-1.4 test fixture")
    return document


def test_run_once_empty_queue_exits_successfully(app_config: AppConfig):
    summary = run_once(app_config, check_stability=False)

    assert summary.exit_code == 0
    assert summary.queued == 0
    assert summary.processed == 0


def test_run_once_persists_exports_and_archives_success(app_config: AppConfig):
    source = _write_inbox_pdf(app_config)
    with patch("ddt_local.production.extract_document", side_effect=lambda doc, _: _result(doc.filename)):
        summary = run_once(app_config, check_stability=False)

    database = Database(app_config.database_path)
    assert summary.processed == 1
    assert summary.exit_code == 0
    assert database.count_production_documents() == 1
    assert app_config.excel_path.exists()
    assert not source.exists()
    assert list(app_config.processed_dir.rglob("test.pdf"))


def test_duplicate_is_not_reextracted_and_is_archived(app_config: AppConfig):
    source = _write_inbox_pdf(app_config, "duplicate.pdf")
    database = Database(app_config.database_path)
    database.initialize()
    with database.transaction() as conn:
        database.insert_source_document(
            conn,
            sha256=compute_sha256(source),
            original_filename=source.name,
            size_bytes=source.stat().st_size,
            status="processed",
        )

    with patch("ddt_local.production.extract_document") as extract:
        summary = run_once(app_config, check_stability=False)

    assert extract.call_count == 0
    assert summary.duplicates == 1
    assert list(app_config.processed_dir.rglob("duplicate.pdf"))


def test_lock_is_a_successful_noop(app_config: AppConfig):
    app_config.ddt_home.mkdir(parents=True)
    lock = acquire_job_lock(app_config)
    try:
        summary = run_once(app_config, check_stability=False)
    finally:
        release_job_lock(lock)

    assert summary.locked is True
    assert summary.exit_code == 0


def test_failed_extraction_is_persisted_and_moved_to_errors(app_config: AppConfig):
    source = _write_inbox_pdf(app_config, "bad.pdf")
    with patch("ddt_local.production.extract_document", side_effect=lambda doc, _: _result(doc.filename, success=False)):
        summary = run_once(app_config, check_stability=False)

    assert summary.errors == 1
    assert not source.exists()
    assert list(app_config.errors_dir.rglob("bad.pdf"))
    assert Database(app_config.database_path).production_status_counts() == {"error": 1}


def test_reprocess_requeues_archived_document(app_config: AppConfig):
    source = _write_inbox_pdf(app_config, "retry.pdf")
    file_hash = compute_sha256(source)
    with patch("ddt_local.production.extract_document", side_effect=lambda doc, _: _result(doc.filename)):
        run_once(app_config, check_stability=False)

    requeued = requeue_document(app_config, file_hash)

    assert requeued.parent == app_config.inbox_dir
    assert requeued.exists()
    assert Database(app_config.database_path).document_exists_by_hash(file_hash) is False


def test_cli_init_run_status_export_and_reprocess(app_config: AppConfig, monkeypatch: pytest.MonkeyPatch, capsys):
    monkeypatch.setenv("DDT_HOME", str(app_config.ddt_home))
    assert main(["init"]) == 0
    _write_inbox_pdf(app_config, "cli.pdf")
    with patch("ddt_local.production.extract_document", side_effect=lambda doc, _: _result(doc.filename)):
        assert main(["run", "--once"]) == 0
    assert main(["status"]) == 0
    assert main(["export"]) == 0
    output = capsys.readouterr().out
    assert "Processed: 1" in output


def test_cli_run_requires_once(app_config: AppConfig, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DDT_HOME", str(app_config.ddt_home))
    assert main(["run"]) == 2
