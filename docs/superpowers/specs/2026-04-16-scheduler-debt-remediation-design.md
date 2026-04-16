# Scheduler Debt Remediation — Design Spec

**Date:** 2026-04-16
**Author:** Bharat Ankaraju + Claude
**Status:** Design approved, ready for plan
**Follow-up of:** 2026-04-14 unified-repo-clockwork, 2026-04-14 Phase A/B/C reverse-regime suite, 2026-04-15 session-log parked triage items

---

## Context — The Apr 12–16 sequence

This remediation is not a new bug hunt. It closes debt accumulated across five days of progressive build:

- **Apr 12** — 7-layer pipeline foundation, terminal, narrative, spread composer. 284 tests. 30+ commits.
- **Apr 13** — Wired autoresearch + live Kite terminal. Absorbed the *USE EXISTING SYSTEMS* rule.
- **Apr 14** — Two big parallel builds on one day: repo unification (Documents\ → askanka.com) AND the Reverse Regime Engine (Phase A profile, Phase B ranker, Phase C correlation breaks). Scheduler grew and changed simultaneously; migration updated `.bat` files but not every `schtasks` Execute string; Phase A/B/C plans built code but didn't mandate "register as task + verify output" steps.
- **Apr 15** — Surface polish (website-cleanup-regime-score, website-recommendations-panel, article-grounding, trailing-stop-and-replay). Session log explicitly parked scheduler staleness as "new triage items" (fno_news, open_signals, msi_history). Chose surface ship over plumbing sweep.
- **Apr 16** — Parked triage compounded. Today's audit finds Phase A unscheduled (2-day-stale profile), Phase C CLI mismatch (never produces output), 28 Documents\ zombies, 27 embedded-quote-bug tasks, 5 never-ran tasks, ~20-file stale cluster at Apr 14 15:38, 11 untracked pipeline scripts.

**Framing:** This plan closes Apr 14's scheduler debt so Apr 15's downstream consumers (website, articles, recs panel, trail stop) can display the truth. The "same issues" feeling is exactly this — Apr 15 patched symptoms; we're now addressing producers.

---

## Section 1 — Scope

**In scope (7 gap categories):**

