@echo off
REM H-2026-05-01-EARNINGS-DRIFT-LONG-v1 -- CLOSE leg
REM Runs daily at 14:30 IST trading days during the holdout window 2026-05-04 -> 2026-08-01.
REM Auto-extends until n>=20 OR 2026-10-31, whichever comes first.
REM
REM Mechanical TIME_STOP per spec section 7: scans OPEN rows in
REM pipeline/data/research/h_2026_05_01_earnings_drift_long/recommendations.csv
REM where (entry_date + 5 trading days) <= today, fetches Kite LTP, writes
REM CLOSED row with gross_bps and net_s1_bps (S1 cost = 20 bps round-trip).
REM
REM ATR(14)*2 per-leg stops are checked at every minute via the separate intraday
REM loop (not implemented at v1 -- TIME_STOP only); v1 captures TIME_STOP exits only.
REM
REM Idempotent: rows already CLOSED are skipped.
REM
REM Spec: docs/superpowers/specs/2026-05-01-earnings-drift-long-v1-design.md
REM Audit: docs/superpowers/specs/2026-05-01-earnings-data-source-audit.md
REM Hypothesis: H-2026-05-01-EARNINGS-DRIFT-LONG-v1
REM Single-touch holdout: 2026-05-04 14:25 IST -> 2026-08-01 14:30 IST. NO PARAMETER CHANGES.

cd /d "C:\Users\Claude_Anka\askanka.com"
set PYTHONPATH=C:\Users\Claude_Anka\askanka.com;C:\Users\Claude_Anka\askanka.com\pipeline
C:\Python313\python.exe -X utf8 -m pipeline.research.h_2026_05_01_earnings_drift_long.earnings_drift_engine close >> pipeline\logs\h_2026_05_01_earnings_drift_long.log 2>&1
