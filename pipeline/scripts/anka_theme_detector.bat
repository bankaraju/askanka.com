@echo off
cd /d C:\Users\Claude_Anka\askanka.com
call .venv\Scripts\activate.bat
for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd"') do set RUN_DATE=%%i
python -m pipeline.research.theme_detector.detector --run-date %RUN_DATE% --themes pipeline\research\theme_detector\themes_frozen.json --state-dir pipeline\data\research\theme_detector\state --output-dir pipeline\data\research\theme_detector
