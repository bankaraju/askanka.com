@echo off
REM Anka — daily article prune (>7 days → _archive/), runs after daily_articles
cd /d "C:\Users\Claude_Anka\askanka.com\pipeline"
python -X utf8 article_lifecycle.py >> logs\article_prune.log 2>&1
