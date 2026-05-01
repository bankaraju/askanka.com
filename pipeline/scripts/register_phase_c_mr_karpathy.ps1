$ErrorActionPreference = 'Stop'
# Registers Anka tasks for H-2026-05-01-phase-c-mr-karpathy-v1.
# Single-touch holdout 2026-05-04 -> 2026-08-01 (auto-extends to 2026-10-31 if n<100).
# Spec: docs/superpowers/specs/2026-05-01-phase-c-mr-karpathy-v1-design.md
# Idempotent: re-run any time to reset.

$repo = 'C:\Users\Claude_Anka\askanka.com'
$logDir = Join-Path $repo 'pipeline\logs'
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir -Force | Out-Null }

$tasks = @(
    @{
        Name = 'AnkaPhaseCMRKarpathyOpen'
        Bat  = (Join-Path $repo 'pipeline\scripts\phase_c_mr_karpathy_open.bat')
        At   = '9:30AM'
        Desc = 'H-2026-05-01-phase-c-mr-karpathy-v1 OPEN: POSSIBLE_OPPORTUNITY mean-revert + regime gate + event skip + Karpathy qualifier. Single-touch holdout 2026-05-04 -> 2026-08-01.'
    },
    @{
        Name = 'AnkaPhaseCMRKarpathyClose'
        Bat  = (Join-Path $repo 'pipeline\scripts\phase_c_mr_karpathy_close.bat')
        At   = '2:30PM'
        Desc = 'H-2026-05-01-phase-c-mr-karpathy-v1 CLOSE: mechanical TIME_STOP at 14:30 IST. Single-touch holdout 2026-05-04 -> 2026-08-01.'
    }
)

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30) `
    -MultipleInstances IgnoreNew

foreach ($t in $tasks) {
    $existing = Get-ScheduledTask -TaskName $t.Name -ErrorAction SilentlyContinue
    if ($existing) { Unregister-ScheduledTask -TaskName $t.Name -Confirm:$false }

    $action  = New-ScheduledTaskAction -Execute 'cmd.exe' -Argument "/c `"$($t.Bat)`""
    $trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At $t.At

    Register-ScheduledTask -TaskName $t.Name -Action $action -Trigger $trigger `
        -Settings $settings -User $env:USERNAME -RunLevel Limited `
        -Description $t.Desc | Out-Null

    Write-Output "registered $($t.Name) at $($t.At)"
}
