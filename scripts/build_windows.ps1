<# Build a portable Windows ZIP. Requires PyInstaller. #>

[CmdletBinding()]
param(
    [string]$Python = "python",
    [string]$Version = "1.0.0"
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
$PackageName = "DDT-Local-Extractor-$Version-Windows-x64"
$PackageDir = Join-Path $ProjectDir (Join-Path "dist" $PackageName)
$ArchivePath = Join-Path $ProjectDir (Join-Path "dist" "$PackageName.zip")

if (Test-Path $PackageDir) { Remove-Item -Recurse -Force $PackageDir }
if (Test-Path $ArchivePath) { Remove-Item -Force $ArchivePath }
New-Item -ItemType Directory -Path $PackageDir | Out-Null

Copy-Item $AppDir $PackageDir -Recurse
Copy-Item (Join-Path $ProjectDir "dist\ddt-local-runner.exe") (Join-Path $PackageDir "DDT Local Extractor\ddt-local-runner.exe") -Force
Copy-Item (Join-Path $ProjectDir "packaging\start.bat") (Join-Path $PackageDir "start.bat")
Copy-Item (Join-Path $ProjectDir "packaging\stop.bat") (Join-Path $PackageDir "stop.bat")
Copy-Item (Join-Path $ProjectDir "packaging\LEGGIMI.txt") (Join-Path $PackageDir "LEGGIMI.txt")

Compress-Archive -Path $PackageDir -DestinationPath $ArchivePath -CompressionLevel Optimal
Write-Output "Created $ArchivePath"
