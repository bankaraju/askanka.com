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

## Section B3 — Manual run verification of never-ran tasks

Script: `C:/Users/Claude_Anka/AppData/Local/Temp/verify_never_ran.ps1`
Captured output: `C:/Users/Claude_Anka/AppData/Local/Temp/never_ran_out.txt`

**Scope adaptation from plan Task 10:** The plan lists 5 never-ran tasks. After B1+B2, the effective set is 4:

- `AnkaSpreadStats` — SKIPPED. Was a Documents\ zombie deleted in B1 (`78e0268`). Its `.bat` target (`Documents\askanka.com\pipeline\scripts\weekly_stats.bat`) no longer exists. Per plan Task 10 Step 3 ("if the .bat is missing, document as subsumed and do not reschedule"), no re-registration attempt. `AnkaWeeklyStats` is the askanka.com-path replacement holding the weekly-stats cron slot.
- Remaining 4 manually run: `AnkaEODNews`, `AnkaGapPredictor`, `AnkaPruneArticles`, `AnkaWeeklyStats`.

**Initial captured output (before AnkaWeeklyStats finished):**

```
=== AnkaEODNews ===
  Execute: C:\Users\Claude_Anka\askanka.com\pipeline\scripts\overnight_news.bat
  Starting...
  DONE: LastResult=0  LastRun=04/16/2026 12:19:49
  PASS

=== AnkaGapPredictor ===
  Execute: C:\Users\Claude_Anka\askanka.com\pipeline\scripts\gap_predictor.bat
  Starting...
  DONE: LastResult=0  LastRun=04/16/2026 12:20:50
  PASS

=== AnkaPruneArticles ===
  Execute: C:\Users\Claude_Anka\askanka.com\pipeline\scripts\prune_articles.bat
  Starting...
  DONE: LastResult=0  LastRun=04/16/2026 12:20:50
  PASS

=== AnkaWeeklyStats ===
  Execute: C:\Users\Claude_Anka\askanka.com\pipeline\scripts\weekly_stats.bat
  Starting...
  DONE: LastResult=267009  LastRun=04/16/2026 12:20:50
  NONZERO result=267009 - inspect task log
```

**AnkaWeeklyStats — initial 267009 was mid-run noise (`SCHED_S_TASK_HAS_NOT_RUN`-ish transient), not a failure.** The 120s poll window clipped the job mid-execution; `weekly_stats.bat` is a long-running weekly aggregator (expected to take several minutes per plan guidance). Extended-poll follow-up:

```
Still running... LastResult=267009
Still running... LastResult=267009
Done: State=Ready LastResult=0 LastRun=04/16/2026 12:20:50
FINAL: State=Ready LastResult=0 LastRun=04/16/2026 12:20:50
```

The task transitioned `Running` → `Ready` with `LastTaskResult=0`. PASS.

**Final per-task verdict:**

| Task | LastTaskResult | LastRunTime | Verdict |
|---|---|---|---|
| AnkaEODNews | 0 | 2026-04-16 12:19:49 | PASS |
| AnkaGapPredictor | 0 | 2026-04-16 12:20:50 | PASS |
| AnkaPruneArticles | 0 | 2026-04-16 12:20:50 | PASS |
| AnkaWeeklyStats | 0 | 2026-04-16 12:20:50 | PASS (after extended poll — transient 267009 while Running) |
| AnkaSpreadStats | n/a | n/a | SUBSUMED by B1 (see above) |

**Result:** 4 PASS, 0 NONZERO, 0 TIMEOUT, 1 SUBSUMED (AnkaSpreadStats). All four B3-scope tasks now have `LastTaskResult=0` and a 2026-04-16 LastRunTime — never-ran flag flipped. `AnkaSpreadStats` remains deleted per B1; no re-registration needed since `AnkaWeeklyStats` covers the weekly-stats slot.

## Section B4 — Post-Batch-B scheduler snapshot

**Script:** `C:/Users/Claude_Anka/AppData/Local/Temp/post_b_sweep.ps1`
**Output:** `C:/Users/Claude_Anka/AppData/Local/Temp/post_b_out.txt`

```
=== Batch B invariants (Anka-scope) ===
Tasks with Documents\ path:        0  (target: 0)
Anka tasks with embedded quotes:   0    (target: 0)
Anka tasks still never-ran:        0  (target: 0 or documented NEW)

Total Anka* tasks: 68

BATCH B GATE: PASS
exit_code=0
```

**Invariant deltas vs Batch A audit (Anka-scope):**

| Invariant | Batch A | Post-B4 | Delta |
|---|---|---|---|
| Documents\ zombies | 29 | 0 | −29 (B1 deletions) |
| Anka quote-bug Execute | 28 | 0 | −28 (3 rewritten in B2; 25 removed as zombies in B1) |
| Anka never-ran | 5 | 0 | −5 (4 manually run in B3; 1 subsumed by B1) |
| Total Anka* tasks | 97 | 68 | −29 (zombie deletions; no new tasks added in Batch B) |

**Gate verdict:** PASS. All three invariants at target. Ready to proceed to Batch C (wiring + freshness).

Batch B executed safely: every destructive op reversible via XML backups in `pipeline/backups/scheduled_tasks/2026-04-16/` (67 files, untouched). No .bat files modified; no Python code modified; no XML backups disturbed.
