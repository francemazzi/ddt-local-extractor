"""CLI entry point for DDT Local Extractor."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ddt_local.config import load_config
from ddt_local.database import Database
from ddt_local.logging_config import configure_logging, get_logger, new_run_id


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
    Database(config.database_path).initialize()
    print(f"Initialized DDT home at {config.ddt_home}")
    return 0


def cmd_doctor() -> int:
    from ddt_local.ollama import OllamaClient

    config = load_config()
    ok = True
    print(f"Python: {sys.version.split()[0]}")
    print(f"DDT_HOME: {config.ddt_home}")
    for name, path in [
        ("inbox", config.inbox_dir),
        ("data", config.data_dir),
        ("output", config.output_dir),
        ("benchmark", config.benchmark_dir),
    ]:
        exists = path.exists()
        print(f"  {name}: {'OK' if exists else 'MISSING'} ({path})")
        if not exists:
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

    return 0 if ok else 1


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

    print(f"Command '{args.command}' not yet implemented.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
