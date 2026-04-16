@echo off
REM ANKA Watchdog — intraday cadence (every 15 min, market hours only)
REM Only checks tier=critical files. Drift check only runs in --all mode.
cd /d "C:\Users\Claude_Anka\askanka.com"
python -X utf8 -m pipeline.watchdog --tier critical >> pipeline\logs\watchdog.log 2>&1
