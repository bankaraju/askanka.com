@echo off
REM Anka Research — EOD Daily Track Record
REM Runs at 16:30 IST every trading day via Task Scheduler
cd /d "C:\Users\Claude_Anka\askanka.com\pipeline"
C:\Python313\python.exe run_eod_report.py >> logs\eod_report.log 2>&1
C:\Python313\python.exe -X utf8 website_exporter.py >> logs\website_exporter.log 2>&1
