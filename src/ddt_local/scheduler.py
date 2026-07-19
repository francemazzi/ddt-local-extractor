"""Per-user operating-system schedulers for the desktop runner."""

from __future__ import annotations

import os
import plistlib
import subprocess
import sys
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Callable, Sequence

LAUNCHD_LABEL = "com.ddt-local-extractor.run"
WINDOWS_TASK_NAME = "DDT Local Extractor"
DEFAULT_INTERVAL_SECONDS = 300

RunCommand = Callable[..., subprocess.CompletedProcess]


class SchedulerError(RuntimeError):
    """Raised when a per-user scheduler cannot be installed or removed."""


def default_runner_command() -> list[str]:
    """Return the development runner command used outside a packaged desktop app."""
    return [sys.executable, "-m", "ddt_local.desktop_runner", "--run-once"]


def install_scheduler(
    *,
    command: Sequence[str],
    ddt_home: Path,
    interval_seconds: int = DEFAULT_INTERVAL_SECONDS,
    platform: str | None = None,
    home: Path | None = None,
    user_id: int | None = None,
    run_command: RunCommand = subprocess.run,
) -> Path | None:
    """Install the invisible one-shot runner for the current user."""
    if not command:
        raise SchedulerError("Runner command cannot be empty")
    if interval_seconds < 60 or interval_seconds % 60:
        raise SchedulerError("Scheduler interval must be a multiple of 60 seconds")

    target_platform = platform or sys.platform
    if target_platform == "darwin":
        return _install_launchd(
            command=list(command),
            ddt_home=ddt_home,
            interval_seconds=interval_seconds,
            home=home or Path.home(),
            user_id=os.getuid() if user_id is None else user_id,
            run_command=run_command,
        )
    if target_platform.startswith("win"):
        _install_windows_task(
            command=list(command),
            interval_seconds=interval_seconds,
            run_command=run_command,
        )
        return None
    raise SchedulerError(f"Automatic scheduling is not supported on {target_platform}")


def remove_scheduler(
    *,
    platform: str | None = None,
    home: Path | None = None,
    user_id: int | None = None,
    run_command: RunCommand = subprocess.run,
) -> None:
    """Remove the current user's schedule without affecting other users."""
    target_platform = platform or sys.platform
    if target_platform == "darwin":
        resolved_home = home or Path.home()
        plist_path = resolved_home / "Library" / "LaunchAgents" / f"{LAUNCHD_LABEL}.plist"
        resolved_user_id = os.getuid() if user_id is None else user_id
        run_command(
            ["launchctl", "bootout", f"gui/{resolved_user_id}", str(plist_path)],
            check=False,
            capture_output=True,
            text=True,
        )
        plist_path.unlink(missing_ok=True)
        return
    if target_platform.startswith("win"):
        run_command(
            ["schtasks", "/Delete", "/TN", WINDOWS_TASK_NAME, "/F"],
            check=False,
            capture_output=True,
            text=True,
        )
        return
    raise SchedulerError(f"Automatic scheduling is not supported on {target_platform}")


def _install_launchd(
    *,
    command: list[str],
    ddt_home: Path,
    interval_seconds: int,
    home: Path,
    user_id: int,
    run_command: RunCommand,
) -> Path:
    plist_path = home / "Library" / "LaunchAgents" / f"{LAUNCHD_LABEL}.plist"
    plist_path.parent.mkdir(parents=True, exist_ok=True)
    logs_dir = ddt_home / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "Label": LAUNCHD_LABEL,
        "ProgramArguments": command,
        "WorkingDirectory": str(ddt_home),
        "RunAtLoad": True,
        "StartInterval": interval_seconds,
        "StandardOutPath": str(logs_dir / "scheduler.out.log"),
        "StandardErrorPath": str(logs_dir / "scheduler.err.log"),
    }
    _write_plist_atomic(payload, plist_path)
    target = f"gui/{user_id}"
    run_command(
        ["launchctl", "bootout", target, str(plist_path)],
        check=False,
        capture_output=True,
        text=True,
    )
    try:
        run_command(
            ["launchctl", "bootstrap", target, str(plist_path)],
            check=True,
            capture_output=True,
            text=True,
        )
        run_command(
            ["launchctl", "enable", f"{target}/{LAUNCHD_LABEL}"],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        raise SchedulerError(f"Cannot install launchd schedule: {exc.stderr or exc}") from exc
    return plist_path


def _install_windows_task(
    *,
    command: list[str],
    interval_seconds: int,
    run_command: RunCommand,
) -> None:
    command_line = subprocess.list2cmdline(command)
    try:
        run_command(
            [
                "schtasks",
                "/Create",
                "/TN",
                WINDOWS_TASK_NAME,
                "/SC",
                "MINUTE",
                "/MO",
                str(interval_seconds // 60),
                "/TR",
                command_line,
                "/RL",
                "LIMITED",
                "/F",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        raise SchedulerError(f"Cannot install Windows schedule: {exc.stderr or exc}") from exc


def _write_plist_atomic(payload: dict, path: Path) -> None:
    temporary_path: Path | None = None
    try:
        with NamedTemporaryFile(dir=path.parent, prefix=f".{path.stem}.", delete=False) as temporary:
            temporary_path = Path(temporary.name)
            plistlib.dump(payload, temporary, sort_keys=False)
        os.replace(temporary_path, path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
