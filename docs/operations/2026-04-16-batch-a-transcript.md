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

```
Backing up 67 tasks to C:\Users\Claude_Anka\askanka.com\pipeline\backups\scheduled_tasks\2026-04-16
  OK   Account Cleanup -> Account_Cleanup.xml
  OK   AnkaARCBE2300 -> AnkaARCBE2300.xml
  OK   AnkaCorrelationBreaks -> AnkaCorrelationBreaks.xml
  OK   AnkaEOD1630 -> AnkaEOD1630.xml
  OK   AnkaEODNews -> AnkaEODNews.xml
  OK   AnkaGapPredictor -> AnkaGapPredictor.xml
  OK   AnkaIntraday0940 -> AnkaIntraday0940.xml
  OK   AnkaIntraday0955 -> AnkaIntraday0955.xml
  OK   AnkaIntraday1010 -> AnkaIntraday1010.xml
  OK   AnkaIntraday1025 -> AnkaIntraday1025.xml
  OK   AnkaIntraday1040 -> AnkaIntraday1040.xml
  OK   AnkaIntraday1055 -> AnkaIntraday1055.xml
  OK   AnkaIntraday1110 -> AnkaIntraday1110.xml
  OK   AnkaIntraday1125 -> AnkaIntraday1125.xml
  OK   AnkaIntraday1140 -> AnkaIntraday1140.xml
  OK   AnkaIntraday1155 -> AnkaIntraday1155.xml
  OK   AnkaIntraday1210 -> AnkaIntraday1210.xml
  OK   AnkaIntraday1225 -> AnkaIntraday1225.xml
  OK   AnkaIntraday1240 -> AnkaIntraday1240.xml
  OK   AnkaIntraday1255 -> AnkaIntraday1255.xml
  OK   AnkaIntraday1310 -> AnkaIntraday1310.xml
  OK   AnkaIntraday1325 -> AnkaIntraday1325.xml
  OK   AnkaIntraday1340 -> AnkaIntraday1340.xml
  OK   AnkaIntraday1355 -> AnkaIntraday1355.xml
  OK   AnkaIntraday1410 -> AnkaIntraday1410.xml
  OK   AnkaIntraday1425 -> AnkaIntraday1425.xml
  OK   AnkaIntraday1440 -> AnkaIntraday1440.xml
  OK   AnkaIntraday1455 -> AnkaIntraday1455.xml
  OK   AnkaIntraday1510 -> AnkaIntraday1510.xml
  OK   AnkaIntraday1525 -> AnkaIntraday1525.xml
  OK   AnkaPruneArticles -> AnkaPruneArticles.xml
  OK   AnkaSpreadStats -> AnkaSpreadStats.xml
  OK   AnkaWeeklyStats -> AnkaWeeklyStats.xml
  OK   AnkaWeeklyVideo -> AnkaWeeklyVideo.xml
  OK   Automatic-Device-Join -> Automatic-Device-Join.xml
  OK   BfeOnServiceStartTypeChange -> BfeOnServiceStartTypeChange.xml
  OK   Cellular -> Cellular.xml
  OK   dusmtask -> dusmtask.xml
  OK   EduPrintProv -> EduPrintProv.xml
  OK   FamilySafetyMonitor -> FamilySafetyMonitor.xml
  OK   GatherNetworkInfo -> GatherNetworkInfo.xml
  OK   HeadsetButtonPress -> HeadsetButtonPress.xml
  OK   LicenseAcquisition -> LicenseAcquisition.xml
  OK   LicenseImdsIntegration -> LicenseImdsIntegration.xml
  OK   MareBackup -> MareBackup.xml
  OK   Microsoft-Windows-DiskDiagnosticResolver -> Microsoft-Windows-DiskDiagnosticResolver.xml
  OK   MNO Metadata Parser -> MNO_Metadata_Parser.xml
  OK   NotificationTask -> NotificationTask.xml
  OK   Office Performance Monitor -> Office_Performance_Monitor.xml
  OK   OpenCapture -> OpenCapture.xml
  OK   PolicyConverter -> PolicyConverter.xml
  OK   Recovery-Check -> Recovery-Check.xml
  OK   Retry -> Retry.xml
  OK   RunOnReboot -> RunOnReboot.xml
  OK   RunUpdateNotificationMgr -> RunUpdateNotificationMgr.xml
  OK   SpaceAgentTask -> SpaceAgentTask.xml
  OK   SpaceManagerTask -> SpaceManagerTask.xml
  OK   Storage Tiers Optimization -> Storage_Tiers_Optimization.xml
  OK   SyspartRepair -> SyspartRepair.xml
  OK   Sysprep Generalize Drivers -> Sysprep_Generalize_Drivers.xml
  OK   UninstallDeviceTask -> UninstallDeviceTask.xml
  OK   UpdateLibrary -> UpdateLibrary.xml
  OK   UPnPHostConfig -> UPnPHostConfig.xml
  OK   VerifiedPublisherCertStoreCheck -> VerifiedPublisherCertStoreCheck.xml
  OK   WiFiTask -> WiFiTask.xml
  OK   WindowsActionDialog -> WindowsActionDialog.xml
  OK   XblGameSaveTask -> XblGameSaveTask.xml

Total: 67 OK, 0 FAIL

```

