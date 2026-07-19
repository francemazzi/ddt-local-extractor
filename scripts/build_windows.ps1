<# Build an unsigned Windows installer. Requires PyInstaller and Inno Setup 6. #>

[CmdletBinding()]
param(
    [string]$Python = "python",
    [string]$Version = "0.1.0"
)

$ErrorActionPreference = "Stop"
$ProjectDir = (Resolve-Path (Join-Path $PSScriptRoot ".."))
Set-Location $ProjectDir

& $Python -m PyInstaller --noconfirm --clean --paths src --exclude-module nltk --windowed `
    --name "DDT Local Extractor" src\ddt_local\desktop_gui.py
if ($LASTEXITCODE -ne 0) { throw "PyInstaller GUI build failed" }
& $Python -m PyInstaller --noconfirm --clean --paths src --exclude-module nltk --onefile --noconsole `
    --name ddt-local-runner src\ddt_local\desktop_runner.py
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

$AppDir = Join-Path $ProjectDir "dist\DDT Local Extractor"
Copy-Item (Join-Path $ProjectDir "dist\ddt-local-runner.exe") $AppDir -Force

$Iscc = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
if (-not (Test-Path $Iscc)) { throw "Inno Setup 6 not found: $Iscc" }
& $Iscc "/DMyAppVersion=$Version" packaging\DDT-Local-Extractor.iss
if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed" }
