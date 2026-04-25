@echo off
REM Earnings calendar daily fetch — 08:00 IST.
REM Source: IndianAPI /corporate_actions per F&O ticker.
REM Feeds H-2026-04-25-001 earnings-decoupling pre-registered hypothesis.
REM Data validation policy §15: freshness contract is cadence x 1.5 grace = 36h.
cd /d C:\Users\Claude_Anka\askanka.com
python -m pipeline.scripts.backfill_earnings_calendar >> C:\Users\Claude_Anka\askanka.com\pipeline\logs\earnings_calendar_fetch.log 2>&1
