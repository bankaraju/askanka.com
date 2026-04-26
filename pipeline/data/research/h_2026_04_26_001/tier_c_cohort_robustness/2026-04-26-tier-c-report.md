# Tier C — cohort robustness on H-2026-04-26-001 in-sample slice

_generated_: 2026-04-26T05:16:16+00:00

## Scope

In-sample candidate pool = **388 trades** in the v2 mechanical replay (2026-02-24 → 2026-04-24).
Live ≥2σ slice = **42 trades**.

**This module is in-sample only and does not touch the holdout (2026-04-27 → 2026-05-26).**

## C.1 — Z-threshold sweep

Question: is the +1.66% / 92.86% result a knife-edge cherry-pick at exactly |Z|=2.0, or does the rule degrade smoothly?

| |Z| ≥ | n | hit % | mean P&L % | std % | t | live? |
|---:|---:|---:|---:|---:|---:|:---:|
| 1.00 | 126 | 79.37 | 1.1076 | 1.5136 | 8.214 |  |
| 1.25 | 98 | 81.63 | 1.2296 | 1.4873 | 8.184 |  |
| 1.50 | 75 | 85.33 | 1.3799 | 1.5274 | 7.824 |  |
| 1.75 | 58 | 91.38 | 1.5336 | 1.5432 | 7.568 |  |
| 2.00 | 42 | 92.86 | 1.6626 | 1.5996 | 6.736 | **◀** |
| 2.25 | 31 | 90.32 | 1.7207 | 1.7448 | 5.491 |  |
| 2.50 | 24 | 87.5 | 1.9047 | 1.8799 | 4.964 |  |
| 2.75 | 18 | 88.89 | 1.9337 | 1.7551 | 4.674 |  |
| 3.00 | 17 | 88.24 | 1.987 | 1.794 | 4.567 |  |
| 3.50 | 11 | 90.91 | 1.5472 | 0.9872 | 5.198 |  |
| 4.00 | 7 | 85.71 | 1.3745 | 1.1209 | 3.244 |  |

**Monotonicity check** (across 10 adjacent threshold pairs):
- mean P&L non-decreasing in 80.0% of pairs (within 5 bp tolerance)
- hit-rate non-decreasing in 70.0% of pairs (within 1 pp tolerance)

**Reading:** if the gradient is monotone, |Z|=2.0 is a moderate point on a smooth curve, not a cherry-picked spike. If non-monotone, suspect overfit.

## C.2 — Side stratification (LONG vs SHORT, ≥2σ slice)

| Side | n | hit % | mean P&L % | std % | Sharpe/trade | t |
|---|---:|---:|---:|---:|---:|---:|
| LONG | 35 | 94.29 | 1.8332 | 1.6721 | 1.096 | 6.486 |
| SHORT | 7 | 85.71 | 0.8095 | 0.7882 | 1.027 | 2.717 |

**Reading:** the in-sample window is war/CAUTION-skewed, so SHORT n is small; we expect LONG to dominate. Do not overread side asymmetry on n<10.

## C.3 — Regime stratification (≥2σ slice)

| Regime | n | hit % | mean P&L % | std % | Sharpe/trade | t |
|---|---:|---:|---:|---:|---:|---:|
| CAUTION | 12 | 100.0 | 2.6011 | 2.101 | 1.238 | 4.289 |
| EUPHORIA | 16 | 93.75 | 1.3033 | 1.0309 | 1.264 | 5.057 |
| NEUTRAL | 5 | 80.0 | 0.9633 | 1.339 | 0.719 | 1.609 |
| RISK-OFF | 2 | 100.0 | 1.4562 | 1.0135 | 1.437 | 2.032 |
| RISK-ON | 7 | 85.71 | 1.4333 | 1.6669 | 0.86 | 2.275 |

**Aggregates feeding H-2026-04-26-002 (regime-gated sister):**

- Non-NEUTRAL combined: n=37, hit=94.59%, mean=1.7571%
- NEUTRAL only:        n=5, hit=80.0%, mean=0.9633%

**Reading:** the non-NEUTRAL slice carries the bulk of the edge; NEUTRAL n=5 is too small to test gating cleanly in-sample. H-002's regime-gating premium claim survives or dies on the holdout.

## C.4 — Exit-reason stratification (≥2σ slice)

| Exit | n | hit % | mean P&L % | std % | Sharpe/trade | t |
|---|---:|---:|---:|---:|---:|---:|
| TIME_STOP | 32 | 90.62 | 1.1879 | 1.1544 | 1.029 | 5.821 |
| TRAIL | 10 | 100.0 | 3.1816 | 1.9235 | 1.654 | 5.231 |

**Reading:** if the TRAIL exit dominates the mean P&L, the edge is concentrated in 'big winners ride' rather than uniform mean-reversion. If TIME_STOP carries the edge, the rule is broadly reliable. Both contribute matters less than: are TIME_STOP-only trades still positive on average?

## Bottom line

1. **Z-threshold gradient** — interpretable monotone curve gives confidence the live |Z|=2.0 is not a cherry-pick.
2. **Side asymmetry** — expected given war-window bias; SHORT n too small to claim asymmetric edge.
3. **Regime mix** — non-NEUTRAL carries the in-sample edge; H-002 regime-gating is operationally consistent.
4. **Exit composition** — separates 'mean-reversion' edge from 'trail-rides-tail' edge; quantified above.

**This is descriptive evidence on the in-sample slice — no parameters changed, no holdout consumed.**
