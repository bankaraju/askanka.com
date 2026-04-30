@echo off
REM ANKA Intraday Scan — every 15 min.
REM Per task #82: -m form from project root for every leg, data paths
REM now project-root-relative. Eliminates the `cd pipeline/` invocation
REM pattern that produced 23h silent crash on 2026-04-29.
cd /d "C:\Users\Claude_Anka\askanka.com"
python -X utf8 -m pipeline.technical_scanner >> pipeline\logs\intraday_scan.log 2>&1
python -X utf8 -m pipeline.oi_scanner >> pipeline\logs\intraday_scan.log 2>&1
python -X utf8 -m pipeline.news_scanner >> pipeline\logs\intraday_scan.log 2>&1
python -X utf8 -m pipeline.fno_news_scanner >> pipeline\logs\intraday_scan.log 2>&1
python -X utf8 -m pipeline.news_intelligence >> pipeline\logs\intraday_scan.log 2>&1
python -X utf8 -m pipeline.spread_intelligence >> pipeline\logs\intraday_scan.log 2>&1
python -X utf8 -m pipeline.msi_refresh >> pipeline\logs\intraday_scan.log 2>&1
python -X utf8 -m pipeline.signal_rescorer >> pipeline\logs\intraday_scan.log 2>&1
REM Phase C: Correlation break scanner (runs after OI scanner so positioning.json is fresh)
for /f "tokens=*" %%r in ('python -c "import json; d=json.load(open('pipeline/data/regime_ranker_state.json')); print(d.get('last_zone',''))" 2^>nul') do set _REGIME=%%r
for /f "tokens=*" %%t in ('python -c "import json; h=json.load(open('pipeline/data/regime_ranker_history.json')); print(h[-1]['transition'])" 2^>nul') do set _TRANS=%%t
if not "%_TRANS%"=="" (
    python -X utf8 -m pipeline.autoresearch.reverse_regime_breaks --transition "%_TRANS%" --regime "%_REGIME%" >> pipeline\logs\intraday_scan.log 2>&1
)
python -X utf8 -m pipeline.feature_scorer.score_universe >> pipeline\logs\intraday_scan.log 2>&1
python -X utf8 -m pipeline.website_exporter >> pipeline\logs\website_exporter.log 2>&1
