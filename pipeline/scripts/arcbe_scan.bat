@echo off
REM Split cmd stdout from Python FileHandler to avoid Windows file-lock race.
cd /d C:\Users\Claude_Anka\askanka.com\pipeline
C:\Python313\python.exe -X utf8 run_correlation_scan.py >> logs\arcbe_scan_stdout.log 2>&1
