# Incumbent re-qualification audit — 2026-04-24

- Audit timestamp: `2026-04-24T07:42:25.433369+00:00`
- Audit commit: `01997b03be279c661bae00f9ebcaaabbbb9e2124`
- Framework cutoff: `2026-04-23`

## Summary

- Rows: 10
- Cells: 50 (rows x 5 regimes)
- BACKED_BY_ARTEFACT: 0
- CORRECTLY_INSUFFICIENT_POWER: 45
- SHOULD_HAVE_BEEN_RUN: 5
- STALE: 0

## Per-strategy verdicts

| Strategy | Status | Priority | Backing artefact | Notes |
|---|---|---|---|---|
| `SI_PRIMARY` | LIVE | NONE | `-` | placeholder accepted; retest when per-regime data available |
| `SI_SECONDARY` | LIVE | NONE | `-` | placeholder accepted; retest when per-regime data available |
| `PHASE_C_LAG` | LIVE_ALERT_ONLY | HIGH | `pipeline/autoresearch/results/compliance_phase_c_lag_H-2026-04-23-002_20260423T183858Z` | artefact compliance_phase_c_lag_H-2026-04-23-002_20260423T183858Z exists but strategy_results_10 cells for ['CAUTION', 'EUPHORIA', 'NEUTRAL', 'RISK-OFF', 'RISK-ON'] were not refreshed |
| `OVERSHOOT_TORNTPOWER` | LIVE | NONE | `-` | placeholder accepted; retest when per-regime data available |
| `OVERSHOOT_MULTITICKER` | LIVE | NONE | `-` | placeholder accepted; retest when per-regime data available |
| `FCS_LONG_TOPK` | LIVE | NONE | `-` | placeholder accepted; retest when per-regime data available |
| `FCS_LONG_SHORT` | LIVE | NONE | `-` | placeholder accepted; retest when per-regime data available |
| `TA_SCORER_RELIANCE` | EXPLORING | NONE | `-` | placeholder accepted; retest when per-regime data available |
| `OPUS_TRUST_SPREAD` | EXPLORING | NONE | `-` | placeholder accepted; retest when per-regime data available |
| `PHASE_AB_REVERSE` | LIVE | NONE | `-` | placeholder accepted; retest when per-regime data available |

## HIGH-priority re-qualification queue

### `PHASE_C_LAG` — Phase C LAG (alert-only post H-107 FAIL)

- Regimes needing re-run: ['CAUTION', 'EUPHORIA', 'NEUTRAL', 'RISK-OFF', 'RISK-ON']
- Current backing artefact: `pipeline/autoresearch/results/compliance_phase_c_lag_H-2026-04-23-002_20260423T183858Z`
- Notes: artefact compliance_phase_c_lag_H-2026-04-23-002_20260423T183858Z exists but strategy_results_10 cells for ['CAUTION', 'EUPHORIA', 'NEUTRAL', 'RISK-OFF', 'RISK-ON'] were not refreshed
- Compute pointer: see `docs/superpowers/plans/2026-04-24-regime-aware-autoresearch.md` §"Incumbent re-qualification runbook" (follow-up task).

## Recommended follow-up tasks

- Open one re-qualification task per HIGH-priority strategy. Each task runs the relevant compliance runner with regime stratification and then wires the cell update back into `strategy_results_10.json` via a separate, explicit step (not this audit).
- If no HIGH items exist, the current scarcity fallback (buy-and-hold benchmark in `hurdle_sharpe_for_regime`) is load-bearing and should remain in force until incumbents are re-qualified.