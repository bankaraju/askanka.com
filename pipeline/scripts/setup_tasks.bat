@echo off
echo ================================================================
echo   ANKA RESEARCH — Scheduled Tasks Setup (Unified Repo)
echo   Path: C:\Users\Claude_Anka\askanka.com\pipeline\scripts
echo ================================================================
echo.

set SCRIPTS=C:\Users\Claude_Anka\askanka.com\pipeline\scripts

REM ── OVERNIGHT (04:30-05:00) ──
schtasks /create /tn "AnkaDailyDump" /tr "%SCRIPTS%\daily_dump.bat" /sc WEEKLY /d MON,TUE,WED,THU,FRI /st 04:30 /f
schtasks /create /tn "AnkaDailyArticles" /tr "%SCRIPTS%\daily_articles.bat" /sc DAILY /st 04:45 /f

REM ── PRE-MARKET (09:00-09:25) ──
schtasks /create /tn "AnkaRefreshKite" /tr "%SCRIPTS%\refresh_kite.bat" /sc WEEKLY /d MON,TUE,WED,THU,FRI /st 09:00 /f
schtasks /create /tn "AnkaPreMarket" /tr "%SCRIPTS%\premarket.bat" /sc WEEKLY /d MON,TUE,WED,THU,FRI /st 09:15 /f
schtasks /create /tn "AnkaMorningScan" /tr "%SCRIPTS%\morning_scan.bat" /sc WEEKLY /d MON,TUE,WED,THU,FRI /st 09:25 /f
schtasks /create /tn "AnkaPhaseCShadowOpen" /tr "%SCRIPTS%\phase_c_shadow_open.bat" /sc WEEKLY /d MON,TUE,WED,THU,FRI /st 09:25 /f

