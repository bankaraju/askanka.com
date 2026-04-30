@echo off
REM ANKA Morning Scan — 9:25 AM IST.
REM Per task #82: -m form from project root for every leg.
cd /d "C:\Users\Claude_Anka\askanka.com"
python -X utf8 -m pipeline.regime_scanner >> pipeline\logs\morning_scan.log 2>&1
python -X utf8 -m pipeline.technical_scanner >> pipeline\logs\morning_scan.log 2>&1
python -X utf8 -m pipeline.oi_scanner >> pipeline\logs\morning_scan.log 2>&1
python -X utf8 -m pipeline.news_scanner >> pipeline\logs\morning_scan.log 2>&1
python -X utf8 -m pipeline.fno_news_scanner >> pipeline\logs\morning_scan.log 2>&1
python -X utf8 -m pipeline.news_intelligence --full >> pipeline\logs\morning_scan.log 2>&1
python -X utf8 -m pipeline.spread_intelligence --morning >> pipeline\logs\morning_scan.log 2>&1
python -X utf8 -m pipeline.autoresearch.reverse_regime_ranker >> pipeline\logs\morning_scan.log 2>&1
python -X utf8 -m pipeline.website_exporter >> pipeline\logs\website_exporter.log 2>&1
