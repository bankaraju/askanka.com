@echo off
REM ANKA Reverse Regime Profile (Phase A) — daily @ 04:45 IST
REM Writes pipeline/data/reverse_regime_profile.json consumed by Phase B ranker.
REM
REM INTERIM — this task was scheduled by remediate/scheduler-debt-2026-04-16
REM because Phase A was never scheduled in the original 2026-04-14
REM reverse-regime-stock-analysis plan. The designed cadence/trigger will be
REM decided in a fresh brainstorm 2026-04-17+.
cd /d "C:\Users\Claude_Anka\askanka.com\pipeline"
python -X utf8 autoresearch\reverse_regime_analysis.py >> logs\reverse_regime_profile.log 2>&1
