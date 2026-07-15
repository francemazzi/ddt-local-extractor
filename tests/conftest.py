"""Pytest configuration and shared fixtures."""

from __future__ import annotations

import pytest

from ddt_local.config import AppConfig, load_config


@pytest.fixture
def app_config(monkeypatch: pytest.MonkeyPatch, tmp_path) -> AppConfig:
    monkeypatch.setenv("DDT_HOME", str(tmp_path / "DDT"))
    return load_config()
