@echo off
REM Anka Gemma 4 Pilot — daily 22:00 IST report card aggregator.
REM Spec: docs/superpowers/specs/2026-04-28-gemma4-pilot-design.md
REM Plan: docs/superpowers/plans/2026-04-28-gemma4-pilot.md (Task 17)
cd /d C:\Users\Claude_Anka\askanka.com
call pipeline\.venv\Scripts\activate.bat
python pipeline\scripts\gemma4_daily_report.py >> opus\logs\gemma4_pilot.log 2>&1
