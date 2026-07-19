"""UI-independent services for desktop onboarding and dashboard actions."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, replace
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Callable, Sequence

from ddt_local.config import AppConfig, load_config
from ddt_local.excel import write_production_excel
from ddt_local.ollama import OllamaClient, OllamaServiceError, PullProgress
from ddt_local.production import RunSummary, initialize_operational_home, run_once
from ddt_local.scheduler import (
    DEFAULT_INTERVAL_SECONDS,
    default_runner_command,
    install_scheduler,
    remove_scheduler,
)
from ddt_local.user_config import (
    UserSettings,
    UserSettingsError,
    load_user_settings,
    read_user_settings,
    save_user_settings,
)

PRODUCTION_MODELS = ("glm-ocr:latest", "qwen3.5:4b")


class DesktopSetupError(RuntimeError):
    """Raised when desktop onboarding cannot safely continue."""


@dataclass(frozen=True)
class OllamaReadiness:
    available: bool
    missing_models: tuple[str, ...] = ()

    @property
    def ready(self) -> bool:
        return self.available and not self.missing_models


@dataclass(frozen=True)
class DesktopStatus:
    configured: bool
    ready: bool
    ddt_home: Path | None
    scheduler_enabled: bool
    ollama: OllamaReadiness
    excel_exists: bool = False


def resolve_headless_runner_command() -> list[str]:
    """Locate the runner next to a packaged GUI, or use the module in development."""
    override = os.getenv("DDT_DESKTOP_RUNNER")
    if override:
        return [str(Path(override).expanduser()), "--run-once"]
    if getattr(sys, "frozen", False):
        executable = Path(sys.executable)
        candidates = [
            executable.with_name("ddt-local-runner"),
            executable.with_name("ddt-local-runner.exe"),
            executable.parent.parent / "Resources" / "ddt-local-runner",
        ]
        for candidate in candidates:
            if candidate.exists():
                return [str(candidate), "--run-once"]
        raise DesktopSetupError("Desktop runner executable not found next to the application")
    return default_runner_command()


class DesktopSetupController:
    """Coordinates setup without importing Tkinter, keeping it straightforward to test."""

    def __init__(
        self,
        *,
        settings_path: Path | None = None,
        config_loader: Callable[[], AppConfig] = load_config,
        scheduler_installer: Callable[..., Path | None] = install_scheduler,
        scheduler_remover: Callable[[], None] = remove_scheduler,
        runner_command: Sequence[str] | None = None,
        ollama_factory: Callable[[AppConfig], OllamaClient] = OllamaClient,
    ) -> None:
        self.settings_path = settings_path
        self._config_loader = config_loader
        self._scheduler_installer = scheduler_installer
        self._scheduler_remover = scheduler_remover
        self._runner_command = list(runner_command) if runner_command else None
        self._ollama_factory = ollama_factory

    def selected_config(self, selected_directory: Path) -> AppConfig:
        """Validate an exact user-selected folder and initialise its data layout."""
        ddt_home = _validate_writable_directory(selected_directory)
        config = replace(self._config_loader(), ddt_home=ddt_home)
        database = initialize_operational_home(config)
        write_production_excel(database, config.excel_path)
        return config

    def readiness(self, config: AppConfig) -> OllamaReadiness:
        client = self._ollama_factory(config)
        if not client.health_check():
            return OllamaReadiness(available=False, missing_models=PRODUCTION_MODELS)
        installed = client.list_models()
        missing = tuple(
            model
            for model in PRODUCTION_MODELS
            if model not in installed and not any(model in candidate for candidate in installed)
        )
        return OllamaReadiness(available=True, missing_models=missing)

    def download_missing_models(
        self,
        config: AppConfig,
        *,
        progress: Callable[[str, PullProgress], None] | None = None,
    ) -> OllamaReadiness:
        readiness = self.readiness(config)
        if not readiness.available:
            raise DesktopSetupError("Ollama is not available. Install it and press Riprova.")
        client = self._ollama_factory(config)
        for model in readiness.missing_models:
            try:
                client.pull_model(
                    model,
                    progress=(lambda event, current_model=model: progress(current_model, event))
                    if progress
                    else None,
                )
            except OllamaServiceError as exc:
                raise DesktopSetupError(str(exc)) from exc
        return self.readiness(config)

    def complete_setup(
        self,
        selected_directory: Path,
        *,
        interval_seconds: int = DEFAULT_INTERVAL_SECONDS,
    ) -> UserSettings:
        """Persist the folder and install a per-user scheduler after readiness succeeds."""
        config = self.selected_config(selected_directory)
        readiness = self.readiness(config)
        if not readiness.ready:
            details = "Ollama non disponibile" if not readiness.available else ", ".join(
                readiness.missing_models
            )
            raise DesktopSetupError(f"Setup incompleto: {details}")
        try:
            self._scheduler_installer(
                command=self._runner_command or resolve_headless_runner_command(),
                ddt_home=config.ddt_home,
                interval_seconds=interval_seconds,
            )
        except Exception as exc:
            raise DesktopSetupError(f"Non è possibile attivare l'elaborazione automatica: {exc}") from exc
        settings = UserSettings(
            ddt_home=config.ddt_home,
            scheduler_enabled=True,
            scheduler_interval_seconds=interval_seconds,
            setup_completed=True,
        )
        save_user_settings(settings, self.settings_path)
        return settings

    def stop_scheduler(self) -> UserSettings | None:
        """Disable automatic processing and remember that choice for this user."""
        try:
            self._scheduler_remover()
        except Exception as exc:
            raise DesktopSetupError(f"Non è possibile disattivare l'elaborazione automatica: {exc}") from exc
        try:
            settings = read_user_settings(self.settings_path)
        except UserSettingsError as exc:
            raise DesktopSetupError(f"Non è possibile aggiornare le impostazioni: {exc}") from exc
        if settings is None:
            return None
        stopped_settings = replace(settings, scheduler_enabled=False)
        save_user_settings(stopped_settings, self.settings_path)
        return stopped_settings

    def status(self) -> DesktopStatus:
        try:
            settings = read_user_settings(self.settings_path)
        except UserSettingsError:
            return DesktopStatus(False, False, None, False, OllamaReadiness(False))
        if settings is None:
            return DesktopStatus(False, False, None, False, OllamaReadiness(False))
        config = self._config_for_settings(settings)
        readiness = self.readiness(config)
        return DesktopStatus(
            configured=True,
            ready=settings.setup_completed and readiness.ready,
            ddt_home=settings.ddt_home,
            scheduler_enabled=settings.scheduler_enabled,
            ollama=readiness,
            excel_exists=config.excel_path.exists(),
        )

    def run_now(self) -> RunSummary:
        settings = load_user_settings(self.settings_path)
        if settings is None or not settings.setup_completed:
            raise DesktopSetupError("Completa prima la configurazione guidata")
        config = self._config_for_settings(settings)
        return run_once(config)

    def _config_for_settings(self, settings: UserSettings) -> AppConfig:
        """Respect an explicit technical ``DDT_HOME`` override when present."""
        config = self._config_loader()
        if os.getenv("DDT_HOME"):
            return config
        return replace(config, ddt_home=settings.ddt_home)


def _validate_writable_directory(path: Path) -> Path:
    try:
        resolved = path.expanduser().resolve()
        resolved.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise DesktopSetupError(f"Impossibile creare la cartella selezionata: {exc}") from exc
    if not resolved.is_dir():
        raise DesktopSetupError("La selezione deve essere una cartella")
    try:
        with NamedTemporaryFile(dir=resolved, prefix=".ddt_write_test_", delete=True):
            pass
    except OSError as exc:
        raise DesktopSetupError(f"La cartella selezionata non è scrivibile: {exc}") from exc
    return resolved
