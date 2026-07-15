"""Tests for inbox scanner."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from ddt_local.database import Database
from ddt_local.scanner import scan_inbox


@pytest.fixture
def db(tmp_path) -> Database:
    database = Database(tmp_path / "ddt.sqlite3")
    database.initialize()
    return database


def test_scan_inbox_finds_new_files(app_config, db: Database, tmp_path):
    inbox = app_config.inbox_dir
    inbox.mkdir(parents=True)
    pdf = inbox / "01_DDT.pdf"
    pdf.write_bytes(b"%PDF-test-content")

    with patch("ddt_local.scanner.is_file_stable", return_value=True):
        found = scan_inbox(app_config, db, check_stability=True)

    assert len(found) == 1
    assert found[0].filename == "01_DDT.pdf"
    assert len(found[0].sha256) == 64


def test_scan_inbox_skips_duplicates(app_config, db: Database):
    inbox = app_config.inbox_dir
    inbox.mkdir(parents=True)
    pdf = inbox / "dup.pdf"
    content = b"same-content"
    pdf.write_bytes(content)

    from ddt_local.files import compute_sha256

    with db.transaction() as conn:
        db.insert_source_document(
            conn,
            sha256=compute_sha256(pdf),
            original_filename="dup.pdf",
            size_bytes=len(content),
        )

    with patch("ddt_local.scanner.is_file_stable", return_value=True):
        found = scan_inbox(app_config, db)

    assert found == []


def test_scan_inbox_ignores_unsupported(app_config, db: Database):
    inbox = app_config.inbox_dir
    inbox.mkdir(parents=True)
    (inbox / "notes.txt").write_text("skip")
    (inbox / ".hidden.pdf").write_bytes(b"x")

    with patch("ddt_local.scanner.is_file_stable", return_value=True):
        found = scan_inbox(app_config, db)

    assert found == []
