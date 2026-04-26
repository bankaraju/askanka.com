@echo off
REM ETF Engine V3 CURATED — Daily Signal
REM Replaces etf_daily_signal.bat (v2). Reads pre-computed weights from
REM etf_v3_curated_optimal_weights.json (written weekly by reoptimize job).
REM
REM Three v1/v2 failure modes locked out by construction:
REM   1. NEVER refits — reads stored weights only (v1 daily-recalibration bug)
REM   2. NO yfinance — uses canonical loader (no silent feature drop, v2 bug)
REM   3. NO zone-threshold drift — center/band read from weights JSON
REM
REM Scheduled: Daily 04:45 IST via AnkaETFv3CuratedSignal (after AnkaDailyDump 04:30)
cd /d C:\Users\Claude_Anka\askanka.com
python -X utf8 -m pipeline.autoresearch.etf_v3_curated_signal >> pipeline\logs\etf_v3_curated_signal.log 2>&1
REM Translate regime_trade_map.json -> today_regime.json so dashboard sees today's
REM zone before market opens (was previously waiting for morning_scan at 09:25).
cd /d C:\Users\Claude_Anka\askanka.com\pipeline
python -X utf8 regime_scanner.py >> logs\regime_scanner.log 2>&1
REM Refresh website JSONs so live site reflects new regime by ~04:46 IST.
python -X utf8 website_exporter.py >> logs\website_exporter.log 2>&1
