@echo off
REM ANKA Watchdog — intraday cadence (STAGE 2 LIVE: Telegram alerts enabled)
REM Only checks tier=critical files. Drift check only runs in --all mode.
cd /d "C:\Users\Claude_Anka\askanka.com"
set PYTHONPATH=C:\Users\Claude_Anka\askanka.com\pipeline;%PYTHONPATH%
python -X utf8 -m pipeline.watchdog --tier critical >> pipeline\logs\watchdog_stdout.log 2>&1
