"""One-shot production job: inbox scan, extraction, archive and Excel export."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ddt_local.config import AppConfig
from ddt_local.database import Database
from ddt_local.excel import write_production_excel
from ddt_local.extractor import extract_document
from ddt_local.files import (
    JobAlreadyRunningError,
    acquire_job_lock,
    compute_sha256,
    destination_for_status,
    is_file_stable,
    is_supported_file,
    move_file_atomic,
    release_job_lock,
)
from ddt_local.logging_config import get_logger
from ddt_local.models import (
    ExecutionMetadata,
    ExtractionMethod,
    ExtractionResult,
    SourceDocument,
)
from ddt_local.scanner import ScannedFile, scan_inbox


@dataclass
class RunSummary:
    queued: int = 0
    processed: int = 0
    errors: int = 0
    duplicates: int = 0
    locked: bool = False
    persistence_failures: int = 0

    @property
    def exit_code(self) -> int:
        # Expected operational conditions (empty inbox, duplicate, lock or extraction
        # error) do not leave a resident job behind and therefore exit successfully.
        return 1 if self.persistence_failures else 0


def initialize_operational_home(config: AppConfig, database: Database | None = None) -> Database:
    """Create the local directory layout and initialise SQLite."""
    for path in (
        config.ddt_home,
        config.inbox_dir,
        config.processed_dir,
        config.errors_dir,
        config.raw_dir,
        config.logs_dir,
        config.output_dir,
        config.benchmark_dir,
        config.data_dir,
    ):
        path.mkdir(parents=True, exist_ok=True)
    database = database or Database(config.database_path)
    database.initialize()
    return database


def run_once(config: AppConfig, *, check_stability: bool = True) -> RunSummary:
    """Process every currently stable, non-duplicate document in the inbox.

    The job lock makes concurrent invocations harmless. Each document follows the
    durable order required by production: extract -> SQLite transaction -> atomic
    Excel refresh -> archive move.
    """
    logger = get_logger("ddt_local.production")
    database = initialize_operational_home(config)
    summary = RunSummary()

    try:
        lock = acquire_job_lock(config)
    except JobAlreadyRunningError:
        logger.info("production job skipped because another instance holds the lock")
        summary.locked = True
        return summary

    try:
        scanned = scan_inbox(config, database, check_stability=check_stability)
        summary.queued = len(scanned)
        new_paths = {item.path.resolve() for item in scanned}

        for item in scanned:
            _process_scanned_file(config, database, item, summary)

        # A duplicate may be an intentional re-delivery or a prior document whose
        # final archive move was interrupted. Archive it without invoking a model.
        summary.duplicates = _archive_known_duplicates(
            config,
            database,
            new_paths=new_paths,
            check_stability=check_stability,
        )
        return summary
    finally:
        release_job_lock(lock)


def requeue_document(config: AppConfig, file_hash: str) -> Path:
    """Move an archived document back to the inbox and remove its old DB record."""
    database = initialize_operational_home(config)
    record = database.source_document_by_hash(file_hash)
    if record is None:
        raise ValueError(f"No source document found for SHA-256 {file_hash}")

    archived = _find_archived_document(config, record["original_filename"], file_hash)
    if archived is None:
        raise FileNotFoundError(
            "The archived source file was not found in processed/ or errors/. "
            "Restore it to the inbox manually before retrying."
        )

    requeued = move_file_atomic(archived, config.inbox_dir / archived.name)
    try:
        deleted = database.delete_source_document_by_hash(file_hash)
        if not deleted:
            raise ValueError(f"No source document found for SHA-256 {file_hash}")
    except Exception:
        # Retain the existing archive/DB state if the requeue transaction cannot be
        # completed, rather than silently leaving a duplicate in the inbox.
        try:
            move_file_atomic(requeued, archived)
        except OSError:
            pass
        raise
    return requeued


def _process_scanned_file(
    config: AppConfig,
    database: Database,
    scanned: ScannedFile,
    summary: RunSummary,
) -> None:
    logger = get_logger("ddt_local.production")
    source = SourceDocument(
        path=scanned.path,
        filename=scanned.filename,
        sha256=scanned.sha256,
        size_bytes=scanned.size_bytes,
    )
    try:
        result = extract_document(source, config)
    except Exception as exc:  # Keep an unexpected pipeline failure visible and retryable.
        logger.exception("extraction crashed for file=%s", scanned.filename)
        result = ExtractionResult(
            metadata=ExecutionMetadata(
                pipeline=config.pipeline,
                ocr_model=config.ocr_model,
                struct_model=config.struct_model,
                vision_model=config.vision_model,
                extraction_method=ExtractionMethod.OCR,
            ),
            success=False,
            error_message=str(exc),
        )

    persisted = False
    try:
        database.persist_extraction_result(source, result)
        persisted = True
        write_production_excel(database, config.excel_path)
    except Exception:
        # Keep the source in inbox and remove any committed record so a corrected
        # Excel/SQLite environment can retry it without manual database surgery.
        logger.exception("persistence or Excel export failed for file=%s", scanned.filename)
        if persisted:
            database.delete_source_document_by_hash(scanned.sha256)
        summary.persistence_failures += 1
        return

    archive_status = "processed" if result.success else "errors"
    try:
        move_file_atomic(scanned.path, destination_for_status(config, archive_status, scanned.filename))
    except OSError:
        # The persisted hash makes the next invocation archive this inbox copy without
        # extracting it again.
        logger.exception("archive move failed for file=%s", scanned.filename)
        summary.persistence_failures += 1
        return

    if result.success:
        summary.processed += 1
    else:
        summary.errors += 1


def _archive_known_duplicates(
    config: AppConfig,
    database: Database,
    *,
    new_paths: set[Path],
    check_stability: bool,
) -> int:
    archived = 0
    for path in sorted(config.inbox_dir.iterdir()):
        if not path.is_file() or not is_supported_file(path) or path.resolve() in new_paths:
            continue
        if check_stability and not is_file_stable(path, config.file_stability_seconds):
            continue
        file_hash = compute_sha256(path)
        record = database.source_document_by_hash(file_hash)
        if record is None:
            continue
        status = "errors" if record["status"] == "error" else "processed"
        move_file_atomic(path, destination_for_status(config, status, path.name))
        archived += 1
    return archived


def _find_archived_document(config: AppConfig, filename: str, file_hash: str) -> Path | None:
    for root in (config.processed_dir, config.errors_dir):
        if not root.exists():
            continue
        for candidate in root.rglob(filename):
            if candidate.is_file() and compute_sha256(candidate) == file_hash:
                return candidate
    return None
