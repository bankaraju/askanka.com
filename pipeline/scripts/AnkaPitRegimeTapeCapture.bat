@echo off
REM PIT regime tape — daily forward-feed capture, 05:00 IST.
REM Reads pipeline/data/today_regime.json (written by AnkaETFSignal at 04:45)
REM and freezes it as pipeline/data/pit_regime_tape/forward/<date>.json.
REM Load-bearing for NEUTRAL_OVERLAY family (H-2026-04-28-001..004).
REM Audit: docs/superpowers/specs/2026-04-28-pit-regime-tape-data-source-audit.md
cd /d C:\Users\Claude_Anka\askanka.com
python -m pipeline.scripts.capture_pit_regime_tape_forward >> C:\Users\Claude_Anka\askanka.com\pipeline\logs\pit_regime_tape_capture.log 2>&1
