@echo off
cd /d "C:\Users\Claude_Anka\Documents\askanka.com\pipeline"
python -X utf8 run_signals.py --telegram >> logs\signals.log 2>&1
