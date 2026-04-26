# Phase 3 Pre-Registration — DRAFT (locks at Phase 3 task 1)

Status: DRAFT. Final lock requires SHA-256 hash committed in Phase 3 plan task 1.

## Hypothesis ID
H-2026-04-XX-XXX  (assigned at lock)

## Strategy version
v3-CURATED-30 + <best marker stack from Phase 2>

## Universe
<126 OR 273 — whichever Phase 2 chose>

## Date window
Start: 2026-04-27 (next trading day after lock)
End: T + 30 trade-eligible days (extend to 60 if vol-low)

## Statistical test
Cluster-robust mean P&L > 0 at p < 0.05, clustered by trade_date.

## Family denominator (§14.5)
Primary: <strategy-class | universe-scope | ticker-family>  (chosen at lock — write rationale)

## Naive comparator (§9B.1)
random_direction permutation null, n=10,000.

## Pass thresholds
- Cluster-robust mean > 0 with p < 0.05
- ≥ 30 trade-eligible days
- Beats random_direction at p < 0.05
- Slippage S1 result still positive

## Kill-switch (§13.3)
Cumulative DD > 3× backtest MaxDD halts and triggers review.
