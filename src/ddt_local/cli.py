"""CLI entry point for DDT Local Extractor."""

from __future__ import annotations

import argparse
import importlib
import os
import sys
from tempfile import NamedTemporaryFile
from pathlib import Path

from ddt_local.config import load_config
from ddt_local.database import Database
from ddt_local.logging_config import configure_logging, get_logger, new_run_id
from ddt_local.production import initialize_operational_home, requeue_document, run_once
from ddt_local.scheduler import DEFAULT_INTERVAL_SECONDS, SchedulerError, install_scheduler, remove_scheduler


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ddt-local",
        description="Local DDT extraction pipeline with Ollama benchmark",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    subparsers.add_parser("init", help="Create directories and initialize database")
    subparsers.add_parser("doctor", help="Verify dependencies and configuration")
    run_parser = subparsers.add_parser("run", help="Process documents from inbox")
    run_parser.add_argument("--once", action="store_true", help="Process queue and exit")
    subparsers.add_parser("export", help="Regenerate Excel from SQLite")
    subparsers.add_parser("status", help="Show processing status")
    reprocess_parser = subparsers.add_parser("reprocess", help="Reprocess a document by hash")
    reprocess_parser.add_argument("file_hash", help="SHA-256 hash of the document")
    scheduler_parser = subparsers.add_parser(
        "scheduler", help="Install or remove the advanced per-user automatic job"
    )
    scheduler_actions = scheduler_parser.add_subparsers(dest="scheduler_action", required=True)
    scheduler_install = scheduler_actions.add_parser("install", help="Install the automatic job")
    scheduler_install.add_argument(
        "--interval-minutes",
        type=int,
        default=DEFAULT_INTERVAL_SECONDS // 60,
        help="Inbox polling interval (default: 5)",
    )
    scheduler_actions.add_parser("remove", help="Remove the automatic job")
    benchmark_parser = subparsers.add_parser("benchmark", help="Run pipeline benchmark")
    benchmark_parser.add_argument("--documents", required=True, help="Path to document folder")
    benchmark_parser.add_argument("--ground-truth", required=True, help="Path to ground truth folder")
    benchmark_parser.add_argument("--config", required=True, help="Path to benchmark YAML config")
    benchmark_parser.add_argument("--runs-filter", help="Run only matching configuration name")
    benchmark_parser.add_argument("--repetitions", type=int, help="Override repetitions from config")
    benchmark_parser.add_argument(
        "--keep-artifacts", action="store_true", help="Keep intermediate images and raw responses"
    )

    return parser


def cmd_init() -> int:
    config = load_config()
    initialize_operational_home(config)
    print(f"Initialized DDT home at {config.ddt_home}")
    return 0


def cmd_doctor() -> int:
    from ddt_local.ollama import OllamaClient

    config = load_config()
    ok = True
    python_ok = sys.version_info >= (3, 12)
    print(f"Python: {'OK' if python_ok else 'UNSUPPORTED'} ({sys.version.split()[0]})")
    ok = ok and python_ok
    print(f"DDT_HOME: {config.ddt_home}")
    for name, path in [
        ("inbox", config.inbox_dir),
        ("data", config.data_dir),
        ("output", config.output_dir),
        ("benchmark", config.benchmark_dir),
    ]:
        exists = path.exists()
        writable = exists and os.access(path, os.W_OK | os.X_OK)
        state = "OK" if writable else ("NOT WRITABLE" if exists else "MISSING")
        print(f"  {name}: {state} ({path})")
        if not writable:
            ok = False

    for module in ("fitz", "openpyxl", "pydantic", "httpx", "filelock"):
        try:
            importlib.import_module(module)
            print(f"Dependency {module}: OK")
        except ImportError:
            print(f"Dependency {module}: MISSING")
            ok = False

    client = OllamaClient(config)
    if client.health_check():
        models = client.list_models()
        print(f"Ollama: OK ({len(models)} models)")
        for required in (config.ocr_model, config.struct_model, config.vision_model):
            present = required in models or any(required in m for m in models)
            print(f"  model {required}: {'OK' if present else 'MISSING'}")
            if not present:
                ok = False
    else:
        print("Ollama: UNAVAILABLE")
        ok = False

    try:
        Database(config.database_path).initialize()
        print(f"SQLite: OK ({config.database_path})")
    except Exception as exc:
        print(f"SQLite: FAIL ({exc})")
        ok = False

    if config.output_dir.exists() and os.access(config.output_dir, os.W_OK | os.X_OK):
        try:
            with NamedTemporaryFile(dir=config.output_dir, prefix=".doctor_excel_", delete=True):
                pass
            print("Excel: OK")
        except OSError as exc:
            print(f"Excel: FAIL ({exc})")
            ok = False
    else:
        print("Excel: FAIL (output directory unavailable)")
        ok = False

    return 0 if ok else 1


