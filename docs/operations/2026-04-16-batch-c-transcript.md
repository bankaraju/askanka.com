# Batch C Transcript — Scheduler Debt Remediation 2026-04-16

**Plan:** `docs/superpowers/plans/2026-04-16-scheduler-debt-remediation.md`
**Spec:** `docs/superpowers/specs/2026-04-16-scheduler-debt-remediation-design.md`
**Branch:** `remediate/scheduler-debt-2026-04-16`

## Section C1 — AnkaCorrelationBreaks CLI fix

**File modified:** `pipeline/scripts/correlation_breaks.bat`

**Change:** removed `--day 1 --no-telegram` from the final `python` invocation. `reverse_regime_breaks.py` argparse only accepts `--regime`, `--transition`, `--dry-run`, `--verbose`. The two extra args caused every AnkaCorrelationBreaks fire to exit non-zero with `error: unrecognized arguments`; Phase C never produced output since its registration.

**Post-fix manual run:** `exit_code=0`

**Log tail (last 30 lines of `pipeline/logs/correlation_breaks.log`):**

```
CORRELATION BREAK: LTF
  Regime: NEUTRAL (day 1)
  Expected: +0.7% | Actual: -1.7% | Z-score: 1.6s
  Classification: UNCERTAIN
  PCR: N/A | OI Anomaly: None
  Action: HOLD — monitor, no action

CORRELATION BREAK: GMRAIRPORT
  Regime: NEUTRAL (day 1)
  Expected: -0.3% | Actual: -2.7% | Z-score: 1.6s
  Classification: POSSIBLE_OPPORTUNITY
  PCR: N/A | OI Anomaly: None
  Action: HOLD — monitor, no action

CORRELATION BREAK: LUPIN
  Regime: NEUTRAL (day 1)
  Expected: -0.3% | Actual: -2.1% | Z-score: 1.6s
  Classification: POSSIBLE_OPPORTUNITY
  PCR: N/A | OI Anomaly: None
  Action: HOLD — monitor, no action

CORRELATION BREAK: TORNTPHARM
  Regime: NEUTRAL (day 1)
  Expected: +0.9% | Actual: -0.9% | Z-score: 1.5s
  Classification: UNCERTAIN
  PCR: N/A | OI Anomaly: None
  Action: HOLD — monitor, no action

============================================================
```

**Output files written (mtimes confirmed today 12:36):**
- `pipeline/data/correlation_breaks.json` — 15,797 bytes (today's breaks; overwritten daily)
- `pipeline/data/correlation_break_history.json` — 14,509 bytes (append-only log)

**Phase C restored end-to-end.** Next scheduled fire (AnkaCorrelationBreaks every 15 min during market hours) will now produce output. Classifications working: UNCERTAIN and POSSIBLE_OPPORTUNITY surfaced from real z-score deviations.

## Section C2 — Phase A interim cron (AnkaReverseRegimeProfile)

**New .bat:** `pipeline/scripts/reverse_regime_profile.bat` (thin wrapper around `python -X utf8 autoresearch/reverse_regime_analysis.py`)

**New scheduled task:** `AnkaReverseRegimeProfile`
- Daily @ 04:45 IST
- WakeToRun, AllowStartIfOnBatteries, StartWhenAvailable, MultipleInstances IgnoreNew, ExecutionTimeLimit 2h, RestartCount 2
- Description field: `INTERIM - pending fresh brainstorm 2026-04-17+. Writes pipeline/autoresearch/reverse_regime_profile.json consumed by Phase B.`

**Direct .bat manual run:** exit 0; `pipeline/autoresearch/reverse_regime_profile.json` refreshed — 3,516,749 bytes, mtime 2026-04-16 12:37 (was Apr 14 — 2 days stale).

**Scheduler-driven run (Start-ScheduledTask):**
```
LastTaskResult : 0
LastRunTime    : 16-04-2026 12:38:08
NextRunTime    : 17-04-2026 04:45:15
```

**Path discovery:** Phase A writes to `pipeline/autoresearch/reverse_regime_profile.json` (not `pipeline/data/`). That's the canonical location the script uses and Phase B consumes. Plan had listed the wrong directory — no correction needed beyond noting it here.

**Phase A interim cron live.** Phase B ranker will now run against fresh (today's) profile on its next fire, not the Apr-14 stale profile that was blocking it.

Designed cadence and trigger for Phase A get a fresh brainstorm 2026-04-17+ — this is interim, clearly labeled in the task's Description field.

## Section C3 — Master EOD job identification

<populated by Task 14>

## Section C3.x — Orphan + untracked writer resolution

<populated by Task 15>

## Section C4 — Downstream Apr 15 consumer smoke test

<populated by Task 16>

## Section C5 — Final health check + closeout

<populated by Task 17>
