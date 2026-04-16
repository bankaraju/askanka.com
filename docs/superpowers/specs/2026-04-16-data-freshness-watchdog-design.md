# Data-Freshness Watchdog — Design Spec

**Date:** 2026-04-16
**Author:** Bharat + Claude (brainstorm session 2026-04-16)
**Status:** Approved for implementation planning
**Related:** `docs/superpowers/specs/2026-04-16-scheduler-debt-remediation-design.md` (predecessor — this spec addresses the root cause surfaced there)

---

## Context — why this exists

On 2026-04-16 a system audit found that critical pipeline outputs had been stale for 48 hours (Phase A `reverse_regime_profile.json` from Apr 14), 29 scheduled tasks were pointing at a retired path, and 5 tasks had never successfully run in their lifetime. None of this was visible to the operator until the audit — because the 69-task Windows scheduler has no git, no health reporting, and no freshness contract for its outputs.

That day's remediation plan (`2026-04-16-scheduler-debt-remediation`) cleaned up the backlog but did not fix the generator of the problem: **the scheduler is invisible**. This spec designs the watchdog that makes it visible.

**Problem statement:** detect stale pipeline outputs and broken scheduled tasks within hours of onset (not days), alert to Telegram with dedup and severity tiers, and prevent the inventory itself from drifting into staleness via a runtime drift check.

---

## Scope

**In scope:**
- A single Python watchdog script (`pipeline/watchdog.py`) invoked from two scheduled-task entries.
- A canonical inventory file (`pipeline/config/anka_inventory.json`) listing every `Anka*` scheduled task with tier, cadence class, expected outputs, and grace multiplier.
- Freshness checks on output file mtimes vs baked-in cadence formulas.
- Drift checks comparing the inventory against live scheduler state (`Get-ScheduledTask`).
- Digest-style Telegram alerts with stable-key deduplication, severity tiers, and `RESOLVED` tail.
- Staged rollout: shadow → critical-live → full.

**Out of scope (for future brainstorms):**
- Auto-remediation (the watchdog alerts; humans fix).
- Pre-commit hook enforcement of inventory updates (deferred to separate plumbing project).
- Monitoring non-`Anka*` scheduled tasks (OS-level or third-party jobs — the drift check ignores them).
- Any UI beyond Telegram + log file (Gap 3 handles terminal/website age badges separately).
- Article re-grounding (Gap 2) and reasoning-chain persistence (Gap 4) — their own specs.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                   Windows Task Scheduler                         │
│   ┌──────────────────────────┐   ┌────────────────────────────┐  │
│   │ AnkaWatchdogIntraday     │   │ AnkaWatchdogGate           │  │
│   │ every 15 min, Mon–Fri    │   │ 09:20 + 16:45 IST daily    │  │
│   │ 09:30–15:30 IST          │   │                            │  │
│   │ args: --tier critical    │   │ args: --all                │  │
│   └────────────┬─────────────┘   └────────────┬───────────────┘  │
└────────────────┼────────────────────────────────┼────────────────┘
                 │                                │
                 └────────────────┬───────────────┘
                                  ▼
                   ┌─────────────────────────────┐
                   │   pipeline/watchdog.py      │
                   │                             │
                   │  1. Load inventory          │
                   │  2. Query live scheduler    │──► PowerShell
                   │  3. File-freshness check    │──► os.stat(mtime)
                   │  4. Drift check             │
                   │  5. Load prior state        │──► watchdog_state.json
                   │  6. Emit digest             │──► telegram_bot.send_alert
                   │  7. Persist new state       │
                   └─────────────────────────────┘
                                  │
                                  ▼
                   ┌─────────────────────────────┐
                   │   Telegram (private chat)   │
                   │   Single digest message     │
                   └─────────────────────────────┘
