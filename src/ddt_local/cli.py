"""CLI entry point for DDT Local Extractor."""

from __future__ import annotations

import argparse
import sys


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


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 0

    print(f"Command '{args.command}' not yet implemented.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
