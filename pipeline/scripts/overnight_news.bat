@echo off
REM ANKA Overnight News Backtest — runs at 04:30 AM
cd /d "C:\Users\Claude_Anka\askanka.com\pipeline"
python -X utf8 news_backtest.py >> logs\overnight_news.log 2>&1
