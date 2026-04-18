@echo off
REM ETF Daily Signal — Apply stored weights to today's data
REM Scheduled: Daily 04:45 IST via AnkaETFSignal (after AnkaDailyDump at 04:30)
cd /d C:\Users\Claude_Anka\askanka.com
python -X utf8 -m pipeline.autoresearch.etf_daily_signal >> pipeline\logs\etf_daily_signal.log 2>&1
