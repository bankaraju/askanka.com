# NEUTRAL hurdle semantics — diagnosis (#195)

**Date:** 2026-04-28
**Owner:** Bharat Ankaraju
**Status:** Diagnosis-only. Recommends a code change but does not ship it
(model-governance rules require explicit approval before tightening a
production verdict gate).

## Problem statement

Bharat's flag: "in NEUTRAL, NIFTY drift is sometimes negative, which makes
`delta_in` (proposal Sharpe minus hurdle Sharpe) a mechanically low bar."

Translated to v2 terms: the v2 hurdle is no longer NIFTY buy-and-hold — it
is the construction-matched null-basket median Sharpe (random k tickers per
event, applying the same sign semantics as the proposal). NIFTY drift is
no longer the literal hurdle. **But the underlying intuition still bites**:
when the null basket loses money in NEUTRAL (and it does, often heavily),
the *absolute level* of the hurdle goes deeply negative, and a proposal
with `net_sharpe ≈ 0` clears `delta_in ≥ 0.15` trivially.

## Where the hurdle lives in v2

Production path:
- `pipeline/autoresearch/regime_autoresearch/scripts/run_pilot.py:203-233`
  `_compute_hurdle()` — calls
  `null_basket_hurdle.load_null_basket_hurdle(construction, k, hold_horizon, regime, window='train_val')`
  and returns its `hurdle_sharpe_median`.
- `pipeline/autoresearch/regime_autoresearch/scripts/run_pilot.py:546-590`
  `_make_verdict()` — gate is
  `passes_delta_in = (net_sharpe - hurdle_sharpe) >= DELTA_IN_SAMPLE`
  where `DELTA_IN_SAMPLE = 0.15`.

Legacy fallback path (only fires if the parquet is missing or the
`(construction, k, h, regime, window)` row is absent):
- `_compute_hurdle` falls through to
  `incumbents.hurdle_sharpe_for_regime(table, regime)`. v2 simplified this
  to "mean of clean incumbents' Sharpe, or 0.0 if none". The old
  `scarcity_fallback:buy_and_hold` branch (which was the original flagged
  bug) was removed in v2 — see
  `pipeline/autoresearch/regime_autoresearch/incumbents.py:1-9` docstring.

## Concrete numbers from the current null-basket parquet

Source: `pipeline/autoresearch/regime_autoresearch/data/null_basket_hurdles_v2.parquet`
(rebuilt 2026-04-25, n_trials=1000, NEUTRAL n_events=165 train_val + 132 holdout).

NEUTRAL train_val medians (Sharpe), by construction × k × h:

| Construction | h | k=1 | k=10 | k=20 | k=40 |
|---|---:|---:|---:|---:|---:|
| single_long | 1 | -1.63 | -1.73 | -1.65 | -1.67 |
| single_long | 5 | +0.35 | +0.33 | +0.35 | +0.34 |
| single_long | 10 | +0.78 | +0.79 | +0.79 | +0.80 |
| single_short | 1 | -2.92 | -3.04 | -2.96 | -2.90 |
| single_short | 5 | -1.17 | -1.17 | -1.18 | -1.16 |
| top_k | 1 | -1.68 | -3.30 | -3.65 | -3.84 |
| top_k | 5 | +0.29 | +0.57 | +0.63 | +0.66 |
| bottom_k | 1 | -2.98 | -5.67 | -6.28 | -6.61 |
| long_short_basket | 1 | -3.49 | -10.51 | -14.91 | -20.88 |

NEUTRAL holdout window medians look the same shape (negative at h=1, less
negative at h=5, occasionally positive at h=10 for `single_long` and
`top_k`). Full table is in the parquet.

## Why the hurdle is so negative at h=1

A 1-day random-pick basket in a sideways/mean-reverting regime is dominated
by transaction friction in our cost model: the trial Sharpe is computed on
the same `_net_sharpe` engine that applies S1 cost. With h=1 the cost is
amortised over 1 day rather than 5 or 10, dragging the per-event Sharpe
deeply negative.

This is **methodologically correct** for the question "is your selection
better than a random pick at the same horizon?". A random pick at h=1
loses to friction; a real edge has to clear that handicap.

