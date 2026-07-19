"""Tests for GUI-independent onboarding behaviour."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import pytest

from ddt_local.desktop_services import DesktopSetupController, DesktopSetupError, PRODUCTION_MODELS
from ddt_local.models import ExtractionMethod
from ddt_local.ollama import PullProgress
from ddt_local.production import RunSummary
from ddt_local.user_config import UserSettings, read_user_settings, save_user_settings


class FakeOllama:
    def __init__(self, config, *, available: bool = True, models: list[str] | None = None) -> None:
        self.config = config
        self.available = available
        self.models = list(models or [])
        self.pulled: list[str] = []

    def health_check(self) -> bool:
        return self.available

    def list_models(self) -> list[str]:
        return self.models

    def pull_model(self, model: str, *, progress=None) -> None:
        self.pulled.append(model)
        self.models.append(model)
        if progress:
            progress(PullProgress(status="success", completed=1, total=1))


def test_prepare_folder_creates_full_layout_and_initial_excel(app_config, tmp_path: Path):
    controller = DesktopSetupController(
        settings_path=tmp_path / "config.json",
        config_loader=lambda: app_config,
        ollama_factory=lambda config: FakeOllama(config, models=list(PRODUCTION_MODELS)),
    )

    config = controller.selected_config(tmp_path / "Chosen DDT")

    assert config.excel_path.exists()
    for path in (config.inbox_dir, config.processed_dir, config.errors_dir, config.logs_dir, config.data_dir):
        assert path.is_dir()


def test_complete_setup_persists_selection_and_installs_scheduler(app_config, tmp_path: Path):
    schedule_calls: list[dict] = []
    controller = DesktopSetupController(
        settings_path=tmp_path / "config.json",
        config_loader=lambda: app_config,
        scheduler_installer=lambda **kwargs: schedule_calls.append(kwargs) or None,
        runner_command=["runner", "--run-once"],
        ollama_factory=lambda config: FakeOllama(config, models=list(PRODUCTION_MODELS)),
    )

    settings = controller.complete_setup(tmp_path / "Selected")

    assert settings.setup_completed is True
    assert read_user_settings(tmp_path / "config.json") == settings
    assert schedule_calls[0]["command"] == ["runner", "--run-once"]
    assert schedule_calls[0]["interval_seconds"] == 300


def test_stop_scheduler_removes_task_and_persists_disabled_choice(app_config, tmp_path: Path):
    settings_path = tmp_path / "config.json"
    save_user_settings(
        UserSettings(ddt_home=tmp_path / "Selected", scheduler_enabled=True, setup_completed=True),
        settings_path,
    )
    removals: list[bool] = []
    controller = DesktopSetupController(
        settings_path=settings_path,
        config_loader=lambda: app_config,
        scheduler_remover=lambda: removals.append(True),
    )

    settings = controller.stop_scheduler()

    assert removals == [True]
    assert settings is not None
    assert settings.scheduler_enabled is False
    assert read_user_settings(settings_path) == settings


def test_missing_models_downloads_with_progress(app_config, tmp_path: Path):
    fake = FakeOllama(app_config, models=[])
    controller = DesktopSetupController(
        settings_path=tmp_path / "config.json",
        config_loader=lambda: app_config,
        ollama_factory=lambda config: fake,
    )
    config = controller.selected_config(tmp_path / "Selected")
    seen: list[tuple[str, str]] = []

    readiness = controller.download_missing_models(
        config,
        progress=lambda model, event: seen.append((model, event.status)),
    )

    assert readiness.ready is True
    assert fake.pulled == list(PRODUCTION_MODELS)
    assert seen == [("glm-ocr:latest", "success"), ("qwen3.5:4b", "success")]


def test_missing_ollama_cannot_complete_setup(app_config, tmp_path: Path):
    controller = DesktopSetupController(
        settings_path=tmp_path / "config.json",
        config_loader=lambda: app_config,
        ollama_factory=lambda config: FakeOllama(config, available=False),
    )

    with pytest.raises(DesktopSetupError, match="Ollama"):
        controller.complete_setup(tmp_path / "Selected")


def test_selected_file_is_not_accepted_as_data_folder(app_config, tmp_path: Path):
    selected_file = tmp_path / "not-a-folder"
    selected_file.write_text("x")
    controller = DesktopSetupController(
        settings_path=tmp_path / "config.json",
        config_loader=lambda: app_config,
    )

    with pytest.raises(DesktopSetupError):
        controller.selected_config(selected_file)


def test_unwritable_selected_folder_is_rejected(app_config, tmp_path: Path):
    controller = DesktopSetupController(
        settings_path=tmp_path / "config.json",
        config_loader=lambda: app_config,
    )
    with patch("ddt_local.desktop_services.NamedTemporaryFile", side_effect=OSError("permission denied")):
        with pytest.raises(DesktopSetupError, match="non è scrivibile"):
            controller.selected_config(tmp_path / "Selected")


def test_runner_action_uses_persisted_desktop_folder(monkeypatch, app_config, tmp_path: Path):
    selected = tmp_path / "Selected"
    save_user_settings(UserSettings(ddt_home=selected, setup_completed=True), tmp_path / "config.json")
    monkeypatch.delenv("DDT_HOME")
    controller = DesktopSetupController(
        settings_path=tmp_path / "config.json",
        config_loader=lambda: app_config,
    )
    with patch("ddt_local.desktop_services.run_once", return_value=RunSummary(processed=1)) as run:
        result = controller.run_now()

    assert result.processed == 1
    assert run.call_args.args[0].ddt_home == selected.resolve()


def test_runner_action_respects_explicit_ddt_home_override(monkeypatch, app_config, tmp_path: Path):
    selected = tmp_path / "Selected"
    overridden = tmp_path / "Override"
    save_user_settings(UserSettings(ddt_home=selected, setup_completed=True), tmp_path / "config.json")
    monkeypatch.setenv("DDT_HOME", str(overridden))
    controller = DesktopSetupController(
        settings_path=tmp_path / "config.json",
        config_loader=lambda: replace(app_config, ddt_home=overridden),
    )
    with patch("ddt_local.desktop_services.run_once", return_value=RunSummary(processed=1)) as run:
        controller.run_now()

    assert run.call_args.args[0].ddt_home == overridden
