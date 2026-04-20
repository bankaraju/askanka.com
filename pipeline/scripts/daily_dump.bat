@echo off
C:\Python313\python.exe -X utf8 C:\Users\Claude_Anka\askanka.com\pipeline\schtask_runner.py run_daily.py >> C:\Users\Claude_Anka\askanka.com\pipeline\logs\daily_dump.log 2>&1
C:\Python313\python.exe -X utf8 C:\Users\Claude_Anka\askanka.com\pipeline\schtask_runner.py website_exporter.py >> C:\Users\Claude_Anka\askanka.com\pipeline\logs\website_exporter.log 2>&1
