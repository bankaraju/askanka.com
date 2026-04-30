@echo off
REM ANKA Weekly Spread Statistics — Sunday 22:00.
REM Per task #82: -m form from project root.
cd /d "C:\Users\Claude_Anka\askanka.com"
python -X utf8 -m pipeline.spread_statistics >> pipeline\logs\spread_stats.log 2>&1
