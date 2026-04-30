@echo off
REM VPS -> laptop sync for AnkaDailyDump artifacts + every VPS-only research ledger.
REM Runs Mon-Fri 04:50 IST after VPS systemd timer (anka-daily-dump.timer @ 04:30 IST) finishes.
REM Pulls today's prices + fundamentals + FII flows + every VPS-resident hypothesis ledger
REM so laptop downstream tasks (morning_scan, intraday) and the operator dashboard have
REM same-day visibility on every VPS-side run.
REM
REM IMPORTANT: only pulls dirs the VPS is authoritative for. Phase C ledgers (host=laptop)
REM are NEVER pulled — laptop is the source of truth for those.

set LOG=C:\Users\Claude_Anka\askanka.com\pipeline\logs\vps_sync_daily.log
set KEY=C:\Users\Claude_Anka\.ssh\contabo_vmi3256563
set HOST=anka@185.182.8.107
set REPO=/home/anka/askanka.com
set LROOT=C:\Users\Claude_Anka\askanka.com

echo. >> %LOG%
echo ===== %DATE% %TIME% VPS sync start ===== >> %LOG%

REM --- AnkaDailyDump artefacts (price + fundamentals + flows + chart tail) ---
scp -B -i %KEY% -o StrictHostKeyChecking=no %HOST%:%REPO%/pipeline/data/daily/*.json %LROOT%\pipeline\data\daily\ >> %LOG% 2>&1
scp -B -i %KEY% -o StrictHostKeyChecking=no %HOST%:%REPO%/pipeline/data/flows/*.json %LROOT%\pipeline\data\flows\ >> %LOG% 2>&1
REM fno_historical/*.csv is the chart endpoint's daily-refresh tail source (273-ticker F&O).
scp -B -i %KEY% -o StrictHostKeyChecking=no %HOST%:%REPO%/pipeline/data/fno_historical/*.csv %LROOT%\pipeline\data\fno_historical\ >> %LOG% 2>&1

REM --- VPS-only research ledgers (every hypothesis hosted on VPS) ---
REM SECRSI (H-2026-04-27-003): 8-leg market-neutral pair, 11:00 IST snapshot -> 14:30 IST exit.
if not exist %LROOT%\pipeline\data\research\h_2026_04_27_secrsi mkdir %LROOT%\pipeline\data\research\h_2026_04_27_secrsi
scp -B -r -i %KEY% -o StrictHostKeyChecking=no %HOST%:%REPO%/pipeline/data/research/h_2026_04_27_secrsi/* %LROOT%\pipeline\data\research\h_2026_04_27_secrsi\ >> %LOG% 2>&1

REM TA Karpathy v1 (H-2026-04-29): per-stock TA Lasso top-10 NIFTY pilot.
if not exist %LROOT%\pipeline\data\research\h_2026_04_29_ta_karpathy_v1 mkdir %LROOT%\pipeline\data\research\h_2026_04_29_ta_karpathy_v1
scp -B -r -i %KEY% -o StrictHostKeyChecking=no %HOST%:%REPO%/pipeline/data/research/h_2026_04_29_ta_karpathy_v1/* %LROOT%\pipeline\data\research\h_2026_04_29_ta_karpathy_v1\ >> %LOG% 2>&1

REM Gemma 4 pilot audit + report cards (2026-04-29 -> 2026-05-19).
if not exist %LROOT%\pipeline\data\research\gemma4_pilot mkdir %LROOT%\pipeline\data\research\gemma4_pilot
scp -B -r -i %KEY% -o StrictHostKeyChecking=no %HOST%:%REPO%/pipeline/data/research/gemma4_pilot/* %LROOT%\pipeline\data\research\gemma4_pilot\ >> %LOG% 2>&1

REM Bulk deals (NSE rolling-today CSV -> daily parquet).
if not exist %LROOT%\pipeline\data\bulk_deals mkdir %LROOT%\pipeline\data\bulk_deals
scp -B -i %KEY% -o StrictHostKeyChecking=no %HOST%:%REPO%/pipeline/data/bulk_deals/* %LROOT%\pipeline\data\bulk_deals\ >> %LOG% 2>&1

REM Insider trades (NSE PIT disclosures, 7-day rolling -> monthly parquet).
if not exist %LROOT%\pipeline\data\insider_trades mkdir %LROOT%\pipeline\data\insider_trades
scp -B -i %KEY% -o StrictHostKeyChecking=no %HOST%:%REPO%/pipeline/data/insider_trades/* %LROOT%\pipeline\data\insider_trades\ >> %LOG% 2>&1

echo ===== %DATE% %TIME% VPS sync done ===== >> %LOG%
