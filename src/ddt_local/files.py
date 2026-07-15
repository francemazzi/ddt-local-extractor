"""File management: hashing, stability, locking, safe moves."""

from __future__ import annotations

import hashlib
import os
import time
from datetime import datetime
from pathlib import Path

from filelock import FileLock, Timeout

from ddt_local.config import AppConfig

SUPPORTED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".webp"}


class JobAlreadyRunningError(Exception):
    """Raised when another job holds the lock."""


def compute_sha256(path: Path, chunk_size: int = 65536) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def is_supported_file(path: Path) -> bool:
    name = path.name
    if name.startswith("."):
        return False
    return path.suffix.lower() in SUPPORTED_EXTENSIONS


def is_file_stable(path: Path, stability_seconds: int) -> bool:
    if not path.exists() or not path.is_file():
        return False
    size = path.stat().st_size
    mtime = path.stat().st_mtime
    time.sleep(stability_seconds)
    if not path.exists():
        return False
    stat = path.stat()
    return stat.st_size == size and stat.st_mtime == mtime


def sanitize_filename(filename: str) -> str:
    cleaned = filename.replace("\x00", "").strip()
    cleaned = cleaned.replace("/", "_").replace("\\", "_")
    cleaned = cleaned.replace("..", "_")
    return cleaned or "unnamed"


def resolve_safe_path(base: Path, user_path: str | Path) -> Path:
    base = base.resolve()
    target = Path(user_path)
    if not target.is_absolute():
        target = (base / target).resolve()
    else:
        target = target.resolve()
    if base not in target.parents and target != base:
        raise ValueError(f"Path traversal blocked: {user_path}")
    return target


def acquire_job_lock(config: AppConfig, timeout: float = 0) -> FileLock:
    config.ddt_home.mkdir(parents=True, exist_ok=True)
    lock = FileLock(str(config.lock_path), timeout=timeout)
    try:
        lock.acquire(timeout=timeout)
    except Timeout as exc:
        raise JobAlreadyRunningError("Another DDT job is already running") from exc
    return lock


def release_job_lock(lock: FileLock) -> None:
    if lock.is_locked:
        lock.release()


def _unique_destination(directory: Path, filename: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    safe_name = sanitize_filename(filename)
    candidate = directory / safe_name
    if not candidate.exists():
        return candidate
    stem = candidate.stem
    suffix = candidate.suffix
    counter = 1
    while True:
        alt = directory / f"{stem}_{counter}{suffix}"
        if not alt.exists():
            return alt
        counter += 1


def destination_for_status(
    config: AppConfig,
    status: str,
    filename: str,
    when: datetime | None = None,
) -> Path:
    when = when or datetime.now()
    subdir = when.strftime("%Y/%m")
    if status == "processed":
        base = config.processed_dir / subdir
    elif status == "errors":
        base = config.errors_dir / subdir
    else:
        raise ValueError(f"Unknown status: {status}")
    return _unique_destination(base, filename)


def move_file_atomic(source: Path, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        destination = _unique_destination(destination.parent, destination.name)
    os.replace(source, destination)
    return destination
