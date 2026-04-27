@echo off
REM Scanner Top-10 paired-shadow — CLOSE leg
REM Runs daily at 15:30 IST — mechanical close of all OPEN scanner paired rows.
REM Fetches live Kite LTP for each symbol still OPEN in the futures and options
REM ledgers, transitions OPEN -> CLOSED with exit_reason = TIME_STOP, and writes
REM realized net P&L via cost_model.
REM
REM Paper engine — exempt from 14:30 IST live-engine cutoff (spec §4 Q3).
REM Sidecar pattern: futures shadow runs unaffected on options-side failure.

cd /d "C:\Users\Claude_Anka\askanka.com"
set PYTHONPATH=C:\Users\Claude_Anka\askanka.com;C:\Users\Claude_Anka\askanka.com\pipeline
C:\Python313\python.exe -X utf8 -m pipeline.cli_pattern_scanner paired-close >> pipeline\logs\scanner_paired_shadow.log 2>&1
