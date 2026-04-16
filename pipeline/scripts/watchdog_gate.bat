@echo off
REM ANKA Watchdog — twice-daily gate (09:20 + 16:45 IST)
REM Checks every task, every tier, plus drift.
cd /d "C:\Users\Claude_Anka\askanka.com"
python -X utf8 -m pipeline.watchdog --all >> pipeline\logs\watchdog.log 2>&1
