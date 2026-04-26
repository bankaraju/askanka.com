@echo off
REM H-2026-04-26-001 forward paper test -- OPEN leg
REM Runs daily at 09:30 IST during the holdout window 2026-04-27 -> 2026-05-26.
REM Reads pipeline/data/correlation_breaks.json, filters |z|>=2.0 signals,
REM fetches Kite LTP, computes ATR(14)*2 stop, appends OPEN rows to
REM pipeline/data/research/h_2026_04_26_001/recommendations.csv.
REM
REM Idempotent: safe to re-run within the same trading day; duplicate
REM (date, ticker) pairs are skipped.
REM
REM Spec: docs/superpowers/specs/2026-04-26-sigma-break-mechanical-v1-design.md
REM Hypothesis: H-2026-04-26-001 (unconditional) + H-2026-04-26-002 (regime-gated sister)
REM Single-touch holdout: 2026-04-27 09:30 IST -> 2026-05-26 14:30 IST. NO PARAMETER CHANGES.

cd /d "C:\Users\Claude_Anka\askanka.com"
set PYTHONPATH=C:\Users\Claude_Anka\askanka.com;C:\Users\Claude_Anka\askanka.com\pipeline
C:\Python313\python.exe -X utf8 -m pipeline.h_2026_04_26_001_paper open >> pipeline\logs\h_2026_04_26_001_paper.log 2>&1
