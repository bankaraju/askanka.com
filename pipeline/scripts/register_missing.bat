@echo off
echo Registering missing scheduled tasks...

set SCRIPTS=C:\Users\Claude_Anka\askanka.com\pipeline\scripts

schtasks /create /tn "AnkaDailyArticles" /tr "%SCRIPTS%\daily_articles.bat" /sc DAILY /st 04:30 /f
schtasks /create /tn "AnkaShadow" /tr "%SCRIPTS%\daily_shadow.bat" /sc DAILY /st 04:30 /f
schtasks /create /tn "AnkaWeeklyVideo" /tr "%SCRIPTS%\weekly_video.bat" /sc WEEKLY /d SAT /st 11:00 /f

echo.
echo Verifying...
schtasks /query /tn "AnkaDailyArticles" /fo TABLE
schtasks /query /tn "AnkaShadow" /fo TABLE
schtasks /query /tn "AnkaWeeklyVideo" /fo TABLE

echo Done!
pause
