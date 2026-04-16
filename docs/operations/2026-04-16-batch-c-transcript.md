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

<populated by Task 13>

## Section C3 — Master EOD job identification

<populated by Task 14>

## Section C3.x — Orphan + untracked writer resolution

<populated by Task 15>

## Section C4 — Downstream Apr 15 consumer smoke test

<populated by Task 16>

## Section C5 — Final health check + closeout

<populated by Task 17>
