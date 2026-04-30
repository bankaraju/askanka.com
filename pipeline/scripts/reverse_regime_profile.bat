@echo off
REM ANKA Reverse Regime Profile (Phase A) — daily @ 04:45 IST
REM Writes pipeline/data/reverse_regime_profile.json consumed by Phase B ranker.
REM Per task #82: -m form from project root.
cd /d "C:\Users\Claude_Anka\askanka.com"
python -X utf8 -m pipeline.autoresearch.reverse_regime_analysis >> pipeline\logs\reverse_regime_profile.log 2>&1
