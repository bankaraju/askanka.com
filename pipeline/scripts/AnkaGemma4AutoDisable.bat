@echo off
REM Anka Gemma 4 Pilot — hourly 09:00-22:00 IST guardrail check.
REM Spec: docs/superpowers/specs/2026-04-28-gemma4-pilot-design.md (§4.2)
REM Plan: docs/superpowers/plans/2026-04-28-gemma4-pilot.md (Task 18)
cd /d C:\Users\Claude_Anka\askanka.com
call pipeline\.venv\Scripts\activate.bat
python pipeline\scripts\gemma4_auto_disable_check.py >> opus\logs\gemma4_pilot.log 2>&1
