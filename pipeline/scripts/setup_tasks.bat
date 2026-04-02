@echo off
echo Setting up Anka Research scheduled tasks...

set SCRIPTS=C:\Users\Claude_Anka\Documents\askanka.com\pipeline\scripts

REM Pre-market briefing at 8:27 AM (weekdays)
schtasks /create /tn "AnkaPreMarket" /tr "%SCRIPTS%\premarket.bat" /sc WEEKLY /d MON,TUE,WED,THU,FRI /st 08:27 /f

REM Open price capture at 9:22 AM (for midday leaderboard)
schtasks /create /tn "AnkaOpenCapture" /tr "%SCRIPTS%\open_capture.bat" /sc WEEKLY /d MON,TUE,WED,THU,FRI /st 09:22 /f

REM Signal checks every ~30 min from 9:42 to 15:12
schtasks /create /tn "AnkaSignal0942" /tr "%SCRIPTS%\signals.bat" /sc WEEKLY /d MON,TUE,WED,THU,FRI /st 09:42 /f
schtasks /create /tn "AnkaSignal1012" /tr "%SCRIPTS%\signals.bat" /sc WEEKLY /d MON,TUE,WED,THU,FRI /st 10:12 /f
schtasks /create /tn "AnkaSignal1042" /tr "%SCRIPTS%\signals.bat" /sc WEEKLY /d MON,TUE,WED,THU,FRI /st 10:42 /f
schtasks /create /tn "AnkaSignal1112" /tr "%SCRIPTS%\signals.bat" /sc WEEKLY /d MON,TUE,WED,THU,FRI /st 11:12 /f
schtasks /create /tn "AnkaSignal1142" /tr "%SCRIPTS%\signals.bat" /sc WEEKLY /d MON,TUE,WED,THU,FRI /st 11:42 /f
schtasks /create /tn "AnkaSignal1212" /tr "%SCRIPTS%\signals.bat" /sc WEEKLY /d MON,TUE,WED,THU,FRI /st 12:12 /f
schtasks /create /tn "AnkaSignal1242" /tr "%SCRIPTS%\signals.bat" /sc WEEKLY /d MON,TUE,WED,THU,FRI /st 12:42 /f
schtasks /create /tn "AnkaSignal1312" /tr "%SCRIPTS%\signals.bat" /sc WEEKLY /d MON,TUE,WED,THU,FRI /st 13:12 /f
schtasks /create /tn "AnkaSignal1342" /tr "%SCRIPTS%\signals.bat" /sc WEEKLY /d MON,TUE,WED,THU,FRI /st 13:42 /f
schtasks /create /tn "AnkaSignal1412" /tr "%SCRIPTS%\signals.bat" /sc WEEKLY /d MON,TUE,WED,THU,FRI /st 14:12 /f
schtasks /create /tn "AnkaSignal1442" /tr "%SCRIPTS%\signals.bat" /sc WEEKLY /d MON,TUE,WED,THU,FRI /st 14:42 /f
schtasks /create /tn "AnkaSignal1512" /tr "%SCRIPTS%\signals.bat" /sc WEEKLY /d MON,TUE,WED,THU,FRI /st 15:12 /f

REM EOD review at 3:47 PM
schtasks /create /tn "AnkaEODReview" /tr "%SCRIPTS%\eod_review.bat" /sc WEEKLY /d MON,TUE,WED,THU,FRI /st 15:47 /f

REM Daily data dump at 4:30 PM (after market close)
schtasks /create /tn "AnkaDailyDump" /tr "%SCRIPTS%\daily_dump.bat" /sc WEEKLY /d MON,TUE,WED,THU,FRI /st 16:30 /f

REM Weekly aggregation Saturday 9:00 AM (aggregates Mon-Fri data into weekly JSON)
schtasks /create /tn "AnkaWeeklyAgg" /tr "%SCRIPTS%\weekly_agg.bat" /sc WEEKLY /d SAT /st 09:00 /f

REM Weekly HTML report Saturday 10:00 AM (converts JSON to HTML, deploys to askanka.com)
schtasks /create /tn "AnkaWeeklyReport" /tr "%SCRIPTS%\weekly_report.bat" /sc WEEKLY /d SAT /st 10:00 /f

echo.
echo Done! All 20 tasks created.
echo Run "schtasks /query /fo TABLE" and grep for Anka to verify.
pause
