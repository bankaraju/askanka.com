@echo off
REM VPS -> laptop sync for AnkaDailyDump artifacts.
REM Runs Mon-Fri 04:50 IST after VPS systemd timer (anka-daily-dump.timer @ 04:30 IST) finishes.
REM Pulls today's prices + fundamentals + FII flows so laptop downstream tasks (morning_scan, intraday) see fresh files.

set LOG=C:\Users\Claude_Anka\askanka.com\pipeline\logs\vps_sync_daily.log
set KEY=C:\Users\Claude_Anka\.ssh\contabo_vmi3256563
set HOST=anka@185.182.8.107
set REPO=/home/anka/askanka.com

echo. >> %LOG%
echo ===== %DATE% %TIME% VPS sync start ===== >> %LOG%

scp -B -i %KEY% -o StrictHostKeyChecking=no %HOST%:%REPO%/pipeline/data/daily/*.json C:\Users\Claude_Anka\askanka.com\pipeline\data\daily\ >> %LOG% 2>&1
scp -B -i %KEY% -o StrictHostKeyChecking=no %HOST%:%REPO%/pipeline/data/flows/*.json C:\Users\Claude_Anka\askanka.com\pipeline\data\flows\ >> %LOG% 2>&1
REM fno_historical/*.csv is the chart endpoint's daily-refresh tail source (273-ticker F&O).
REM Without this line, charts never see today/yesterday's bar after the AnkaDailyDump VPS migration.
scp -B -i %KEY% -o StrictHostKeyChecking=no %HOST%:%REPO%/pipeline/data/fno_historical/*.csv C:\Users\Claude_Anka\askanka.com\pipeline\data\fno_historical\ >> %LOG% 2>&1

echo ===== %DATE% %TIME% VPS sync done ===== >> %LOG%