## Section A3 — Data snapshots

```
-rw-r--r-- 1 Claude_Anka 197121  64902 Apr 14 15:38 pipeline/backups/data_snapshots/2026-04-16/correlation_history.json
-rw-r--r-- 1 Claude_Anka 197121  10710 Apr 14 15:38 pipeline/backups/data_snapshots/2026-04-16/correlation_report_2026-04-03.json
-rw-r--r-- 1 Claude_Anka 197121  16332 Apr 14 15:38 pipeline/backups/data_snapshots/2026-04-16/expiry_divergence_log.json
-rw-r--r-- 1 Claude_Anka 197121   1033 Apr 14 15:38 pipeline/backups/data_snapshots/2026-04-16/fragility_model.json
-rw-r--r-- 1 Claude_Anka 197121   6841 Apr 14 15:38 pipeline/backups/data_snapshots/2026-04-16/fragility_scores.json
-rw-r--r-- 1 Claude_Anka 197121     51 Apr 14 15:38 pipeline/backups/data_snapshots/2026-04-16/gamma_generation.json
-rw-r--r-- 1 Claude_Anka 197121    231 Apr 14 15:38 pipeline/backups/data_snapshots/2026-04-16/gamma_result.json
-rw-r--r-- 1 Claude_Anka 197121    407 Apr 14 15:38 pipeline/backups/data_snapshots/2026-04-16/gex_history.json
-rw-r--r-- 1 Claude_Anka 197121  16937 Apr 14 15:38 pipeline/backups/data_snapshots/2026-04-16/historical_events.json
-rw-r--r-- 1 Claude_Anka 197121     71 Apr 14 15:38 pipeline/backups/data_snapshots/2026-04-16/macro_trigger_state.json
-rw-r--r-- 1 Claude_Anka 197121   1025 Apr 14 15:38 pipeline/backups/data_snapshots/2026-04-16/ml_performance.json
-rw-r--r-- 1 Claude_Anka 197121   8512 Apr 14 15:38 pipeline/backups/data_snapshots/2026-04-16/msi_history.json
-rw-r--r-- 1 Claude_Anka 197121  19151 Apr 14 15:38 pipeline/backups/data_snapshots/2026-04-16/oi_history.json
-rw-r--r-- 1 Claude_Anka 197121 364244 Apr 14 15:38 pipeline/backups/data_snapshots/2026-04-16/pattern_lookup.json
-rw-r--r-- 1 Claude_Anka 197121    494 Apr 14 15:38 pipeline/backups/data_snapshots/2026-04-16/pinning_backtest_summary.json
-rw-r--r-- 1 Claude_Anka 197121  30437 Apr 14 15:38 pipeline/backups/data_snapshots/2026-04-16/pinning_history.json
-rw-r--r-- 1 Claude_Anka 197121   3558 Apr 14 15:38 pipeline/backups/data_snapshots/2026-04-16/regime_history.json
-rw-r--r-- 1 Claude_Anka 197121  14473 Apr 14 13:04 pipeline/backups/data_snapshots/2026-04-16/scorecard_alpha_results.json

```

## Section A4 — Migration spec re-read gate

<populated by Task 5>

## Section A5 — Dry-run output

<populated by Task 6>
