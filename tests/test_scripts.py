"""Static and dry-run checks for the cross-platform scheduling helpers."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PROJECT_ROOT / "scripts"


@pytest.mark.skipif(os.name == "nt", reason="Bash and launchd are validated on the macOS runner")
@pytest.mark.parametrize(
    "name", ["run_macos.sh", "install_launchd.sh", "pull_models.sh", "build_macos.sh"]
)
def test_shell_scripts_have_valid_bash_syntax(name: str):
    result = subprocess.run(
        ["bash", "-n", SCRIPTS / name],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.skipif(os.name == "nt", reason="launchd helper is a macOS facility")
def test_launchd_dry_run_delegates_to_headless_runner():
    result = subprocess.run(
        ["bash", SCRIPTS / "install_launchd.sh", "--dry-run"],
        check=False,
        capture_output=True,
        env={**os.environ, "DDT_PYTHON": shutil.which("python3.12") or "python3"},
    )
    assert result.returncode == 0, result.stderr.decode()
    assert b"ddt_local.desktop_runner --run-once" in result.stdout


def test_platform_wrappers_delegate_scheduling_to_the_headless_runner():
    wrapper = (SCRIPTS / "run_windows.cmd").read_text(encoding="utf-8")
    scheduler = (SCRIPTS / "install_task_scheduler.ps1").read_text(encoding="utf-8")
    assert "-m ddt_local run --once" in wrapper
    assert "-m ddt_local scheduler install" in scheduler
    assert "-m ddt_local scheduler remove" in scheduler


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


def test_windows_build_script_parses_when_powershell_is_available():
    if shutil.which("pwsh") is None:
        pytest.skip("PowerShell is not installed on this host")
    command = (
        "$tokens = $null; $parseErrors = $null; "
        "[System.Management.Automation.Language.Parser]::ParseFile("
        "(Resolve-Path 'scripts/build_windows.ps1'), [ref]$tokens, [ref]$parseErrors) "
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


def test_packaging_scripts_define_unsigned_native_installers():
    macos = (SCRIPTS / "build_macos.sh").read_text(encoding="utf-8")
    windows = (SCRIPTS / "build_windows.ps1").read_text(encoding="utf-8")
    inno = (PROJECT_ROOT / "packaging" / "DDT-Local-Extractor.iss").read_text(encoding="utf-8")
    assert "PyInstaller" in macos
    assert "--exclude-module nltk" in macos
    assert "hdiutil create" in macos
    assert "PyInstaller" in windows
    assert "--exclude-module nltk" in windows
    assert "ISCC.exe" in windows
    assert "DDT-Local-Extractor-{#MyAppVersion}-Setup" in inno
    assert 'OutputDir=..\\dist\\installer' in inno
    assert 'Source: "..\\dist\\DDT Local Extractor\\*"' in inno
    assert "UninstallDisplayIcon" in inno


def test_release_workflow_publishes_versioned_packages_for_each_desktop_platform():
    workflow = (PROJECT_ROOT / ".github" / "workflows" / "build-desktop.yml").read_text(encoding="utf-8")
    assert 'tags:\n      - "v*"' in workflow
    assert "macOS-Apple-Silicon" in workflow
    assert "macOS-Intel" in workflow
    assert "ddt-local-extractor-windows" in workflow
    assert "softprops/action-gh-release@v3" in workflow
    assert '"$PYTHON_BIN" -m venv .build-venv' in workflow
    assert '"$BUILD_PYTHON" -m pip install -e ".[dev]"' in workflow
    assert "Packaged runner failed with exit code" in workflow


def test_pages_workflow_deploys_the_download_landing_page():
    workflow = (PROJECT_ROOT / ".github" / "workflows" / "deploy-pages.yml").read_text(encoding="utf-8")
    page = (PROJECT_ROOT / "site" / "index.html").read_text(encoding="utf-8")
    assert "actions/deploy-pages@v4" in workflow
    assert "actions/upload-pages-artifact@v4" in workflow
    assert "path: site" in workflow
    assert "DDT-Local-Extractor-1.0.0-macOS-Apple-Silicon.dmg" in page
    assert "DDT-Local-Extractor-1.0.0-macOS-Intel.dmg" in page
    assert "DDT-Local-Extractor-1.0.0-Setup.exe" in page
