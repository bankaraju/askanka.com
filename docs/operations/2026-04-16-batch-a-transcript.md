# Batch A Transcript — Scheduler Debt Remediation 2026-04-16

**Plan:** `docs/superpowers/plans/2026-04-16-scheduler-debt-remediation.md`
**Spec:** `docs/superpowers/specs/2026-04-16-scheduler-debt-remediation-design.md`
**Branch:** `remediate/scheduler-debt-2026-04-16`

## Section A1 — Task audit

```
### Zombies (Documents\ path) -- count: 29
  AnkaARCBE2300 [\] Execute=C:\Users\Claude_Anka\Documents\askanka.com\pipeline\scripts\arcbe_scan.bat
  AnkaEOD1630 [\] Execute=C:\Users\Claude_Anka\Documents\askanka.com\pipeline\scripts\eod_track_record.bat
  AnkaIntraday0940 [\] Execute="C:\Users\Claude_Anka\Documents\askanka.com\pipeline\scripts\intraday_scan.bat"
  AnkaIntraday0955 [\] Execute="C:\Users\Claude_Anka\Documents\askanka.com\pipeline\scripts\intraday_scan.bat"
  AnkaIntraday1010 [\] Execute="C:\Users\Claude_Anka\Documents\askanka.com\pipeline\scripts\intraday_scan.bat"
  AnkaIntraday1025 [\] Execute="C:\Users\Claude_Anka\Documents\askanka.com\pipeline\scripts\intraday_scan.bat"
  AnkaIntraday1040 [\] Execute="C:\Users\Claude_Anka\Documents\askanka.com\pipeline\scripts\intraday_scan.bat"
  AnkaIntraday1055 [\] Execute="C:\Users\Claude_Anka\Documents\askanka.com\pipeline\scripts\intraday_scan.bat"
  AnkaIntraday1110 [\] Execute="C:\Users\Claude_Anka\Documents\askanka.com\pipeline\scripts\intraday_scan.bat"
  AnkaIntraday1125 [\] Execute="C:\Users\Claude_Anka\Documents\askanka.com\pipeline\scripts\intraday_scan.bat"
  AnkaIntraday1140 [\] Execute="C:\Users\Claude_Anka\Documents\askanka.com\pipeline\scripts\intraday_scan.bat"
  AnkaIntraday1155 [\] Execute="C:\Users\Claude_Anka\Documents\askanka.com\pipeline\scripts\intraday_scan.bat"
  AnkaIntraday1210 [\] Execute="C:\Users\Claude_Anka\Documents\askanka.com\pipeline\scripts\intraday_scan.bat"
  AnkaIntraday1225 [\] Execute="C:\Users\Claude_Anka\Documents\askanka.com\pipeline\scripts\intraday_scan.bat"
  AnkaIntraday1240 [\] Execute="C:\Users\Claude_Anka\Documents\askanka.com\pipeline\scripts\intraday_scan.bat"
  AnkaIntraday1255 [\] Execute="C:\Users\Claude_Anka\Documents\askanka.com\pipeline\scripts\intraday_scan.bat"
  AnkaIntraday1310 [\] Execute="C:\Users\Claude_Anka\Documents\askanka.com\pipeline\scripts\intraday_scan.bat"
  AnkaIntraday1325 [\] Execute="C:\Users\Claude_Anka\Documents\askanka.com\pipeline\scripts\intraday_scan.bat"
  AnkaIntraday1340 [\] Execute="C:\Users\Claude_Anka\Documents\askanka.com\pipeline\scripts\intraday_scan.bat"
  AnkaIntraday1355 [\] Execute="C:\Users\Claude_Anka\Documents\askanka.com\pipeline\scripts\intraday_scan.bat"
  AnkaIntraday1410 [\] Execute="C:\Users\Claude_Anka\Documents\askanka.com\pipeline\scripts\intraday_scan.bat"
  AnkaIntraday1425 [\] Execute="C:\Users\Claude_Anka\Documents\askanka.com\pipeline\scripts\intraday_scan.bat"
  AnkaIntraday1440 [\] Execute="C:\Users\Claude_Anka\Documents\askanka.com\pipeline\scripts\intraday_scan.bat"
  AnkaIntraday1455 [\] Execute="C:\Users\Claude_Anka\Documents\askanka.com\pipeline\scripts\intraday_scan.bat"
  AnkaIntraday1510 [\] Execute="C:\Users\Claude_Anka\Documents\askanka.com\pipeline\scripts\intraday_scan.bat"
  AnkaIntraday1525 [\] Execute="C:\Users\Claude_Anka\Documents\askanka.com\pipeline\scripts\intraday_scan.bat"
  AnkaSpreadStats [\] Execute="C:\Users\Claude_Anka\Documents\askanka.com\pipeline\scripts\weekly_stats.bat"
  AnkaWeeklyVideo [\] Execute=C:\Users\Claude_Anka\Documents\askanka.com\pipeline\scripts\weekly_video.bat
  OpenCapture [\Anka\] Execute=C:\Users\Claude_Anka\Documents\askanka.com\pipeline\scripts\open_capture.bat

### Quote-bug Execute strings -- count: 29
  AnkaCorrelationBreaks [\] Execute="C:\Users\Claude_Anka\askanka.com\pipeline\scripts\correlation_breaks.bat"
  AnkaGapPredictor [\] Execute="C:\Users\Claude_Anka\askanka.com\pipeline\scripts\gap_predictor.bat"
  AnkaIntraday0940 [\] Execute="C:\Users\Claude_Anka\Documents\askanka.com\pipeline\scripts\intraday_scan.bat"
  AnkaIntraday0955 [\] Execute="C:\Users\Claude_Anka\Documents\askanka.com\pipeline\scripts\intraday_scan.bat"
  AnkaIntraday1010 [\] Execute="C:\Users\Claude_Anka\Documents\askanka.com\pipeline\scripts\intraday_scan.bat"
  AnkaIntraday1025 [\] Execute="C:\Users\Claude_Anka\Documents\askanka.com\pipeline\scripts\intraday_scan.bat"
  AnkaIntraday1040 [\] Execute="C:\Users\Claude_Anka\Documents\askanka.com\pipeline\scripts\intraday_scan.bat"
  AnkaIntraday1055 [\] Execute="C:\Users\Claude_Anka\Documents\askanka.com\pipeline\scripts\intraday_scan.bat"
  AnkaIntraday1110 [\] Execute="C:\Users\Claude_Anka\Documents\askanka.com\pipeline\scripts\intraday_scan.bat"
  AnkaIntraday1125 [\] Execute="C:\Users\Claude_Anka\Documents\askanka.com\pipeline\scripts\intraday_scan.bat"
  AnkaIntraday1140 [\] Execute="C:\Users\Claude_Anka\Documents\askanka.com\pipeline\scripts\intraday_scan.bat"
  AnkaIntraday1155 [\] Execute="C:\Users\Claude_Anka\Documents\askanka.com\pipeline\scripts\intraday_scan.bat"
  AnkaIntraday1210 [\] Execute="C:\Users\Claude_Anka\Documents\askanka.com\pipeline\scripts\intraday_scan.bat"
  AnkaIntraday1225 [\] Execute="C:\Users\Claude_Anka\Documents\askanka.com\pipeline\scripts\intraday_scan.bat"
  AnkaIntraday1240 [\] Execute="C:\Users\Claude_Anka\Documents\askanka.com\pipeline\scripts\intraday_scan.bat"
  AnkaIntraday1255 [\] Execute="C:\Users\Claude_Anka\Documents\askanka.com\pipeline\scripts\intraday_scan.bat"
  AnkaIntraday1310 [\] Execute="C:\Users\Claude_Anka\Documents\askanka.com\pipeline\scripts\intraday_scan.bat"
  AnkaIntraday1325 [\] Execute="C:\Users\Claude_Anka\Documents\askanka.com\pipeline\scripts\intraday_scan.bat"
  AnkaIntraday1340 [\] Execute="C:\Users\Claude_Anka\Documents\askanka.com\pipeline\scripts\intraday_scan.bat"
  AnkaIntraday1355 [\] Execute="C:\Users\Claude_Anka\Documents\askanka.com\pipeline\scripts\intraday_scan.bat"
  AnkaIntraday1410 [\] Execute="C:\Users\Claude_Anka\Documents\askanka.com\pipeline\scripts\intraday_scan.bat"
  AnkaIntraday1425 [\] Execute="C:\Users\Claude_Anka\Documents\askanka.com\pipeline\scripts\intraday_scan.bat"
  AnkaIntraday1440 [\] Execute="C:\Users\Claude_Anka\Documents\askanka.com\pipeline\scripts\intraday_scan.bat"
  AnkaIntraday1455 [\] Execute="C:\Users\Claude_Anka\Documents\askanka.com\pipeline\scripts\intraday_scan.bat"
  AnkaIntraday1510 [\] Execute="C:\Users\Claude_Anka\Documents\askanka.com\pipeline\scripts\intraday_scan.bat"
  AnkaIntraday1525 [\] Execute="C:\Users\Claude_Anka\Documents\askanka.com\pipeline\scripts\intraday_scan.bat"
  AnkaPruneArticles [\] Execute="C:\Users\Claude_Anka\askanka.com\pipeline\scripts\prune_articles.bat"
  AnkaSpreadStats [\] Execute="C:\Users\Claude_Anka\Documents\askanka.com\pipeline\scripts\weekly_stats.bat"
  UpdateLibrary [\Microsoft\Windows\Windows Media Sharing\] Execute="%ProgramFiles%\Windows Media Player\wmpnscfg.exe"

### Never-ran tasks -- count: 38
  AnkaEODNews LastResult=267011 LastRun=11/30/1999 00:00:30 Execute=C:\Users\Claude_Anka\askanka.com\pipeline\scripts\overnight_news.bat
  AnkaGapPredictor LastResult=267011 LastRun=11/30/1999 00:00:30 Execute="C:\Users\Claude_Anka\askanka.com\pipeline\scripts\gap_predictor.bat"
  AnkaPruneArticles LastResult=267011 LastRun=11/30/1999 00:00:30 Execute="C:\Users\Claude_Anka\askanka.com\pipeline\scripts\prune_articles.bat"
  AnkaSpreadStats LastResult=267011 LastRun=11/30/1999 00:00:30 Execute="C:\Users\Claude_Anka\Documents\askanka.com\pipeline\scripts\weekly_stats.bat"
  AnkaWeeklyStats LastResult=267011 LastRun=11/30/1999 00:00:30 Execute=C:\Users\Claude_Anka\askanka.com\pipeline\scripts\weekly_stats.bat
  Office Performance Monitor LastResult=267011 LastRun=11/30/1999 00:00:30 Execute=C:\Program Files\Microsoft Office\root\VFS\ProgramFilesCommonX64\Microsoft Shared\Office16\operfmon.exe
  PolicyConverter LastResult=267011 LastRun=11/30/1999 00:00:30 Execute=%windir%\system32\appidpolicyconverter.exe
  VerifiedPublisherCertStoreCheck LastResult=267011 LastRun=11/30/1999 00:00:30 Execute=%windir%\system32\appidcertstorecheck.exe
  MareBackup LastResult=267011 LastRun=11/30/1999 00:00:30 Execute=%windir%\system32\compattelrunner.exe
  UninstallDeviceTask LastResult=267011 LastRun=11/30/1999 00:00:30 Execute=BthUdTask.exe
  SyspartRepair LastResult=267011 LastRun=11/30/1999 00:00:30 Execute=%windir%\system32\bcdboot.exe
  LicenseImdsIntegration LastResult=267011 LastRun=11/30/1999 00:00:30 Execute=%SystemRoot%\system32\fclip.exe
  Microsoft-Windows-DiskDiagnosticResolver LastResult=267011 LastRun=11/30/1999 00:00:30 Execute=%windir%\system32\DFDWiz.exe
  dusmtask LastResult=267011 LastRun=11/30/1999 00:00:30 Execute=%SystemRoot%\System32\dusmtask.exe
  WindowsActionDialog LastResult=267011 LastRun=11/30/1999 00:00:30 Execute=%windir%\System32\WindowsActionDialog.exe
  Cellular LastResult=267011 LastRun=11/30/1999 00:00:30 Execute=%windir%\system32\ProvTool.exe
  Retry LastResult=267011 LastRun=11/30/1999 00:00:30 Execute=%windir%\system32\ProvTool.exe
  RunOnReboot LastResult=267011 LastRun=11/30/1999 00:00:30 Execute=%windir%\system32\ProvTool.exe
  MNO Metadata Parser LastResult=267011 LastRun=11/30/1999 00:00:30 Execute=%SystemRoot%\System32\MbaeParserTask.exe
  GatherNetworkInfo LastResult=267011 LastRun=11/30/1999 00:00:30 Execute=%windir%\system32\gatherNetworkInfo.vbs
  WiFiTask LastResult=267011 LastRun=11/30/1999 00:00:30 Execute=%SystemRoot%\System32\WiFiTask.exe
  Sysprep Generalize Drivers LastResult=267011 LastRun=11/30/1999 00:00:30 Execute=%SystemRoot%\System32\drvinst.exe
  EduPrintProv LastResult=267011 LastRun=11/30/1999 00:00:30 Execute=%windir%\system32\eduprintprov.exe
  Account Cleanup LastResult=267011 LastRun=11/30/1999 00:00:30 Execute=%windir%\System32\rundll32.exe
  FamilySafetyMonitor LastResult=267011 LastRun=11/30/1999 00:00:30 Execute=%windir%\System32\wpcmon.exe
  SpaceAgentTask LastResult=267011 LastRun=11/30/1999 00:00:30 Execute=%windir%\system32\SpaceAgent.exe
  SpaceManagerTask LastResult=267011 LastRun=11/30/1999 00:00:30 Execute=%windir%\system32\spaceman.exe
  HeadsetButtonPress LastResult=267011 LastRun=11/30/1999 00:00:30 Execute=%windir%\system32\speech_onecore\common\SpeechRuntime.exe
  Storage Tiers Optimization LastResult=267011 LastRun=11/30/1999 00:00:30 Execute=%windir%\system32\defrag.exe
  LicenseAcquisition LastResult=267011 LastRun=11/30/1999 00:00:30 Execute=%SystemRoot%\system32\ClipRenew.exe
  RunUpdateNotificationMgr LastResult=267011 LastRun=11/30/1999 00:00:30 Execute=%windir%\System32\UNP\UpdateNotificationMgr.exe
  UPnPHostConfig LastResult=267011 LastRun=11/30/1999 00:00:30 Execute=sc.exe
  BfeOnServiceStartTypeChange LastResult=267011 LastRun=11/30/1999 00:00:30 Execute=%windir%\system32\rundll32.exe
  UpdateLibrary LastResult=267011 LastRun=11/30/1999 00:00:30 Execute="%ProgramFiles%\Windows Media Player\wmpnscfg.exe"
  Automatic-Device-Join LastResult=267011 LastRun=11/30/1999 00:00:30 Execute=%SystemRoot%\System32\dsregcmd.exe
  Recovery-Check LastResult=267011 LastRun=11/30/1999 00:00:30 Execute=%SystemRoot%\System32\dsregcmd.exe
  NotificationTask LastResult=267011 LastRun=11/30/1999 00:00:30 Execute=%SystemRoot%\System32\WiFiTask.exe
  XblGameSaveTask LastResult=267011 LastRun=11/30/1999 00:00:30 Execute=%windir%\System32\XblGameSaveTask.exe

### All unique affected task names (for XML backup)
Account Cleanup
AnkaARCBE2300
AnkaCorrelationBreaks
AnkaEOD1630
AnkaEODNews
AnkaGapPredictor
AnkaIntraday0940
AnkaIntraday0955
AnkaIntraday1010
AnkaIntraday1025
AnkaIntraday1040
AnkaIntraday1055
AnkaIntraday1110
AnkaIntraday1125
AnkaIntraday1140
AnkaIntraday1155
AnkaIntraday1210
AnkaIntraday1225
AnkaIntraday1240
AnkaIntraday1255
AnkaIntraday1310
AnkaIntraday1325
AnkaIntraday1340
AnkaIntraday1355
AnkaIntraday1410
AnkaIntraday1425
AnkaIntraday1440
AnkaIntraday1455
AnkaIntraday1510
AnkaIntraday1525
AnkaPruneArticles
AnkaSpreadStats
AnkaWeeklyStats
AnkaWeeklyVideo
Automatic-Device-Join
BfeOnServiceStartTypeChange
Cellular
dusmtask
EduPrintProv
FamilySafetyMonitor
GatherNetworkInfo
HeadsetButtonPress
LicenseAcquisition
LicenseImdsIntegration
MareBackup
Microsoft-Windows-DiskDiagnosticResolver
MNO Metadata Parser
NotificationTask
Office Performance Monitor
OpenCapture
PolicyConverter
Recovery-Check
Retry
RunOnReboot
RunUpdateNotificationMgr
SpaceAgentTask
SpaceManagerTask
Storage Tiers Optimization
SyspartRepair
Sysprep Generalize Drivers
UninstallDeviceTask
UpdateLibrary
UPnPHostConfig
VerifiedPublisherCertStoreCheck
WiFiTask
WindowsActionDialog
XblGameSaveTask

TOTAL_AFFECTED=67

```

## Section A2 — XML backups

<populated by Task 3>

## Section A3 — Data snapshots

<populated by Task 4>

## Section A4 — Migration spec re-read gate

<populated by Task 5>

## Section A5 — Dry-run output

<populated by Task 6>
