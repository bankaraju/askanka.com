$ErrorActionPreference = 'Stop'
# One-shot: retire AnkaShadow (broken) and repoint 13 AnkaTrust* tasks
# from the retired opus-anka/ clone to canonical askanka.com/opus/scripts/.
# Safe to re-run; idempotent.

$shadow = Get-ScheduledTask -TaskName 'AnkaShadow' -ErrorAction SilentlyContinue
if ($shadow) {
    Unregister-ScheduledTask -TaskName 'AnkaShadow' -Confirm:$false
    Write-Output "retired AnkaShadow"
}

$map = @{
    'AnkaTrustEOD'       = 'C:\Users\Claude_Anka\askanka.com\opus\scripts\eod_review.bat'
    'AnkaTrustMorning'   = 'C:\Users\Claude_Anka\askanka.com\opus\scripts\morning_portfolio.bat'
    'AnkaTrustIntra0942' = 'C:\Users\Claude_Anka\askanka.com\opus\scripts\intraday_monitor.bat'
    'AnkaTrustIntra1012' = 'C:\Users\Claude_Anka\askanka.com\opus\scripts\intraday_monitor.bat'
    'AnkaTrustIntra1042' = 'C:\Users\Claude_Anka\askanka.com\opus\scripts\intraday_monitor.bat'
    'AnkaTrustIntra1112' = 'C:\Users\Claude_Anka\askanka.com\opus\scripts\intraday_monitor.bat'
    'AnkaTrustIntra1142' = 'C:\Users\Claude_Anka\askanka.com\opus\scripts\intraday_monitor.bat'
    'AnkaTrustIntra1212' = 'C:\Users\Claude_Anka\askanka.com\opus\scripts\intraday_monitor.bat'
    'AnkaTrustIntra1242' = 'C:\Users\Claude_Anka\askanka.com\opus\scripts\intraday_monitor.bat'
    'AnkaTrustIntra1312' = 'C:\Users\Claude_Anka\askanka.com\opus\scripts\intraday_monitor.bat'
    'AnkaTrustIntra1342' = 'C:\Users\Claude_Anka\askanka.com\opus\scripts\intraday_monitor.bat'
    'AnkaTrustIntra1412' = 'C:\Users\Claude_Anka\askanka.com\opus\scripts\intraday_monitor.bat'
    'AnkaTrustIntra1442' = 'C:\Users\Claude_Anka\askanka.com\opus\scripts\intraday_monitor.bat'
    'AnkaTrustIntra1512' = 'C:\Users\Claude_Anka\askanka.com\opus\scripts\intraday_monitor.bat'
}

foreach ($name in $map.Keys) {
    $newCmd = $map[$name]
    $task = Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
    if (-not $task) {
        Write-Output "  SKIP (not found): $name"
        continue
    }
    $action = New-ScheduledTaskAction -Execute $newCmd
    Set-ScheduledTask -TaskName $name -Action $action | Out-Null
    Write-Output "  repointed $name -> $newCmd"
}

Write-Output "done"