def cmd_run(args: argparse.Namespace) -> int:
    if not args.once:
        print("Only one-shot mode is supported; pass --once.", file=sys.stderr)
        return 2
    config = load_config()
    configure_logging(config.log_level)
    new_run_id()
    summary = run_once(config)
    if summary.locked:
        print("Another job is already running; nothing processed.")
    else:
        print(
            "Run complete: "
            f"queued={summary.queued} processed={summary.processed} "
            f"errors={summary.errors} duplicates={summary.duplicates}"
        )
    return summary.exit_code


def cmd_export() -> int:
    from ddt_local.excel import write_production_excel

    config = load_config()
    database = initialize_operational_home(config)
    output = write_production_excel(database, config.excel_path)
    print(f"Excel exported to {output}")
    return 0


def cmd_status() -> int:
    from ddt_local.files import is_supported_file

    config = load_config()
    database = initialize_operational_home(config)
    queued = sum(
        1 for path in config.inbox_dir.iterdir() if path.is_file() and is_supported_file(path)
    )
    counts = database.production_status_counts()
    print(f"Inbox queued: {queued}")
    print(f"Processed: {counts.get('processed', 0)}")
    print(f"Errors: {counts.get('error', 0)}")
    print(f"Excel: {config.excel_path} ({'OK' if config.excel_path.exists() else 'MISSING'})")
    return 0


def cmd_reprocess(args: argparse.Namespace) -> int:
    config = load_config()
    try:
        queued_path = requeue_document(config, args.file_hash)
    except (ValueError, FileNotFoundError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"Requeued {queued_path.name}")
    return cmd_run(argparse.Namespace(once=True))


def cmd_scheduler(args: argparse.Namespace) -> int:
    from ddt_local.scheduler import default_runner_command

    config = load_config()
    if args.scheduler_action == "remove":
        try:
            remove_scheduler()
        except SchedulerError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        print("Automatic job removed.")
        return 0

    interval_seconds = args.interval_minutes * 60
    try:
        initialize_operational_home(config)
        location = install_scheduler(
            command=default_runner_command(),
            ddt_home=config.ddt_home,
            interval_seconds=interval_seconds,
        )
    except (SchedulerError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"Automatic job installed every {args.interval_minutes} minutes.")
    if location is not None:
        print(f"Schedule: {location}")
    return 0


def cmd_benchmark(args: argparse.Namespace) -> int:
    from ddt_local.benchmark.report import format_ranking_text, write_reports
    from ddt_local.benchmark.runner import run_benchmark

    config = load_config()
    configure_logging(config.log_level)
    new_run_id()
    logger = get_logger("ddt_local.cli")

    config.benchmark_dir.mkdir(parents=True, exist_ok=True)
    Database(config.database_path).initialize()

    summary = run_benchmark(
        documents_dir=Path(args.documents),
        ground_truth_dir=Path(args.ground_truth),
        config_path=Path(args.config),
        app_config=config,
        runs_filter=args.runs_filter,
        repetitions=args.repetitions,
        keep_artifacts=args.keep_artifacts,
    )
    csv_path, xlsx_path = write_reports(summary, config.benchmark_dir)
    ranking = format_ranking_text(summary)
    print(ranking)
    print(f"CSV: {csv_path}")
    print(f"Excel: {xlsx_path}")
    logger.info("benchmark completed results=%s", len(summary.results))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 0

    if args.command == "init":
        return cmd_init()
    if args.command == "doctor":
        return cmd_doctor()
    if args.command == "benchmark":
        return cmd_benchmark(args)
    if args.command == "run":
        return cmd_run(args)
    if args.command == "export":
        return cmd_export()
    if args.command == "status":
        return cmd_status()
    if args.command == "reprocess":
        return cmd_reprocess(args)
    if args.command == "scheduler":
        return cmd_scheduler(args)

    print(f"Command '{args.command}' not yet implemented.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
