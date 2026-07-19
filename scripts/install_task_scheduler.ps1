<#
Advanced developer helper. The desktop wizard installs the per-user schedule without
showing a console; this script delegates to the same scheduler backend.
#>

[CmdletBinding()]
param(
    [switch]$Uninstall,
    [ValidateRange(1, 1440)]
    [int]$IntervalMinutes = 5
)

$ErrorActionPreference = "Stop"
$ProjectDir = (Resolve-Path (Join-Path $PSScriptRoot ".."))
if ($env:DDT_PYTHON) {
    $Python = $env:DDT_PYTHON
} else {
    $Python = Join-Path $ProjectDir ".venv\Scripts\python.exe"
}

if (-not (Test-Path $Python -PathType Leaf)) {
    throw "Python environment not found: $Python"
}

Set-Location $ProjectDir
if ($Uninstall) {
    & $Python -m ddt_local scheduler remove
} else {
    & $Python -m ddt_local scheduler install --interval-minutes $IntervalMinutes
}
exit $LASTEXITCODE
