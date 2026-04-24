@echo off
REM v2 per-regime BH-FDR batch trigger -- 05:00 IST daily.
cd /d C:\Users\Claude_Anka\askanka.com
python -m pipeline.autoresearch.regime_autoresearch.scripts.run_bh_fdr_check >> C:\Users\Claude_Anka\askanka.com\pipeline\logs\autoresearch_bh_fdr.log 2>&1
