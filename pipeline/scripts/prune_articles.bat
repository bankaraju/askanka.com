@echo off
REM Anka — daily article prune (>7 days → _archive/), runs after daily_articles.
REM Per task #82: -m form from project root.
cd /d "C:\Users\Claude_Anka\askanka.com"
python -X utf8 -m pipeline.article_lifecycle >> pipeline\logs\article_prune.log 2>&1