But it's also why `delta_in` becomes a low bar in absolute terms: clearing
"your strategy beats a -1.7-Sharpe random pick by 0.15 Sharpe" is achievable
by a strategy that is itself net-negative.

## How often it bites in production

Spot-check from the most recent NEUTRAL pilot
(`proposal_log_neutral.jsonl`, 2026-04-25): of 22 proposals that
populated `passes_delta_in`, the median `(net_sharpe - hurdle_sharpe)` gap
was **+1.34** Sharpe — i.e. most proposals clear the gate by ~9× the
threshold. The threshold is doing very little work in NEUTRAL.

In contrast, the `passes_min_events` and `passes_all_folds_populated`
gates that landed in #194 and #198 are doing the load-bearing filtering:
those reject proposals with 0 events, 0 trades, or empty walk-forward
folds, regardless of the Sharpe-vs-hurdle math.

## Recommended change

**Option A — add an absolute-Sharpe floor to `passes_delta_in`** (recommended):

```python
MIN_NET_SHARPE = 0.0  # net_sharpe must be at least zero
passes_delta_in = (
    net_sharpe is not None
    and hurdle_sharpe is not None
    and (net_sharpe - hurdle_sharpe) >= DELTA_IN_SAMPLE
    and net_sharpe >= MIN_NET_SHARPE   # NEW
)
```

Justification: the delta-vs-hurdle gate measures "do you beat random
selection?" — an information-content question. The absolute floor measures
"are you tradeable?" — a deployment question. Both are legitimate, both
should pass before a proposal goes APPROVED.

`MIN_NET_SHARPE = 0.0` is the minimum honest floor; tightening to 0.5 or
1.0 would also be defensible but is a separate decision.

**Option B — clip hurdle floor at 0**:

```python
hurdle_sharpe = max(0.0, raw_hurdle_sharpe)
```

Cheaper change, but throws away signal: a -3 hurdle and a 0 hurdle should
not be treated identically. Not recommended.

**Option C — switch to NIFTY-residual hurdle**:

Compute hurdle as `median(Sharpe(strategy_return - beta × nifty_return))`
across the trial baskets. This pulls out the NIFTY-drift component
explicitly and the residual hurdle is symmetric around 0 by construction.
This is the "right" answer in principle but requires non-trivial
infrastructure (regime-level beta panel, residual computation, beta
serialisation) and is a v3 design question rather than a #195-scope fix.

## Recommendation

Ship **Option A** as a one-line addition to `_make_verdict` plus a test.
Defer **Option C** to a v3 design.

Action requires explicit user nod because it tightens a production
verdict gate and may reject some proposals that previously passed in
the historical reanalyze log.

## Test plan (when shipped)

Add a unit test to
`pipeline/tests/autoresearch/regime_autoresearch/test_run_pilot_verdict.py`
(or wherever the existing `_make_verdict` tests live) covering:

1. `net_sharpe = -0.05`, `hurdle_sharpe = -1.5`: with current code
   `passes_delta_in = True` (gap +1.45). With Option A,
   `passes_delta_in = False` (net_sharpe < 0).
2. `net_sharpe = +0.30`, `hurdle_sharpe = -1.5`: passes both before and
   after.
3. `net_sharpe = +0.10`, `hurdle_sharpe = +0.50`: gap +0.40 > 0.15 but
   net_sharpe just-positive — passes both before and after.
4. `net_sharpe = +0.30`, `hurdle_sharpe = +0.50`: gap +0.30 > 0.15 and
   net_sharpe positive — passes both.

## Honest caveat

The user's original phrasing referenced "NIFTY-negative" specifically. In
v1 that was literally the hurdle (NIFTY buy-and-hold). In v2 it isn't —
the hurdle is a NIFTY-free random-basket null. So the title is slightly
out of date, but the **substance** of the concern (low absolute hurdle
makes delta_in trivial in NEUTRAL) carries over: replace "NIFTY drift is
negative" with "the random-basket null has negative Sharpe at h=1" and
the same fix applies.

## Closure (no code change, awaiting approval)

This document closes the diagnosis half of #195. The implementation half
(adding the `MIN_NET_SHARPE` floor + test + commit) needs explicit user
approval per model-governance rules before shipping.
