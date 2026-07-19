@echo off
rem Double-click stop command for the portable Windows archive.

setlocal EnableExtensions
set "RUNNER_PATH=%~dp0DDT Local Extractor\ddt-local-runner.exe"

if exist "%RUNNER_PATH%" (
    "%RUNNER_PATH%" --stop-scheduler
    if not errorlevel 1 goto stopped
)

rem Fallback: also works if the app was deleted but stop.bat was kept.
schtasks /Delete /TN "DDT Local Extractor" /F >nul 2>&1
if errorlevel 1 (
    echo.
    echo Non e' stato possibile disattivare l'automazione.
    pause
    exit /b 1
)

:stopped
echo.
echo Elaborazione automatica disattivata.
pause
