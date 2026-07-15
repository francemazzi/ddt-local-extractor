"""Tests for structured logging."""

from __future__ import annotations

import logging

from ddt_local.logging_config import (
    StructuredFormatter,
    clear_log_context,
    configure_logging,
    get_logger,
    new_run_id,
    set_log_context,
)


def test_structured_formatter_includes_context():
    configure_logging("DEBUG")
    new_run_id()
    set_log_context(
        filename="01_DDT.pdf",
        phase="ocr",
        pipeline="ocr_struct",
        model="glm-ocr:latest",
    )
    logger = get_logger("test")
    record = logger.makeRecord(
        "test", logging.INFO, "", 0, "OCR completed", (), None
    )
    formatted = StructuredFormatter().format(record)
    assert "phase=ocr" in formatted
    assert "pipeline=ocr_struct" in formatted
    assert "model=glm-ocr:latest" in formatted
    assert "filename=01_DDT.pdf" in formatted
    clear_log_context()


def test_blocked_pii_fields_not_logged():
    configure_logging("DEBUG")
    logger = get_logger("test")
    record = logger.makeRecord(
        "test",
        logging.INFO,
        "",
        0,
        "test",
        (),
        None,
    )
    record.extra_fields = {
        "partita_iva": "IT123",
        "duration_seconds": 1.5,
    }
    formatted = StructuredFormatter().format(record)
    assert "partita_iva" not in formatted
    assert "duration_seconds=1.5" in formatted
