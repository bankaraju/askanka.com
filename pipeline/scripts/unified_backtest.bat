@echo off
REM Unified Backtest — Statistical Referee (Sunday night)
REM Scheduled: Sunday 00:00 IST via AnkaUnifiedBacktest
cd /d C:\Users\Claude_Anka\askanka.com
python -X utf8 -m pipeline.autoresearch.unified_backtest >> pipeline\logs\unified_backtest.log 2>&1
