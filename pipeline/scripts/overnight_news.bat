@echo off
REM ANKA News Backtest — scheduled post-close (16:20 IST).
REM Classifies today's detected events using today's ret_1d/5d price reactions.
REM See AnkaEODNews scheduled task.
cd /d "C:\Users\Claude_Anka\askanka.com\pipeline"
python -X utf8 news_backtest.py >> logs\overnight_news.log 2>&1
