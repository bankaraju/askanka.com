@echo off
REM v2 Mode 2 autoresearch orchestrator -- 20:00 IST daily.
cd /d C:\Users\Claude_Anka\askanka.com
python -m pipeline.autoresearch.regime_autoresearch.scripts.run_mode2 >> C:\Users\Claude_Anka\askanka.com\pipeline\logs\autoresearch_mode2.log 2>&1
