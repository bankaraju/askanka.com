@echo off
REM RELOMC EUPHORIA (H-2026-04-30-RELOMC-EUPHORIA) basket-monitor leg.
REM Runs every 15 min during 09:30-14:25 IST. For each open basket, computes
REM weighted basket pnl in bps; if <= -300 bps, closes all 3 legs at LTP
REM with exit_reason=BASKET_STOP.
REM
REM Spec: docs/superpowers/specs/2026-04-30-relomc-euphoria-design.md

cd /d "C:\Users\Claude_Anka\askanka.com"
set PYTHONPATH=C:\Users\Claude_Anka\askanka.com;C:\Users\Claude_Anka\askanka.com\pipeline
C:\Python313\python.exe -X utf8 -m pipeline.research.h_2026_04_30_relomc.forward_shadow basket-monitor >> pipeline\logs\relomc.log 2>&1
