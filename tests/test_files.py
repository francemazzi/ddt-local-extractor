"""Tests for file utilities."""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from ddt_local.config import AppConfig
from ddt_local.files import (
    JobAlreadyRunningError,
    acquire_job_lock,
    compute_sha256,
    destination_for_status,
    is_file_stable,
    is_supported_file,
    move_file_atomic,
    release_job_lock,
    resolve_safe_path,
    sanitize_filename,
)


def test_compute_sha256_deterministic(tmp_path):
    f = tmp_path / "doc.pdf"
    f.write_bytes(b"hello ddt")
    h1 = compute_sha256(f)
    h2 = compute_sha256(f)
    assert h1 == h2
    assert len(h1) == 64


def test_is_supported_file_filters_hidden_and_extensions(tmp_path):
    assert is_supported_file(tmp_path / "doc.pdf")
    assert is_supported_file(tmp_path / "img.PNG")
    assert not is_supported_file(tmp_path / ".hidden.pdf")
    assert not is_supported_file(tmp_path / "file.txt")


def test_is_file_stable_detects_growth(tmp_path, monkeypatch):
    f = tmp_path / "growing.pdf"
    f.write_bytes(b"x")

    original_sleep = time.sleep
    sizes = iter([1, 2])

    def fake_sleep(seconds):
        f.write_bytes(b"x" * next(sizes, 2))
        original_sleep(0)

    monkeypatch.setattr(time, "sleep", fake_sleep)
    monkeypatch.setenv("DDT_FILE_STABILITY_SECONDS", "0")
    assert not is_file_stable(f, stability_seconds=0)


def test_sanitize_filename():
    assert sanitize_filename("../evil.pdf") == "__evil.pdf"
    assert sanitize_filename("  ok.pdf  ") == "ok.pdf"


def test_resolve_safe_path_blocks_traversal(tmp_path):
    base = tmp_path / "DDT"
    base.mkdir()
    safe = resolve_safe_path(base, "inbox/doc.pdf")
    assert safe == (base / "inbox/doc.pdf").resolve()
    with pytest.raises(ValueError, match="Path traversal"):
        resolve_safe_path(base, "/etc/passwd")


def test_move_file_atomic_no_overwrite(tmp_path):
    src = tmp_path / "src.pdf"
    dst_dir = tmp_path / "out"
    dst_dir.mkdir()
    existing = dst_dir / "src.pdf"
    src.write_bytes(b"new")
    existing.write_bytes(b"old")
    final = move_file_atomic(src, existing)
    assert final.name == "src_1.pdf"
    assert final.read_bytes() == b"new"
    assert existing.read_bytes() == b"old"


def test_destination_for_status_uses_year_month(app_config: AppConfig):
    dest = destination_for_status(app_config, "processed", "doc.pdf")
    assert "processed" in str(dest)
    assert dest.name == "doc.pdf"


def test_job_lock_prevents_concurrent_acquire(app_config: AppConfig):
    app_config.ddt_home.mkdir(parents=True, exist_ok=True)
    lock1 = acquire_job_lock(app_config)
    try:
        with pytest.raises(JobAlreadyRunningError):
            acquire_job_lock(app_config, timeout=0)
    finally:
        release_job_lock(lock1)


def test_job_lock_release_allows_reacquire(app_config: AppConfig):
    app_config.ddt_home.mkdir(parents=True, exist_ok=True)
    lock1 = acquire_job_lock(app_config)
    release_job_lock(lock1)
    lock2 = acquire_job_lock(app_config)
    release_job_lock(lock2)
