@echo off
REM NSE PIT (insider trading) disclosures daily fetch — 18:30 IST.
REM Source: nseindia.com/api/corporates-pit (free, session-cookie auth).
REM Pulls last 7 days each run because PIT filings often arrive 1-3 days
REM after the actual trade date.
REM Backfill (one-shot) lives at 2021-01-01 → 2026-04-25 in pipeline/data/insider_trades/.
cd /d C:\Users\Claude_Anka\askanka.com
python -m pipeline.insider_trades >> C:\Users\Claude_Anka\askanka.com\pipeline\logs\insider_trades.log 2>&1
