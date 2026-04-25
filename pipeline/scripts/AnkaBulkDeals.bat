@echo off
REM NSE bulk + block deals daily fetch — 16:30 IST.
REM Source: nsearchives.nseindia.com/content/equities/{bulk,block}.csv (rolling-today CSVs).
REM Forward-only collection — no historical backfill exists from NSE direct.
REM Feeds the forensic card v2 bulk_deal_T channel + future deep-investigation hooks.
cd /d C:\Users\Claude_Anka\askanka.com
python -m pipeline.bulk_deals >> C:\Users\Claude_Anka\askanka.com\pipeline\logs\bulk_deals.log 2>&1
