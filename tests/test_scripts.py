"""Static and dry-run checks for the cross-platform scheduling helpers."""

from __future__ import annotations

import os
import plistlib
import shutil
import subprocess
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PROJECT_ROOT / "scripts"


@pytest.mark.parametrize("name", ["run_macos.sh", "install_launchd.sh", "pull_models.sh"])
def test_shell_scripts_have_valid_bash_syntax(name: str):
    result = subprocess.run(
        ["bash", "-n", SCRIPTS / name],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_launchd_dry_run_generates_a_valid_agent_plist(tmp_path: Path):
    environment = {**os.environ, "DDT_HOME": str(tmp_path / "DDT")}
    result = subprocess.run(
        ["bash", SCRIPTS / "install_launchd.sh", "--dry-run"],
        check=False,
        capture_output=True,
        env=environment,
    )
    assert result.returncode == 0, result.stderr.decode()
    plist = plistlib.loads(result.stdout)
    assert plist["Label"] == "com.ddt-local-extractor.run"
    assert plist["ProgramArguments"][0].endswith("scripts/run_macos.sh")
    assert plist["StartInterval"] == 300
    assert plist["EnvironmentVariables"]["DDT_HOME"] == str(tmp_path / "DDT")


def test_windows_wrappers_define_one_shot_scheduler_contract():
    wrapper = (SCRIPTS / "run_windows.cmd").read_text(encoding="utf-8")
    scheduler = (SCRIPTS / "install_task_scheduler.ps1").read_text(encoding="utf-8")
    assert "-m ddt_local run --once" in wrapper
    assert "DDT_HOME" in wrapper
    assert "New-ScheduledTaskAction" in scheduler
    assert "New-ScheduledTaskTrigger" in scheduler
    assert "run_windows.cmd" in scheduler


def test_task_scheduler_script_parses_when_powershell_is_available():
    if shutil.which("pwsh") is None:
        pytest.skip("PowerShell is not installed on this host")
    command = (
        "$tokens = $null; $parseErrors = $null; "
        "[System.Management.Automation.Language.Parser]::ParseFile("
        "(Resolve-Path 'scripts/install_task_scheduler.ps1'), [ref]$tokens, [ref]$parseErrors) "
        "| Out-Null; "
        "if ($parseErrors.Count -gt 0) { $parseErrors | ForEach-Object { Write-Error $_ }; exit 1 }"
    )
    result = subprocess.run(
        ["pwsh", "-NoLogo", "-NoProfile", "-Command", command],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_pull_models_uses_configurable_required_models():
    script = (SCRIPTS / "pull_models.sh").read_text(encoding="utf-8")
    assert "DDT_OCR_MODEL" in script
    assert "DDT_STRUCT_MODEL" in script
    assert "DDT_VISION_MODEL" in script
    assert '"$OLLAMA_BIN" pull "$model"' in script
