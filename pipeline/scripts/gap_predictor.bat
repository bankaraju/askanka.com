@echo off
REM Anka Research - Layer-0 overnight gap predictor
REM Runs at 08:30 IST every trading day, after Asian markets open and
REM before the 09:15 pre-market brief. Writes data/gap_risk.json.
REM Per task #82: -m form from project root.
cd /d "C:\Users\Claude_Anka\askanka.com"
C:\Python313\python.exe -X utf8 -m pipeline.autoresearch.gap_predictor >> pipeline\logs\gap_predictor.log 2>&1
