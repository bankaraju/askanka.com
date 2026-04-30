@echo off
REM DEFIT (H-2026-04-30-DEFENCE-IT-NEUTRAL) basket-open leg.
REM Runs daily at 09:25 IST during the holdout window 2026-05-01 -> 2027-04-30.
REM Fires only if today_regime.json zone == NEUTRAL. Computes ATR(14)-scaled
REM per-leg weights, opens 6 legs (LONG HAL+BEL+BDL / SHORT TCS+INFY+WIPRO),
REM 5-day hold, basket-stop at -2.5%.
REM
REM Spec: docs/superpowers/specs/2026-04-30-defence-momentum-design.md

cd /d "C:\Users\Claude_Anka\askanka.com"
set PYTHONPATH=C:\Users\Claude_Anka\askanka.com;C:\Users\Claude_Anka\askanka.com\pipeline
C:\Python313\python.exe -X utf8 -m pipeline.research.h_2026_04_30_defence_momentum.forward_shadow --hypothesis DEFIT basket-open >> pipeline\logs\defence_momentum.log 2>&1
