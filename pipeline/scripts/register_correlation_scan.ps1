$ErrorActionPreference = 'Stop'
# Registers AnkaCorrelationScan at 07:15 Mon-Fri. Upstream feed for
# AnkaMorningBrief0730 (07:30 Mon-Fri). Re-run any time to reset.

$name = 'AnkaCorrelationScan'
$bat = 'C:\Users\Claude_Anka\askanka.com\pipeline\scripts\arcbe_scan.bat'

$existing = Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
if ($existing) { Unregister-ScheduledTask -TaskName $name -Confirm:$false }

$action   = New-ScheduledTaskAction -Execute 'cmd.exe' -Argument "/c `"$bat`""
$trigger  = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At 7:15AM
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Hours 1) `
    -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName $name -Action $action -Trigger $trigger `
    -Settings $settings -User $env:USERNAME -RunLevel Limited `
    -Description 'Daily correlation scan feeding AnkaMorningBrief0730 (07:15 Mon-Fri).' | Out-Null

Write-Output "registered $name"
