@echo off
REM ANKA News Backtest — scheduled post-close (16:20 IST).
REM Classifies today's detected events using today's ret_1d/5d price reactions.
REM See AnkaEODNews scheduled task. Per task #82: -m form from project root.
cd /d "C:\Users\Claude_Anka\askanka.com"
python -X utf8 -m pipeline.news_backtest >> pipeline\logs\overnight_news.log 2>&1
