@echo off
REM ANKA Morning Scan — 9:25 AM IST
cd /d "C:\Users\Claude_Anka\askanka.com\pipeline"
python -X utf8 regime_scanner.py >> logs\morning_scan.log 2>&1
python -X utf8 technical_scanner.py >> logs\morning_scan.log 2>&1
python -X utf8 oi_scanner.py >> logs\morning_scan.log 2>&1
python -X utf8 news_scanner.py >> logs\morning_scan.log 2>&1
python -X utf8 news_intelligence.py --full >> logs\morning_scan.log 2>&1
python -X utf8 spread_intelligence.py --morning >> logs\morning_scan.log 2>&1
python -X utf8 autoresearch\reverse_regime_ranker.py >> logs\morning_scan.log 2>&1
