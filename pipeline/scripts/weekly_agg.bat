@echo off
REM Split cmd stdout from Python FileHandler to avoid Windows file-lock race.
C:\Python313\python.exe -X utf8 C:\Users\Claude_Anka\askanka.com\pipeline\schtask_runner.py weekly_aggregator.py >> C:\Users\Claude_Anka\askanka.com\pipeline\logs\weekly_aggregator_stdout.log 2>&1
