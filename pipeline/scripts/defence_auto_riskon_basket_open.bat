@echo off
REM DEFAU (H-2026-04-30-DEFENCE-AUTO-RISKON) basket-open leg.
REM Runs daily at 09:25 IST during the holdout window 2026-05-01 -> 2027-04-30.
REM Fires only if today_regime.json zone == RISK-ON. Computes ATR(14)-scaled
REM per-leg weights with 2x baseline cap, opens 4 legs (LONG HAL+BEL /
REM SHORT TMPV+MARUTI), 5-day hold, basket-stop at -2.5%.
REM
REM Spec: docs/superpowers/specs/2026-04-30-defence-momentum-design.md

cd /d "C:\Users\Claude_Anka\askanka.com"
set PYTHONPATH=C:\Users\Claude_Anka\askanka.com;C:\Users\Claude_Anka\askanka.com\pipeline
C:\Python313\python.exe -X utf8 -m pipeline.research.h_2026_04_30_defence_momentum.forward_shadow --hypothesis DEFAU basket-open >> pipeline\logs\defence_momentum.log 2>&1
