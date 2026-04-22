@echo off
REM ANKA Feature Coincidence Scorer — weekly fit, Sunday 01:00 IST
REM Runs quarterly walk-forward per-ticker over the F&O universe.
REM Output: pipeline/data/ticker_feature_models.json
cd /d "C:\Users\Claude_Anka\askanka.com"
python -X utf8 -m pipeline.feature_scorer.fit_universe >> pipeline\logs\fit_feature_scorer.log 2>&1
