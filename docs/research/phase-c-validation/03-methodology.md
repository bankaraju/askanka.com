# Phase C — Methodology

This section documents every choice that affects the falsifiability of the H1 claim. If a reviewer disagrees with any of these, the whole verdict is up for grabs — that's the point.

## Windows

| leg | window | bars | purpose |
|---|---|---|---|
| In-sample | 2022-04-01 → 2026-03-31 (4 yrs) or 2024-10-01 → 2026-03-31 (mid-size replay) | daily OHLCV | sample-size and regime-depth test |
| Forward | 2026-02-20 → 2026-04-19 (60 sessions) or 2026-04-01 → 2026-04-20 (mid-size replay) | 1-minute OHLCV | genuine out-of-sample, intraday exit |
| Regime backfill | (in-sample-start − lookback_years) → forward-end | daily | ensures walk-forward cutoffs have trained labels |

The backfill window extends **backwards** by `lookback_years=2` so the first walk-forward cutoff has a full training set. This was a bug found and fixed during Task 16: without the backwards extension, the first two quarterly cutoffs trained on 0 symbols.

## Walk-forward training

Phase A profiles are refit at **quarterly month-start cadence** (`profile.cutoff_dates_for_walk_forward(..., refit_months=3)`). At each cutoff `c`:

1. Take the trailing 2 years of daily bars strictly before `c`.
2. Compute next-day return `next_ret[t] = close[t+1] / close[t] − 1`.
3. Filter **`next_date < cutoff_ts`** (not `date < cutoff`) — this is the strict no-lookahead guard. It correctly excludes the last bar in the window whose next-day close falls on or after the cutoff, and it is robust to weekends/holidays.
4. Group by regime, require `n ≥ 5` per regime, write `{expected_return, std_return, hit_rate, n}`.

The active profile at classification time `d` is the most recent cutoff `c ≤ d`. This matches live trading: the most recently fitted profile is the one actually in use at the decision moment.

## Classification

`classifier.classify_universe` applies the 5-class matrix from `02-strategy-description.md` to every (symbol × date) pair. Two small but load-bearing details:

- **z-score threshold for "meaningfully moved":** `|z| > 0.001` in fractional units. This is the unit-equivalent of the live engine's percent-space `> 0.1` (i.e. > 0.1 percentage points). The 0.001 value is pinned by `test_classifier.py` so percent-space / fractional-space drift is caught.
- **Missing PCR / OI:** treated as "silent" (neither agrees nor disagrees). This is what pushes the classifier from `OPPORTUNITY` to `POSSIBLE_OPPORTUNITY` on 100% of historical rows.

## Entry and exit mechanics

In-sample (daily bars): entry is modelled as the next open, exit at the next day's close — a daily surrogate for the intraday rule. This is an **upper bound** on what a real intraday exit would achieve, because the surrogate captures overnight drift that a 14:30 flat cannot.

Forward (1-min bars): `simulator_intraday.run_simulation` steps bar-by-bar from the signal time. Stop and target are evaluated on bar highs/lows; if both are touched in the same minute (a "straddle"), the stop wins (conservative). Time stop at 14:30 closes at that bar's close.

## Stop / target policy

The current implementation uses a **flat 2% stop / 1% target**. A natural refinement is per-(symbol, regime) stops derived from the stored `std_return`; this is explicitly in the follow-up list, not this run's verdict.

## Cost model

See `cost_model.py`. Per round-trip on ₹50k notional:

- Slippage: 5 bps × 2 = 10 bps (₹50)
- Brokerage: ₹20 × 2 = ₹40
- STT (sell side): 0.03% × ₹50k = ₹15
- Exchange + SEBI + stamp: ~₹2
- **Total ≈ ₹107 / trade** (≈ 21 bps round-trip)

The 21 bps figure is what the strategy has to clear gross of P&L just to break even. This is the retail-intraday benchmark against which the Sharpe CI is computed.

## Statistical tests

Three independent tests per hypothesis, all applied to `pnl_net_inr / notional_inr`:

### Sharpe confidence interval

Bootstrap at α = 0.01 (99% two-sided), 10,000 IID resamples, fixed seed=7 for reproducibility. The lower bound of the CI is what we check against zero. See `stats.bootstrap_sharpe_ci`.

### Binomial p-value

`stats.binomial_p(wins, total)` tests the null that hit rate = 0.5. The strategy passes only if p ≤ 0.01 **after Bonferroni correction**.

### Hit rate threshold

≥ 0.55 (absolute). This threshold is chosen to cover the round-trip cost — a 55% hit rate on a 2:1 reward/risk is just barely profitable.

## Multiple-hypothesis correction

The full H1 spec tests 5 hypotheses (OPPORTUNITY, POSSIBLE_OPPORTUNITY, UNCERTAIN-as-null, WARNING-as-null, degraded-ablation). Bonferroni: α/5 = **0.01** per test, preserving family-wise α = 0.05. The binomial p-values above are evaluated against this corrected threshold.

## Per-regime breakdown

To pass H1, **at least 3 of 5 regimes** must individually satisfy the hit-rate and p-value bars with `n ≥ 30` trades per regime. This prevents a single good regime (e.g. NEUTRAL, which dominates sample count) from carrying a failing strategy.

## Ablation

`ablation.run_all_variants` runs the classifier four ways — full / no-OI / no-PCR / degraded — and the H1 verdict requires the **degraded** variant to have non-negative net P&L. This is the honest floor: if the strategy only works when the derivatives-market side signals are present, but those signals are exactly what's unavailable historically, the verdict must be blocked until live capture makes them observable.

In this run, degraded is the only variant actually tested (historical PCR/OI unavailable), so the four-way ablation collapses into a single trajectory. The `degraded_ablation_positive` field in the verdict is therefore the net-P&L sign of that single trajectory.

## Robustness checks

`robustness.py` runs:

- **Slippage sweep:** re-price the same ledger at 3, 5, 7, 10 bps per side. Report Sharpe CI at each.
- **Top-N sweep:** vary `top_n ∈ {1, 3, 5, 10, 15}` (per-day signal cap). Report P&L and Sharpe.

Both sweeps operate on the same signal set — only the cost or the per-day cap changes. The verdict is robust only if the Sharpe CI lower bound stays non-negative across reasonable parameter ranges.

## Reproducibility

- All stats functions take `seed` or `random_state` and default to fixed values.
- All caches are content-addressed by cutoff date and symbol; deleting the cache and re-running produces byte-identical ledgers.
- The ledger parquet files in this directory are the exact artifacts emitted by the orchestrator and are the source of every number quoted in sections 04, 05, and 07.
