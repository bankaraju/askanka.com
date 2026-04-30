@echo off
REM RELOMC EUPHORIA (H-2026-04-30-RELOMC-EUPHORIA) basket-close leg.
REM Runs daily at 14:25 IST. For each open basket whose target_close_date
REM (entry_date + 5 trading days) <= today, closes all 3 legs at Kite LTP
REM with exit_reason=TIME_STOP.
REM
REM Spec: docs/superpowers/specs/2026-04-30-relomc-euphoria-design.md

cd /d "C:\Users\Claude_Anka\askanka.com"
set PYTHONPATH=C:\Users\Claude_Anka\askanka.com;C:\Users\Claude_Anka\askanka.com\pipeline
C:\Python313\python.exe -X utf8 -m pipeline.research.h_2026_04_30_relomc.forward_shadow basket-close >> pipeline\logs\relomc.log 2>&1
