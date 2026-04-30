@echo off
REM RELOMC EUPHORIA (H-2026-04-30-RELOMC-EUPHORIA) basket-open leg.
REM Runs daily at 09:25 IST during the holdout window 2026-05-01 -> 2027-04-30.
REM Fires only if today_regime.json zone == EUPHORIA AND basket-id for today
REM is not already in the ledger. Writes 3 OPEN rows (RELIANCE LONG / BPCL+IOC
REM SHORT) at Kite LTP, equal-notional dollar-neutral, 5-day hold.
REM
REM Spec: docs/superpowers/specs/2026-04-30-relomc-euphoria-design.md
REM Single-touch holdout: 2026-05-01 -> 2027-04-30. NO PARAMETER CHANGES.

cd /d "C:\Users\Claude_Anka\askanka.com"
set PYTHONPATH=C:\Users\Claude_Anka\askanka.com;C:\Users\Claude_Anka\askanka.com\pipeline
C:\Python313\python.exe -X utf8 -m pipeline.research.h_2026_04_30_relomc.forward_shadow basket-open >> pipeline\logs\relomc.log 2>&1
