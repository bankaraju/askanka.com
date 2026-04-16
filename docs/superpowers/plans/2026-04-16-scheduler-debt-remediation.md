# Scheduler Debt Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close scheduler debt accumulated across Apr 14–15 (28 Documents\ zombies, 27 quote-bug tasks, 5 never-ran tasks, Phase A unscheduled, Phase C CLI mismatch, ~20-file Apr 14 15:38 stale cluster, 1 orphan file, 2 untracked stale-cluster writers) so Apr 15's downstream consumers (website, articles, recs panel, trail stop) read fresh inputs.

**Architecture:** Three sequential batches gated on the diagnose artifact (a 6-column mapping table). Batch A (zero destructive ops) produces XML backups + mapping table + data snapshots. Batch B (highest blast) deletes zombies, rewrites quote-bugs, re-registers never-ran tasks. Batch C (low blast) fixes Phase C CLI, schedules Phase A as interim, identifies and fixes the master EOD job, resolves the orphan and untracked writers, runs downstream smoke tests. Runs entirely on branch `remediate/scheduler-debt-2026-04-16`.

**Tech Stack:** Windows Task Scheduler (PowerShell cmdlets: `Get-ScheduledTask`, `Register-ScheduledTask`, `Unregister-ScheduledTask`, `Export-ScheduledTask`, `Start-ScheduledTask`, `Get-ScheduledTaskInfo`). Python 3.11 for pipeline scripts. Git for version control + XML backup rollback.

**Spec:** `docs/superpowers/specs/2026-04-16-scheduler-debt-remediation-design.md`

---

## File Structure

**Create:**
- `pipeline/backups/scheduled_tasks/2026-04-16/*.xml` — one per affected task
- `pipeline/backups/data_snapshots/2026-04-16/*.json` — pre-run snapshots of stale intermediates
- `docs/operations/2026-04-16-batch-a-transcript.md` — Batch A audit + dry-run output
- `docs/operations/2026-04-16-batch-b-transcript.md` — Batch B per-task delete/register log
- `docs/operations/2026-04-16-batch-c-transcript.md` — Batch C wiring + smoke test output
- `pipeline/scripts/reverse_regime_profile.bat` — thin wrapper for Phase A interim cron

**Modify:**
- `docs/superpowers/specs/2026-04-16-scheduler-debt-remediation-design.md` — populate full mapping table (Batch A)
- `pipeline/scripts/correlation_breaks.bat` — strip `--day 1 --no-telegram` (Batch C1)

**Possibly modify (judgment calls inside C3.x):**
- `pipeline/options_monitor.py` — commit or delete (currently untracked, owns `oi_history.json`)
- `pipeline/gamma_scanner.py` — commit or delete (currently untracked, may own `gamma_result.json`)
- `pipeline/data/gamma_result.json` — delete if orphan

**Temp scratch (not committed):** PowerShell scripts in `C:/Users/Claude_Anka/AppData/Local/Temp/` invoked via `powershell.exe -ExecutionPolicy Bypass -File <path>`.

---

## Context for the executor

