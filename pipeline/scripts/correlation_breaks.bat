@echo off
REM ANKA Correlation Break Scanner (Phase C) — runs every 15 min intraday
REM Reads regime from Phase B state, OI from latest positioning.json
cd /d "C:\Users\Claude_Anka\askanka.com\pipeline"

REM Get current regime from state file
for /f "tokens=*" %%a in ('python -c "import json; d=json.load(open('data/regime_ranker_state.json')); print(d.get('last_zone','NEUTRAL'))"') do set REGIME=%%a

REM Infer last transition from ranker history
for /f "tokens=*" %%a in ('python -c "import json; h=json.load(open('data/regime_ranker_history.json')); print(h[-1]['transition'] if h else '')" 2^>nul') do set TRANSITION=%%a

if "%TRANSITION%"=="" (
    echo No transition history found. Skipping break scan.
    exit /b 0
)

python -X utf8 autoresearch\reverse_regime_breaks.py --transition "%TRANSITION%" --regime "%REGIME%" --day 1 --no-telegram >> logs\correlation_breaks.log 2>&1
