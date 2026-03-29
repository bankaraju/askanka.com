@echo off
echo ============================================
echo Anka Research — Setting Up Scheduled Tasks
echo ============================================

echo.
echo [1/2] Creating DAILY price + fundamentals dump (6:30 AM IST / Mon-Sat)
echo     NOTE: Saturday dump captures Friday US close (US closes 2:30 AM IST Sat)
schtasks /create /tn "Anka Research - Daily Data Dump" /tr "python C:\Users\Claude_Anka\Documents\askanka.com\pipeline\run_daily.py" /sc weekly /d MON,TUE,WED,THU,FRI,SAT /st 06:30 /f
if %errorlevel% equ 0 (
    echo     SUCCESS: Daily dump scheduled for 6:30 AM weekdays
) else (
    echo     FAILED: Could not create daily task
)

echo.
echo [2/2] Creating WEEKLY aggregator (Saturday 9:00 AM IST)
schtasks /create /tn "Anka Research - Weekly Aggregator" /tr "python C:\Users\Claude_Anka\Documents\askanka.com\pipeline\weekly_aggregator.py" /sc weekly /d SAT /st 09:00 /f
if %errorlevel% equ 0 (
    echo     SUCCESS: Weekly aggregation scheduled for Saturday 9:00 AM
) else (
    echo     FAILED: Could not create weekly task
)

echo.
echo ============================================
echo Verifying scheduled tasks...
echo ============================================
schtasks /query /tn "Anka Research - Daily Data Dump" /fo list 2>nul
echo.
schtasks /query /tn "Anka Research - Weekly Aggregator" /fo list 2>nul
echo.
echo DONE. Tasks will run automatically.
echo Make sure your EODHD API key is set in pipeline\.env
pause
