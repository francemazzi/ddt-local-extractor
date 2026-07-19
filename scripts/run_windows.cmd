@echo off
rem Run one local DDT extraction pass on Windows Task Scheduler or cmd.exe.

setlocal EnableExtensions
set "PROJECT_DIR=%~dp0.."
for %%I in ("%PROJECT_DIR%") do set "PROJECT_DIR=%%~fI"

if defined DDT_PYTHON (
    set "PYTHON_BIN=%DDT_PYTHON%"
) else (
    set "PYTHON_BIN=%PROJECT_DIR%\.venv\Scripts\python.exe"
)

if not exist "%PYTHON_BIN%" (
    echo Python environment not found at "%PYTHON_BIN%". 1>&2
    echo Create it first: py -3.12 -m venv .venv ^&^& .venv\Scripts\pip install -e ".[dev]" 1>&2
    exit /b 1
)

cd /d "%PROJECT_DIR%"
"%PYTHON_BIN%" -m ddt_local run --once %*
exit /b %ERRORLEVEL%
