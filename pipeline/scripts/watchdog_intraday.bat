@echo off
REM ANKA Watchdog — intraday cadence (STAGE 1 SHADOW: --dry-run ON)
REM Only checks tier=critical files. Drift check only runs in --all mode.
cd /d "C:\Users\Claude_Anka\askanka.com"
python -X utf8 -m pipeline.watchdog --tier critical --dry-run >> pipeline\logs\watchdog_stdout.log 2>&1
