@echo off
REM ETF Engine V3 CURATED — Weekly Karpathy Reoptimization
REM Replaces etf_reoptimize.bat (v2). Cycle-3 verdict 2026-04-26: v3 CURATED-30
REM is the only configuration with positive pooled edge under honest rolling
REM walk-forward (53.55%% acc, +1.83pp edge over majority baseline, P>base 78.7%%).
REM See pipeline/data/research/etf_v3/2026-04-26-etf-v3-verdict.md
REM
REM Scheduled: Saturday 22:00 IST via AnkaETFv3CuratedReoptimize
REM Calibration window: 2024-04-23 onwards (signal distribution -> zone bands)
REM Refit cadence: governed by AnkaETFv3CuratedSignal job; this only refits weekly
cd /d C:\Users\Claude_Anka\askanka.com
python -X utf8 -m pipeline.autoresearch.etf_v3_curated_reoptimize >> pipeline\logs\etf_v3_curated_reoptimize.log 2>&1
