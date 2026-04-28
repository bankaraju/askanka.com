$ErrorActionPreference = 'Stop'
# Registers the 18 Windows Scheduled Tasks for the H-2026-04-29-intraday-data-driven-v1
# stocks-pool kickoff (2026-04-29).
#
# Layout:
#   1 loader (04:30 daily)
#   1 live open (09:30)
#   15 shadow ledger snapshots (09:30, 09:45, ..., 13:00)
#   1 mechanical close (14:30)
#
# All triggers are Mon-Fri IST (laptop time). Per
# memory/feedback_prefer_vps_systemd_over_windows_scheduler.md every registration
# is verified with Get-ScheduledTask AFTER Register-ScheduledTask. The script
# throws if any task is missing post-register, even when Register-ScheduledTask
# itself returned successfully.
#
# Re-run any time to reset; existing AnkaIntradayV1* tasks are unregistered first.

$scriptDir = 'C:\Users\Claude_Anka\askanka.com\pipeline\scripts'

# Hashtable: TaskName -> @{ Bat; Time; ExecMinutes; Description }
$tasks = [ordered]@{}

$tasks['AnkaIntradayV1LoaderRefresh'] = @{
    Bat = "$scriptDir\anka_intraday_v1_loader.bat"
    Time = '4:30AM'
    ExecMinutes = 60
    Description = 'H-2026-04-29-intraday-data-driven-v1 Kite 1-min cache delta-refresh (~60 instruments).'
}

$tasks['AnkaIntradayV1Open'] = @{
    Bat = "$scriptDir\anka_intraday_v1_open.bat"
    Time = '9:30AM'
    ExecMinutes = 30
    Description = 'H-2026-04-29-intraday-data-driven-v1 live-open paper trades for V1 holdout.'
}

# 15 shadow tasks every 15 min from 09:30 to 13:00.
$shadowTimes = @(
    @{ Slot = '0930'; Time = '9:30AM' },
    @{ Slot = '0945'; Time = '9:45AM' },
    @{ Slot = '1000'; Time = '10:00AM' },
    @{ Slot = '1015'; Time = '10:15AM' },
    @{ Slot = '1030'; Time = '10:30AM' },
    @{ Slot = '1045'; Time = '10:45AM' },
    @{ Slot = '1100'; Time = '11:00AM' },
    @{ Slot = '1115'; Time = '11:15AM' },
    @{ Slot = '1130'; Time = '11:30AM' },
    @{ Slot = '1145'; Time = '11:45AM' },
    @{ Slot = '1200'; Time = '12:00PM' },
    @{ Slot = '1215'; Time = '12:15PM' },
    @{ Slot = '1230'; Time = '12:30PM' },
    @{ Slot = '1245'; Time = '12:45PM' },
    @{ Slot = '1300'; Time = '1:00PM' }
)

foreach ($s in $shadowTimes) {
    $name = "AnkaIntradayV1Shadow_$($s.Slot)"
    $tasks[$name] = @{
        Bat = "$scriptDir\anka_intraday_v1_shadow_$($s.Slot).bat"
        Time = $s.Time
        ExecMinutes = 30
        Description = "H-2026-04-29-intraday-data-driven-v1 15-min shadow ledger snapshot at $($s.Slot) IST."
    }
}

$tasks['AnkaIntradayV1Close'] = @{
    Bat = "$scriptDir\anka_intraday_v1_close.bat"
    Time = '2:30PM'
    ExecMinutes = 30
    Description = 'H-2026-04-29-intraday-data-driven-v1 mechanical TIME_STOP close at Kite LTP.'
}

Write-Output "Registering $($tasks.Count) AnkaIntradayV1* scheduled tasks..."
Write-Output ""

$registered = New-Object System.Collections.ArrayList
$failed     = New-Object System.Collections.ArrayList

foreach ($name in $tasks.Keys) {
    $cfg = $tasks[$name]

    if (-not (Test-Path $cfg.Bat)) {
        $failed.Add($name) | Out-Null
        throw "BAT FILE MISSING for $name : $($cfg.Bat)"
    }

    $existing = Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
    if ($existing) {
        Unregister-ScheduledTask -TaskName $name -Confirm:$false
    }

    $action   = New-ScheduledTaskAction -Execute 'cmd.exe' -Argument "/c `"$($cfg.Bat)`""
    $trigger  = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At $cfg.Time
    $settings = New-ScheduledTaskSettingsSet `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -StartWhenAvailable `
        -ExecutionTimeLimit (New-TimeSpan -Minutes $cfg.ExecMinutes) `
        -MultipleInstances IgnoreNew

    Register-ScheduledTask `
        -TaskName $name `
        -Action $action `
        -Trigger $trigger `
        -Settings $settings `
        -User $env:USERNAME `
        -RunLevel Limited `
        -Description $cfg.Description | Out-Null

    # Verify (per feedback_prefer_vps_systemd_over_windows_scheduler.md)
    $check = Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
    if (-not $check) {
        $failed.Add($name) | Out-Null
        throw "VERIFICATION FAILED: $name was NOT registered (Get-ScheduledTask returned null)"
    }

    $registered.Add($name) | Out-Null
    Write-Output "OK  $name  trigger=$($cfg.Time)  bat=$([System.IO.Path]::GetFileName($cfg.Bat))"
}

Write-Output ""
Write-Output "Registered + verified: $($registered.Count) / $($tasks.Count)"
if ($failed.Count -gt 0) {
    Write-Output "Failed: $($failed -join ', ')"
    throw "One or more registrations failed verification."
}

# Independent re-verification via fresh Get-ScheduledTask query
$final = Get-ScheduledTask | Where-Object { $_.TaskName -like 'AnkaIntradayV1*' -and $_.TaskName -ne 'AnkaIntradayV1Recalibrate' }
Write-Output ""
Write-Output "Independent verification: Get-ScheduledTask sees $($final.Count) AnkaIntradayV1* tasks (excluding recalibrate)."
if ($final.Count -ne $tasks.Count) {
    throw "MISMATCH: expected $($tasks.Count) tasks, Get-ScheduledTask sees $($final.Count)."
}
Write-Output "ALL 18 TASKS REGISTERED AND VERIFIED."
