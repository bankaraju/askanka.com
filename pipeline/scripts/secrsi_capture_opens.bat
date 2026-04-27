@echo off
REM SECRSI (H-2026-04-27-003) capture-opens leg
REM Runs daily at 09:16 IST during the holdout window 2026-04-28 -> 2026-07-31.
REM Fetches Kite LTP for the full F&O universe (canonical_fno_research_v3) and
REM writes to pipeline/data/research/h_2026_04_27_secrsi/opens/<date>.json.
REM
REM Required by basket-open at 11:00 IST. Without this, basket-open aborts.
REM Idempotent: re-runs overwrite the same file.
REM
REM Spec: docs/superpowers/specs/2026-04-27-intraday-sector-rs-pair-design.md
REM Hypothesis: H-2026-04-27-003 (Sector RS Intraday Pair, regime-agnostic)
REM Single-touch holdout: 2026-04-28 -> 2026-07-31. NO PARAMETER CHANGES.

cd /d "C:\Users\Claude_Anka\askanka.com"
set PYTHONPATH=C:\Users\Claude_Anka\askanka.com;C:\Users\Claude_Anka\askanka.com\pipeline
C:\Python313\python.exe -X utf8 -m pipeline.research.h_2026_04_27_secrsi.forward_shadow capture-opens >> pipeline\logs\secrsi.log 2>&1
