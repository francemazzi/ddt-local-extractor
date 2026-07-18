"""SQLite database layer for production and benchmark data."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Generator, Iterator

from ddt_local.models import ExtractionResult, SourceDocument

SCHEMA_VERSION = "1"


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_default(obj: Any) -> Any:
    if isinstance(obj, Decimal):
        return str(obj)
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


@dataclass
class Database:
    path: Path

    def connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    @contextmanager
    def transaction(self) -> Generator[sqlite3.Connection, None, None]:
        conn = self.connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def initialize(self) -> None:
        with self.transaction() as conn:
            self._create_schema(conn)

    def _create_schema(self, conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS source_documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sha256 TEXT NOT NULL UNIQUE,
                original_filename TEXT NOT NULL,
                size_bytes INTEGER NOT NULL,
                modified_at TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                page_count INTEGER DEFAULT 0,
                extraction_method TEXT,
                pipeline TEXT,
                started_at TEXT,
                finished_at TEXT,
                duration_seconds REAL,
                error_message TEXT,
                schema_version TEXT NOT NULL DEFAULT '1',
                ocr_model TEXT,
                struct_model TEXT
            );

            CREATE TABLE IF NOT EXISTS ocr_pages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_document_id INTEGER NOT NULL,
                page_number INTEGER NOT NULL,
                ocr_text TEXT,
                table_text TEXT,
                ocr_duration_seconds REAL,
                warning TEXT,
                FOREIGN KEY (source_document_id) REFERENCES source_documents(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS ddt_headers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_document_id INTEGER NOT NULL UNIQUE,
                source_filename TEXT NOT NULL,
                numero_ddt TEXT,
                data_ddt TEXT,
                riferimento_ordine TEXT,
                causale_trasporto TEXT,
                numero_colli TEXT,
                peso_lordo TEXT,
                peso_netto TEXT,
                vettore TEXT,
                destinazione TEXT,
                fornitore_ragione_sociale TEXT,
                fornitore_partita_iva TEXT,
                fornitore_indirizzo TEXT,
                destinatario_ragione_sociale TEXT,
                destinatario_partita_iva TEXT,
                destinatario_indirizzo TEXT,
                quality_score REAL DEFAULT 0,
                requires_review INTEGER DEFAULT 0,
                raw_json TEXT,
                FOREIGN KEY (source_document_id) REFERENCES source_documents(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS ddt_lines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_document_id INTEGER NOT NULL,
                line_index INTEGER NOT NULL,
                codice TEXT,
                descrizione TEXT,
                quantita TEXT,
                unita_misura TEXT,
                lotto TEXT,
                matricola TEXT,
                FOREIGN KEY (source_document_id) REFERENCES source_documents(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS validation_issues (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_document_id INTEGER NOT NULL,
                field_path TEXT NOT NULL,
                issue_type TEXT NOT NULL,
                severity TEXT NOT NULL,
                description TEXT,
                FOREIGN KEY (source_document_id) REFERENCES source_documents(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS benchmark_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_name TEXT NOT NULL,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                pipeline TEXT NOT NULL,
                ocr_model TEXT,
                struct_model TEXT,
                vision_model TEXT,
                render_dpi INTEGER,
                seed INTEGER,
                schema_version TEXT NOT NULL DEFAULT '1',
                notes TEXT
            );

            CREATE TABLE IF NOT EXISTS benchmark_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                benchmark_run_id INTEGER NOT NULL,
                document_filename TEXT NOT NULL,
                repetition INTEGER NOT NULL DEFAULT 1,
                field_metrics_json TEXT,
                lines_found INTEGER DEFAULT 0,
                lines_missing INTEGER DEFAULT 0,
                lines_invented INTEGER DEFAULT 0,
                wrong_quantities INTEGER DEFAULT 0,
                total_latency_seconds REAL,
                phase_latency_json TEXT,
                peak_memory_bytes INTEGER,
                validation_passed INTEGER DEFAULT 0,
                retry_count INTEGER DEFAULT 0,
                weighted_score REAL,
                FOREIGN KEY (benchmark_run_id) REFERENCES benchmark_runs(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_source_documents_status
                ON source_documents(status);
            CREATE INDEX IF NOT EXISTS idx_ddt_headers_requires_review
                ON ddt_headers(requires_review);
            CREATE INDEX IF NOT EXISTS idx_benchmark_results_run
                ON benchmark_results(benchmark_run_id);
            """
        )

    def document_exists_by_hash(self, sha256: str) -> bool:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM source_documents WHERE sha256 = ?", (sha256,)
            ).fetchone()
            return row is not None

    def source_document_by_hash(self, sha256: str) -> sqlite3.Row | None:
        """Return a production source record, if it exists."""
        with self.connect() as conn:
            return conn.execute(
                "SELECT * FROM source_documents WHERE sha256 = ?", (sha256,)
            ).fetchone()

    def delete_source_document_by_hash(self, sha256: str) -> bool:
        """Delete one source record and all of its dependent production records."""
        with self.transaction() as conn:
            cursor = conn.execute("DELETE FROM source_documents WHERE sha256 = ?", (sha256,))
        return cursor.rowcount > 0

    def insert_source_document(
        self,
        conn: sqlite3.Connection,
        *,
        sha256: str,
        original_filename: str,
        size_bytes: int,
        status: str = "processing",
        pipeline: str | None = None,
        ocr_model: str | None = None,
        struct_model: str | None = None,
        page_count: int = 0,
        extraction_method: str | None = None,
    ) -> int:
        cursor = conn.execute(
            """
            INSERT INTO source_documents (
                sha256, original_filename, size_bytes, status, started_at,
                pipeline, ocr_model, struct_model, page_count, extraction_method,
                schema_version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                sha256,
                original_filename,
                size_bytes,
                status,
                _utcnow(),
                pipeline,
                ocr_model,
                struct_model,
                page_count,
                extraction_method,
                SCHEMA_VERSION,
            ),
        )
        return int(cursor.lastrowid)

    def insert_ocr_page(
        self,
        conn: sqlite3.Connection,
        *,
        source_document_id: int,
        page_number: int,
        ocr_text: str | None,
        table_text: str | None = None,
        ocr_duration_seconds: float | None = None,
        warning: str | None = None,
    ) -> int:
        cursor = conn.execute(
            """
            INSERT INTO ocr_pages (
                source_document_id, page_number, ocr_text, table_text,
                ocr_duration_seconds, warning
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                source_document_id,
                page_number,
                ocr_text,
                table_text,
                ocr_duration_seconds,
                warning,
            ),
        )
        return int(cursor.lastrowid)

    def insert_validation_issue(
        self,
        conn: sqlite3.Connection,
        *,
        source_document_id: int,
        field_path: str,
        issue_type: str,
        severity: str,
        description: str | None = None,
    ) -> int:
        cursor = conn.execute(
            """
            INSERT INTO validation_issues (
                source_document_id, field_path, issue_type, severity, description
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (source_document_id, field_path, issue_type, severity, description),
        )
        return int(cursor.lastrowid)

    def persist_extraction_result(
        self,
        source: SourceDocument,
        result: ExtractionResult,
    ) -> int:
        """Persist one production result atomically, including its artifacts and issues.

        A successful extraction creates the header and line archive. A failed one is
        retained as an ``error`` source document so it can be inspected or retried.
        Any database exception rolls back the complete document record.
        """
        metadata = result.metadata
        with self.transaction() as conn:
            document_id = self.insert_source_document(
                conn,
                sha256=source.sha256,
                original_filename=source.filename,
                size_bytes=source.size_bytes,
                status="processing",
                pipeline=metadata.pipeline,
                ocr_model=metadata.ocr_model,
                struct_model=metadata.struct_model,
                page_count=metadata.page_count or source.page_count,
                extraction_method=str(metadata.extraction_method),
            )

            ocr_duration = sum(
                timing.duration_seconds
                for timing in metadata.phase_timings
                if timing.phase == "ocr"
            )
            for page_number, ocr_text in enumerate(result.artifacts.ocr_text_by_page, start=1):
                self.insert_ocr_page(
                    conn,
                    source_document_id=document_id,
                    page_number=page_number,
                    ocr_text=ocr_text,
                    table_text=result.artifacts.table_markdown if page_number == 1 else None,
                    ocr_duration_seconds=ocr_duration or None,
                )

            if result.success:
                if result.document is None:
                    raise ValueError("A successful extraction requires a DocumentoDDT")
                header_data = _header_data_from_document(
                    result.document.model_dump(mode="json"),
                    raw_json=result.artifacts.raw_json_response,
                )
                self.insert_ddt_header(
                    conn,
                    source_document_id=document_id,
                    header_data=header_data,
                )
                self.insert_ddt_lines(
                    conn,
                    source_document_id=document_id,
                    lines=_line_data_from_document(result.document.model_dump(mode="json")),
                )
                for field_path in result.document.campi_da_verificare:
                    self.insert_validation_issue(
                        conn,
                        source_document_id=document_id,
                        field_path=field_path,
                        issue_type="quality_flag",
                        severity="warning",
                    )
                for warning in result.document.warning:
                    self.insert_validation_issue(
                        conn,
                        source_document_id=document_id,
                        field_path="document",
                        issue_type="pipeline_warning",
                        severity="warning",
                        description=warning,
                    )
                status = "processed"
                error_message = None
            else:
                status = "error"
                error_message = result.error_message or "Extraction failed"
                self.insert_validation_issue(
                    conn,
                    source_document_id=document_id,
                    field_path="document",
                    issue_type="extraction_error",
                    severity="error",
                    description=error_message,
                )

            conn.execute(
                """
                UPDATE source_documents
                SET status = ?, page_count = ?, extraction_method = ?, pipeline = ?,
                    ocr_model = ?, struct_model = ?, finished_at = ?,
                    duration_seconds = ?, error_message = ?
                WHERE id = ?
                """,
                (
                    status,
                    metadata.page_count or source.page_count,
                    str(metadata.extraction_method),
                    metadata.pipeline,
                    metadata.ocr_model,
                    metadata.struct_model,
                    _utcnow(),
                    metadata.total_duration_seconds,
                    error_message,
                    document_id,
                ),
            )
        return document_id

    def insert_ddt_header(
        self,
        conn: sqlite3.Connection,
        *,
        source_document_id: int,
        header_data: dict[str, Any],
    ) -> int:
        cursor = conn.execute(
            """
            INSERT INTO ddt_headers (
                source_document_id, source_filename, numero_ddt, data_ddt,
                riferimento_ordine, causale_trasporto, numero_colli, peso_lordo,
                peso_netto, vettore, destinazione, fornitore_ragione_sociale,
                fornitore_partita_iva, fornitore_indirizzo, destinatario_ragione_sociale,
                destinatario_partita_iva, destinatario_indirizzo, quality_score,
                requires_review, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                source_document_id,
                header_data.get("source_filename"),
                header_data.get("numero_ddt"),
                header_data.get("data_ddt"),
                header_data.get("riferimento_ordine"),
                header_data.get("causale_trasporto"),
                header_data.get("numero_colli"),
                header_data.get("peso_lordo"),
                header_data.get("peso_netto"),
                header_data.get("vettore"),
                header_data.get("destinazione"),
                header_data.get("fornitore_ragione_sociale"),
                header_data.get("fornitore_partita_iva"),
                header_data.get("fornitore_indirizzo"),
                header_data.get("destinatario_ragione_sociale"),
                header_data.get("destinatario_partita_iva"),
                header_data.get("destinatario_indirizzo"),
                header_data.get("quality_score", 0),
                int(header_data.get("requires_review", False)),
                header_data.get("raw_json"),
            ),
        )
        return int(cursor.lastrowid)

    def insert_ddt_lines(
        self,
        conn: sqlite3.Connection,
        *,
        source_document_id: int,
        lines: list[dict[str, Any]],
    ) -> None:
        conn.executemany(
            """
            INSERT INTO ddt_lines (
                source_document_id, line_index, codice, descrizione, quantita,
                unita_misura, lotto, matricola
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    source_document_id,
                    line.get("line_index"),
                    line.get("codice"),
                    line.get("descrizione"),
                    line.get("quantita"),
                    line.get("unita_misura"),
                    line.get("lotto"),
                    line.get("matricola"),
                )
                for line in lines
            ],
        )

    def insert_benchmark_run(
        self,
        conn: sqlite3.Connection,
        *,
        run_name: str,
        pipeline: str,
        ocr_model: str | None = None,
        struct_model: str | None = None,
        vision_model: str | None = None,
        render_dpi: int | None = None,
        seed: int | None = None,
        notes: str | None = None,
    ) -> int:
        cursor = conn.execute(
            """
            INSERT INTO benchmark_runs (
                run_name, started_at, pipeline, ocr_model, struct_model,
                vision_model, render_dpi, seed, schema_version, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_name,
                _utcnow(),
                pipeline,
                ocr_model,
                struct_model,
                vision_model,
                render_dpi,
                seed,
                SCHEMA_VERSION,
                notes,
            ),
        )
        return int(cursor.lastrowid)

    def insert_benchmark_result(
        self,
        conn: sqlite3.Connection,
        *,
        benchmark_run_id: int,
        document_filename: str,
        repetition: int,
        metrics: dict[str, Any],
    ) -> int:
        cursor = conn.execute(
            """
            INSERT INTO benchmark_results (
                benchmark_run_id, document_filename, repetition,
                field_metrics_json, lines_found, lines_missing, lines_invented,
                wrong_quantities, total_latency_seconds, phase_latency_json,
                peak_memory_bytes, validation_passed, retry_count, weighted_score
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                benchmark_run_id,
                document_filename,
                repetition,
                json.dumps(metrics.get("field_metrics", {}), default=_json_default),
                metrics.get("lines_found", 0),
                metrics.get("lines_missing", 0),
                metrics.get("lines_invented", 0),
                metrics.get("wrong_quantities", 0),
                metrics.get("total_latency_seconds"),
                json.dumps(metrics.get("phase_latency", {})),
                metrics.get("peak_memory_bytes"),
                int(metrics.get("validation_passed", False)),
                metrics.get("retry_count", 0),
                metrics.get("weighted_score"),
            ),
        )
        return int(cursor.lastrowid)

    def count_production_documents(self) -> int:
        with self.connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS c FROM ddt_headers").fetchone()
            return int(row["c"])

    def count_benchmark_results(self) -> int:
        with self.connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS c FROM benchmark_results").fetchone()
            return int(row["c"])

    def production_headers(self) -> list[sqlite3.Row]:
        """Return persisted DDT headers in stable export order."""
        with self.connect() as conn:
            return conn.execute(
                """
                SELECT h.*, s.sha256, s.original_filename, s.finished_at
                FROM ddt_headers AS h
                JOIN source_documents AS s ON s.id = h.source_document_id
                ORDER BY h.data_ddt, h.id
                """
            ).fetchall()

    def production_lines(self) -> list[sqlite3.Row]:
        """Return persisted DDT lines with their header context."""
        with self.connect() as conn:
            return conn.execute(
                """
                SELECT l.*, h.numero_ddt, h.data_ddt, h.source_filename
                FROM ddt_lines AS l
                JOIN ddt_headers AS h ON h.source_document_id = l.source_document_id
                ORDER BY h.data_ddt, h.id, l.line_index, l.id
                """
            ).fetchall()

    def production_errors(self) -> list[sqlite3.Row]:
        """Return extraction failures and validation errors for the Excel archive."""
        with self.connect() as conn:
            return conn.execute(
                """
                SELECT s.original_filename, s.sha256, s.status, s.error_message,
                       s.finished_at, v.field_path, v.issue_type, v.severity,
                       v.description
                FROM source_documents AS s
                LEFT JOIN validation_issues AS v ON v.source_document_id = s.id
                WHERE s.status = 'error' OR v.severity = 'error'
                ORDER BY s.finished_at, s.id, v.id
                """
            ).fetchall()

    def production_review_items(self) -> list[sqlite3.Row]:
        """Return headers requiring human review, with their recorded flags."""
        with self.connect() as conn:
            return conn.execute(
                """
                SELECT h.source_filename, h.numero_ddt, h.data_ddt,
                       h.quality_score, h.requires_review,
                       GROUP_CONCAT(v.field_path || ': ' || COALESCE(v.description, v.issue_type), '\n')
                           AS issues
                FROM ddt_headers AS h
                LEFT JOIN validation_issues AS v ON v.source_document_id = h.source_document_id
                WHERE h.requires_review = 1
                GROUP BY h.id
                ORDER BY h.quality_score, h.data_ddt, h.id
                """
            ).fetchall()

    def production_status_counts(self) -> dict[str, int]:
        """Count source documents by status for the ``status`` CLI command."""
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT status, COUNT(*) AS count FROM source_documents GROUP BY status"
            ).fetchall()
        return {str(row["status"]): int(row["count"]) for row in rows}


def _header_data_from_document(data: dict[str, Any], *, raw_json: str | None) -> dict[str, Any]:
    document = data.get("documento", {})
    supplier = data.get("fornitore", {})
    recipient = data.get("destinatario", {})
    return {
        "source_filename": data.get("source_filename"),
        "numero_ddt": document.get("numero_ddt"),
        "data_ddt": document.get("data_ddt"),
        "riferimento_ordine": document.get("riferimento_ordine"),
        "causale_trasporto": document.get("causale_trasporto"),
        "numero_colli": document.get("numero_colli"),
        "peso_lordo": document.get("peso_lordo"),
        "peso_netto": document.get("peso_netto"),
        "vettore": document.get("vettore"),
        "destinazione": document.get("destinazione"),
        "fornitore_ragione_sociale": supplier.get("ragione_sociale"),
        "fornitore_partita_iva": supplier.get("partita_iva"),
        "fornitore_indirizzo": supplier.get("indirizzo"),
        "destinatario_ragione_sociale": recipient.get("ragione_sociale"),
        "destinatario_partita_iva": recipient.get("partita_iva"),
        "destinatario_indirizzo": recipient.get("indirizzo"),
        "quality_score": data.get("quality_score", 0),
        "requires_review": bool(data.get("campi_da_verificare")) or data.get("quality_score", 0) < 0.85,
        "raw_json": raw_json or json.dumps(data, default=_json_default, ensure_ascii=False),
    }


def _line_data_from_document(data: dict[str, Any]) -> list[dict[str, Any]]:
    lines: list[dict[str, Any]] = []
    for index, line in enumerate(data.get("articoli", []), start=1):
        lines.append(
            {
                "line_index": line.get("numero_riga") or index,
                "codice": line.get("codice"),
                "descrizione": line.get("descrizione"),
                "quantita": line.get("quantita"),
                "unita_misura": line.get("unita_misura"),
                "lotto": line.get("lotto"),
                "matricola": line.get("matricola"),
            }
        )
    return lines
