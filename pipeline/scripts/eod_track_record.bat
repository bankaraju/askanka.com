@echo off
REM Anka Research — EOD Daily Track Record. Runs at 16:30 IST every trading day.
REM Per task #82: -m form from project root.
cd /d "C:\Users\Claude_Anka\askanka.com"
C:\Python313\python.exe -m pipeline.run_eod_report >> pipeline\logs\eod_report.log 2>&1
C:\Python313\python.exe -X utf8 -m pipeline.website_exporter >> pipeline\logs\website_exporter.log 2>&1
