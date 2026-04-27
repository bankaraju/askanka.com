@echo off
REM SECRSI (H-2026-04-27-003) basket-open leg
REM Runs daily at 11:00 IST during the holdout window 2026-04-28 -> 2026-07-31.
REM Reads pipeline/data/research/h_2026_04_27_secrsi/opens/<date>.json,
REM fetches Kite LTP, runs sector_snapshot + basket_builder, computes
REM ATR(14)*2 stops, appends 8 OPEN rows to recommendations.csv.
REM
REM Idempotent: re-runs on the same trading day skip if basket already opened.
REM
REM Spec: docs/superpowers/specs/2026-04-27-intraday-sector-rs-pair-design.md
REM Hypothesis: H-2026-04-27-003 (Sector RS Intraday Pair, regime-agnostic)
REM Single-touch holdout: 2026-04-28 -> 2026-07-31. NO PARAMETER CHANGES.

cd /d "C:\Users\Claude_Anka\askanka.com"
set PYTHONPATH=C:\Users\Claude_Anka\askanka.com;C:\Users\Claude_Anka\askanka.com\pipeline
C:\Python313\python.exe -X utf8 -m pipeline.research.h_2026_04_27_secrsi.forward_shadow basket-open >> pipeline\logs\secrsi.log 2>&1
