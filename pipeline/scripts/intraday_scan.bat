@echo off
REM ANKA Intraday Scan — every 15 min
cd /d "C:\Users\Claude_Anka\askanka.com\pipeline"
python -X utf8 technical_scanner.py >> logs\intraday_scan.log 2>&1
python -X utf8 oi_scanner.py >> logs\intraday_scan.log 2>&1
python -X utf8 news_scanner.py >> logs\intraday_scan.log 2>&1
python -X utf8 news_intelligence.py >> logs\intraday_scan.log 2>&1
python -X utf8 spread_intelligence.py >> logs\intraday_scan.log 2>&1
REM Phase C: Correlation break scanner (runs after OI scanner so positioning.json is fresh)
for /f "tokens=*" %%r in ('python -c "import json; d=json.load(open('data/regime_ranker_state.json')); print(d.get('last_zone',''))" 2^>nul') do set _REGIME=%%r
for /f "tokens=*" %%t in ('python -c "import json; h=json.load(open('data/regime_ranker_history.json')); print(h[-1]['transition'])" 2^>nul') do set _TRANS=%%t
if not "%_TRANS%"=="" (
    python -X utf8 autoresearch\reverse_regime_breaks.py --transition "%_TRANS%" --regime "%_REGIME%" --day 1 >> logs\intraday_scan.log 2>&1
)
