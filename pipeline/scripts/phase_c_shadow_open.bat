@echo off
REM Phase C F3 live shadow ledger — OPEN leg
REM Runs daily at 09:25 IST, right after the morning_scan publishes today's
REM correlation_breaks.json. Filters OPPORTUNITY classifications, fetches
REM live Kite LTP for each symbol, appends OPEN rows to
REM pipeline/data/research/phase_c/live_paper_ledger.json.
REM
REM Idempotent: safe to re-run within the same trading day.

cd /d "C:\Users\Claude_Anka\askanka.com"
C:\Python313\python.exe -X utf8 -m pipeline.phase_c_shadow open >> pipeline\logs\phase_c_shadow.log 2>&1
