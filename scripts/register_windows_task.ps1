<#
.SYNOPSIS
  Register a Windows Task Scheduler job that runs scripts\run_update.ps1.

.DESCRIPTION
  The update is incremental, so a run with nothing new finishes in seconds.
  Default: every 4 weeks on Monday at 03:00.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\register_windows_task.ps1
  powershell -ExecutionPolicy Bypass -File scripts\register_windows_task.ps1 -Day Sunday -At "02:00" -WeeksInterval 1

.NOTES
  Runs as the current user while logged on (no password stored).
  Remove with: Unregister-ScheduledTask -TaskName "Gaia air-quality update"
#>
param(
    [ValidateSet("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")]
    [string]$Day = "Monday",
    [string]$At = "03:00",
    [int]$WeeksInterval = 4,
    [string]$TaskName = "Gaia air-quality update"
)
$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
$script = Join-Path $PSScriptRoot "run_update.ps1"

$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$script`"" `
    -WorkingDirectory $repo
$trigger = New-ScheduledTaskTrigger -Weekly -WeeksInterval $WeeksInterval -DaysOfWeek $Day -At $At
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -RunOnlyIfNetworkAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Hours 12)

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings `
    -Description "Incremental CAMS download, warehouse load and dbt build" -Force | Out-Null

Write-Host "Registered '$TaskName': every $WeeksInterval week(s) on $Day at $At."
Write-Host "Run it now with: Start-ScheduledTask -TaskName '$TaskName'"
Write-Host "Logs: $repo\logs\"
