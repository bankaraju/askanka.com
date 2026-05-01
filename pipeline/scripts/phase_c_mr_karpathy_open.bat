@echo off
REM H-2026-05-01-phase-c-mr-karpathy-v1 forward holdout -- OPEN leg
REM Runs daily at 09:30 IST during the holdout window 2026-05-04 -> 2026-08-01
REM (auto-extends to 2026-10-31 if n<100 by close).
REM
REM Loads frozen universe (top-100 ADV) + frozen profile + frozen sector map,
REM iterates the 19-step snap grid 09:30 -> 14:00 IST, applies regime + event-day
REM + Karpathy gates (if karpathy_chosen_cell.json exists), simulates ATR(14)*2
REM stop or 14:30 mechanical close, appends rows to
REM pipeline/data/research/h_2026_05_01_phase_c_mr_karpathy/recommendations.csv.
REM
REM Idempotent: safe to re-run within the same trading day; date already in
REM ledger -> skip_reason=already_in_ledger.
REM
REM Spec: docs/superpowers/specs/2026-05-01-phase-c-mr-karpathy-v1-design.md
REM Hypothesis: H-2026-05-01-phase-c-mr-karpathy-v1 (POSSIBLE_OPPORTUNITY mean-revert)
REM Single-touch holdout: 2026-05-04 09:30 IST -> 2026-08-01 14:30 IST. NO PARAMETER CHANGES.

cd /d "C:\Users\Claude_Anka\askanka.com"
set PYTHONPATH=C:\Users\Claude_Anka\askanka.com;C:\Users\Claude_Anka\askanka.com\pipeline
for /f "tokens=2 delims==" %%I in ('"wmic os get localdatetime /value" 2^>nul') do set DT=%%I
set TODAY=%DT:~0,4%-%DT:~4,2%-%DT:~6,2%
C:\Python313\python.exe -X utf8 -m pipeline.research.h_2026_05_01_phase_c_mr_karpathy.holdout_runner --date %TODAY% --phase open >> pipeline\logs\phase_c_mr_karpathy.log 2>&1
