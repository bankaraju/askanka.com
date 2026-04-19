@echo off
C:\Python313\python.exe -X utf8 C:\Users\Claude_Anka\askanka.com\pipeline\schtask_runner.py run_signals.py --eod --telegram >> C:\Users\Claude_Anka\askanka.com\pipeline\logs\eod.log 2>&1
REM Archive the day's final positioning.json for future computations (PCR trend, OI velocity).
C:\Python313\python.exe -X utf8 C:\Users\Claude_Anka\askanka.com\pipeline\schtask_runner.py oi_scanner.py --archive-only >> C:\Users\Claude_Anka\askanka.com\pipeline\logs\eod.log 2>&1
