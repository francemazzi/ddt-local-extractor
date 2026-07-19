"""CLI completion tests that do not require an Ollama server."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from ddt_local.cli import main


class _HealthyOllama:
    def __init__(self, config) -> None:
        self.config = config

    def health_check(self) -> bool:
        return True

    def list_models(self) -> list[str]:
        return [self.config.ocr_model, self.config.struct_model, self.config.vision_model]


def test_doctor_checks_local_dependencies_dirs_database_and_excel(
    app_config, monkeypatch: pytest.MonkeyPatch, capsys
):
    monkeypatch.setenv("DDT_HOME", str(app_config.ddt_home))
    assert main(["init"]) == 0

    with patch("ddt_local.ollama.OllamaClient", _HealthyOllama):
        assert main(["doctor"]) == 0

    output = capsys.readouterr().out
    assert "Python: OK" in output
    assert "Ollama: OK" in output
    assert "SQLite: OK" in output
    assert "Excel: OK" in output


def test_reprocess_unknown_hash_returns_error(app_config, monkeypatch: pytest.MonkeyPatch, capsys):
    monkeypatch.setenv("DDT_HOME", str(app_config.ddt_home))
    assert main(["reprocess", "f" * 64]) == 1
    assert "No source document found" in capsys.readouterr().err


def test_scheduler_cli_installs_headless_job(app_config, monkeypatch: pytest.MonkeyPatch, capsys):
    monkeypatch.setenv("DDT_HOME", str(app_config.ddt_home))
    with patch("ddt_local.cli.install_scheduler", return_value=app_config.ddt_home / "agent.plist") as install:
        assert main(["scheduler", "install"]) == 0

    assert install.call_args.kwargs["interval_seconds"] == 300
    assert install.call_args.kwargs["ddt_home"] == app_config.ddt_home
    assert "Automatic job installed" in capsys.readouterr().out
