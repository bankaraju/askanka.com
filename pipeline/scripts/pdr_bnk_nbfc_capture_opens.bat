@echo off
REM PDR-BNK-NBFC (H-2026-04-30-PDR-BNK-NBFC) capture-opens leg.
REM Runs daily at 09:16 IST during the holdout window 2026-05-01 -> 2026-08-31
REM (auto-extend to 2026-12-31 if n<40). Fetches Kite LTP for the F&O subset
REM of Banks + NBFC_HFC sectors and writes to opens/<date>.json.
REM
REM Spec: docs/superpowers/specs/2026-04-30-pdr-banks-nbfc-design.md

cd /d "C:\Users\Claude_Anka\askanka.com"
set PYTHONPATH=C:\Users\Claude_Anka\askanka.com;C:\Users\Claude_Anka\askanka.com\pipeline
C:\Python313\python.exe -X utf8 -m pipeline.research.h_2026_04_30_pdr_bnk_nbfc.forward_shadow capture-opens >> pipeline\logs\pdr_bnk_nbfc.log 2>&1
