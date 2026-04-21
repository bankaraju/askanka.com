@echo off
REM Phase C F3 live shadow ledger — CLOSE leg
REM Runs daily at 14:30 IST — mechanical time-stop per the H1 backtest.
REM Fetches live Kite LTP for all symbols still OPEN in the ledger,
REM transitions OPEN -> CLOSED with exit_reason = TIME_STOP, and writes
REM realized net P&L via pipeline.research.phase_c_backtest.cost_model.

cd /d "C:\Users\Claude_Anka\askanka.com"
set PYTHONPATH=C:\Users\Claude_Anka\askanka.com;C:\Users\Claude_Anka\askanka.com\pipeline
C:\Python313\python.exe -X utf8 -m pipeline.phase_c_shadow close >> pipeline\logs\phase_c_shadow.log 2>&1
