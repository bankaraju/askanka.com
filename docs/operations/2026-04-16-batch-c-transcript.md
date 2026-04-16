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

**Hypothesis revision:** The plan's "single master EOD job" framing does not hold. Investigation found:

**Writer map for the 18-file Apr-14-15:38 stale cluster:**

| Writer script | Files owned | Tracked? |
|---|---|---|
| `pipeline/correlation_regime.py` | correlation_history, fragility_model, fragility_scores | yes |
| `pipeline/macro_stress.py` | macro_trigger_state, msi_history | yes |
| `pipeline/pattern_engine.py` | historical_events, pattern_lookup | yes |
| `pipeline/model_drift.py` | ml_performance | yes |
| `pipeline/gamma_scanner.py` | gex_history | **UNTRACKED** |
| `pipeline/options_monitor.py` | oi_history | **UNTRACKED** |
| `pipeline/pinning_detector.py` | pinning_history | **UNTRACKED** |
| `pipeline/unified_regime_engine.py` | regime_history | **UNTRACKED** |
| `pipeline/expiry_monitor.py` | expiry_divergence_log | **UNTRACKED** |
| no writer in codebase | gamma_result, gamma_generation, pinning_backtest_summary | orphan |

8 distinct writers (5 of them untracked), not one master.

**Surviving Anka EOD tasks in live scheduler (after B1 zombie cleanup):**

| Task | .bat | LastRun | LastResult |
|------|------|---------|-----------|
| `AnkaEODReview` | `eod_review.bat` | 2026-04-15 16:00:30 | 0 |
| `AnkaEODTrackRecord` | `eod_track_record.bat` | 2026-04-15 16:15:45 | 0 |
| `AnkaTrustEOD` | (opus-anka repo, external) | 2026-04-15 16:35:05 | 0 |
| `AnkaWeeklyReport` | `weekly_report.bat` | 2026-04-11 10:00:30 | **1 (FAILED)** |

`eod_track_record.bat` only calls `run_eod_report.py` + `website_exporter.py` — **neither writes any of the 18 cluster files**. So the live EOD tasks are not the missing orchestrator; they never wrote the cluster.

**Attempted in-session remediation (tracked writers only):**

| Writer | Exit | Output file refreshed? |
|---|---|---|
| `correlation_regime.py` | 1 | ❌ `ImportError: cannot import name 'CORRELATION_PAIRS' from 'config'` — config.py doesn't define this constant anywhere in the repo (only this script and the old 2026-04-03 plan reference it) |
| `macro_stress.py` | 0 | ❌ Ran clean to exit 0 but `macro_trigger_state.json` + `msi_history.json` still Apr 14 15:38 — internal no-op guard |
| `model_drift.py` | 0 | ❌ Ran to exit 0, `ml_performance.json` still Apr 14 15:38 — internal no-op |
| `pattern_engine.py` | 0 | ✅ `pattern_lookup.json` refreshed to 2026-04-16 12:44; `historical_events.json` still Apr 14 15:38 (same script, partial refresh) |

**Conclusion — deferred to future brainstorm (DEFERRED-NEW):**

This is not scheduler debt; it's **script rot + missing orchestrator**. Each writer needs its own triage:
1. `correlation_regime.py` — genuine break (CORRELATION_PAIRS removed from config.py at some point; needs either restore or refactor).
2. `macro_stress.py`, `model_drift.py`, `pattern_engine.py` (historical_events branch) — have internal guards that silently no-op on daily runs; need to understand the "refresh" mode flags or alternative invocation pattern.
3. 5 untracked writers — single-repo mandate violation; need separate audit (fate-per-file) — already flagged in row 68 as `DEFERRED-NEW`.
4. No scheduled orchestrator wires them together — by design (they may each have their own cadence) or by drift; needs design call.

**In-scope remediation action for C3:** None safe to apply in this plan. Row 65 -> `DEFERRED-NEW`. Snapshots in `pipeline/backups/data_snapshots/2026-04-16/` remain available as a baseline for the future mini-plan.

**Partial win:** `pattern_lookup.json` refreshed to today (pattern_engine.py partial success). Documented but does not change row 65 status.

## Section C3.x — Orphan + untracked writer resolution

<populated by Task 15>

## Section C4 — Downstream Apr 15 consumer smoke test

<populated by Task 16>

## Section C5 — Final health check + closeout

<populated by Task 17>
