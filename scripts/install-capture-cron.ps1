<#
.SYNOPSIS
    Register a daily Windows Task Scheduler job to generate the journal at 06:00.

.DESCRIPTION
    Installs "MetisPrime-DailyJournal" task.
    Run once as an Administrator or as the current user (no admin needed for user tasks).

.EXAMPLE
    .\scripts\install-capture-cron.ps1

.EXAMPLE
    # Custom time
    .\scripts\install-capture-cron.ps1 -TriggerTime "08:00"
#>
param(
    [string]$TriggerTime = "06:00"
)

$TaskName   = "MetisPrime-DailyJournal"
$WorkingDir = (Get-Location).Path
$Executable = "uv"
$Arguments  = "run second-brain capture journal"

# Remove existing task silently
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

$action  = New-ScheduledTaskAction -Execute $Executable -Argument $Arguments -WorkingDirectory $WorkingDir
$trigger = New-ScheduledTaskTrigger -Daily -At $TriggerTime
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes 5) -RunOnlyIfNetworkAvailable:$false

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "Metis Prime: generate daily journal at $TriggerTime" `
    -RunLevel Limited `
    -Force

Write-Host "Registered task '$TaskName' — fires daily at $TriggerTime."
Write-Host "To verify: Get-ScheduledTask -TaskName '$TaskName'"
Write-Host "To remove:  Unregister-ScheduledTask -TaskName '$TaskName' -Confirm:`$false"
