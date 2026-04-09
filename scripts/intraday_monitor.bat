@echo off
REM ANKA Intraday Monitor — every 30 min during market hours
C:\Python313\python.exe -X utf8 C:\Users\Claude_Anka\opus-anka\run_model_portfolio.py intraday >> C:\Users\Claude_Anka\opus-anka\logs\intraday.log 2>&1