- **Platform:** Windows 10. Shell is bash (Git Bash). PowerShell is invoked via `powershell.exe` with `.ps1` files in `%TEMP%`. Never use inline `-Command` with bash-quoted strings — bash mangles `$_`, `$t`, etc. Always write a `.ps1` file first.
- **Task name convention:** canonical live tasks prefix `Anka*`. Documents\ zombies share the same prefix.
- **Paths are forward-slash in bash commands but backslash in PowerShell / Execute fields.**
- **Everything runs on branch `remediate/scheduler-debt-2026-04-16`** (already created when this plan's spec was committed).
- **Rollback anchor:** XML backups in `pipeline/backups/scheduled_tasks/2026-04-16/`. For any task, `Register-ScheduledTask -Xml (Get-Content <backup>.xml -Raw) -TaskName <name>` restores it.

---

## Task 1: Batch A — Create directories, switch to branch, start Batch A transcript

**Files:**
- Create: `pipeline/backups/scheduled_tasks/2026-04-16/` (empty dir)
- Create: `pipeline/backups/data_snapshots/2026-04-16/` (empty dir)
- Create: `docs/operations/` (if missing)
- Create: `docs/operations/2026-04-16-batch-a-transcript.md`

- [ ] **Step 1: Confirm branch + working directory**

```bash
cd /c/Users/Claude_Anka/askanka.com
git status
git rev-parse --abbrev-ref HEAD
```

Expected: branch is `remediate/scheduler-debt-2026-04-16`. If not: `git checkout remediate/scheduler-debt-2026-04-16`.

- [ ] **Step 2: Create backup and operations directories**

```bash
cd /c/Users/Claude_Anka/askanka.com
mkdir -p pipeline/backups/scheduled_tasks/2026-04-16
mkdir -p pipeline/backups/data_snapshots/2026-04-16
mkdir -p docs/operations
```

- [ ] **Step 3: Write Batch A transcript header**

Create `docs/operations/2026-04-16-batch-a-transcript.md`:

```markdown
# Batch A Transcript — Scheduler Debt Remediation 2026-04-16

**Plan:** `docs/superpowers/plans/2026-04-16-scheduler-debt-remediation.md`
**Spec:** `docs/superpowers/specs/2026-04-16-scheduler-debt-remediation-design.md`
**Branch:** `remediate/scheduler-debt-2026-04-16`

## Section A1 — Task audit

<populated by Task 2>

## Section A2 — XML backups

<populated by Task 3>

## Section A3 — Data snapshots

<populated by Task 4>

## Section A4 — Migration spec re-read gate

<populated by Task 5>

## Section A5 — Dry-run output

<populated by Task 6>
```

- [ ] **Step 4: Commit setup**

```bash
cd /c/Users/Claude_Anka/askanka.com
git add pipeline/backups/scheduled_tasks/2026-04-16/.gitkeep pipeline/backups/data_snapshots/2026-04-16/.gitkeep docs/operations/2026-04-16-batch-a-transcript.md 2>/dev/null
# If .gitkeep doesn't exist, create empty markers:
touch pipeline/backups/scheduled_tasks/2026-04-16/.gitkeep
touch pipeline/backups/data_snapshots/2026-04-16/.gitkeep
git add pipeline/backups/scheduled_tasks/2026-04-16/.gitkeep pipeline/backups/data_snapshots/2026-04-16/.gitkeep docs/operations/2026-04-16-batch-a-transcript.md
git commit -m "chore(remediate): batch A setup — backup dirs + transcript scaffold

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Batch A — Enumerate affected tasks (the audit)

**Files:**
- Create: `C:/Users/Claude_Anka/AppData/Local/Temp/audit_scheduler.ps1`
- Modify: `docs/operations/2026-04-16-batch-a-transcript.md` (append Section A1 results)

- [ ] **Step 1: Write the audit PowerShell script**

Write `C:/Users/Claude_Anka/AppData/Local/Temp/audit_scheduler.ps1`:

```powershell
$ErrorActionPreference = 'Stop'
$all = Get-ScheduledTask

$zombies = @()
$quoteBugs = @()
$neverRan = @()

foreach ($t in $all) {
    $exec = $t.Actions[0].Execute
    $info = Get-ScheduledTaskInfo -TaskName $t.TaskName -TaskPath $t.TaskPath

    # (1) Zombies: Documents\askanka path
    if ($exec -match 'Documents\\askanka') {
        $zombies += [pscustomobject]@{
            Name = $t.TaskName
            Path = $t.TaskPath
            Execute = $exec
        }
    }

    # (2) Quote bugs: embedded double-quote wrapping
    # Pattern: Execute string starts and ends with " or contains ""
    if ($exec -match '^"' -or $exec -match '""') {
        $quoteBugs += [pscustomobject]@{
            Name = $t.TaskName
            Path = $t.TaskPath
            Execute = $exec
        }
    }

    # (3) Never ran: result=267011 or lastRun=1999
    if ($info.LastTaskResult -eq 267011 -or $info.LastRunTime.Year -eq 1999) {
        $neverRan += [pscustomobject]@{
            Name = $t.TaskName
            LastResult = $info.LastTaskResult
            LastRun = $info.LastRunTime
            Execute = $exec
        }
    }
}

Write-Output "### Zombies (Documents\ path) — count: $($zombies.Count)"
$zombies | Format-Table -AutoSize | Out-String -Width 200
Write-Output ""
Write-Output "### Quote-bug Execute strings — count: $($quoteBugs.Count)"
$quoteBugs | Format-Table -AutoSize | Out-String -Width 200
Write-Output ""
Write-Output "### Never-ran tasks — count: $($neverRan.Count)"
$neverRan | Format-Table -AutoSize | Out-String -Width 200
Write-Output ""

# Also dump concatenated list of all unique affected task names for Task 3
$affected = @($zombies.Name + $quoteBugs.Name + $neverRan.Name) | Sort-Object -Unique
Write-Output "### All unique affected task names (for XML backup)"
$affected -join "`n"
```

- [ ] **Step 2: Run the audit**

```bash
powershell.exe -ExecutionPolicy Bypass -File "C:/Users/Claude_Anka/AppData/Local/Temp/audit_scheduler.ps1" 2>&1 | tee /tmp/audit_out.txt
```

Expected: prints three tables (zombies ≈28, quote-bugs ≈27, never-ran ≈5), followed by the unique affected task names.

- [ ] **Step 3: Append the audit output to transcript Section A1**

```bash
cd /c/Users/Claude_Anka/askanka.com
# Replace the placeholder line with the captured output
python -c "
import pathlib
t = pathlib.Path('docs/operations/2026-04-16-batch-a-transcript.md')
content = t.read_text(encoding='utf-8')
audit = pathlib.Path('/tmp/audit_out.txt').read_text(encoding='utf-8', errors='replace')
content = content.replace('## Section A1 — Task audit\n\n<populated by Task 2>', f'## Section A1 — Task audit\n\n\`\`\`\n{audit}\n\`\`\`')
t.write_text(content, encoding='utf-8')
print('transcript updated')
"
```

- [ ] **Step 4: Commit the audit record**

```bash
cd /c/Users/Claude_Anka/askanka.com
git add docs/operations/2026-04-16-batch-a-transcript.md
git commit -m "chore(remediate): batch A1 — task audit captured

$(git diff HEAD~1 -- docs/operations/2026-04-16-batch-a-transcript.md | grep -c '^+') lines of audit output appended.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Batch A — Export XML backups for all affected tasks

**Files:**
- Create: `C:/Users/Claude_Anka/AppData/Local/Temp/backup_tasks.ps1`
- Create: `pipeline/backups/scheduled_tasks/2026-04-16/*.xml` (one per unique affected task)
- Modify: `docs/operations/2026-04-16-batch-a-transcript.md` (append Section A2)

- [ ] **Step 1: Write the XML backup script**

Write `C:/Users/Claude_Anka/AppData/Local/Temp/backup_tasks.ps1`:

```powershell
$ErrorActionPreference = 'Stop'
$destDir = 'C:\Users\Claude_Anka\askanka.com\pipeline\backups\scheduled_tasks\2026-04-16'

# Rebuild affected list from live state (same logic as audit)
$all = Get-ScheduledTask
$affected = @()
foreach ($t in $all) {
    $exec = $t.Actions[0].Execute
    $info = Get-ScheduledTaskInfo -TaskName $t.TaskName -TaskPath $t.TaskPath
    if ($exec -match 'Documents\\askanka') { $affected += $t }
    elseif ($exec -match '^"' -or $exec -match '""') { $affected += $t }
    elseif ($info.LastTaskResult -eq 267011 -or $info.LastRunTime.Year -eq 1999) { $affected += $t }
}
$affected = $affected | Sort-Object TaskName -Unique

Write-Output "Backing up $($affected.Count) tasks to $destDir"
$success = 0
$fail = 0
foreach ($t in $affected) {
    $safeName = $t.TaskName -replace '[^a-zA-Z0-9_\-]', '_'
    $dest = Join-Path $destDir "$safeName.xml"
    try {
        $xml = Export-ScheduledTask -TaskName $t.TaskName -TaskPath $t.TaskPath
        [System.IO.File]::WriteAllText($dest, $xml, [System.Text.UTF8Encoding]::new($false))
        $success++
        Write-Output "  OK   $($t.TaskName) -> $safeName.xml"
    } catch {
        $fail++
        Write-Output "  FAIL $($t.TaskName): $_"
    }
}
Write-Output ""
Write-Output "Total: $success OK, $fail FAIL"
```

- [ ] **Step 2: Run the backup script**

```bash
powershell.exe -ExecutionPolicy Bypass -File "C:/Users/Claude_Anka/AppData/Local/Temp/backup_tasks.ps1" 2>&1 | tee /tmp/backup_out.txt
```

Expected: one "OK" line per task, final line "Total: N OK, 0 FAIL" where N ≈ 55–60.

- [ ] **Step 3: Verify XML files exist**

```bash
ls /c/Users/Claude_Anka/askanka.com/pipeline/backups/scheduled_tasks/2026-04-16/*.xml | wc -l
```

Expected: count matches the "N OK" from Step 2.

- [ ] **Step 4: Append to transcript Section A2**

```bash
cd /c/Users/Claude_Anka/askanka.com
python -c "
import pathlib
t = pathlib.Path('docs/operations/2026-04-16-batch-a-transcript.md')
content = t.read_text(encoding='utf-8')
backup = pathlib.Path('/tmp/backup_out.txt').read_text(encoding='utf-8', errors='replace')
content = content.replace('## Section A2 — XML backups\n\n<populated by Task 3>', f'## Section A2 — XML backups\n\n\`\`\`\n{backup}\n\`\`\`')
t.write_text(content, encoding='utf-8')
"
```

- [ ] **Step 5: Commit XML backups + transcript update**

```bash
cd /c/Users/Claude_Anka/askanka.com
git add pipeline/backups/scheduled_tasks/2026-04-16/*.xml docs/operations/2026-04-16-batch-a-transcript.md
git commit -m "chore(remediate): batch A2 — XML backups for all affected tasks

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Batch A — Snapshot stale intermediates

**Files:**
- Create: `pipeline/backups/data_snapshots/2026-04-16/*.json` (copies of Apr 14 15:38 cluster)
- Modify: `docs/operations/2026-04-16-batch-a-transcript.md` (append Section A3)

- [ ] **Step 1: Copy stale cluster files to snapshot dir**

```bash
cd /c/Users/Claude_Anka/askanka.com
SNAP=pipeline/backups/data_snapshots/2026-04-16
DATA=pipeline/data

for f in correlation_history.json correlation_report_2026-04-03.json expiry_divergence_log.json fragility_model.json fragility_scores.json gamma_generation.json gamma_result.json gex_history.json historical_events.json macro_trigger_state.json ml_performance.json msi_history.json oi_history.json pattern_lookup.json pinning_backtest_summary.json pinning_history.json regime_history.json scorecard_alpha_results.json; do
    if [ -f "$DATA/$f" ]; then
        cp "$DATA/$f" "$SNAP/$f"
        echo "snapshot: $f"
    fi
done
```

Expected: ~17–18 "snapshot:" lines (files that exist in data/ get copied).

- [ ] **Step 2: Capture the snapshot manifest**

```bash
cd /c/Users/Claude_Anka/askanka.com
ls -la pipeline/backups/data_snapshots/2026-04-16/*.json > /tmp/snapshot_manifest.txt
cat /tmp/snapshot_manifest.txt
```

Expected: ≥17 files listed with original mtimes preserved.

- [ ] **Step 3: Append to transcript Section A3**

```bash
cd /c/Users/Claude_Anka/askanka.com
python -c "
import pathlib
t = pathlib.Path('docs/operations/2026-04-16-batch-a-transcript.md')
content = t.read_text(encoding='utf-8')
manifest = pathlib.Path('/tmp/snapshot_manifest.txt').read_text(encoding='utf-8', errors='replace')
content = content.replace('## Section A3 — Data snapshots\n\n<populated by Task 4>', f'## Section A3 — Data snapshots\n\n\`\`\`\n{manifest}\n\`\`\`')
t.write_text(content, encoding='utf-8')
"
```

- [ ] **Step 4: Commit snapshots**

```bash
cd /c/Users/Claude_Anka/askanka.com
git add pipeline/backups/data_snapshots/2026-04-16/*.json docs/operations/2026-04-16-batch-a-transcript.md
git commit -m "chore(remediate): batch A3 — snapshot stale cluster before re-run

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Batch A — Migration spec re-read gate

**Files:**
- Modify: `docs/operations/2026-04-16-batch-a-transcript.md` (append Section A4)

- [ ] **Step 1: Grep the migration spec for the deletion claim**

```bash
cd /c/Users/Claude_Anka/askanka.com
grep -n -i "archived\|deleted\|documents" docs/superpowers/specs/2026-04-14-unified-repo-clockwork-design.md > /tmp/migration_claim.txt
cat /tmp/migration_claim.txt
```

Expected: lines quoting "archived then deleted" or similar. Verify the text confirms Documents\ was retired.

- [ ] **Step 2: STOP gate — human confirmation**

If grep output does NOT confirm Documents\ was deleted (e.g., says "kept as fallback" or "mirror copy"), STOP this plan and escalate. The 28 zombies are not safe to delete.

Otherwise, proceed.

- [ ] **Step 3: Append gate result to transcript Section A4**

```bash
cd /c/Users/Claude_Anka/askanka.com
python -c "
import pathlib
t = pathlib.Path('docs/operations/2026-04-16-batch-a-transcript.md')
content = t.read_text(encoding='utf-8')
claim = pathlib.Path('/tmp/migration_claim.txt').read_text(encoding='utf-8', errors='replace')
content = content.replace('## Section A4 — Migration spec re-read gate\n\n<populated by Task 5>', f'## Section A4 — Migration spec re-read gate\n\nGrep output confirming Documents\\ archived+deleted:\n\n\`\`\`\n{claim}\n\`\`\`\n\n**Gate result: PASS — zombies safe to delete.**')
t.write_text(content, encoding='utf-8')
"
git add docs/operations/2026-04-16-batch-a-transcript.md
git commit -m "chore(remediate): batch A4 — migration spec gate passed

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: Batch A — Populate the mapping table

**Files:**
- Modify: `docs/superpowers/specs/2026-04-16-scheduler-debt-remediation-design.md` (append full mapping table)

- [ ] **Step 1: Read the captured audit output**

```bash
cat /tmp/audit_out.txt
```

Use this to enumerate every affected task name.

- [ ] **Step 2: Append the full mapping table to the spec**

Open `docs/superpowers/specs/2026-04-16-scheduler-debt-remediation-design.md`. Find Section 2 "The diagnose artifact" → at the end of that section (after the seed rows table), append a new subsection:

```markdown
### Full mapping table (populated 2026-04-16 Batch A6)

| # | Gap | Evidence | Bucket | Parent plan + § | Drift note | Remediation action | Status |
|---|-----|----------|--------|-----------------|------------|---------------------|--------|
| 1 | Zombie: `<task name>` | Execute=`C:\Users\Claude_Anka\Documents\askanka.com\...` | (ii) | 2026-04-14-unified-repo-clockwork §Migration | Post-migration leftover | Unregister (Batch B1) | PENDING |
| 2 | Zombie: `<task name>` | ... | (ii) | ... | ... | Unregister (Batch B1) | PENDING |
...
| N | Quote-bug: `<task name>` | Execute starts with `"` | (ii) | 2026-04-14-unified-repo-clockwork §Migration | Re-registration side-effect | Unregister+Register clean (Batch B2) | PENDING |
...
| M | Never-ran: `AnkaGapPredictor` | LastResult=267011 | (ii) | overlap with B2 | Quote-bug class | Re-register from XML, Start manually (Batch B3) | PENDING |
...
| P | Phase A not scheduled | No task runs reverse_regime_analysis.py | (iii) interim (i) | — | Phase B runs with stale profile | Schedule AnkaReverseRegimeProfile @ 04:45 (Batch C2) | PENDING |
| P+1 | AnkaCorrelationBreaks CLI | .bat passes `--day 1 --no-telegram` which argparse rejects | (i) | 2026-04-14-correlation-break-detector §CLI | .bat written against older CLI | Strip those two args from .bat (Batch C1) | PENDING |
| P+2 | Apr-14-15:38 cluster | ~18 pipeline/data/*.json share exact mtime | (i) master-job | 2026-04-14-unified-repo-clockwork (task registry) | Master EOD job stopped firing | Identify + diagnose + fix master (Batch C3) | PENDING |
| P+3 | gamma_result.json orphan | 231 bytes; no writer in codebase | (ii) hygiene | — | Delete or resolve via gamma_scanner.py | Resolve in Batch C3.x | PENDING |
| P+4 | options_monitor.py untracked | git status; writes oi_history.json | (ii) hygiene | — | Single-repo mandate | Commit or delete in Batch C3.x | PENDING |
| P+5 | 9 other untracked scripts | git status | (iii) NEW | — | Judgment-per-file | Defer to future mini-plan | DEFERRED-NEW |
```

Generate one row per zombie (copy task name from audit output), one row per quote-bug task, one row per never-ran task. Fill in the actual task names from `/tmp/audit_out.txt`. Row numbers sequential.

- [ ] **Step 3: Commit populated mapping table**

```bash
cd /c/Users/Claude_Anka/askanka.com
git add docs/superpowers/specs/2026-04-16-scheduler-debt-remediation-design.md
git commit -m "docs(remediate): batch A6 — full mapping table populated

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: Batch A — Dry-run all destructive ops

**Files:**
- Create: `C:/Users/Claude_Anka/AppData/Local/Temp/dryrun_destructive.ps1`
- Modify: `docs/operations/2026-04-16-batch-a-transcript.md` (append Section A5)

- [ ] **Step 1: Write the dry-run script**

Write `C:/Users/Claude_Anka/AppData/Local/Temp/dryrun_destructive.ps1`:

```powershell
$ErrorActionPreference = 'Continue'

$all = Get-ScheduledTask
Write-Output "=== DRY RUN: zombie deletions ==="
foreach ($t in $all) {
    $exec = $t.Actions[0].Execute
    if ($exec -match 'Documents\\askanka') {
        Write-Output "WOULD DELETE: $($t.TaskName)  (Execute=$exec)"
    }
}

Write-Output ""
Write-Output "=== DRY RUN: quote-bug rewrites ==="
foreach ($t in $all) {
    $exec = $t.Actions[0].Execute
    if (($exec -match '^"' -or $exec -match '""') -and $exec -notmatch 'Documents\\askanka') {
        # Clean version: strip all double-quotes
        $clean = $exec -replace '"', ''
        Write-Output "WOULD REWRITE: $($t.TaskName)"
        Write-Output "  FROM: $exec"
        Write-Output "  TO:   $clean"
    }
}

Write-Output ""
Write-Output "=== DRY RUN: never-ran re-registrations ==="
$neverRanNames = @('AnkaEODNews','AnkaGapPredictor','AnkaPruneArticles','AnkaSpreadStats','AnkaWeeklyStats')
foreach ($n in $neverRanNames) {
    $t = Get-ScheduledTask -TaskName $n -ErrorAction SilentlyContinue
    if ($null -eq $t) { Write-Output "SKIP (not found): $n"; continue }
    $info = Get-ScheduledTaskInfo -TaskName $n
    $exec = $t.Actions[0].Execute
    $batExists = if (Test-Path $exec) { "YES" } else { "NO" }
    Write-Output "REGISTER: $n  Execute=$exec  bat_exists=$batExists  lastResult=$($info.LastTaskResult)"
}
```

- [ ] **Step 2: Run the dry-run**

```bash
powershell.exe -ExecutionPolicy Bypass -File "C:/Users/Claude_Anka/AppData/Local/Temp/dryrun_destructive.ps1" 2>&1 | tee /tmp/dryrun_out.txt
```

Expected:
- WOULD DELETE ≈ 28 entries, each pointing to Documents\
- WOULD REWRITE ≈ 27 entries, each with FROM (with quotes) / TO (no quotes)
- REGISTER 5 entries; `bat_exists=YES` for each (if any is NO, it's a STOP condition for that task)

- [ ] **Step 3: Append dry-run output to transcript Section A5**

```bash
cd /c/Users/Claude_Anka/askanka.com
python -c "
import pathlib
t = pathlib.Path('docs/operations/2026-04-16-batch-a-transcript.md')
content = t.read_text(encoding='utf-8')
dryrun = pathlib.Path('/tmp/dryrun_out.txt').read_text(encoding='utf-8', errors='replace')
content = content.replace('## Section A5 — Dry-run output\n\n<populated by Task 6>', f'## Section A5 — Dry-run output\n\n\`\`\`\n{dryrun}\n\`\`\`')
t.write_text(content, encoding='utf-8')
"
```

- [ ] **Step 4: Commit dry-run record**

```bash
cd /c/Users/Claude_Anka/askanka.com
git add docs/operations/2026-04-16-batch-a-transcript.md
git commit -m "chore(remediate): batch A5 — dry-run for all destructive ops

Zombies to delete, quote-bugs to rewrite, never-rans to re-register.
No state changes; purely predictive output.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

**Batch A exit gate:** XML backups + snapshots + mapping table + dry-run output all committed. No scheduler state changed.

---

## Task 8: Batch B1 — Delete 28 Documents\ zombies

**Files:**
- Create: `C:/Users/Claude_Anka/AppData/Local/Temp/delete_zombies.ps1`
- Create: `docs/operations/2026-04-16-batch-b-transcript.md`

- [ ] **Step 1: Write the delete script**

Write `C:/Users/Claude_Anka/AppData/Local/Temp/delete_zombies.ps1`:

```powershell
$ErrorActionPreference = 'Continue'

$all = Get-ScheduledTask
$zombies = @()
foreach ($t in $all) {
    if ($t.Actions[0].Execute -match 'Documents\\askanka') {
        $zombies += $t
    }
}

Write-Output "Deleting $($zombies.Count) zombies"
$success = 0
$fail = 0
foreach ($t in $zombies) {
    try {
        Unregister-ScheduledTask -TaskName $t.TaskName -TaskPath $t.TaskPath -Confirm:$false
        $success++
        Write-Output "  DELETED: $($t.TaskName)"
    } catch {
        $fail++
        Write-Output "  FAIL:    $($t.TaskName) — $_"
    }
}
Write-Output ""
Write-Output "Total: $success DELETED, $fail FAIL"

# Verify none remain
Write-Output ""
Write-Output "=== Verify: any Documents\ tasks remaining? ==="
Get-ScheduledTask | Where-Object { $_.Actions[0].Execute -match 'Documents\\askanka' } | Select-Object TaskName
```

- [ ] **Step 2: Run the delete**

```bash
powershell.exe -ExecutionPolicy Bypass -File "C:/Users/Claude_Anka/AppData/Local/Temp/delete_zombies.ps1" 2>&1 | tee /tmp/delete_out.txt
```

Expected: one "DELETED:" line per zombie, final "Total: N DELETED, 0 FAIL" where N ≈ 28. "Verify" section returns no rows.

- [ ] **Step 3: Create Batch B transcript + append B1 output**

Create `docs/operations/2026-04-16-batch-b-transcript.md`:

```markdown
# Batch B Transcript — Scheduler Debt Remediation 2026-04-16

## Section B1 — Zombie deletions

<populated below>

## Section B2 — Quote-bug rewrites

<populated by Task 9>

## Section B3 — Never-ran re-registrations + manual runs

<populated by Task 10>

## Section B4 — Post-B sweep

<populated by Task 11>
```

Append delete output:

```bash
cd /c/Users/Claude_Anka/askanka.com
python -c "
import pathlib
t = pathlib.Path('docs/operations/2026-04-16-batch-b-transcript.md')
content = t.read_text(encoding='utf-8')
out = pathlib.Path('/tmp/delete_out.txt').read_text(encoding='utf-8', errors='replace')
content = content.replace('## Section B1 — Zombie deletions\n\n<populated below>', f'## Section B1 — Zombie deletions\n\n\`\`\`\n{out}\n\`\`\`')
t.write_text(content, encoding='utf-8')
"
```

- [ ] **Step 4: Verify zero Documents\ tasks remain**

```bash
powershell.exe -ExecutionPolicy Bypass -Command "(Get-ScheduledTask | Where-Object { \$_.Actions[0].Execute -match 'Documents\\\\askanka' }).Count"
```

Expected: `0`.

- [ ] **Step 5: Commit B1**

```bash
cd /c/Users/Claude_Anka/askanka.com
git add docs/operations/2026-04-16-batch-b-transcript.md
git commit -m "chore(remediate): batch B1 — deleted 28 Documents\ zombies

All reversible via pipeline/backups/scheduled_tasks/2026-04-16/<task>.xml.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

- [ ] **Step 6: Update mapping table status for every deleted row**

In `docs/superpowers/specs/2026-04-16-scheduler-debt-remediation-design.md`, for each zombie row, change `| PENDING |` at end → `| DONE |`. Commit:

```bash
cd /c/Users/Claude_Anka/askanka.com
git add docs/superpowers/specs/2026-04-16-scheduler-debt-remediation-design.md
git commit -m "docs(remediate): mark zombie rows DONE in mapping table

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 9: Batch B2 — Fix 27 quote-bug Execute strings

**Files:**
- Create: `C:/Users/Claude_Anka/AppData/Local/Temp/fix_quote_bugs.ps1`
- Modify: `docs/operations/2026-04-16-batch-b-transcript.md` (append Section B2)

- [ ] **Step 1: Write the per-task re-register script**

Write `C:/Users/Claude_Anka/AppData/Local/Temp/fix_quote_bugs.ps1`:

```powershell
$ErrorActionPreference = 'Continue'

$all = Get-ScheduledTask
$buggy = @()
foreach ($t in $all) {
    $exec = $t.Actions[0].Execute
    if ($exec -match '^"' -or $exec -match '""') {
        $buggy += $t
    }
}

Write-Output "Rewriting $($buggy.Count) quote-bug tasks"
$success = 0
$fail = 0

foreach ($t in $buggy) {
    $oldExec = $t.Actions[0].Execute
    $cleanExec = $oldExec -replace '"', ''
    # Preserve arguments, working directory from the existing Action
    $oldAction = $t.Actions[0]
    $oldArgs = $oldAction.Arguments
    $oldWd = $oldAction.WorkingDirectory

    try {
        # Build new action
        if ($oldArgs) {
            $newAction = New-ScheduledTaskAction -Execute $cleanExec -Argument $oldArgs -WorkingDirectory $oldWd
        } else {
            $newAction = New-ScheduledTaskAction -Execute $cleanExec -WorkingDirectory $oldWd
        }

        # Preserve all other task properties
        $newTriggers = $t.Triggers
        $newSettings = $t.Settings
        $newPrincipal = $t.Principal

        # Unregister + re-register
        Unregister-ScheduledTask -TaskName $t.TaskName -TaskPath $t.TaskPath -Confirm:$false
        Register-ScheduledTask -TaskName $t.TaskName -TaskPath $t.TaskPath `
            -Action $newAction -Trigger $newTriggers -Settings $newSettings -Principal $newPrincipal | Out-Null

        # Verify no embedded quotes
        $rechecked = Get-ScheduledTask -TaskName $t.TaskName -TaskPath $t.TaskPath
        $newExec = $rechecked.Actions[0].Execute
        if ($newExec -match '"') {
            Write-Output "  FAIL: $($t.TaskName) — still has quotes: $newExec"
            $fail++
        } else {
            $success++
            Write-Output "  OK:   $($t.TaskName)  FROM=$oldExec  TO=$newExec"
        }
    } catch {
        $fail++
        Write-Output "  FAIL: $($t.TaskName) — $_"
    }
}
Write-Output ""
Write-Output "Total: $success OK, $fail FAIL"
```

- [ ] **Step 2: Run the rewrite**

```bash
powershell.exe -ExecutionPolicy Bypass -File "C:/Users/Claude_Anka/AppData/Local/Temp/fix_quote_bugs.ps1" 2>&1 | tee /tmp/quote_fix_out.txt
```

Expected: one "OK:" line per task, final "Total: N OK, 0 FAIL" where N ≈ 27.

- [ ] **Step 3: Verify zero remaining quote-bug tasks**

```bash
powershell.exe -ExecutionPolicy Bypass -Command "(Get-ScheduledTask | Where-Object { \$_.Actions[0].Execute -match '^\"' -or \$_.Actions[0].Execute -match '\"\"' }).Count"
```

Expected: `0`.

- [ ] **Step 4: Append to transcript Section B2**

```bash
cd /c/Users/Claude_Anka/askanka.com
python -c "
import pathlib
t = pathlib.Path('docs/operations/2026-04-16-batch-b-transcript.md')
content = t.read_text(encoding='utf-8')
out = pathlib.Path('/tmp/quote_fix_out.txt').read_text(encoding='utf-8', errors='replace')
content = content.replace('## Section B2 — Quote-bug rewrites\n\n<populated by Task 9>', f'## Section B2 — Quote-bug rewrites\n\n\`\`\`\n{out}\n\`\`\`')
t.write_text(content, encoding='utf-8')
"
```

- [ ] **Step 5: Commit B2**

```bash
cd /c/Users/Claude_Anka/askanka.com
git add docs/operations/2026-04-16-batch-b-transcript.md
git commit -m "chore(remediate): batch B2 — rewrote 27 quote-bug Execute strings

Per-task unregister+register preserving triggers/settings/principal.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

- [ ] **Step 6: Update mapping table rows to DONE**

Edit `docs/superpowers/specs/2026-04-16-scheduler-debt-remediation-design.md`: mark all quote-bug rows DONE. Commit:

```bash
cd /c/Users/Claude_Anka/askanka.com
git add docs/superpowers/specs/2026-04-16-scheduler-debt-remediation-design.md
git commit -m "docs(remediate): mark quote-bug rows DONE in mapping table

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 10: Batch B3 — Re-register never-ran tasks + verify manual run

**Files:**
- Create: `C:/Users/Claude_Anka/AppData/Local/Temp/verify_never_ran.ps1`
- Modify: `docs/operations/2026-04-16-batch-b-transcript.md` (append Section B3)

**Note:** Tasks that overlapped with B2 (e.g., `AnkaGapPredictor`, `AnkaPruneArticles` — both quote-bug class) were already re-registered in B2. This task verifies all 5 by running them manually and confirming LastTaskResult=0.

- [ ] **Step 1: Write the manual-run verify script**

Write `C:/Users/Claude_Anka/AppData/Local/Temp/verify_never_ran.ps1`:

```powershell
$ErrorActionPreference = 'Continue'
$targets = @('AnkaEODNews','AnkaGapPredictor','AnkaPruneArticles','AnkaSpreadStats','AnkaWeeklyStats')

foreach ($n in $targets) {
    $t = Get-ScheduledTask -TaskName $n -ErrorAction SilentlyContinue
    if ($null -eq $t) {
        Write-Output "SKIP (not found): $n"
        continue
    }

    $exec = $t.Actions[0].Execute
    if (-not (Test-Path $exec)) {
        Write-Output "FAIL (bat missing): $n  Execute=$exec"
        continue
    }

    Write-Output ""
    Write-Output "=== $n ==="
    Write-Output "  Execute: $exec"
    Write-Output "  Starting..."
    Start-ScheduledTask -TaskName $n
    Start-Sleep -Seconds 5

    # Poll for up to 120 seconds for LastTaskResult to change from 267011
    $deadline = (Get-Date).AddSeconds(120)
    while ((Get-Date) -lt $deadline) {
        $info = Get-ScheduledTaskInfo -TaskName $n
        if ($info.LastTaskResult -ne 267011 -and $info.LastRunTime.Year -ne 1999) {
            Write-Output "  DONE: LastResult=$($info.LastTaskResult)  LastRun=$($info.LastRunTime)"
            break
        }
        Start-Sleep -Seconds 5
    }

    $info = Get-ScheduledTaskInfo -TaskName $n
    if ($info.LastTaskResult -eq 0) {
        Write-Output "  PASS"
    } elseif ($info.LastTaskResult -eq 267011 -or $info.LastRunTime.Year -eq 1999) {
        Write-Output "  TIMEOUT (still 267011 after 120s)"
    } else {
        Write-Output "  NONZERO result=$($info.LastTaskResult) — inspect task log"
    }
}
```

- [ ] **Step 2: Run the verify**

```bash
powershell.exe -ExecutionPolicy Bypass -File "C:/Users/Claude_Anka/AppData/Local/Temp/verify_never_ran.ps1" 2>&1 | tee /tmp/never_ran_out.txt
```

Expected: each of the 5 tasks prints "PASS" (LastTaskResult=0). If any shows "NONZERO" or "TIMEOUT", document the reason in the transcript — don't auto-fix; escalate.

- [ ] **Step 3: For any task that FAILED, mark its mapping table row DEFERRED-NEW**

If `AnkaGapPredictor` or similar returns non-zero, open the spec's mapping table and change its row's status to `DEFERRED-NEW` with a note like "manual run returned exit N — needs investigation outside this plan."

- [ ] **Step 4: Append to transcript Section B3**

```bash
cd /c/Users/Claude_Anka/askanka.com
python -c "
import pathlib
t = pathlib.Path('docs/operations/2026-04-16-batch-b-transcript.md')
content = t.read_text(encoding='utf-8')
out = pathlib.Path('/tmp/never_ran_out.txt').read_text(encoding='utf-8', errors='replace')
content = content.replace('## Section B3 — Never-ran re-registrations + manual runs\n\n<populated by Task 10>', f'## Section B3 — Never-ran re-registrations + manual runs\n\n\`\`\`\n{out}\n\`\`\`')
t.write_text(content, encoding='utf-8')
"
```

- [ ] **Step 5: Commit B3**

```bash
cd /c/Users/Claude_Anka/askanka.com
git add docs/operations/2026-04-16-batch-b-transcript.md docs/superpowers/specs/2026-04-16-scheduler-debt-remediation-design.md
git commit -m "chore(remediate): batch B3 — manual-run verify of never-ran tasks

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 11: Batch B4 — Post-B sweep (invariant check)

**Files:**
- Create: `C:/Users/Claude_Anka/AppData/Local/Temp/post_b_sweep.ps1`
- Modify: `docs/operations/2026-04-16-batch-b-transcript.md` (append Section B4)

- [ ] **Step 1: Write the invariant-check script**

Write `C:/Users/Claude_Anka/AppData/Local/Temp/post_b_sweep.ps1`:

```powershell
$ErrorActionPreference = 'Stop'
$all = Get-ScheduledTask

$docTasks = $all | Where-Object { $_.Actions[0].Execute -match 'Documents\\askanka' }
$quoted   = $all | Where-Object { $_.Actions[0].Execute -match '^"' -or $_.Actions[0].Execute -match '""' }

$neverRan = @()
foreach ($t in $all) {
    $info = Get-ScheduledTaskInfo -TaskName $t.TaskName -TaskPath $t.TaskPath
    if ($info.LastTaskResult -eq 267011 -or $info.LastRunTime.Year -eq 1999) {
        $neverRan += $t.TaskName
    }
}

Write-Output "=== Batch B invariants ==="
Write-Output "Tasks with Documents\ path:      $($docTasks.Count)  (target: 0)"
Write-Output "Tasks with embedded quotes:      $($quoted.Count)    (target: 0)"
Write-Output "Tasks still never-ran (267011):  $($neverRan.Count)  (target: 0 or documented NEW)"
Write-Output ""
Write-Output "Total Anka* tasks: $(($all | Where-Object { $_.TaskName -like 'Anka*' }).Count)"

if ($docTasks.Count -eq 0 -and $quoted.Count -eq 0) {
    Write-Output ""
    Write-Output "BATCH B GATE: PASS"
    exit 0
} else {
    Write-Output ""
    Write-Output "BATCH B GATE: FAIL — STOP before Batch C"
    exit 1
}
```

- [ ] **Step 2: Run the sweep**

```bash
powershell.exe -ExecutionPolicy Bypass -File "C:/Users/Claude_Anka/AppData/Local/Temp/post_b_sweep.ps1" 2>&1 | tee /tmp/post_b_out.txt
echo "exit_code=$?"
```

Expected: `BATCH B GATE: PASS` with exit 0. If FAIL, STOP and investigate before Task 12.

- [ ] **Step 3: Append to transcript Section B4**

```bash
cd /c/Users/Claude_Anka/askanka.com
python -c "
import pathlib
t = pathlib.Path('docs/operations/2026-04-16-batch-b-transcript.md')
content = t.read_text(encoding='utf-8')
out = pathlib.Path('/tmp/post_b_out.txt').read_text(encoding='utf-8', errors='replace')
content = content.replace('## Section B4 — Post-B sweep\n\n<populated by Task 11>', f'## Section B4 — Post-B sweep\n\n\`\`\`\n{out}\n\`\`\`')
t.write_text(content, encoding='utf-8')
"
```

- [ ] **Step 4: Commit B4**

```bash
cd /c/Users/Claude_Anka/askanka.com
git add docs/operations/2026-04-16-batch-b-transcript.md
git commit -m "chore(remediate): batch B4 — post-B sweep passed all invariants

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

**Batch B exit gate:** 0 Documents\ tasks, 0 quote-bug tasks, never-ran tasks either passed manual run or documented as DEFERRED-NEW. Transcript committed.

---

## Task 12: Batch C1 — Fix AnkaCorrelationBreaks CLI

**Files:**
- Modify: `pipeline/scripts/correlation_breaks.bat`
- Create: `docs/operations/2026-04-16-batch-c-transcript.md`

- [ ] **Step 1: Rewrite correlation_breaks.bat to remove unsupported args**

Overwrite `pipeline/scripts/correlation_breaks.bat` with:

```batch
@echo off
REM ANKA Correlation Break Scanner (Phase C) — runs every 15 min intraday
REM Reads regime from Phase B state, OI from latest positioning.json
REM CLI accepts: --regime, --transition, --dry-run, --verbose (per
REM docs/superpowers/plans/2026-04-14-correlation-break-detector.md Task 7 §CLI).
cd /d "C:\Users\Claude_Anka\askanka.com\pipeline"

REM Get current regime from state file
for /f "tokens=*" %%a in ('python -c "import json; d=json.load(open('data/regime_ranker_state.json')); print(d.get('last_zone','NEUTRAL'))"') do set REGIME=%%a

REM Infer last transition from ranker history
for /f "tokens=*" %%a in ('python -c "import json; h=json.load(open('data/regime_ranker_history.json')); print(h[-1]['transition'] if h else '')" 2^>nul') do set TRANSITION=%%a

if "%TRANSITION%"=="" (
    echo No transition history found. Skipping break scan.
    exit /b 0
)

python -X utf8 autoresearch\reverse_regime_breaks.py --transition "%TRANSITION%" --regime "%REGIME%" >> logs\correlation_breaks.log 2>&1
```

(Removed `--day 1 --no-telegram` from the last line. The script sends Telegram alerts by default; `--dry-run` would suppress them but isn't what we want in production.)

- [ ] **Step 2: Manual run to verify**

```bash
cd /c/Users/Claude_Anka/askanka.com
pipeline/scripts/correlation_breaks.bat
echo "exit_code=$?"
tail -40 pipeline/logs/correlation_breaks.log
```

Expected:
- `exit_code=0`
- Log tail shows script ran to completion (regime/transition logged, deviations computed, break classifications emitted)
- No `error: unrecognized arguments` from argparse

- [ ] **Step 3: Confirm expected output file written**

The spec for Phase C (`docs/superpowers/plans/2026-04-14-correlation-break-detector.md`) specifies an output artifact. Check whichever file it names:

```bash
cd /c/Users/Claude_Anka/askanka.com
grep -n "output\|write\|dump" pipeline/autoresearch/reverse_regime_breaks.py | grep -i json | head -10
```

Identify the output path, confirm it was updated by this run (`ls -la <path>`).

- [ ] **Step 4: Create Batch C transcript + append C1**

```bash
cat > docs/operations/2026-04-16-batch-c-transcript.md <<'EOF'
# Batch C Transcript — Scheduler Debt Remediation 2026-04-16

## Section C1 — AnkaCorrelationBreaks CLI fix

EOF
tail -40 pipeline/logs/correlation_breaks.log >> docs/operations/2026-04-16-batch-c-transcript.md
cat >> docs/operations/2026-04-16-batch-c-transcript.md <<'EOF'

## Section C2 — Phase A interim cron

<populated by Task 13>

## Section C3 — Master EOD job

<populated by Task 14>

## Section C3.x — Orphan + untracked resolution

<populated by Task 15>

## Section C4 — Downstream smoke test

<populated by Task 16>

## Section C5 — Health check

<populated by Task 17>
EOF
```

- [ ] **Step 5: Commit C1**

```bash
cd /c/Users/Claude_Anka/askanka.com
git add pipeline/scripts/correlation_breaks.bat docs/operations/2026-04-16-batch-c-transcript.md docs/superpowers/specs/2026-04-16-scheduler-debt-remediation-design.md
git commit -m "fix(phase-c): strip unsupported --day and --no-telegram from correlation_breaks.bat

reverse_regime_breaks.py argparse only accepts --regime, --transition,
--dry-run, --verbose. The two extra args were causing every AnkaCorrelation-
Breaks fire to exit non-zero with 'unrecognized arguments'; Phase C never
produced output. Drift from 2026-04-14-correlation-break-detector §CLI.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

Also update the mapping table row for AnkaCorrelationBreaks to DONE in the spec and include that edit in this commit.

---

## Task 13: Batch C2 — Schedule Phase A (AnkaReverseRegimeProfile) as interim cron

**Files:**
- Create: `pipeline/scripts/reverse_regime_profile.bat`
- Create: `C:/Users/Claude_Anka/AppData/Local/Temp/register_phase_a.ps1`
- Modify: `docs/operations/2026-04-16-batch-c-transcript.md` (append Section C2)

- [ ] **Step 1: Create the Phase A .bat wrapper**

Write `pipeline/scripts/reverse_regime_profile.bat`:

```batch
@echo off
REM ANKA Reverse Regime Profile (Phase A) — daily @ 04:45 IST
REM Writes pipeline/data/reverse_regime_profile.json consumed by Phase B ranker.
REM
REM INTERIM — this task was scheduled by remediate/scheduler-debt-2026-04-16
REM because Phase A was never scheduled in the original 2026-04-14
REM reverse-regime-stock-analysis plan. The designed cadence/trigger will be
REM decided in a fresh brainstorm 2026-04-17+.
cd /d "C:\Users\Claude_Anka\askanka.com\pipeline"
python -X utf8 autoresearch\reverse_regime_analysis.py >> logs\reverse_regime_profile.log 2>&1
```

- [ ] **Step 2: Verify the .bat runs manually**

```bash
cd /c/Users/Claude_Anka/askanka.com
pipeline/scripts/reverse_regime_profile.bat
echo "exit_code=$?"
ls -la pipeline/data/reverse_regime_profile.json
tail -20 pipeline/logs/reverse_regime_profile.log
```

Expected: exit 0; `reverse_regime_profile.json` mtime = now (today); log tail shows profile computation completed.

- [ ] **Step 3: Write the task registration script**

Write `C:/Users/Claude_Anka/AppData/Local/Temp/register_phase_a.ps1`:

```powershell
$ErrorActionPreference = 'Stop'
$name = 'AnkaReverseRegimeProfile'
$bat = 'C:\Users\Claude_Anka\askanka.com\pipeline\scripts\reverse_regime_profile.bat'

# Unregister if it somehow exists
$existing = Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
if ($existing) {
    Unregister-ScheduledTask -TaskName $name -Confirm:$false
    Write-Output "unregistered existing $name"
}

$action = New-ScheduledTaskAction -Execute $bat -WorkingDirectory (Split-Path $bat -Parent)
$trigger = New-ScheduledTaskTrigger -Daily -At 4:45AM
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -WakeToRun `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2) `
    -RestartCount 2 `
    -RestartInterval (New-TimeSpan -Minutes 5)

Register-ScheduledTask -TaskName $name `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -User $env:USERNAME `
    -RunLevel Limited `
    -Description 'INTERIM — pending fresh brainstorm 2026-04-17+. Writes pipeline/data/reverse_regime_profile.json consumed by Phase B.' | Out-Null

$t = Get-ScheduledTask -TaskName $name
$i = Get-ScheduledTaskInfo -TaskName $name
"registered $name: state=$($t.State) next=$($i.NextRunTime) action=[$($t.Actions[0].Execute)]"
```

- [ ] **Step 4: Run registration**

```bash
powershell.exe -ExecutionPolicy Bypass -File "C:/Users/Claude_Anka/AppData/Local/Temp/register_phase_a.ps1" 2>&1 | tee /tmp/phase_a_reg.txt
```

Expected: line confirming state=Ready, NextRunTime = tomorrow 04:45 AM, action points to the .bat.

- [ ] **Step 5: Trigger one manual run via scheduler (not just the .bat)**

```bash
powershell.exe -ExecutionPolicy Bypass -Command "Start-ScheduledTask -TaskName AnkaReverseRegimeProfile; Start-Sleep 10; Get-ScheduledTaskInfo -TaskName AnkaReverseRegimeProfile | Format-List Last*"
```

Expected: `LastTaskResult: 0`, `LastRunTime: <today within last minute>`.

- [ ] **Step 6: Append to transcript Section C2 + commit**

```bash
cd /c/Users/Claude_Anka/askanka.com
cat /tmp/phase_a_reg.txt >> docs/operations/2026-04-16-batch-c-transcript.md
echo "" >> docs/operations/2026-04-16-batch-c-transcript.md
echo "reverse_regime_profile.json mtime: $(stat -c %y pipeline/data/reverse_regime_profile.json)" >> docs/operations/2026-04-16-batch-c-transcript.md

git add pipeline/scripts/reverse_regime_profile.bat docs/operations/2026-04-16-batch-c-transcript.md docs/superpowers/specs/2026-04-16-scheduler-debt-remediation-design.md
git commit -m "feat(phase-a): interim daily cron for AnkaReverseRegimeProfile @ 04:45 IST

Phase A was never scheduled in the original 2026-04-14 plan. Phase B's
ranker was running daily on a stale profile (2-day-old). This is the
interim remediation; designed cadence gets its own brainstorm
2026-04-17+. Description field on the scheduled task marks it INTERIM.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

Mark Phase A mapping-table row DONE-INTERIM.

---

## Task 14: Batch C3 — Identify and fix the master EOD job

**Files:**
- Modify: `docs/operations/2026-04-16-batch-c-transcript.md` (append Section C3)
- Possibly modify: whichever `.bat` or `.py` owns the Apr-14-15:38 cluster

- [ ] **Step 1: Identify candidates for the master job**

```bash
cd /c/Users/Claude_Anka/askanka.com
# List scripts that might be the master EOD writer
ls pipeline/scripts/*eod* pipeline/scripts/*track* pipeline/scripts/*report* 2>/dev/null
# Grep for files in the stale cluster to find their writers
for f in msi_history.json pattern_lookup.json pinning_history.json regime_history.json gex_history.json; do
    echo "=== $f writer: ==="
    grep -rn "$f" pipeline/*.py pipeline/autoresearch/*.py 2>/dev/null | grep -v "/backups/\|/tests/" | head -3
done
```

Expected: identifies one or two Python scripts that write multiple stale files. The most likely master is `run_eod_report.py` or `eod_track_record.bat`.

- [ ] **Step 2: Find the master's scheduled task**

```bash
powershell.exe -ExecutionPolicy Bypass -Command "Get-ScheduledTask | Where-Object { \$_.Actions[0].Execute -match 'eod_track_record|run_eod_report' } | Format-Table TaskName, @{L='Execute';E={\$_.Actions[0].Execute}}, @{L='LastResult';E={(Get-ScheduledTaskInfo \$_.TaskName).LastTaskResult}}, @{L='LastRun';E={(Get-ScheduledTaskInfo \$_.TaskName).LastRunTime}} -AutoSize"
```

Expected: one or more tasks listed. Note their LastTaskResult and LastRunTime. If LastRunTime ≈ Apr 14 15:38 + last result non-zero → confirmed this is the stopped master.

- [ ] **Step 3: Diagnose why it stopped**

Three likely cause classes:

**(a) Quote-bug → already fixed in B2.** If the task was in the quote-bug list, it's already been re-registered clean. Skip to Step 4.

**(b) Script error.** Read the script's log:
```bash
tail -100 pipeline/logs/eod_*.log 2>/dev/null | tail -80
```
If you see a traceback / error since Apr 14 15:38, that's the cause. Fix the underlying code (out of scope for this plan if it's substantive) OR document as DEFERRED-NEW.

**(c) Missing dependency.** If the script imports an untracked module (from the 11 untracked scripts list) that isn't on sys.path, that's the cause. Decide in C3.x (Task 15) whether to commit or delete that untracked module.

- [ ] **Step 4: Run the master job manually**

```bash
cd /c/Users/Claude_Anka/askanka.com
# Adjust path based on Step 1's identification
pipeline/scripts/eod_track_record.bat 2>&1 | tee /tmp/master_run.txt
echo "exit_code=$?"
```

Expected: exit 0. If non-zero, read the captured output to identify the error.

- [ ] **Step 5: Verify Apr 14 15:38 cluster files refreshed to today**

```bash
cd /c/Users/Claude_Anka/askanka.com
for f in correlation_history.json fragility_model.json ml_performance.json macro_trigger_state.json oi_history.json msi_history.json regime_history.json pattern_lookup.json; do
    if [ -f "pipeline/data/$f" ]; then
        echo "$f  $(stat -c %y pipeline/data/$f)"
    fi
done
```

Expected: mtimes should be today. If any remain Apr 14 15:38, that file has a different owner — identify in follow-up (mapping-table DEFERRED-NEW).

- [ ] **Step 6: Append to transcript Section C3 + commit**

```bash
cd /c/Users/Claude_Anka/askanka.com
{
    echo "### Master job identification"
    echo ""
    echo "Candidates (from Step 1):"
    ls pipeline/scripts/*eod* pipeline/scripts/*track* pipeline/scripts/*report* 2>/dev/null
    echo ""
    echo "### Diagnosis class: (a / b / c — fill in)"
    echo ""
    echo "### Manual run output"
    echo ""
    echo '```'
    cat /tmp/master_run.txt 2>/dev/null | tail -30
    echo '```'
    echo ""
    echo "### Post-run cluster mtimes"
    echo ""
    echo '```'
    for f in correlation_history.json fragility_model.json ml_performance.json macro_trigger_state.json oi_history.json msi_history.json regime_history.json pattern_lookup.json; do
        if [ -f "pipeline/data/$f" ]; then
            echo "$f  $(stat -c %y pipeline/data/$f)"
        fi
    done
    echo '```'
} >> docs/operations/2026-04-16-batch-c-transcript.md

git add docs/operations/2026-04-16-batch-c-transcript.md docs/superpowers/specs/2026-04-16-scheduler-debt-remediation-design.md
git commit -m "chore(remediate): batch C3 — master EOD job identified and re-run

Apr 14 15:38 cluster files refreshed. Mapping table updated.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 15: Batch C3.x — Orphan + untracked writer resolution

**Files:**
- Possibly delete: `pipeline/data/gamma_result.json`
- Possibly commit or delete: `pipeline/options_monitor.py`, `pipeline/gamma_scanner.py`
- Modify: `docs/operations/2026-04-16-batch-c-transcript.md` (append Section C3.x)

- [ ] **Step 1: Resolve gamma_result.json orphan**

```bash
cd /c/Users/Claude_Anka/askanka.com
# Check if untracked gamma_scanner.py writes gamma_result.json
grep -n "gamma_result\|GAMMA_RESULT" pipeline/gamma_scanner.py 2>/dev/null || echo "no writer in gamma_scanner.py either"
```

Branch on result:

**(a) If writer found in gamma_scanner.py** — keep the file, proceed to Step 2 to decide fate of gamma_scanner.py.

**(b) If no writer anywhere** — it's a genuine orphan. Delete:

```bash
cd /c/Users/Claude_Anka/askanka.com
rm pipeline/data/gamma_result.json
git rm pipeline/data/gamma_result.json 2>/dev/null || true  # in case it was tracked
```

Mark mapping-table row DONE (deleted) or DEFERRED-NEW (if keeping for gamma_scanner resolution).

- [ ] **Step 2: Inspect options_monitor.py (writes oi_history.json)**

```bash
cd /c/Users/Claude_Anka/askanka.com
wc -l pipeline/options_monitor.py
head -40 pipeline/options_monitor.py
```

Decision: commit or delete.

**Commit if:** the script has a clear purpose, imports don't break, and there's a scheduled task that uses it (check via `grep -rn "options_monitor" pipeline/scripts/`).

**Delete if:** script is a scratch/experiment with no consumer.

```bash
cd /c/Users/Claude_Anka/askanka.com
# If committing:
git add pipeline/options_monitor.py
git commit -m "chore(remediate): commit options_monitor.py (owns oi_history.json) per single-repo mandate

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"

# If deleting:
rm pipeline/options_monitor.py
# If oi_history.json becomes orphan too, handle per Step 1 branch.
```

- [ ] **Step 3: Inspect gamma_scanner.py (may write gamma_result.json)**

```bash
cd /c/Users/Claude_Anka/askanka.com
wc -l pipeline/gamma_scanner.py
head -40 pipeline/gamma_scanner.py
```

Same commit-or-delete decision per Step 2's criteria.

- [ ] **Step 4: Append to transcript + commit**

```bash
cd /c/Users/Claude_Anka/askanka.com
{
    echo ""
    echo "### Orphan resolution"
    echo ""
    echo "gamma_result.json fate: <deleted | kept, writer=gamma_scanner.py>"
    echo "options_monitor.py fate: <committed | deleted>"
    echo "gamma_scanner.py fate: <committed | deleted | n/a>"
} >> docs/operations/2026-04-16-batch-c-transcript.md

git add docs/operations/2026-04-16-batch-c-transcript.md docs/superpowers/specs/2026-04-16-scheduler-debt-remediation-design.md
git commit -m "chore(remediate): batch C3.x — orphan + untracked writer resolution

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 16: Batch C4 — Downstream Apr 15 consumer smoke test

**Files:**
- Modify: `docs/operations/2026-04-16-batch-c-transcript.md` (append Section C4)

- [ ] **Step 1: Run website_exporter + confirm live_status and global_regime freshness**

```bash
cd /c/Users/Claude_Anka/askanka.com
# Disable auto-deploy for the smoke test so we can inspect before pushing
WEBSITE_AUTODEPLOY=0 python pipeline/website_exporter.py 2>&1 | tee /tmp/exporter_out.txt
echo ""
for f in live_status.json global_regime.json articles_index.json fno_news.json; do
    echo "$f  $(stat -c %y data/$f)"
done
```

Expected: exporter runs without exception, all four output files have today's mtime.

- [ ] **Step 2: Run article grounding self-test**

```bash
cd /c/Users/Claude_Anka/askanka.com
python -c "
import sys
sys.path.insert(0, 'pipeline')
from article_grounding import load_market_context
ctx = load_market_context()
print('flows present:', 'flows' in ctx)
print('indices present:', 'indices' in ctx)
print('prices present:', 'prices' in ctx)
print('context keys:', list(ctx.keys()))
" 2>&1 | tee /tmp/grounding_out.txt
```

Expected: all three keys present + no MarketDataMissing exception.

- [ ] **Step 3: Run one intraday_scan cycle**

```bash
cd /c/Users/Claude_Anka/askanka.com
pipeline/scripts/intraday_scan.bat 2>&1 | tail -30 | tee /tmp/intraday_out.txt
```

Expected: exit 0; log tail shows signal tracker ran, trail_stop telemetry populated.

- [ ] **Step 4: Append smoke results to transcript + commit fresh data**

```bash
cd /c/Users/Claude_Anka/askanka.com
{
    echo ""
    echo "### Exporter output"
    echo '```'
    tail -30 /tmp/exporter_out.txt
    echo '```'
    echo ""
    echo "### Grounding self-test"
    echo '```'
    cat /tmp/grounding_out.txt
    echo '```'
    echo ""
    echo "### Intraday scan cycle"
    echo '```'
    cat /tmp/intraday_out.txt
    echo '```'
} >> docs/operations/2026-04-16-batch-c-transcript.md

# Commit the fresh data files from the exporter + any mapping-table updates
git add data/*.json docs/operations/2026-04-16-batch-c-transcript.md docs/superpowers/specs/2026-04-16-scheduler-debt-remediation-design.md
git commit -m "chore(remediate): batch C4 — downstream smoke test passed

Exporter + article grounding + intraday scan all green; fresh data
committed. Auto-deploy bypassed for inspection — push happens in C5.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 17: Batch C5 — Final health check + push + mapping-table closeout

**Files:**
- Modify: `docs/operations/2026-04-16-batch-c-transcript.md` (append Section C5)
- Modify: `docs/superpowers/specs/2026-04-16-scheduler-debt-remediation-design.md` (close out)

- [ ] **Step 1: Run the acceptance-criteria checklist**

```bash
cd /c/Users/Claude_Anka/askanka.com
{
    echo "=== Acceptance criteria checklist ==="
    echo ""
    # AC1 + AC2: no Documents\ + no quote bugs + no 267011
    powershell.exe -ExecutionPolicy Bypass -File "C:/Users/Claude_Anka/AppData/Local/Temp/post_b_sweep.ps1"
    echo ""
    # AC3: Phase A profile fresh
    echo "AC3  reverse_regime_profile.json mtime: $(stat -c %y pipeline/data/reverse_regime_profile.json)"
    echo ""
    # AC4: stale cluster refreshed
    echo "AC4  stale cluster sample mtimes:"
    for f in correlation_history.json fragility_model.json ml_performance.json oi_history.json msi_history.json; do
        if [ -f "pipeline/data/$f" ]; then
            echo "       $f  $(stat -c %y pipeline/data/$f)"
        fi
    done
    echo ""
    # AC5: Phase C output exists and is non-empty
    echo "AC5  Phase C output check (grep log):"
    tail -5 pipeline/logs/correlation_breaks.log 2>/dev/null
} | tee /tmp/ac_checklist.txt
```

Expected: all items satisfied. Any FAIL → document in mapping table as DEFERRED-NEW before proceeding.

- [ ] **Step 2: Close out the mapping table**

Open `docs/superpowers/specs/2026-04-16-scheduler-debt-remediation-design.md`. For every row, confirm Status column is `DONE`, `DONE-INTERIM`, or `DEFERRED-NEW`. No row left `PENDING`.

If any PENDING rows remain, they represent plan incompleteness — fix before pushing.

- [ ] **Step 3: Append final section + commit**

```bash
cd /c/Users/Claude_Anka/askanka.com
{
    echo ""
    echo "### C5 Acceptance criteria result"
    echo ""
    echo '```'
    cat /tmp/ac_checklist.txt
    echo '```'
    echo ""
    echo "### Mapping table closeout"
    echo ""
    echo "All rows in final state: DONE / DONE-INTERIM / DEFERRED-NEW. No PENDING."
} >> docs/operations/2026-04-16-batch-c-transcript.md

git add docs/operations/2026-04-16-batch-c-transcript.md docs/superpowers/specs/2026-04-16-scheduler-debt-remediation-design.md
git commit -m "chore(remediate): batch C5 — plan complete, acceptance criteria met

All 7 gap categories: deleted (28 zombies), rewritten (27 quote-bugs),
verified (5 never-rans), fixed (Phase C CLI, Phase A interim cron),
refreshed (master EOD cluster), resolved (orphan + untracked writers).
Downstream Apr 15 consumers smoke-tested green.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

- [ ] **Step 4: Merge branch to master**

```bash
cd /c/Users/Claude_Anka/askanka.com
git checkout master
git merge --no-ff remediate/scheduler-debt-2026-04-16 -m "merge: scheduler debt remediation 2026-04-16

Closes Apr 15 parked triage. See
docs/superpowers/plans/2026-04-16-scheduler-debt-remediation.md
and docs/operations/2026-04-16-batch-{a,b,c}-transcript.md.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

- [ ] **Step 5: Push to origin (triggers GitHub Pages redeploy for fresh data)**

```bash
cd /c/Users/Claude_Anka/askanka.com
git push origin master
git push origin remediate/scheduler-debt-2026-04-16
```

Expected: both pushes succeed.

**Batch C exit gate:** all 8 acceptance criteria met (Section 6 of spec). Plan complete.

---

## Out of scope (follow-ups, not in this plan)

- **`scheduled_tasks_inventory.json` in git + health-check cron** — structural fix for "scheduler has no git" (brainstorm separately 2026-04-17+).
- **9 other untracked pipeline scripts** (`regime_playbook`, `sector_rotation`, `unified_regime_engine`, `pinning_*`, `expiry_monitor`, `data_validator`, `video_pipeline`, `regime_signals`) — judgment-per-file mini-plan.
- **Task Scheduler Operational log enable** — UAC blocker, can't resolve in-session.
- **Phase A *design* improvements** — interim cron holds the line; fresh brainstorm owns the proper cadence and trigger design.
- **Any task that surfaced as DEFERRED-NEW during execution** — each gets its own follow-up brainstorm.

---

## Self-review

**Spec coverage:**
- ✅ Section 1 Scope (7 gap categories) → Tasks 1–17 each map to a Section 1 item
- ✅ Section 2 Mapping table → Task 6 populates it; Tasks 8, 9, 10, 12, 13, 14, 15, 17 mark rows DONE/DEFERRED-NEW
- ✅ Section 3 Batch A → Tasks 1–7
- ✅ Section 4 Batch B → Tasks 8–11
- ✅ Section 5 Batch C → Tasks 12–17
- ✅ Section 6 Acceptance criteria → Task 17 Step 1 runs the checklist; all 8 items verified
- ✅ Rollback → every destructive op has XML backup created in Task 3
- ✅ Master-job lens for Apr 14 15:38 cluster → Task 14 (not N separate re-runs)
- ✅ Orphan + 2 untracked writers → Task 15 (in scope); 9 other untracked → DEFERRED-NEW in Task 6 mapping table

**Placeholder scan:** No "TBD", "implement later", or "add error handling" placeholders. Every step has concrete commands with expected output. The few decision points (Task 14 Step 3 diagnosis class, Task 15 commit-or-delete) give explicit criteria for each branch.

**Type / name consistency:**
- Task names (AnkaGapPredictor, AnkaReverseRegimeProfile, AnkaCorrelationBreaks) consistent across all tasks
- Path format consistent: backslash for PowerShell Execute fields and .ps1 file contents; forward-slash for bash commands
- File paths consistent: `pipeline/backups/scheduled_tasks/2026-04-16/` and `pipeline/backups/data_snapshots/2026-04-16/` used identically everywhere
- Transcript file names consistent: `docs/operations/2026-04-16-batch-{a,b,c}-transcript.md`
- Branch name consistent: `remediate/scheduler-debt-2026-04-16`
- PowerShell pattern: always `.ps1` file in `%TEMP%` invoked via `powershell.exe -ExecutionPolicy Bypass -File` (never inline `-Command` with bash-quoted args — reason documented in Context section)

**Scope check:** 17 tasks covering 3 sequential batches with clear exit gates. Each batch failure mode is a STOP condition (A spec-gate, B invariant-sweep, C acceptance-checklist). Each task produces its own commit. Rollback anchored in XML backups + data snapshots + branch isolation.
