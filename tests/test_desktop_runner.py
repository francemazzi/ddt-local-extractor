"""Tests for the invisible scheduled runner."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from ddt_local.desktop_runner import main
from ddt_local.production import RunSummary
from ddt_local.user_config import UserSettings, save_user_settings


def test_runner_exits_quietly_when_desktop_setup_is_missing(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("DDT_USER_CONFIG", str(tmp_path / "missing.json"))
    assert main(["--run-once"]) == 0


def test_runner_uses_persisted_path_and_writes_log(monkeypatch, tmp_path: Path):
    config_path = tmp_path / "config.json"
    ddt_home = tmp_path / "DDT"
    save_user_settings(UserSettings(ddt_home=ddt_home, setup_completed=True), config_path)
    monkeypatch.setenv("DDT_USER_CONFIG", str(config_path))
    monkeypatch.delenv("DDT_HOME", raising=False)

    with patch("ddt_local.desktop_runner.run_once", return_value=RunSummary(processed=1)) as run:
        assert main(["--run-once"]) == 0

    assert run.call_args.args[0].ddt_home == ddt_home.resolve()
    assert (ddt_home / "logs" / "desktop-runner.log").exists()
    assert (ddt_home / "output" / "DDT_estratti.xlsx").exists()


def test_runner_can_stop_the_automatic_scheduler():
    with patch("ddt_local.desktop_runner.DesktopSetupController.stop_scheduler") as stop_scheduler:
        assert main(["--stop-scheduler"]) == 0

    stop_scheduler.assert_called_once_with()