```

**Reads from:**
- `pipeline/config/anka_inventory.json` (committed, canonical)
- Windows scheduler via `powershell.exe Get-ScheduledTask -TaskName Anka*`
- File mtimes on disk (via `os.stat`)
- `pipeline/data/watchdog_state.json` (runtime memory, gitignored)

**Writes to:**
- `pipeline/data/watchdog_state.json` (dedup state, gitignored — runtime)
- `pipeline/logs/watchdog.log` (every run, always — even when clean)
- `pipeline/logs/watchdog_alerts.log` (only when Telegram delivery fails)
- Telegram (only when there's something to report)

**Key property — the watchdog is not special.** It is itself a pair of `Anka*` scheduled tasks listed in the inventory. If `AnkaWatchdogIntraday` crashes, `AnkaWatchdogGate` will surface it on its next 09:20 / 16:45 run, and vice versa. The watchdog's own output files (`watchdog.log`, `watchdog_state.json`) are NOT in its own output list — no self-reference, no recursion risk. We do not need a watchdog-of-the-watchdog because the cross-check is already built in.

---

## Inventory schema — `pipeline/config/anka_inventory.json`

Example row:

```json
{
  "version": 1,
  "updated": "2026-04-16",
  "tasks": [
    {
      "task_name": "AnkaReverseRegimeProfile",
      "tier": "critical",
      "cadence_class": "daily",
      "outputs": ["pipeline/autoresearch/reverse_regime_profile.json"],
      "grace_multiplier": 1.5,
      "notes": "Phase A overnight profile @ 04:45 IST. Backbone of Phase B ranker."
    }
  ]
}
```

### Field contract

| Field | Values | Meaning |
|---|---|---|
| `task_name` | Exact `Anka*` name as registered in scheduler | Join key against live `Get-ScheduledTask` output. Case-sensitive exact match. |
| `tier` | `critical` \| `warn` \| `info` | `critical`/`warn` go to Telegram; `info` stays log-only. |
| `cadence_class` | `intraday` \| `daily` \| `weekly` | Selects the baked-in freshness formula (below). |
| `outputs` | list of paths from repo root | Files this task owns. Empty list = task has no file output (e.g., pre-market briefing sends Telegram and exits); freshness judged on task-last-run only. |
| `grace_multiplier` | float, default 1.5, recommended 1.25–2.0 | Forgiveness factor. Applied to the cadence-class base grace window. |
| `notes` | free text, required | Human context (which spec/plan justified this entry). Empty notes = future audit target. |

### Baked-in cadence formulas (in `watchdog.py`, not in inventory)

Window formula: `window = base_interval + base_grace × grace_multiplier`. A file is `OUTPUT_STALE` when `age_seconds > window`.

| cadence_class | base_interval | base_grace | effective grace @ `grace_multiplier=1.5` | total window @ 1.5× |
|---|---|---|---|---|
| `intraday` | 15 min (Mon–Fri 09:15–15:30 IST only) | 30 min | 45 min | 60 min |
| `daily` | 24 h | 4 h | 6 h | 30 h |
| `weekly` | 7 d | 1 d | 1.5 d | 8.5 d |

**Market-hours awareness:** `cadence_class=intraday` entries are only checked for staleness during 09:15–15:30 IST on weekdays. A 4-hour-old `live_status.json` at 20:00 IST overnight is fresh by definition; same 4-hour-old file at 10:00 IST Tuesday is stale.

**Bootstrap source:** first inventory version is seeded from (a) the remediation spec's mapping table rows 30–62 and (b) live `Anka*` task enumeration on 2026-04-16. Every row gets a `notes` field pointing to the spec/plan that justified it.

**Growth policy:** adding a new `Anka*` scheduled task without updating the inventory will trigger `ORPHAN_TASK` alerts on the next drift check — this is the forcing function. Operators are expected to update the inventory in the same commit as the task registration.

---

## Stale-detection logic

A task entry is evaluated in two parts — file freshness and task liveness:

### File freshness (per `outputs` entry)

1. If file does not exist → flag `OUTPUT_MISSING` and skip remaining steps (strictly louder than `OUTPUT_STALE`).
2. Compute `age_seconds = now - os.stat(output_path).st_mtime`.
3. Compute `window_seconds = base_interval + base_grace × grace_multiplier` (values from the cadence table above).
4. If `cadence_class == "intraday"` AND `now` is NOT within 09:15–15:30 IST weekdays → skip this file (always fresh outside market hours, regardless of age).
5. Else if `age_seconds > window_seconds` → flag `OUTPUT_STALE`.

### Task liveness (per task)

1. Query `Get-ScheduledTask -TaskName <task_name>` + `Get-ScheduledTaskInfo`.
2. If task doesn't exist in scheduler → flag `INVENTORY_GHOST` (inventory has it, scheduler doesn't).
3. If `LastTaskResult == 267011` AND `LastRunTime` is the 1999 sentinel → flag `TASK_NEVER_RAN`.
4. If `LastTaskResult != 0` → flag `TASK_STALE_RESULT` with the hex code.
5. If `LastRunTime` is older than expected for its cadence class + grace → flag `TASK_STALE_RUN`.

### Drift check (whole-inventory)

1. Enumerate all live `Get-ScheduledTask -TaskName Anka*`.
2. For each live task not in inventory → flag `ORPHAN_TASK`.
3. (Inventory-side ghosts are already caught in task liveness step 2.)

---

## Alert payload + dedup

### Digest format (one Telegram message per run)

```
🚨 Anka Watchdog — 2026-04-16 09:20 IST
Gate run • 3 issues

