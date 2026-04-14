@echo off
REM Daily article generation — runs after market close (4:30 PM IST)
REM Generates war + epstein articles with AI header images, publishes to askanka.com

C:\Python313\python.exe -X utf8 C:\Users\Claude_Anka\askanka.com\pipeline\schtask_runner.py daily_articles.py >> C:\Users\Claude_Anka\askanka.com\pipeline\logs\daily_articles.log 2>&1
