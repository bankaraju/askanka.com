@echo off
echo Setting up Anka Research scheduled tasks...

set SCRIPTS=C:\Users\Claude_Anka\Documents\askanka.com\pipeline\scripts

REM Pre-market briefing at 8:27 AM
schtasks /create /tn "Anka\PreMarketBriefing" /tr "%SCRIPTS%\premarket.bat" /sc daily /st 08:27 /d MON,TUE,WED,THU,FRI /f

REM Signal checks every ~30 min from 9:42 to 15:12
schtasks /create /tn "Anka\Signal0942" /tr "%SCRIPTS%\signals.bat" /sc daily /st 09:42 /d MON,TUE,WED,THU,FRI /f
schtasks /create /tn "Anka\Signal1012" /tr "%SCRIPTS%\signals.bat" /sc daily /st 10:12 /d MON,TUE,WED,THU,FRI /f
schtasks /create /tn "Anka\Signal1042" /tr "%SCRIPTS%\signals.bat" /sc daily /st 10:42 /d MON,TUE,WED,THU,FRI /f
schtasks /create /tn "Anka\Signal1112" /tr "%SCRIPTS%\signals.bat" /sc daily /st 11:12 /d MON,TUE,WED,THU,FRI /f
schtasks /create /tn "Anka\Signal1142" /tr "%SCRIPTS%\signals.bat" /sc daily /st 11:42 /d MON,TUE,WED,THU,FRI /f
schtasks /create /tn "Anka\Signal1212" /tr "%SCRIPTS%\signals.bat" /sc daily /st 12:12 /d MON,TUE,WED,THU,FRI /f
schtasks /create /tn "Anka\Signal1242" /tr "%SCRIPTS%\signals.bat" /sc daily /st 12:42 /d MON,TUE,WED,THU,FRI /f
schtasks /create /tn "Anka\Signal1312" /tr "%SCRIPTS%\signals.bat" /sc daily /st 13:12 /d MON,TUE,WED,THU,FRI /f
schtasks /create /tn "Anka\Signal1342" /tr "%SCRIPTS%\signals.bat" /sc daily /st 13:42 /d MON,TUE,WED,THU,FRI /f
schtasks /create /tn "Anka\Signal1412" /tr "%SCRIPTS%\signals.bat" /sc daily /st 14:12 /d MON,TUE,WED,THU,FRI /f
schtasks /create /tn "Anka\Signal1442" /tr "%SCRIPTS%\signals.bat" /sc daily /st 14:42 /d MON,TUE,WED,THU,FRI /f
schtasks /create /tn "Anka\Signal1512" /tr "%SCRIPTS%\signals.bat" /sc daily /st 15:12 /d MON,TUE,WED,THU,FRI /f

REM EOD review at 3:47 PM
schtasks /create /tn "Anka\EODReview" /tr "%SCRIPTS%\eod_review.bat" /sc daily /st 15:47 /d MON,TUE,WED,THU,FRI /f

echo.
echo Done! All 15 tasks created.
echo Run "schtasks /query /tn Anka\" to verify.
pause
