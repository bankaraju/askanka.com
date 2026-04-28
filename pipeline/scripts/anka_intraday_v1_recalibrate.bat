@echo off
cd /d C:\Users\Claude_Anka\askanka.com
python -m pipeline.research.intraday_v1.runner recalibrate --pool stocks
python -m pipeline.research.intraday_v1.runner recalibrate --pool indices
