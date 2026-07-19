"""Invisible one-shot runner invoked by launchd or Windows Task Scheduler."""

from __future__ import annotations

import argparse

from ddt_local.config import load_config
from ddt_local.excel import write_production_excel
from ddt_local.logging_config import configure_logging, get_logger, new_run_id
from ddt_local.production import initialize_operational_home, run_once
from ddt_local.user_config import load_user_settings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ddt-local-runner")
    parser.add_argument("--run-once", action="store_true", help="Process the inbox once and exit")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.run_once:
        return 2

    settings = load_user_settings()
    # A scheduler can survive a manually deleted configuration file. Do not open a
    # dialog or create a default folder from an invisible process in that case.
    if settings is None or not settings.setup_completed:
        return 0

    config = load_config()
    configure_logging(
        config.log_level,
        log_path=config.logs_dir / "desktop-runner.log",
        console=False,
    )
    new_run_id()
    logger = get_logger("ddt_local.desktop_runner")
    try:
        database = initialize_operational_home(config)
        if not config.excel_path.exists():
            write_production_excel(database, config.excel_path)
        summary = run_once(config)
    except Exception:
        logger.exception("desktop runner failed")
        return 1
    logger.info(
        "desktop run complete queued=%s processed=%s errors=%s duplicates=%s locked=%s",
        summary.queued,
        summary.processed,
        summary.errors,
        summary.duplicates,
        summary.locked,
    )
    return summary.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
