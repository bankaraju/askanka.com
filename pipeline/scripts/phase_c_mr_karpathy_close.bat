@echo off
REM H-2026-05-01-phase-c-mr-karpathy-v1 forward holdout -- CLOSE leg
REM Runs daily at 14:30 IST during the holdout window 2026-05-04 -> 2026-08-01
REM (auto-extends to 2026-10-31 if n<100 by close).
REM
REM The v1 engine simulates exits at OPEN time (full-day 5m bars are read at
REM run time), so this CLOSE phase is idempotent: re-runs the same logic and
REM short-circuits if rows already exist for today's date. If OPEN was missed
REM (e.g., scheduler skip), CLOSE will pick it up.
REM
REM Spec: docs/superpowers/specs/2026-05-01-phase-c-mr-karpathy-v1-design.md
REM Hypothesis: H-2026-05-01-phase-c-mr-karpathy-v1 (POSSIBLE_OPPORTUNITY mean-revert)
REM Single-touch holdout: 2026-05-04 09:30 IST -> 2026-08-01 14:30 IST. NO PARAMETER CHANGES.

cd /d "C:\Users\Claude_Anka\askanka.com"
set PYTHONPATH=C:\Users\Claude_Anka\askanka.com;C:\Users\Claude_Anka\askanka.com\pipeline
for /f "tokens=2 delims==" %%I in ('"wmic os get localdatetime /value" 2^>nul') do set DT=%%I
set TODAY=%DT:~0,4%-%DT:~4,2%-%DT:~6,2%
C:\Python313\python.exe -X utf8 -m pipeline.research.h_2026_05_01_phase_c_mr_karpathy.holdout_runner --date %TODAY% --phase close >> pipeline\logs\phase_c_mr_karpathy.log 2>&1
