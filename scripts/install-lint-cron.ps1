# install-lint-cron.ps1
# Registers a Windows Task Scheduler job to run 'second-brain lint' every Sunday at 08:00.
# Run once as Administrator: powershell -ExecutionPolicy Bypass -File scripts\install-lint-cron.ps1

param(
    [string]$VaultPath = $env:SECOND_BRAIN_VAULT_PATH,
    [string]$PythonExe = (Get-Command uv -ErrorAction SilentlyContinue).Source
)

if (-not $VaultPath) {
    Write-Error "Set SECOND_BRAIN_VAULT_PATH environment variable or pass -VaultPath."
    exit 1
}

if (-not $PythonExe) {
    Write-Error "uv not found in PATH. Install uv first."
    exit 1
}

$TaskName = "MetisPrime-WeeklyLint"
$ProjectDir = Split-Path -Parent $PSScriptRoot

$Action = New-ScheduledTaskAction `
    -Execute $PythonExe `
    -Argument "run second-brain lint" `
    -WorkingDirectory $ProjectDir

$Trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At "08:00"

$Settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Hours 1) `
    -RestartCount 2 `
    -RestartInterval (New-TimeSpan -Minutes 5)

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -RunLevel Highest `
    -Force | Out-Null

Write-Host "Scheduled task '$TaskName' registered successfully."
Write-Host "Runs every Sunday at 08:00 in: $ProjectDir"
Write-Host ""
Write-Host "To run immediately:  Start-ScheduledTask -TaskName '$TaskName'"
Write-Host "To remove:           Unregister-ScheduledTask -TaskName '$TaskName' -Confirm:`$false"
