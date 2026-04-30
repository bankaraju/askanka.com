@echo off
REM Anka Research — Kite Token Refresh
REM Runs at 09:00 IST every trading day via Task Scheduler.
REM
REM Per task #82: invoke as `python -m pipeline.kite_auth` from project root
REM so all `from pipeline.X import` resolve cleanly. The legacy
REM `cd pipeline/; python script.py` pattern broke 3 modules on 2026-04-29.
cd /d "C:\Users\Claude_Anka\askanka.com"
C:\Python313\python.exe -m pipeline.kite_auth >> pipeline\logs\kite_auth.log 2>&1