REM ── INTRADAY (09:30-15:30 every 15 min) ──
schtasks /create /tn "AnkaIntraday0930" /tr "%SCRIPTS%\intraday_scan.bat" /sc WEEKLY /d MON,TUE,WED,THU,FRI /st 09:30 /f
schtasks /create /tn "AnkaIntraday0945" /tr "%SCRIPTS%\intraday_scan.bat" /sc WEEKLY /d MON,TUE,WED,THU,FRI /st 09:45 /f
schtasks /create /tn "AnkaIntraday1000" /tr "%SCRIPTS%\intraday_scan.bat" /sc WEEKLY /d MON,TUE,WED,THU,FRI /st 10:00 /f
schtasks /create /tn "AnkaIntraday1015" /tr "%SCRIPTS%\intraday_scan.bat" /sc WEEKLY /d MON,TUE,WED,THU,FRI /st 10:15 /f
schtasks /create /tn "AnkaIntraday1030" /tr "%SCRIPTS%\intraday_scan.bat" /sc WEEKLY /d MON,TUE,WED,THU,FRI /st 10:30 /f
schtasks /create /tn "AnkaIntraday1045" /tr "%SCRIPTS%\intraday_scan.bat" /sc WEEKLY /d MON,TUE,WED,THU,FRI /st 10:45 /f
schtasks /create /tn "AnkaIntraday1100" /tr "%SCRIPTS%\intraday_scan.bat" /sc WEEKLY /d MON,TUE,WED,THU,FRI /st 11:00 /f
schtasks /create /tn "AnkaIntraday1115" /tr "%SCRIPTS%\intraday_scan.bat" /sc WEEKLY /d MON,TUE,WED,THU,FRI /st 11:15 /f
schtasks /create /tn "AnkaIntraday1130" /tr "%SCRIPTS%\intraday_scan.bat" /sc WEEKLY /d MON,TUE,WED,THU,FRI /st 11:30 /f
schtasks /create /tn "AnkaIntraday1145" /tr "%SCRIPTS%\intraday_scan.bat" /sc WEEKLY /d MON,TUE,WED,THU,FRI /st 11:45 /f
schtasks /create /tn "AnkaIntraday1200" /tr "%SCRIPTS%\intraday_scan.bat" /sc WEEKLY /d MON,TUE,WED,THU,FRI /st 12:00 /f
schtasks /create /tn "AnkaIntraday1215" /tr "%SCRIPTS%\intraday_scan.bat" /sc WEEKLY /d MON,TUE,WED,THU,FRI /st 12:15 /f
schtasks /create /tn "AnkaIntraday1230" /tr "%SCRIPTS%\intraday_scan.bat" /sc WEEKLY /d MON,TUE,WED,THU,FRI /st 12:30 /f
schtasks /create /tn "AnkaIntraday1245" /tr "%SCRIPTS%\intraday_scan.bat" /sc WEEKLY /d MON,TUE,WED,THU,FRI /st 12:45 /f
schtasks /create /tn "AnkaIntraday1300" /tr "%SCRIPTS%\intraday_scan.bat" /sc WEEKLY /d MON,TUE,WED,THU,FRI /st 13:00 /f
schtasks /create /tn "AnkaIntraday1315" /tr "%SCRIPTS%\intraday_scan.bat" /sc WEEKLY /d MON,TUE,WED,THU,FRI /st 13:15 /f
schtasks /create /tn "AnkaIntraday1330" /tr "%SCRIPTS%\intraday_scan.bat" /sc WEEKLY /d MON,TUE,WED,THU,FRI /st 13:30 /f
schtasks /create /tn "AnkaIntraday1345" /tr "%SCRIPTS%\intraday_scan.bat" /sc WEEKLY /d MON,TUE,WED,THU,FRI /st 13:45 /f
schtasks /create /tn "AnkaIntraday1400" /tr "%SCRIPTS%\intraday_scan.bat" /sc WEEKLY /d MON,TUE,WED,THU,FRI /st 14:00 /f
schtasks /create /tn "AnkaIntraday1415" /tr "%SCRIPTS%\intraday_scan.bat" /sc WEEKLY /d MON,TUE,WED,THU,FRI /st 14:15 /f
schtasks /create /tn "AnkaIntraday1430" /tr "%SCRIPTS%\intraday_scan.bat" /sc WEEKLY /d MON,TUE,WED,THU,FRI /st 14:30 /f
schtasks /create /tn "AnkaPhaseCShadowClose" /tr "%SCRIPTS%\phase_c_shadow_close.bat" /sc WEEKLY /d MON,TUE,WED,THU,FRI /st 14:30 /f
schtasks /create /tn "AnkaIntraday1445" /tr "%SCRIPTS%\intraday_scan.bat" /sc WEEKLY /d MON,TUE,WED,THU,FRI /st 14:45 /f
schtasks /create /tn "AnkaIntraday1500" /tr "%SCRIPTS%\intraday_scan.bat" /sc WEEKLY /d MON,TUE,WED,THU,FRI /st 15:00 /f
schtasks /create /tn "AnkaIntraday1515" /tr "%SCRIPTS%\intraday_scan.bat" /sc WEEKLY /d MON,TUE,WED,THU,FRI /st 15:15 /f
schtasks /create /tn "AnkaIntraday1530" /tr "%SCRIPTS%\intraday_scan.bat" /sc WEEKLY /d MON,TUE,WED,THU,FRI /st 15:30 /f

REM ── SIGNAL GENERATION (same 15-min slots) ──
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

REM ── POST-MARKET (15:30-16:30) ──
schtasks /create /tn "AnkaOpenCapture" /tr "%SCRIPTS%\open_capture.bat" /sc WEEKLY /d MON,TUE,WED,THU,FRI /st 15:35 /f
schtasks /create /tn "AnkaEODReview" /tr "%SCRIPTS%\eod_review.bat" /sc WEEKLY /d MON,TUE,WED,THU,FRI /st 16:00 /f
schtasks /create /tn "AnkaEODTrackRecord" /tr "%SCRIPTS%\eod_track_record.bat" /sc WEEKLY /d MON,TUE,WED,THU,FRI /st 16:15 /f

REM ── WEEKLY ──
schtasks /create /tn "AnkaWeeklyAgg" /tr "%SCRIPTS%\weekly_agg.bat" /sc WEEKLY /d SAT /st 09:00 /f
schtasks /create /tn "AnkaWeeklyReport" /tr "%SCRIPTS%\weekly_report.bat" /sc WEEKLY /d SAT /st 10:00 /f
schtasks /create /tn "AnkaWeeklyStats" /tr "%SCRIPTS%\weekly_stats.bat" /sc WEEKLY /d SUN /st 22:00 /f

echo.
echo ================================================================
echo   ALL TASKS CREATED
echo   Total: ~55 scheduled tasks
echo   Path: %SCRIPTS%
echo   Run "schtasks /query /fo TABLE" to verify
echo ================================================================
pause
