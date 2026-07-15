"""Inbox scanner for new documents."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ddt_local.config import AppConfig
from ddt_local.database import Database
from ddt_local.files import compute_sha256, is_file_stable, is_supported_file


@dataclass
class ScannedFile:
    path: Path
    filename: str
    sha256: str
    size_bytes: int


def scan_inbox(
    config: AppConfig,
    database: Database,
    *,
    check_stability: bool = True,
) -> list[ScannedFile]:
    """Return inbox files not yet present in the database by SHA-256."""
    inbox = config.inbox_dir
    inbox.mkdir(parents=True, exist_ok=True)

    results: list[ScannedFile] = []
    for path in sorted(inbox.iterdir()):
        if not path.is_file() or not is_supported_file(path):
            continue
        if check_stability and not is_file_stable(path, config.file_stability_seconds):
            continue
        sha256 = compute_sha256(path)
        if database.document_exists_by_hash(sha256):
            continue
        results.append(
            ScannedFile(
                path=path,
                filename=path.name,
                sha256=sha256,
                size_bytes=path.stat().st_size,
            )
        )
    return results
