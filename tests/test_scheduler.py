"""Tests for the native per-user scheduler backends."""

from __future__ import annotations

import plistlib
import subprocess
from pathlib import Path

import pytest

from ddt_local.scheduler import (
    LAUNCHD_LABEL,
    WINDOWS_TASK_NAME,
    SchedulerError,
    install_scheduler,
    remove_scheduler,
)


def _completed(*args, **kwargs) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args[0], 0, stdout="", stderr="")


def test_install_launchd_uses_headless_command_and_five_minute_interval(tmp_path: Path):
    calls: list[list[str]] = []

    def fake_run(command, **kwargs):
        calls.append(command)
        return _completed(command)

    plist_path = install_scheduler(
        command=["/Applications/DDT Local Extractor.app/Contents/Resources/ddt-local-runner", "--run-once"],
        ddt_home=tmp_path / "DDT",
        platform="darwin",
        home=tmp_path / "home",
        user_id=501,
        run_command=fake_run,
    )

    assert plist_path is not None and plist_path.exists()
    payload = plistlib.loads(plist_path.read_bytes())
    assert payload["Label"] == LAUNCHD_LABEL
    assert payload["ProgramArguments"][-1] == "--run-once"
    assert payload["StartInterval"] == 300
    assert calls[1][:3] == ["launchctl", "bootstrap", "gui/501"]


def test_install_windows_task_uses_hidden_headless_runner():
    calls: list[list[str]] = []

    def fake_run(command, **kwargs):
        calls.append(command)
        return _completed(command)

    install_scheduler(
        command=[r"C:\Program Files\DDT Local Extractor\ddt-local-runner.exe", "--run-once"],
        ddt_home=Path(r"C:\Users\example\DDT"),
        platform="win32",
        run_command=fake_run,
    )

    assert calls[0][0] == "schtasks"
    assert calls[0][calls[0].index("/TN") + 1] == WINDOWS_TASK_NAME
    assert calls[0][calls[0].index("/MO") + 1] == "5"
    assert "ddt-local-runner.exe" in calls[0][calls[0].index("/TR") + 1]


def test_remove_launchd_deletes_only_its_own_agent(tmp_path: Path):
    plist = tmp_path / "home" / "Library" / "LaunchAgents" / f"{LAUNCHD_LABEL}.plist"
    plist.parent.mkdir(parents=True)
    plist.write_text("test")
    calls: list[list[str]] = []

    remove_scheduler(
        platform="darwin",
        home=tmp_path / "home",
        user_id=501,
        run_command=lambda command, **kwargs: calls.append(command) or _completed(command),
    )

    assert not plist.exists()
    assert calls[0][:3] == ["launchctl", "bootout", "gui/501"]


def test_scheduler_rejects_non_minute_interval(tmp_path: Path):
    with pytest.raises(SchedulerError, match="multiple"):
        install_scheduler(
            command=["runner"],
            ddt_home=tmp_path,
            interval_seconds=61,
            platform="darwin",
        )
