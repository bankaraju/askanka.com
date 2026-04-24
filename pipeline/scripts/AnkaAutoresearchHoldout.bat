@echo off
REM v2 holdout runner -- 05:30 IST daily.
cd /d C:\Users\Claude_Anka\askanka.com
python -m pipeline.autoresearch.regime_autoresearch.holdout_runner >> C:\Users\Claude_Anka\askanka.com\pipeline\logs\autoresearch_holdout.log 2>&1