1. Phase A (`reverse_regime_analysis.py`) not scheduled → `reverse_regime_profile.json` 2 days stale; Phase B's input contract broken.
2. `AnkaCorrelationBreaks` CLI mismatch — `.bat` passes `--day 1 --no-telegram`; `reverse_regime_breaks.py` argparse expects `--regime / --transition / --dry-run / --verbose`. Phase C never produces output.
3. 28 scheduled tasks pointing to retired `C:\Users\Claude_Anka\Documents\askanka.com\` path (migration zombies).
4. 27 tasks with embedded `""` double-quote bugs in Execute strings — some never launch.
5. 5 tasks never ran (`LastTaskResult=267011`, `LastRunTime=1999-12-30`): `AnkaEODNews` (registered today 16:20 — likely fine), `AnkaGapPredictor`, `AnkaPruneArticles`, `AnkaSpreadStats`, `AnkaWeeklyStats`.
6. ~20-file stale cluster at Apr 14 15:38 in `pipeline/data/*.json` — symptom of a single master EOD job silently failing since Apr 14.
7. 2 untracked pipeline scripts that own stale-cluster files: `options_monitor.py` (owns `oi_history.json`), and `gamma_scanner.py` if it turns out to write `gamma_result.json` (grep came up empty — orphan suspected).

**Out of scope (deferred, each gets own future brainstorm):**

- Structural "scheduler has no git" problem — `scheduled_tasks_inventory.json` + health-check cron for file-age invariants.
- 9 other untracked pipeline scripts (`regime_playbook`, `sector_rotation`, `unified_regime_engine`, `pinning_*`, `expiry_monitor`, `data_validator`, `video_pipeline`, `regime_signals`) — judgment-per-file, not pure cleanup.
- Task Scheduler Operational log enable (needs UAC, can't resolve in-session).
- Phase A *design* improvements — this plan schedules Phase A as interim cron; proper design is fresh brainstorm.
- Investor deck review (separate artifact).
- Any algorithm / new signal work.

**Anchoring documents:**

- `docs/superpowers/specs/2026-04-14-unified-repo-clockwork-design.md` (proves Documents\ was archived + deleted → zombies safe to delete)
- `docs/superpowers/plans/2026-04-14-correlation-break-detector.md` (Phase C authoritative CLI)
- `docs/superpowers/plans/2026-04-14-reverse-regime-stock-analysis.md` (Phase A expected cadence)
- `docs/superpowers/plans/2026-04-14-daily-regime-stock-ranker.md` (Phase B input contract)
- `docs/superpowers/plans/2026-04-15-website-cleanup-regime-score.md` (downstream consumer)
- `docs/superpowers/plans/2026-04-15-website-recommendations-panel.md` (downstream consumer)
- `docs/superpowers/plans/2026-04-15-article-grounding.md` (downstream consumer)
- `docs/superpowers/plans/2026-04-15-trailing-stop-and-replay.md` (downstream consumer)
- `memory/project_session_2026_04_15.md` (parked triage items this plan closes)

---

## Section 2 — The diagnose artifact

A single mapping table embedded at the top of the implementation plan. One row per gap. Six columns:

| Gap | Evidence (file / task — what's wrong) | Bucket | Parent plan + § | Drift note | Remediation action |
|-----|---------------------------------------|--------|-----------------|------------|---------------------|

**Buckets:**
- **(i) Re-run** — parent plan exists; live state drifted; re-execute a specific plan step.
- **(ii) Hygiene** — parent plan says this should not exist or should look different; delete or rewrite.
- **(iii) NEW** — no parent plan covers this; flag for future brainstorm; do NOT fix in this plan.

**Seed rows (drafted now; plan produces the full table):**

| Gap | Evidence | Bucket | Parent plan + § | Drift note | Remediation action |
|-----|----------|--------|-----------------|------------|---------------------|
| 28 Documents\ zombies | `schtasks /query` shows Execute=`C:\Users\Claude_Anka\Documents\askanka.com\...` on 28 tasks | (ii) | `2026-04-14-unified-repo-clockwork` §Migration | Spec says Documents\ "archived then deleted" — these are post-migration leftovers | Batch B1: Unregister-ScheduledTask on all 28 after XML backup |
| AnkaCorrelationBreaks CLI | `.bat` passes `--day 1 --no-telegram`; script argparse rejects | (i) | `2026-04-14-correlation-break-detector` §CLI | `.bat` written against earlier CLI spec | Batch C1: rewrite `.bat` per §CLI, run once manually, confirm output file produced |
| Phase A not scheduled | No Anka* task executes `reverse_regime_analysis.py`; `reverse_regime_profile.json` = Apr 14 | (iii) interim (i) | — | Phase B runs anyway with 2-day-stale profile — *live data-integrity issue* | Batch C2: schedule `AnkaReverseRegimeProfile` @ 04:45 IST as INTERIM-BEFORE-BRAINSTORM |
| 27 quote-bug Execute strings | `Actions[0].Execute` contains `""...""` | (ii) | `2026-04-14-unified-repo-clockwork` §Migration | Re-registration side-effect during migration | Batch B2: per-task Unregister + Register with clean `New-ScheduledTaskAction -Execute` |
| 5 never-ran tasks | `LastTaskResult=267011`, `LastRunTime=1999-12-30` | (ii) | overlap with B2 | Quote-bug-class; re-registration clears both | Batch B3: re-register from XML backup, Start-ScheduledTask manually, confirm LastTaskResult=0 |
| Apr 14 15:38 cluster (~20 files) | 20+ `pipeline/data/*.json` share exact mtime Apr 14 15:38 | (i) master-job | `2026-04-14-unified-repo-clockwork` (task registry) | Single master EOD job wrote them all, stopped firing cleanly after Apr 14 | Batch C3: identify master job (likely `eod_track_record.bat` / `run_eod_report.py`), diagnose why it stopped, fix once |
| gamma_result.json orphan | File exists (231 bytes); no writer in codebase; `gamma_scanner.py` untracked | (ii) hygiene | — | Either orphan (delete) or writer is in untracked `gamma_scanner.py` (commit-or-delete) | Batch C3.x: grep untracked writer; if orphan, delete file; if untracked writer, decide commit / delete |
| 2 untracked writers (options_monitor, gamma_scanner?) | `git status` shows untracked; owns stale-cluster files | (ii) hygiene | — | Single-repo mandate violation | Batch C3.x: commit or delete per judgment after reading the scripts |
| 9 other untracked scripts | `git status` — 9 files unrelated to stale cluster | (iii) NEW | — | Single-repo mandate; judgment-per-file | Flag in mapping; defer to own mini-plan |

**Why this is the anchor artifact:** every Batch-B and Batch-C step cites a row number in this table. If a step has no row, it's out of scope. If a row has no Remediation-action, the plan is not complete.

---

## Section 3 — Batch A: Backup + verification (zero destructive ops)

**Goal:** Produce the mapping table. Make every destructive step in Batch B/C reversible. No scheduler state changes.

**Steps:**

1. **Export XML for every affected scheduled task** via `Export-ScheduledTask` → `pipeline/backups/scheduled_tasks/2026-04-16/*.xml`. Covers: 28 zombies, 27 quote-bug tasks, 5 never-ran tasks, `AnkaCorrelationBreaks`, plus any task touched by Batch C. Deduplicated.

2. **Produce the full mapping table** — populate every row for all 7 gap categories + the orphan/untracked rows. Write to this spec's implementation plan.

3. **Dry-run every deletion and re-registration.** For each zombie: re-confirm Documents\ in Execute. For each quote-bug fix: print proposed-clean vs current-broken Execute. For each never-ran task: confirm target `.bat` exists on disk.

4. **Verify the 2026-04-14-unified-repo-clockwork spec claim.** Re-read §Migration, confirm "archived then deleted." If spec says anything else, STOP and escalate.

5. **Snapshot current stale intermediates** to `pipeline/backups/data_snapshots/2026-04-16/` before any Batch-C re-run that could overwrite.

6. **Commit XML backups + mapping-table spec** on dedicated branch `remediate/scheduler-debt-2026-04-16`. One commit per logical group.

**Exit gate:**

- XML backups exist for every affected task
- Mapping table written, self-reviewed for placeholders/contradictions, committed
- Dry-run transcript captured in `docs/operations/2026-04-16-batch-a-transcript.md` (committed)
- Snapshot of stale intermediates in place

**Blast radius:** zero. Read-only + file writes to backup/spec/transcript paths.

---

## Section 4 — Batch B: Hygiene (highest blast radius)

**Precondition:** Batch A exit gate passed.

**Step B1 — Delete 28 Documents\ zombies.**
- Re-read `2026-04-14-unified-repo-clockwork-design.md` §Migration (confirmation gate).
- For each of 28: `Unregister-ScheduledTask -TaskName <n> -Confirm:$false`.
- Per-task, not batched; log each to transcript.
- **Verify:** `Get-ScheduledTask | ? { $_.Actions[0].Execute -like '*Documents\askanka*' }` returns 0 rows.

**Step B2 — Fix 27 quote-bug Execute strings.**
- Strategy: `Unregister` + `Register-ScheduledTask` with clean `New-ScheduledTaskAction -Execute <path>`.
- Preserve trigger / settings / RunLevel / user from XML backup.
- Per-task, not batched (different API surface per task makes one-error-kills-run risk in batched mode).
- **Verify per task:** new Execute has zero embedded `"`; `Get-ScheduledTaskInfo` shows populated NextRunTime.

**Step B3 — Re-register the 5 never-ran tasks.**
- List: `AnkaEODNews`, `AnkaGapPredictor`, `AnkaPruneArticles`, `AnkaSpreadStats`, `AnkaWeeklyStats`.
- For each: confirm target `.bat` exists; if it does, re-registration from XML backup typically clears the quote-bug class (overlap with B2).
- `AnkaEODNews` exception: registered today, just verify state=Ready + clean action.
- **Run once manually** via `Start-ScheduledTask` inside this batch; confirm `LastTaskResult=0` within 2 min.
- If any target `.bat` missing OR manual run non-zero: do NOT re-schedule; log as (iii) NEW and escalate.

**Step B4 — Post-Batch-B sweep.**
- Re-run Batch A audit queries:
  - 0 tasks with Documents\ path
  - 0 tasks with `""` in Execute
  - 0 tasks with `LastTaskResult=267011` or `LastRunTime=1999`
  - Task count decreased by exactly 28 minus any legitimate B3 adds
- Commit transcript to `docs/operations/2026-04-16-batch-b-transcript.md`.

**Exit gate:**
- Sweep passes all four invariants
- Transcript committed
- Every re-registered task either ran clean (LastTaskResult=0) or is queued with valid NextRunTime

**Blast radius:** moderate. ~55 total ops (28 deletions + ~27 re-registrations). Reversible via `Register-ScheduledTask -Xml (Get-Content <backup>.xml | Out-String)`.

---

## Section 5 — Batch C: Wiring & freshness (master-job lens)

**Precondition:** Batch B exit gate passed.

**Step C1 — Fix AnkaCorrelationBreaks CLI.**
- Rewrite `pipeline/scripts/correlation_breaks.bat` to pass the args that `reverse_regime_breaks.py` actually accepts per `2026-04-14-correlation-break-detector.md` §CLI.
- **Verify:** manual run; script returns 0; expected output file written.

**Step C2 — Schedule Phase A (interim-before-brainstorm).**
- Register `AnkaReverseRegimeProfile`:
  - Action: `pipeline/scripts/reverse_regime_profile.bat` (create thin wrapper around `python reverse_regime_analysis.py`)
  - Trigger: Daily @ 04:45 IST
  - Settings: canonical Anka defaults (WakeToRun, AllowStartIfOnBatteries, StartWhenAvailable, MultipleInstances IgnoreNew, ExecutionTimeLimit 2h)
- Description field: `INTERIM — pending fresh brainstorm 2026-04-17+`.
- **Verify:** `Start-ScheduledTask` immediately; within 5 min confirm `pipeline/data/reverse_regime_profile.json` mtime = today + LastTaskResult=0.

**Step C3 — Master EOD job: identify, diagnose, fix once.**
- **Identify:** grep pipeline/ for writers of the Apr-14-15:38 cluster files (beyond the 6 we already owner-mapped). Candidates: `eod_track_record.bat`, `run_eod_report.py`, `eod_review.bat`. Cross-reference schtasks for a task that matches the 15:38 cadence.
- **Diagnose:** inspect the master task's logs + last run result. Likely root causes: quote-bug (→ fixed in B2 if task was in that set), .bat points to missing script, upstream data source change.
- **Fix once:** apply root-cause fix, manual run, confirm cluster files refresh to today's mtime.
- If master turns out to be *multiple* jobs: handle each; abandon "one master" framing; document in transcript.

**Step C3.x — Orphan / untracked writer resolution.**
- `gamma_result.json`: grep untracked `gamma_scanner.py` for the filename; if writer found, decide commit / delete per judgment; if orphan, delete `gamma_result.json`.
- `options_monitor.py` (untracked, owns `oi_history.json`): read the script, decide commit / delete. If committing, ensure a scheduled task exists and is healthy (may overlap with B2).

**Step C4 — Downstream Apr 15 consumer verification.**
- Run `pipeline/website_exporter.py` manually; confirm `live_status.json`, `global_regime.json`, `articles_index.json`, recommendations panel all render with today's timestamps.
- Run article grounding self-test against today's war article — confirm no `MarketDataMissing` exception.
- Run one full `intraday_scan.bat` cycle; confirm trail_stop telemetry populated on each open signal.
- Fresh `data/*.json` → auto-deploy commit + push (already wired in `website_exporter.py`).

**Step C5 — Post-Batch-C health check.**
- `pipeline/data/reverse_regime_profile.json` mtime = today
- Apr-14-15:38 cluster: files refreshed to today OR master-job fate documented in mapping table as NEW
- Mapping table: every row's Remediation-action = DONE or DEFERRED-NEW (no pending rows)
- Transcript committed to `docs/operations/2026-04-16-batch-c-transcript.md`

**Exit gate:** all of C5 above.

**Blast radius:** low. One CLI rewrite (reversible via git), one new task (reversible via Unregister), one-shot job re-runs (no state change).

---

## Section 6 — Acceptance criteria, rollback, risks, testing

**Acceptance criteria (measurable end-state invariants):**

1. `Get-ScheduledTask` returns 0 tasks whose Execute contains `Documents\askanka.com` or `""`.
2. 0 tasks with `LastTaskResult=267011` or `LastRunTime=1999-12-30`.
3. `pipeline/data/reverse_regime_profile.json` mtime = today.
4. Master EOD job identified + re-run successfully → Apr 14 15:38 cluster refreshed to today (OR master-job fate documented in mapping table as NEW if irrecoverable).
5. AnkaCorrelationBreaks manual run produces non-empty expected output file.
6. Mapping table: every row's Remediation-action = DONE or DEFERRED-NEW.
7. All three batch transcripts committed to `docs/operations/`.
8. No drive-by code changes outside the plan's batches.

**Rollback strategy:**

- Per-batch: every destructive op reversible via XML re-import from `pipeline/backups/scheduled_tasks/2026-04-16/`.
- Meta-rollback: entire plan runs on branch `remediate/scheduler-debt-2026-04-16`. Go off-rails → `git branch -D` + re-register from XML backups. Zero lasting damage.
- Snapshot intermediates in `pipeline/backups/data_snapshots/2026-04-16/` enable diff against re-run output.

**Risks + mitigations:**

| Risk | Likelihood | Blast | Mitigation |
|------|------------|-------|-----------|
| XML re-register changes task ID / GUID breaks downstream consumers | low | medium | Rollback-test on `AnkaGapPredictor` (already broken) before production-critical tasks |
| Master EOD turns out to be N > 1 jobs, not one | medium | low-medium | Handle each; abandon "one master" framing; document |
| Re-run writes worse output than stale | low | low | Snapshots in place |
| Hidden load-bearing Documents\ task | very low | high | §Migration spec re-read gate in Batch A — STOP if spec says keep anything |
| PowerShell encoding / special-char task names | low | low | `-FilePath` with UTF-8 `.ps1` files, not inline `-Command` |
| Plan execution spans sessions, context lost | medium | medium | Checkbox-task format per superpowers:writing-plans; each step independently re-runnable |

**Testing approach:**

- No new unit tests — ops remediation, not code.
- "Test" = each step has a verify command whose output goes to the batch transcript.
- End-to-end smoke at Batch C4: `website_exporter.py` + article grounding self-check + one full `intraday_scan.bat` cycle. All green → plan complete.

**Deferred (flagged, not in this plan):**

- `scheduled_tasks_inventory.json` in git + health-check cron (structural fix for "scheduler has no git")
- 9 other untracked pipeline scripts (judgment-per-file mini-plan)
- Task Scheduler Operational log enable (UAC blocker)
- Phase A *design* improvements (fresh brainstorm after interim cron lands)

---

## Self-review

**Placeholder scan:** None. Every section has concrete commands, paths, and verify steps. "TBD" absent.

**Internal consistency:**
- Batch A creates XML backups → Batch B uses them for rollback. ✓
- Batch A produces mapping table → Batches B/C cite row numbers. ✓
- Batch B fixes quote-bugs → Batch B3 notes overlap with B2 instead of duplicating. ✓
- Master-job lens in C3 is the single root-cause fix for the 20-file cluster, not 20 separate re-runs. ✓
- Acceptance criteria #4 explicitly allows "documented as NEW" escape hatch if master job is irrecoverable. ✓

**Scope check:** Focused. 7 in-scope gap categories, 4 explicit deferrals. Not mixing algorithm changes, not mixing UI work, not re-brainstorming Phase A design.

**Ambiguity:** The 27-vs-28 accounting in Batch B is clear (28 deletions + some overlap with B2/B3 re-registrations, tracked per-task in transcript). "Master EOD job" is hypothesis-framed, with explicit fallback if it turns out to be multiple.
