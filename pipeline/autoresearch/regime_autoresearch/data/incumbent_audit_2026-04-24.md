# Incumbent re-qualification audit — 2026-04-24

- Audit timestamp: `2026-04-28T10:12:48.047758+00:00`
- Audit commit: `3cd177887987cf68b6fc7eb0a617e8a182b2f32e`
- Framework cutoff: `2026-04-23`

## Summary

- Rows: 10
- Cells: 50 (rows x 5 regimes)
- BACKED_BY_ARTEFACT: 0
- BACKED_AS_CROSS_REGIME_FAIL: 5
- CORRECTLY_INSUFFICIENT_POWER: 45
- SHOULD_HAVE_BEEN_RUN: 0
- STALE: 0

## Per-strategy verdicts

| Strategy | Status | Priority | Backing artefact | Notes |
|---|---|---|---|---|
| `SI_PRIMARY` | LIVE | NONE | `-` | placeholder accepted; retest when per-regime data available |
| `SI_SECONDARY` | LIVE | NONE | `-` | placeholder accepted; retest when per-regime data available |
| `PHASE_C_LAG` | LIVE_ALERT_ONLY | NONE | `pipeline/autoresearch/results/compliance_phase_c_lag_H-2026-04-23-002_20260423T183858Z` | backing artefact is a pooled cross-regime FAIL (per-regime metrics correctly absent); refresh requires a regime-stratified re-run |
| `OVERSHOOT_TORNTPOWER` | LIVE | NONE | `-` | placeholder accepted; retest when per-regime data available |
| `OVERSHOOT_MULTITICKER` | LIVE | NONE | `-` | placeholder accepted; retest when per-regime data available |
| `FCS_LONG_TOPK` | LIVE | NONE | `-` | placeholder accepted; retest when per-regime data available |
| `FCS_LONG_SHORT` | LIVE | NONE | `-` | placeholder accepted; retest when per-regime data available |
| `TA_SCORER_RELIANCE` | EXPLORING | NONE | `-` | placeholder accepted; retest when per-regime data available |
| `OPUS_TRUST_SPREAD` | EXPLORING | NONE | `-` | placeholder accepted; retest when per-regime data available |
| `PHASE_AB_REVERSE` | LIVE | NONE | `-` | placeholder accepted; retest when per-regime data available |

## HIGH-priority re-qualification queue

_No HIGH-priority items — all incumbents either backed or correctly flagged INSUFFICIENT_POWER._
## Recommended follow-up tasks

- Open one re-qualification task per HIGH-priority strategy. Each task runs the relevant compliance runner with regime stratification and then wires the cell update back into `strategy_results_10.json` via a separate, explicit step (not this audit).
- If no HIGH items exist, the current scarcity fallback (buy-and-hold benchmark in `hurdle_sharpe_for_regime`) is load-bearing and should remain in force until incumbents are re-qualified.