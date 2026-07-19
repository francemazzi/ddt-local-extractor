"""Tests for the persistent desktop configuration."""

from __future__ import annotations

from pathlib import Path

import pytest

from ddt_local.config import load_config
from ddt_local.user_config import (
    APP_NAME,
    UserSettings,
    UserSettingsError,
    load_user_settings,
    read_user_settings,
    save_user_settings,
    user_config_path,
)


def test_platform_config_paths():
    home = Path("/Users/example")
    assert user_config_path(platform="darwin", home=home, environ={}) == (
        home / "Library" / "Application Support" / APP_NAME / "config.json"
    )
    assert user_config_path(platform="win32", home=home, environ={"APPDATA": "C:/Users/example/AppData/Roaming"}) == (
        Path("C:/Users/example/AppData/Roaming") / APP_NAME / "config.json"
    )


def test_save_and_read_user_settings_atomically(tmp_path: Path):
    path = tmp_path / "settings" / "config.json"
    expected = UserSettings(ddt_home=tmp_path / "DDT", scheduler_enabled=True, setup_completed=True)

    saved = save_user_settings(expected, path)

    assert saved == path
    assert read_user_settings(path) == UserSettings(
        ddt_home=(tmp_path / "DDT").resolve(),
        scheduler_enabled=True,
        setup_completed=True,
    )
    assert list(path.parent.glob(".config.*.json")) == []


def test_corrupt_settings_are_reported_but_runtime_falls_back(tmp_path: Path):
    path = tmp_path / "config.json"
    path.write_text("{broken", encoding="utf-8")

    with pytest.raises(UserSettingsError):
        read_user_settings(path)
    assert load_user_settings(path) is None


def test_persisted_desktop_folder_is_used_when_env_is_absent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    path = tmp_path / "config.json"
    selected = tmp_path / "Selected DDT"
    save_user_settings(UserSettings(ddt_home=selected), path)
    monkeypatch.setenv("DDT_USER_CONFIG", str(path))
    monkeypatch.delenv("DDT_HOME", raising=False)

    assert load_config().ddt_home == selected.resolve()


def test_ddt_home_environment_override_wins_over_persisted_selection(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    path = tmp_path / "config.json"
    save_user_settings(UserSettings(ddt_home=tmp_path / "Selected"), path)
    override = tmp_path / "Support override"
    monkeypatch.setenv("DDT_USER_CONFIG", str(path))
    monkeypatch.setenv("DDT_HOME", str(override))

    assert load_config().ddt_home == override.resolve()
