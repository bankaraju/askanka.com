@echo off
REM DEFIT (H-2026-04-30-DEFENCE-IT-NEUTRAL) basket-monitor leg.
REM Runs every 15 min during 09:30-14:25 IST. Closes basket if weighted pnl
REM <= -250bp (basket stop).

cd /d "C:\Users\Claude_Anka\askanka.com"
set PYTHONPATH=C:\Users\Claude_Anka\askanka.com;C:\Users\Claude_Anka\askanka.com\pipeline
C:\Python313\python.exe -X utf8 -m pipeline.research.h_2026_04_30_defence_momentum.forward_shadow --hypothesis DEFIT basket-monitor >> pipeline\logs\defence_momentum.log 2>&1
