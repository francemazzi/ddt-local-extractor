"""Persistent per-user settings used by the desktop application."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile

APP_NAME = "DDT Local Extractor"
CONFIG_FILENAME = "config.json"


class UserSettingsError(ValueError):
    """Raised when the persisted desktop settings are malformed."""


@dataclass(frozen=True)
class UserSettings:
    """Settings chosen by the non-technical desktop user."""

    ddt_home: Path
    scheduler_enabled: bool = False
    scheduler_interval_seconds: int = 300
    setup_completed: bool = False

    def __post_init__(self) -> None:
        if self.scheduler_interval_seconds < 60:
            raise UserSettingsError("Scheduler interval must be at least 60 seconds")


def user_config_path(
    *,
    platform: str | None = None,
    environ: dict[str, str] | None = None,
    home: Path | None = None,
) -> Path:
    """Return the platform-standard location for the desktop configuration."""
    environ = os.environ if environ is None else environ
    override = environ.get("DDT_USER_CONFIG")
    if override:
        return Path(override).expanduser().resolve()

    current_platform = platform or sys.platform
    resolved_home = (home or Path.home()).expanduser()
    if current_platform == "darwin":
        root = resolved_home / "Library" / "Application Support"
    elif current_platform.startswith("win"):
        root = Path(environ.get("APPDATA", resolved_home / "AppData" / "Roaming"))
    else:
        root = Path(environ.get("XDG_CONFIG_HOME", resolved_home / ".config"))
    return root / APP_NAME / CONFIG_FILENAME


def read_user_settings(path: Path | None = None) -> UserSettings | None:
    """Read persisted settings, raising ``UserSettingsError`` for bad content."""
    path = path or user_config_path()
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise UserSettingsError(f"Cannot read desktop settings: {exc}") from exc

    if not isinstance(payload, dict) or not isinstance(payload.get("ddt_home"), str):
        raise UserSettingsError("Desktop settings require a string ddt_home")
    try:
        return UserSettings(
            ddt_home=Path(payload["ddt_home"]).expanduser().resolve(),
            scheduler_enabled=bool(payload.get("scheduler_enabled", False)),
            scheduler_interval_seconds=int(payload.get("scheduler_interval_seconds", 300)),
            setup_completed=bool(payload.get("setup_completed", False)),
        )
    except (TypeError, ValueError, OSError) as exc:
        raise UserSettingsError(f"Invalid desktop settings: {exc}") from exc


def load_user_settings(path: Path | None = None) -> UserSettings | None:
    """Best-effort reader for runtime configuration fallback."""
    try:
        return read_user_settings(path)
    except UserSettingsError:
        return None


def save_user_settings(settings: UserSettings, path: Path | None = None) -> Path:
    """Write settings atomically so a power loss never leaves partial JSON."""
    path = path or user_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "ddt_home": str(settings.ddt_home.expanduser().resolve()),
        "scheduler_enabled": settings.scheduler_enabled,
        "scheduler_interval_seconds": settings.scheduler_interval_seconds,
        "setup_completed": settings.setup_completed,
    }
    temporary_path: Path | None = None
    try:
        with NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            prefix=f".{path.stem}.",
            suffix=".json",
            dir=path.parent,
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            json.dump(payload, temporary, ensure_ascii=False, indent=2)
            temporary.write("\n")
        os.replace(temporary_path, path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
    return path
