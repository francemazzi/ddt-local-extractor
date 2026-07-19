@echo off
rem Double-click launcher for the portable Windows archive.

setlocal EnableExtensions
set "APP_PATH=%~dp0DDT Local Extractor\DDT Local Extractor.exe"

if not exist "%APP_PATH%" (
    echo.
    echo DDT Local Extractor non e' stato trovato.
    echo Estrai completamente lo ZIP e avvia start.bat dalla cartella estratta.
    echo.
    pause
    exit /b 1
)

start "DDT Local Extractor" "%APP_PATH%"
