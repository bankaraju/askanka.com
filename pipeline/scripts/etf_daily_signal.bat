@echo off
REM ETF Daily Signal — Apply stored weights to today's data
REM Scheduled: Daily 04:45 IST via AnkaETFSignal (after AnkaDailyDump at 04:30)
cd /d C:\Users\Claude_Anka\askanka.com
python -X utf8 -m pipeline.autoresearch.etf_daily_signal >> pipeline\logs\etf_daily_signal.log 2>&1
REM Translate regime_trade_map.json -> today_regime.json so dashboard sees today's
REM zone before market opens (was previously waiting for morning_scan at 09:25).
cd /d C:\Users\Claude_Anka\askanka.com\pipeline
python -X utf8 regime_scanner.py >> logs\regime_scanner.log 2>&1
REM Refresh website JSONs so live site reflects new regime by ~04:46 IST.
python -X utf8 website_exporter.py >> logs\website_exporter.log 2>&1
