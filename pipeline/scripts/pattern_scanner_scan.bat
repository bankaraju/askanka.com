@echo off
cd /d C:\Users\Claude_Anka\askanka.com
call .venv\Scripts\activate.bat
python -m pipeline.cli_pattern_scanner scan
