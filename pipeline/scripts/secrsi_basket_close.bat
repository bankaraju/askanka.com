@echo off
REM SECRSI (H-2026-04-27-003) basket-close leg
REM Runs daily at 14:30 IST during the holdout window 2026-04-28 -> 2026-07-31.
REM Mechanical TIME_STOP per spec section 3.5: closes all OPEN legs at current
REM Kite LTP, writes exit_reason=TIME_STOP and pnl_pct.
REM
REM Idempotent: rows already CLOSED are skipped.
REM
REM Spec: docs/superpowers/specs/2026-04-27-intraday-sector-rs-pair-design.md
REM Hypothesis: H-2026-04-27-003 (Sector RS Intraday Pair, regime-agnostic)
REM Single-touch holdout: 2026-04-28 -> 2026-07-31. NO PARAMETER CHANGES.

cd /d "C:\Users\Claude_Anka\askanka.com"
set PYTHONPATH=C:\Users\Claude_Anka\askanka.com;C:\Users\Claude_Anka\askanka.com\pipeline
C:\Python313\python.exe -X utf8 -m pipeline.research.h_2026_04_27_secrsi.forward_shadow basket-close >> pipeline\logs\secrsi.log 2>&1
