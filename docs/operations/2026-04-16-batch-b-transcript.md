# Batch B Transcript — Scheduler Debt Remediation 2026-04-16

**Plan:** `docs/superpowers/plans/2026-04-16-scheduler-debt-remediation.md`
**Spec:** `docs/superpowers/specs/2026-04-16-scheduler-debt-remediation-design.md`
**Branch:** `remediate/scheduler-debt-2026-04-16`

## Section B1 — Delete 29 zombie tasks (Documents\ path)

Script: `C:/Users/Claude_Anka/AppData/Local/Temp/delete_zombies.ps1`
Captured output: `C:/Users/Claude_Anka/AppData/Local/Temp/delete_out.txt`

```
Deleting 29 zombies
  DELETED: AnkaARCBE2300
  DELETED: AnkaEOD1630
  DELETED: AnkaIntraday0940
  DELETED: AnkaIntraday0955
  DELETED: AnkaIntraday1010
  DELETED: AnkaIntraday1025
  DELETED: AnkaIntraday1040
  DELETED: AnkaIntraday1055
  DELETED: AnkaIntraday1110
  DELETED: AnkaIntraday1125
  DELETED: AnkaIntraday1140
  DELETED: AnkaIntraday1155
  DELETED: AnkaIntraday1210
  DELETED: AnkaIntraday1225
  DELETED: AnkaIntraday1240
  DELETED: AnkaIntraday1255
  DELETED: AnkaIntraday1310
  DELETED: AnkaIntraday1325
  DELETED: AnkaIntraday1340
  DELETED: AnkaIntraday1355
  DELETED: AnkaIntraday1410
  DELETED: AnkaIntraday1425
  DELETED: AnkaIntraday1440
  DELETED: AnkaIntraday1455
  DELETED: AnkaIntraday1510
  DELETED: AnkaIntraday1525
  DELETED: AnkaSpreadStats
  DELETED: AnkaWeeklyVideo
  DELETED: OpenCapture

Total: 29 DELETED, 0 FAIL

=== Verify: any Documents\ tasks remaining? ===
```

**Independent verify (separate PowerShell invocation):**

```
powershell.exe -ExecutionPolicy Bypass -Command "(Get-ScheduledTask | Where-Object { $_.Actions[0].Execute -match 'Documents\\askanka' }).Count"
0
```

**Result:** 29 DELETED, 0 FAIL. Zero Documents\ tasks remain in the live scheduler. XML backups in `pipeline/backups/scheduled_tasks/2026-04-16/` untouched (67 files).

## Section B2 — Re-register quote-bug tasks (populated by Task 9)

_Placeholder: will capture the unregister+register-clean cycle for the three askanka.com-path tasks whose Execute has stray quote-wrapping (AnkaCorrelationBreaks, AnkaGapPredictor, AnkaPruneArticles)._

## Section B3 — Manual run verification of never-ran tasks (populated by Task 10)

_Placeholder: will capture Start-ScheduledTask + LastResult check for AnkaEODNews, AnkaGapPredictor, AnkaPruneArticles, AnkaWeeklyStats to flip the never-ran flag._

## Section B4 — Post-Batch-B scheduler snapshot (populated by Task 11)

_Placeholder: full scheduler audit re-run after B1/B2/B3. Expected: 0 Documents\ tasks, 0 quote-bug tasks, 0 never-ran tasks (or documented exceptions)._
