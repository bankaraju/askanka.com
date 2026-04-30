@echo off
REM PDR-BNK-NBFC (H-2026-04-30-PDR-BNK-NBFC) basket-close leg.
REM Runs daily at 14:25 IST. Closes all OPEN legs from today at Kite LTP
REM with exit_reason=TIME_STOP.
REM
REM Spec: docs/superpowers/specs/2026-04-30-pdr-banks-nbfc-design.md

cd /d "C:\Users\Claude_Anka\askanka.com"
set PYTHONPATH=C:\Users\Claude_Anka\askanka.com;C:\Users\Claude_Anka\askanka.com\pipeline
C:\Python313\python.exe -X utf8 -m pipeline.research.h_2026_04_30_pdr_bnk_nbfc.forward_shadow basket-close >> pipeline\logs\pdr_bnk_nbfc.log 2>&1
