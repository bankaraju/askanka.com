@echo off
cd /d C:\Users\Claude_Anka\askanka.com
call .venv\Scripts\activate.bat
python -m pipeline.scripts.fetch_nse_index_weights
