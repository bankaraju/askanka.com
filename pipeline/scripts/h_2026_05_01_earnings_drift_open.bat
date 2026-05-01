@echo off
REM H-2026-05-01-EARNINGS-DRIFT-LONG-v1 -- OPEN leg
REM Runs daily at 14:25 IST trading days during the holdout window 2026-05-04 -> 2026-08-01.
REM Auto-extends until n>=20 OR 2026-10-31, whichever comes first.
REM
REM Reads earnings calendar, finds (symbol, event_date) where event_date == next
REM trading day for the symbol AND symbol is in the frozen 40-name universe AND
REM features at T-1 (today) pass the FROZEN entry rule:
REM   - vol_z(5d/30d)        >= 0.52
REM   - short_mom(5d log)    > 0
REM   - realized_vol_21d_pct >= 29.0
REM   - V3-CURATED-30 regime in {NEUTRAL, RISK-ON} at T-1 close
REM Fetches Kite LTP, appends OPEN rows to
REM pipeline/data/research/h_2026_05_01_earnings_drift_long/recommendations.csv.
REM
REM Idempotent: first-touch dedup per (symbol, event_date) -- at most one OPEN
REM per name per quarterly earnings event.
REM
REM Spec: docs/superpowers/specs/2026-05-01-earnings-drift-long-v1-design.md
REM Audit: docs/superpowers/specs/2026-05-01-earnings-data-source-audit.md
REM Hypothesis: H-2026-05-01-EARNINGS-DRIFT-LONG-v1
REM Single-touch holdout: 2026-05-04 14:25 IST -> 2026-08-01 14:30 IST. NO PARAMETER CHANGES.

cd /d "C:\Users\Claude_Anka\askanka.com"
set PYTHONPATH=C:\Users\Claude_Anka\askanka.com;C:\Users\Claude_Anka\askanka.com\pipeline
C:\Python313\python.exe -X utf8 -m pipeline.research.h_2026_05_01_earnings_drift_long.earnings_drift_engine open >> pipeline\logs\h_2026_05_01_earnings_drift_long.log 2>&1
