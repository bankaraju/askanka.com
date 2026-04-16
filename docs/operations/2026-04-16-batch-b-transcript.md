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

## Section B2 — Re-register quote-bug tasks

Script: `C:/Users/Claude_Anka/AppData/Local/Temp/fix_quote_bugs.ps1`
Captured output: `C:/Users/Claude_Anka/AppData/Local/Temp/quote_fix_out.txt`

**Intentional deviation from the plan's PowerShell:** the filter was tightened from the plan's naive quote-match to `... -and $t.TaskName -like 'Anka*'`. The plan's filter would have swept in `UpdateLibrary` (a Windows Media Player SYSTEM task whose `"%ProgramFiles%\Windows Media Player\wmpnscfg.exe"` Execute legitimately uses quote-wrapping as a system-task convention). Batch A's concern #2 flagged this; the design spec §scope also excludes it. The Anka-only filter keeps rewrite scope to the remediation's declared scope.

**Second deviation (empty-WorkingDirectory guard):** the plan's `New-ScheduledTaskAction` call passes `-WorkingDirectory $oldWd` unconditionally. The 3 target tasks all have empty `WorkingDirectory`, which makes the cmdlet throw `The argument is null or empty`. First run failed cleanly (New-ScheduledTaskAction is validated before Unregister is called, so all 3 tasks were still intact — verified). The script was updated to pass `-Argument`/`-WorkingDirectory` only when non-empty, then re-run.

**Live count discovered by the filter:** 3 Anka quote-bug tasks (matches Batch A mapping table rows 30-32; the other 25 quote-bugs from the raw Batch A audit were subsumed by the Documents\ zombie set already deleted in B1).

```
Rewriting 3 Anka quote-bug tasks
  OK:   AnkaCorrelationBreaks  FROM="C:\Users\Claude_Anka\askanka.com\pipeline\scripts\correlation_breaks.bat"  TO=C:\Users\Claude_Anka\askanka.com\pipeline\scripts\correlation_breaks.bat
  OK:   AnkaGapPredictor  FROM="C:\Users\Claude_Anka\askanka.com\pipeline\scripts\gap_predictor.bat"  TO=C:\Users\Claude_Anka\askanka.com\pipeline\scripts\gap_predictor.bat
  OK:   AnkaPruneArticles  FROM="C:\Users\Claude_Anka\askanka.com\pipeline\scripts\prune_articles.bat"  TO=C:\Users\Claude_Anka\askanka.com\pipeline\scripts\prune_articles.bat

Total: 3 OK, 0 FAIL
```

**Independent verify (Anka-scope quote-bug count):**

```
powershell.exe -ExecutionPolicy Bypass -Command "(Get-ScheduledTask | Where-Object { (`$_.Actions[0].Execute -match '^\"' -or `$_.Actions[0].Execute -match '\"\"') -and `$_.TaskName -like 'Anka*' }).Count"
0
```

**Post-rewrite sanity check (state / triggers / principal preserved):**

```
AnkaCorrelationBreaks | State=Ready | Exec=C:\Users\Claude_Anka\askanka.com\pipeline\scripts\correlation_breaks.bat | Triggers=1 | RunAs=Claude_Anka
AnkaGapPredictor      | State=Ready | Exec=C:\Users\Claude_Anka\askanka.com\pipeline\scripts\gap_predictor.bat      | Triggers=1 | RunAs=Claude_Anka
AnkaPruneArticles     | State=Ready | Exec=C:\Users\Claude_Anka\askanka.com\pipeline\scripts\prune_articles.bat     | Triggers=1 | RunAs=Claude_Anka
```

**UpdateLibrary untouched (Windows system task — outside Anka scope):**

```
UpdateLibrary | Exec="%ProgramFiles%\Windows Media Player\wmpnscfg.exe"
```

**Result:** 3 OK, 0 FAIL. Zero Anka quote-bug tasks remain. Triggers, settings, and principal preserved across re-register. XML backups in `pipeline/backups/scheduled_tasks/2026-04-16/` untouched.

## Section B3 — Manual run verification of never-ran tasks (populated by Task 10)

_Placeholder: will capture Start-ScheduledTask + LastResult check for AnkaEODNews, AnkaGapPredictor, AnkaPruneArticles, AnkaWeeklyStats to flip the never-ran flag._

## Section B4 — Post-Batch-B scheduler snapshot (populated by Task 11)

_Placeholder: full scheduler audit re-run after B1/B2/B3. Expected: 0 Documents\ tasks, 0 quote-bug tasks, 0 never-ran tasks (or documented exceptions)._
