@echo off
REM ETF Engine V2 — Weekly Reoptimization with Indian Data
REM Scheduled: Saturday 22:00 IST via AnkaETFReoptimize
cd /d C:\Users\Claude_Anka\askanka.com
python -X utf8 -m pipeline.autoresearch.etf_reoptimize >> pipeline\logs\etf_reoptimize.log 2>&1
