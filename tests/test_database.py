"""Tests for SQLite database layer."""

from __future__ import annotations

import sqlite3

import pytest

from ddt_local.database import Database


@pytest.fixture
def db(tmp_path) -> Database:
    database = Database(tmp_path / "test.sqlite3")
    database.initialize()
    return database


def test_initialize_creates_all_tables(db: Database):
    with db.connect() as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    expected = {
        "source_documents",
        "ocr_pages",
        "ddt_headers",
        "ddt_lines",
        "validation_issues",
        "benchmark_runs",
        "benchmark_results",
    }
    assert expected.issubset(tables)


def test_sha256_unique_constraint(db: Database):
    with db.transaction() as conn:
        db.insert_source_document(
            conn,
            sha256="hash1",
            original_filename="a.pdf",
            size_bytes=100,
        )
    with pytest.raises(sqlite3.IntegrityError):
        with db.transaction() as conn:
            db.insert_source_document(
                conn,
                sha256="hash1",
                original_filename="b.pdf",
                size_bytes=200,
            )


def test_transaction_rollback_on_error(db: Database):
    with pytest.raises(RuntimeError):
        with db.transaction() as conn:
            db.insert_source_document(
                conn,
                sha256="hash2",
                original_filename="a.pdf",
                size_bytes=100,
            )
            raise RuntimeError("simulated failure")

    assert not db.document_exists_by_hash("hash2")


def test_insert_header_and_lines(db: Database):
    with db.transaction() as conn:
        doc_id = db.insert_source_document(
            conn,
            sha256="hash3",
            original_filename="01_DDT.pdf",
            size_bytes=500,
            pipeline="ocr_struct",
        )
        db.insert_ddt_header(
            conn,
            source_document_id=doc_id,
            header_data={
                "source_filename": "01_DDT.pdf",
                "numero_ddt": "NE/2026/0714-018",
                "data_ddt": "2026-07-14",
                "quality_score": 0.9,
                "requires_review": False,
            },
        )
        db.insert_ddt_lines(
            conn,
            source_document_id=doc_id,
            lines=[
                {
                    "line_index": 1,
                    "codice": "S355",
                    "descrizione": "Lamiera",
                    "quantita": "24",
                    "unita_misura": "FOGLI",
                    "lotto": "COL-1",
                    "matricola": None,
                }
            ],
        )

    assert db.count_production_documents() == 1
    with db.connect() as conn:
        lines = conn.execute(
            "SELECT codice FROM ddt_lines WHERE source_document_id = ?",
            (doc_id,),
        ).fetchall()
        assert lines[0]["codice"] == "S355"


def test_benchmark_tables_isolated_from_production(db: Database):
    with db.transaction() as conn:
        run_id = db.insert_benchmark_run(
            conn,
            run_name="ocr_qwen4b",
            pipeline="ocr_struct",
            ocr_model="glm-ocr:latest",
            struct_model="qwen3.5:4b",
        )
        db.insert_benchmark_result(
            conn,
            benchmark_run_id=run_id,
            document_filename="01_DDT.pdf",
            repetition=1,
            metrics={
                "lines_found": 3,
                "lines_missing": 0,
                "weighted_score": 0.95,
                "validation_passed": True,
            },
        )

    assert db.count_production_documents() == 0
    assert db.count_benchmark_results() == 1


def test_foreign_key_cascade_delete(db: Database):
    with db.transaction() as conn:
        doc_id = db.insert_source_document(
            conn,
            sha256="hash4",
            original_filename="del.pdf",
            size_bytes=10,
        )
        db.insert_ddt_header(
            conn,
            source_document_id=doc_id,
            header_data={"source_filename": "del.pdf"},
        )

    with db.transaction() as conn:
        conn.execute("DELETE FROM source_documents WHERE id = ?", (doc_id,))

    with db.connect() as conn:
        count = conn.execute("SELECT COUNT(*) AS c FROM ddt_headers").fetchone()["c"]
        assert count == 0
