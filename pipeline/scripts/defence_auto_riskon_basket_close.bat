@echo off
REM DEFAU (H-2026-04-30-DEFENCE-AUTO-RISKON) basket-close leg.
REM Runs daily at 14:25 IST. Closes baskets whose target_close_date
REM (entry_date + 5 trading days) <= today.

cd /d "C:\Users\Claude_Anka\askanka.com"
set PYTHONPATH=C:\Users\Claude_Anka\askanka.com;C:\Users\Claude_Anka\askanka.com\pipeline
C:\Python313\python.exe -X utf8 -m pipeline.research.h_2026_04_30_defence_momentum.forward_shadow --hypothesis DEFAU basket-close >> pipeline\logs\defence_momentum.log 2>&1
