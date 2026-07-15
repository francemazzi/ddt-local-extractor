"""Tests for configuration loading."""

from __future__ import annotations

import os

import pytest

from ddt_local.config import AppConfig, load_config


def test_load_config_defaults(monkeypatch: pytest.MonkeyPatch, tmp_path):
    home = tmp_path / "DDT"
    monkeypatch.delenv("DDT_HOME", raising=False)
    monkeypatch.setenv("DDT_HOME", str(home))
    config = load_config()

    assert config.ddt_home == home.resolve()
    assert config.pipeline == "ocr_struct"
    assert config.ocr_model == "glm-ocr:latest"
    assert config.struct_model == "qwen3.5:4b"
    assert config.vision_model == "qwen3.5:4b"
    assert config.render_dpi == 250
    assert config.seed == 42
    assert config.keep_raw_ocr is True
    assert config.unload_models is True


def test_derived_paths(app_config: AppConfig):
    assert app_config.inbox_dir == app_config.ddt_home / "inbox"
    assert app_config.processed_dir == app_config.ddt_home / "processed"
    assert app_config.errors_dir == app_config.ddt_home / "errors"
    assert app_config.database_path == app_config.data_dir / "ddt.sqlite3"
    assert app_config.excel_path == app_config.output_dir / "DDT_estratti.xlsx"
    assert app_config.lock_path == app_config.ddt_home / ".ddt_job.lock"


def test_env_bool_parsing(monkeypatch: pytest.MonkeyPatch, tmp_path):
    monkeypatch.setenv("DDT_HOME", str(tmp_path))
    monkeypatch.setenv("DDT_KEEP_RAW_OCR", "false")
    monkeypatch.setenv("DDT_UNLOAD_MODELS", "0")
    config = load_config()
    assert config.keep_raw_ocr is False
    assert config.unload_models is False


def test_ollama_base_url_strips_trailing_slash(monkeypatch: pytest.MonkeyPatch, tmp_path):
    monkeypatch.setenv("DDT_HOME", str(tmp_path))
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434/")
    config = load_config()
    assert config.ollama_base_url == "http://localhost:11434"


def test_custom_pipeline_and_models(monkeypatch: pytest.MonkeyPatch, tmp_path):
    monkeypatch.setenv("DDT_HOME", str(tmp_path))
    monkeypatch.setenv("DDT_PIPELINE", "vision_direct")
    monkeypatch.setenv("DDT_STRUCT_MODEL", "qwen3.5:9b")
    monkeypatch.setenv("DDT_VISION_MODEL", "qwen3.5:9b")
    config = load_config()
    assert config.pipeline == "vision_direct"
    assert config.struct_model == "qwen3.5:9b"
    assert config.vision_model == "qwen3.5:9b"


def test_tilde_expansion(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DDT_HOME", "~/DDT")
    config = load_config()
    assert str(config.ddt_home).endswith("DDT")
    assert "~" not in str(config.ddt_home)
