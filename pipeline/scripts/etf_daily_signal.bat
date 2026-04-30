@echo off
REM ETF Daily Signal — Apply stored weights to today's data
REM Scheduled: Daily 04:45 IST via AnkaETFSignal (after AnkaDailyDump at 04:30)
REM
REM All three modules are invoked as packages (-m pipeline.X) from the
REM project root so `from pipeline import ...` works. Running them as
REM scripts from inside pipeline/ added the wrong directory to sys.path
REM and broke `from pipeline import provenance` silently — caught
REM 2026-04-30, the 78h-stale today_regime.json provenance sidecar
REM traces to that path bug. Same fix shape as commit 97b01a7 (#82).
cd /d C:\Users\Claude_Anka\askanka.com
python -X utf8 -m pipeline.autoresearch.etf_daily_signal >> pipeline\logs\etf_daily_signal.log 2>&1
REM Translate regime_trade_map.json -> today_regime.json so dashboard sees today's
REM zone before market opens (was previously waiting for morning_scan at 09:25).
python -X utf8 -m pipeline.regime_scanner >> pipeline\logs\regime_scanner.log 2>&1
REM Refresh website JSONs so live site reflects new regime by ~04:46 IST.
python -X utf8 -m pipeline.website_exporter >> pipeline\logs\website_exporter.log 2>&1
