@echo off
REM Phase 3: Daily shadow runner — 4:30 AM IST
C:\Python313\python.exe -X utf8 C:\Users\Claude_Anka\askanka.com\pipeline\live_shadow\daily_shadow_runner.py >> C:\Users\Claude_Anka\askanka.com\pipeline\logs\shadow.log 2>&1
