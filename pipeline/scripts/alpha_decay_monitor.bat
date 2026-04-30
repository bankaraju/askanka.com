@echo off
REM Alpha decay monitor — daily verdict per live spread basket.
REM Runs daily at 16:05 IST after AnkaEODReview/AnkaEODTrackRecord so it
REM reads all of today's closed shadow trades.
REM
REM Output:
REM   pipeline/data/research/alpha_decay/decay_<YYYY-MM-DD>.json
REM
REM Cadence: daily 16:05 IST (post-close, after track record write).
REM Watchdog tier: warn — failure means we lose decay visibility for one day,
REM not a hard outage.

cd /d "C:\Users\Claude_Anka\askanka.com"
set PYTHONPATH=C:\Users\Claude_Anka\askanka.com;C:\Users\Claude_Anka\askanka.com\pipeline
set PYTHONIOENCODING=utf-8
C:\Python313\python.exe -X utf8 -m pipeline.research.alpha_decay.monitor >> pipeline\logs\alpha_decay.log 2>&1
