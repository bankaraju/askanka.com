@echo off
cd /d "C:\Users\Claude_Anka\Documents\askanka.com\pipeline"
python -X utf8 run_premarket.py --telegram >> logs\premarket.log 2>&1
