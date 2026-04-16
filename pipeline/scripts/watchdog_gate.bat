@echo off
REM ANKA Watchdog — twice-daily gate (STAGE 1 SHADOW: --dry-run ON)
REM Checks every task, every tier, plus drift.
cd /d "C:\Users\Claude_Anka\askanka.com"
python -X utf8 -m pipeline.watchdog --all --dry-run >> pipeline\logs\watchdog_stdout.log 2>&1
