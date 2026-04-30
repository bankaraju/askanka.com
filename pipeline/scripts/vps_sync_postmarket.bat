@echo off
REM Post-market VPS -> laptop sync — runs Mon-Fri 15:00 IST.
REM
REM The 04:50 IST daily sync covers AnkaDailyDump artefacts. But every
REM intraday-strategy ledger written between market open and 14:30 IST
REM (SECRSI, TA Karpathy, intraday Gemma 4 audit) doesn't reach the
REM laptop until 04:50 the NEXT morning — same-day operator audit +
REM dashboard freshness lag by ~14 hours. This script closes that gap
REM by re-syncing the post-market-relevant dirs at 15:00 IST, ~30 min
REM after the last close fires.
REM
REM Pulls only research ledgers — the AnkaDailyDump dirs (daily/,
REM flows/, fno_historical/) are intentionally skipped here since they
REM don't change after market.

set LOG=C:\Users\Claude_Anka\askanka.com\pipeline\logs\vps_sync_postmarket.log
set KEY=C:\Users\Claude_Anka\.ssh\contabo_vmi3256563
set HOST=anka@185.182.8.107
set REPO=/home/anka/askanka.com
set LROOT=C:\Users\Claude_Anka\askanka.com

echo. >> %LOG%
echo ===== %DATE% %TIME% post-market VPS sync start ===== >> %LOG%

REM SECRSI (H-2026-04-27-003): closes at 14:30 IST.
if not exist %LROOT%\pipeline\data\research\h_2026_04_27_secrsi mkdir %LROOT%\pipeline\data\research\h_2026_04_27_secrsi
scp -B -r -i %KEY% -o StrictHostKeyChecking=no %HOST%:%REPO%/pipeline/data/research/h_2026_04_27_secrsi/* %LROOT%\pipeline\data\research\h_2026_04_27_secrsi\ >> %LOG% 2>&1

REM TA Karpathy v1 (H-2026-04-29): closes at 15:25 IST — 15:00 sync may miss
REM today's close on a slow day. The 04:50 morning sync catches it regardless.
if not exist %LROOT%\pipeline\data\research\h_2026_04_29_ta_karpathy_v1 mkdir %LROOT%\pipeline\data\research\h_2026_04_29_ta_karpathy_v1
scp -B -r -i %KEY% -o StrictHostKeyChecking=no %HOST%:%REPO%/pipeline/data/research/h_2026_04_29_ta_karpathy_v1/* %LROOT%\pipeline\data\research\h_2026_04_29_ta_karpathy_v1\ >> %LOG% 2>&1

REM Gemma 4 pilot — daily report card writes 22:00 IST, but intraday audit
REM jsonls accumulate throughout the day; pull what's there.
if not exist %LROOT%\pipeline\data\research\gemma4_pilot mkdir %LROOT%\pipeline\data\research\gemma4_pilot
scp -B -r -i %KEY% -o StrictHostKeyChecking=no %HOST%:%REPO%/pipeline/data/research/gemma4_pilot/* %LROOT%\pipeline\data\research\gemma4_pilot\ >> %LOG% 2>&1

echo ===== %DATE% %TIME% post-market VPS sync done ===== >> %LOG%
