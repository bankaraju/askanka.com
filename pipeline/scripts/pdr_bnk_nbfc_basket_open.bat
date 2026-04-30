@echo off
REM PDR-BNK-NBFC (H-2026-04-30-PDR-BNK-NBFC) basket-open leg.
REM Runs daily at 11:00 IST during the holdout window. Computes Banks vs
REM NBFC_HFC sector-mean divergence Z over rolling 60-day panel; if |Z|>1.0,
REM opens 4-leg basket (LONG laggard top-2 by liquidity, SHORT leader top-2);
REM writes diagnostic row regardless. Idempotent on basket_id.
REM
REM Spec: docs/superpowers/specs/2026-04-30-pdr-banks-nbfc-design.md

cd /d "C:\Users\Claude_Anka\askanka.com"
set PYTHONPATH=C:\Users\Claude_Anka\askanka.com;C:\Users\Claude_Anka\askanka.com\pipeline
C:\Python313\python.exe -X utf8 -m pipeline.research.h_2026_04_30_pdr_bnk_nbfc.forward_shadow basket-open >> pipeline\logs\pdr_bnk_nbfc.log 2>&1
