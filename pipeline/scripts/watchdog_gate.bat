@echo off
REM ANKA Watchdog — twice-daily gate (STAGE 2 LIVE: Telegram alerts enabled)
REM Checks every task, every tier, plus drift.
cd /d "C:\Users\Claude_Anka\askanka.com"
set PYTHONPATH=C:\Users\Claude_Anka\askanka.com\pipeline;%PYTHONPATH%
python -X utf8 -m pipeline.watchdog --all >> pipeline\logs\watchdog_stdout.log 2>&1