CRITICAL (2):
  • AnkaReverseRegimeProfile — output stale
    reverse_regime_profile.json  mtime 2026-04-14 15:38 (42h old, max 30h)
  • AnkaIntraday0930 — task never ran
    LastRunTime: 1999-12-30 (scheduler: registered, result 267011)

WARN (1):
  • AnkaSpreadStats — task + output stale
    spread_stats.json  mtime 2026-04-06 (10d old, max 8d)
    LastTaskResult: 0x1, LastRunTime: 2026-04-06 22:00

DRIFT (0)

RESOLVED (1):
  ✅ AnkaEODReview — fresh again (was stale 6h)
```

Sections with 0 items are printed with the count so the operator sees the check ran (not the watchdog skipped).

### Stable key for dedup

`f"{task_name}|{output_path_or_empty}|{stale_class}"` where `stale_class ∈ {OUTPUT_STALE, OUTPUT_MISSING, TASK_NEVER_RAN, TASK_STALE_RESULT, TASK_STALE_RUN, INVENTORY_GHOST, ORPHAN_TASK}`.

### Dedup state — `pipeline/data/watchdog_state.json`

```json
{
  "last_run": "2026-04-16T09:20:00+05:30",
  "active_issues": {
    "AnkaReverseRegimeProfile|pipeline/autoresearch/reverse_regime_profile.json|OUTPUT_STALE": {
      "first_seen": "2026-04-16T09:20:00+05:30",
      "last_seen": "2026-04-16T09:20:00+05:30",
      "alert_count": 1
    }
  }
}
```

### Message rules

| Condition | Operator sees |
|---|---|
| New stale item (key absent from prior state) | Full loud block with age, expected window, file path, task-last-run |
| Persistent stale, `alert_count < 6` | Compact one-line reminder: `• AnkaReverseRegimeProfile still stale (3rd run, 7h)` |
| `alert_count == 6` (approx 3 days of twice-daily gate runs) | Full loud block prefixed with `⚠️ STILL BROKEN AFTER 3 DAYS`. Then reminder-format again |
| Resolved (key in prior state, not current) | Single `RESOLVED` line |
| All clean | No Telegram message. One-line entry in `watchdog.log`: `2026-04-16 09:20 OK 69 tasks, 0 issues` |

### Telegram-unreachable fallback

If the `send_alert` call raises (network down, token revoked, rate-limited), the watchdog:
1. Writes the full digest to `pipeline/logs/watchdog_alerts.log` with a `TELEGRAM_FAILED <timestamp>` prefix.
2. Exits 0 (the check ran fine, only delivery failed — scheduler non-zero would be misleading).
3. Next run retries Telegram normally and includes any orphaned alerts from `watchdog_alerts.log` that haven't been acknowledged (acknowledgement = `last_seen` in state file matches the log entry's timestamp).

---

## Error handling + failure modes

| Failure | Watchdog behavior |
|---|---|
| Inventory file missing | Emergency Telegram (`🚨 watchdog has no inventory — skipping this run`), exit 1. Do NOT fall back to "enumerate whatever's in scheduler." Silent drift is the bug we're fixing. |
| Inventory JSON malformed | Same as above — emergency Telegram, exit 1. No partial parse. |
| PowerShell `Get-ScheduledTask` failure | Log warning, skip the drift check only, continue file freshness checks. Digest includes `DRIFT: skipped (scheduler query failed — see log)`. |
| File in inventory missing on disk | Flag `OUTPUT_MISSING` (strictly louder than stale). Dedup same as stale. |
| Telegram API failure | Fallback to `watchdog_alerts.log`, exit 0. |
| Malformed `watchdog_state.json` | Treat state as empty (first-run semantics), alert everything as new. Non-fatal. |
| Any other unhandled exception | Log full traceback, re-raise. Scheduler records non-zero exit, next audit surfaces it. |

### Invariant

The watchdog never silently swallows errors. Every branch above either alerts (Telegram or log) or crashes (scheduler captures).

---

## Testing strategy

### Unit tests — `pipeline/tests/test_watchdog_*.py`

1. **`test_watchdog_freshness.py`** — cadence math
   - Synthesize mtimes at grace-window edges (one-second-before, exactly-at, one-second-after) for each of 3 cadence classes; assert stale/fresh classification.
   - Market-hours: same mtime at 02:00 IST Saturday vs 10:00 IST Tuesday for an `intraday` file — fresh Saturday, stale Tuesday.
   - Grace multiplier math: `daily` + `grace_multiplier=1.5` → window = 24h + 4h × 1.5 = 30h, asserted explicitly. `intraday` + `grace_multiplier=2.0` → window = 15min + 30min × 2.0 = 75min.

2. **`test_watchdog_drift.py`** — drift detection
   - Inventory of 5 tasks + fake scheduler dump of 7 → exactly 2 `ORPHAN_TASK` entries.
   - Inventory of 5 + scheduler dump of 3 → exactly 2 `INVENTORY_GHOST` entries.
   - Exact agreement → 0 drift entries.

3. **`test_watchdog_dedup.py`** — dedup semantics
   - Run 1: new stale → loud block, state entry `alert_count=1`.
   - Run 2 (same issue): compact reminder, `alert_count=2`.
   - Run 6: escalation block re-fires.
   - Run N+1 (resolved): `RESOLVED` line, state entry removed.

4. **`test_watchdog_errors.py`** — failure modes
   - Missing inventory → emergency Telegram + `SystemExit(1)`.
   - Malformed state JSON → empty-state fallback, all items new.
   - PowerShell mock raising → drift check skipped, file checks continue, digest shows `DRIFT: skipped`.

5. **`test_watchdog_telegram_fallback.py`**
   - `send_alert` mock raises → `watchdog_alerts.log` gets `TELEGRAM_FAILED` block, exit 0.

### Integration test (manual, documented in rollout transcript)

```
python pipeline/watchdog.py --inventory tests/fixtures/inventory_staged.json --dry-run
```

`--dry-run` prints the digest to stdout instead of Telegram. Used to eyeball wording before going live. Not automated.

---

## Rollout — three gated stages

**Stage 1 — shadow mode (~1 week)**
- Both scheduled tasks run with `--dry-run` flag.
- Digest written to `watchdog.log` only; no Telegram.
- Operator reviews log daily. Inventory corrections (wrong tier, wrong cadence, missing `outputs`) land as normal commits.

**Stage 2 — live alerts, `critical` tier only**
- Remove `--dry-run` from both tasks.
- `tier=critical` items alert to Telegram; `warn` and `info` stay log-only.
- One-week observation to confirm alert rate is bearable and messages are actionable.

**Stage 3 — full live**
- `warn` also alerts.
- `info` stays log-only forever (that's what the tier means).

**Gating:** each stage requires explicit go-ahead. No auto-promotion. Stage-N → Stage-N+1 is a separate commit with the flag flip in the `.bat` wrapper.

---

## File structure

**Create:**
- `pipeline/watchdog.py` — main module, ~300–500 LoC.
- `pipeline/config/anka_inventory.json` — canonical inventory (bootstrapped from remediation mapping table + live scheduler dump).
- `pipeline/scripts/watchdog_intraday.bat` — thin wrapper invoked by `AnkaWatchdogIntraday` task with `--tier critical`.
- `pipeline/scripts/watchdog_gate.bat` — thin wrapper invoked by `AnkaWatchdogGate` task with `--all`.
- `pipeline/tests/test_watchdog_freshness.py`
- `pipeline/tests/test_watchdog_drift.py`
- `pipeline/tests/test_watchdog_dedup.py`
- `pipeline/tests/test_watchdog_errors.py`
- `pipeline/tests/test_watchdog_telegram_fallback.py`
- `pipeline/tests/fixtures/inventory_staged.json` — fixture for dry-run smoke test.
- `docs/operations/2026-04-16-watchdog-bootstrap-transcript.md` — rollout log across the three stages.

**Modify:**
- `pipeline/config/.gitignore` (or equivalent) — ensure `watchdog_state.json` is gitignored and `anka_inventory.json` is tracked.
- `CLAUDE.md` — one paragraph under "Clockwork Schedule" referencing `anka_inventory.json` as the canonical task registry.

**Register (via PowerShell, not committed as source):**
- `AnkaWatchdogIntraday` scheduled task — every 15 min, Mon–Fri, 09:30–15:30 IST, runs `watchdog_intraday.bat`, `ExecutionTimeLimit 10min`, `RestartCount 1`.
- `AnkaWatchdogGate` scheduled task — daily at 09:20 and 16:45 IST, runs `watchdog_gate.bat`, `ExecutionTimeLimit 10min`, `RestartCount 2`, `WakeToRun`.

---

## Acceptance criteria

The implementation is done when:

1. `pipeline/watchdog.py` exists and its 5 test files pass in CI/local `pytest`.
2. `pipeline/config/anka_inventory.json` is committed and contains every `Anka*` task live on 2026-04-16 (enumerated at bootstrap time).
3. Both scheduled tasks are registered with verified `LastTaskResult=0` on their first manual run.
4. Stage 1 (shadow mode) runs for ≥ 5 weekday cycles with each daily log reviewed; inventory corrections landed if any false positives surfaced.
5. Stage 2 (critical-live) has fired at least one true-positive Telegram alert (we can deliberately stale a test file if nothing real has gone wrong by the end of stage 1 — or wait for a real incident).
6. Stage 3 (full live) is reached with no escalation-level `STILL BROKEN` alerts from the prior stage.
7. Drift check proven live via a 4-step canary sequence, each step observed on the next watchdog run:
   (a) Register `AnkaWatchdogDriftCanary` in scheduler without updating inventory → observe `ORPHAN_TASK` alert.
   (b) Add canary row to inventory → observe `ORPHAN_TASK` resolves (`RESOLVED` line).
   (c) Unregister canary from scheduler (inventory still has it) → observe `INVENTORY_GHOST` alert.
   (d) Remove canary row from inventory → observe `INVENTORY_GHOST` resolves.

---

## Risks + open questions (escalated during implementation)

- **Scheduler query latency** — `Get-ScheduledTask` against 69 tasks on a slow laptop might exceed 30s. If watchdog run-time approaches `ExecutionTimeLimit` (10 min), narrow the query to `-TaskName Anka*` + cache `TaskInfo` in a single PS invocation, not one-per-task.
- **Clock drift** — if the machine's system clock is off, `cadence_class=intraday` market-hours check could misclassify. Mitigation deferred to DEFERRED-NEW if it becomes a real issue; baseline is "trust the system clock."
- **Telegram rate limits** — 30 messages/sec limit is high above our cadence; no real risk. If digest exceeds Telegram's 4096-char message limit (rare — would require ~30+ simultaneous stale items), split into two messages at section boundaries.
- **Inventory mass edit** — if a large pipeline change (e.g., shipping a new phase with 8 tasks) lands without inventory update, Stage-2+ will emit 8 `ORPHAN_TASK` alerts in one digest. Acceptable — that's the forcing function working.

---

## Related artifacts

- Predecessor plan: `docs/superpowers/plans/2026-04-16-scheduler-debt-remediation.md`
- Predecessor spec: `docs/superpowers/specs/2026-04-16-scheduler-debt-remediation-design.md`
- Operations transcripts: `docs/operations/2026-04-16-batch-{a,b,c}-transcript.md`
- This spec will be followed by: `docs/superpowers/plans/2026-04-XX-data-freshness-watchdog.md` (implementation plan, authored next via `superpowers:writing-plans`).

---

## Gap 1 within the 4-gap roadmap

This spec is Gap 1 of the 4-gap observability roadmap (see prior brainstorm narrative):

| Gap | Status |
|---|---|
| 1. Data-freshness watchdog | **this spec** |
| 2. Continuous article re-grounding | future — depends on Gap 1 alert pipe |
| 3. Terminal + website age badges | future — reads Gap 1 freshness feed |
| 4. Reasoning-chain persistence | future — independent |

Gap 3 will land next after Gap 1 is in Stage 2 or Stage 3 live.
