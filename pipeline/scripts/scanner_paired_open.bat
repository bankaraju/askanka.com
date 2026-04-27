@echo off
REM Scanner Top-10 paired-shadow — OPEN leg
REM Runs daily at 09:25 IST, right after AnkaPatternScannerScan publishes
REM yesterday's pattern_signals_today.json (written the prior evening at 16:30).
REM Opens a paired (futures + ATM monthly options) shadow row for each of the
REM Top-10 scanner signals, recording entry at live Kite LTP.
REM
REM Paper engine — exempt from 14:30 IST live-engine cutoff (spec §4 Q3).
REM Idempotent: safe to re-run within the same trading day.

cd /d "C:\Users\Claude_Anka\askanka.com"
set PYTHONPATH=C:\Users\Claude_Anka\askanka.com;C:\Users\Claude_Anka\askanka.com\pipeline
C:\Python313\python.exe -X utf8 -m pipeline.cli_pattern_scanner paired-open >> pipeline\logs\scanner_paired_shadow.log 2>&1
