@echo off
REM Anka Research — Kite Token Refresh
REM Runs at 08:15 IST every trading day via Task Scheduler
cd /d "C:\Users\Claude_Anka\askanka.com\pipeline"
C:\Python313\python.exe kite_auth.py >> logs\kite_auth.log 2>&1
