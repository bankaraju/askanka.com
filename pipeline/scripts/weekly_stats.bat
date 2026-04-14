@echo off
REM ANKA Weekly Spread Statistics — Sunday 22:00
cd /d "C:\Users\Claude_Anka\askanka.com\pipeline"
python -X utf8 spread_statistics.py >> logs\spread_stats.log 2>&1
