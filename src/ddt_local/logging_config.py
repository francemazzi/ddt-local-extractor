"""Structured logging configuration without PII in log output."""

from __future__ import annotations

import logging
import sys
import uuid
from contextvars import ContextVar
from pathlib import Path
from typing import Any

_run_id_var: ContextVar[str] = ContextVar("run_id", default="")
_document_id_var: ContextVar[str] = ContextVar("document_id", default="")
_file_hash_var: ContextVar[str] = ContextVar("file_hash", default="")
_filename_var: ContextVar[str] = ContextVar("filename", default="")
_phase_var: ContextVar[str] = ContextVar("phase", default="")
_pipeline_var: ContextVar[str] = ContextVar("pipeline", default="")
_model_var: ContextVar[str] = ContextVar("model", default="")


class StructuredFormatter(logging.Formatter):
    """Emit key=value structured log lines without document content."""

    def format(self, record: logging.LogRecord) -> str:
        parts: list[str] = [
            f"timestamp={self.formatTime(record, '%Y-%m-%dT%H:%M:%S')}",
            f"level={record.levelname}",
            f"logger={record.name}",
            f"message={record.getMessage()}",
        ]
        context_fields: list[tuple[str, ContextVar[str]]] = [
            ("run_id", _run_id_var),
            ("document_id", _document_id_var),
            ("file_hash", _file_hash_var),
            ("filename", _filename_var),
            ("phase", _phase_var),
            ("pipeline", _pipeline_var),
            ("model", _model_var),
        ]
        for name, var in context_fields:
            value = var.get()
            if value:
                parts.append(f"{name}={value}")

        for key, value in getattr(record, "extra_fields", {}).items():
            if _is_safe_log_value(key, value):
                parts.append(f"{key}={value}")

        if record.exc_info and record.exc_info[1]:
            parts.append(f"error={type(record.exc_info[1]).__name__}")

        return " ".join(parts)


def _is_safe_log_value(key: str, value: Any) -> bool:
    """Reject fields that may contain PII or full document content."""
    blocked_keys = {
        "ocr_text",
        "native_text",
        "raw_json",
        "partita_iva",
        "indirizzo",
        "descrizione",
        "ragione_sociale",
        "content",
        "body",
    }
    if key.lower() in blocked_keys:
        return False
    if isinstance(value, str) and len(value) > 200:
        return False
    return True


def configure_logging(
    level: str = "INFO",
    *,
    log_path: Path | None = None,
    console: bool = True,
) -> None:
    """Configure structured logging for CLI or an invisible desktop runner."""
    root = logging.getLogger()
    root.handlers.clear()
    formatter = StructuredFormatter()
    if console:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(formatter)
        root.addHandler(handler)
    if log_path is not None:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handler = logging.FileHandler(log_path, encoding="utf-8")
        handler.setFormatter(formatter)
        root.addHandler(handler)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))


def new_run_id() -> str:
    run_id = uuid.uuid4().hex[:12]
    _run_id_var.set(run_id)
    return run_id


def set_log_context(**kwargs: str) -> None:
    mapping = {
        "run_id": _run_id_var,
        "document_id": _document_id_var,
        "file_hash": _file_hash_var,
        "filename": _filename_var,
        "phase": _phase_var,
        "pipeline": _pipeline_var,
        "model": _model_var,
    }
    for key, value in kwargs.items():
        if key in mapping and value:
            mapping[key].set(value)


def clear_log_context() -> None:
    for var in (
        _document_id_var,
        _file_hash_var,
        _filename_var,
        _phase_var,
        _pipeline_var,
        _model_var,
    ):
        var.set("")


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
