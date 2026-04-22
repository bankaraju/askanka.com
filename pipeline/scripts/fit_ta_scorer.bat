@echo off
REM ANKA TA Coincidence Scorer — weekly fit, Sunday 01:30 IST (RELIANCE pilot v1)
REM Runs 2y/3mo quarterly walk-forward for the pilot ticker only.
REM Output: pipeline/data/ta_feature_models.json
cd /d "C:\Users\Claude_Anka\askanka.com"
python -X utf8 -m pipeline.ta_scorer.fit_universe >> pipeline\logs\fit_ta_scorer.log 2>&1
