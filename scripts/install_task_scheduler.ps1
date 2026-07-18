<#
Install or remove a per-user Windows Task Scheduler job for DDT Local Extractor.
The task invokes the wrapper every five minutes; no resident Python service is used.
#>

[CmdletBinding()]
param(
    [switch]$Uninstall,
    [string]$TaskName = "DDT Local Extractor",
    [ValidateRange(1, 1440)]
    [int]$IntervalMinutes = 5
)

$ErrorActionPreference = "Stop"
$ProjectDir = (Resolve-Path (Join-Path $PSScriptRoot ".."))
$Wrapper = Join-Path $ProjectDir "scripts\run_windows.cmd"

if ($Uninstall) {
    $existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($null -ne $existing) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Host "Removed scheduled task '$TaskName'."
    } else {
        Write-Host "Scheduled task '$TaskName' is not installed."
    }
    exit 0
}

if (-not (Test-Path $Wrapper -PathType Leaf)) {
    throw "Windows wrapper not found: $Wrapper"
}

# DDT_HOME defaults to %USERPROFILE%\DDT in run_windows.cmd. To use another
# location, define the DDT_HOME user environment variable before installing.
$Action = New-ScheduledTaskAction -Execute $Wrapper -WorkingDirectory $ProjectDir
$Trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) `
    -RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes) `
    -RepetitionDuration (New-TimeSpan -Days 3650)
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger `
    -Settings $Settings -Description "One-shot local DDT extraction queue job" -Force | Out-Null

Write-Host "Installed '$TaskName' every $IntervalMinutes minutes."
Write-Host "Run manually: $Wrapper"
