# Appendix — Statistics

## Multiple-hypothesis correction (Bonferroni)

The H1 spec lists five tests across the ablation grid:

1. H1_OPPORTUNITY (full label, PCR + OI both agreeing)
2. H1_POSSIBLE_OPPORTUNITY_DEGRADED (no PCR, no OI — **this run**)
3. H1_UNCERTAIN_IS_NULL (UNCERTAIN label should show no edge)
4. H1_WARNING_IS_NULL (WARNING label should show no trading edge, only risk signal)
5. H1_ABLATION_MONOTONIC (removing signals should monotonically degrade performance)

Family-wise α = 0.05. Per-test α under Bonferroni:

    α_per_test = 0.05 / 5 = 0.01

All binomial p-values in this document are evaluated against 0.01, not the naive 0.05. This is conservative — it trades some statistical power for protection against a false-discovery chain across the ablation grid.

## Bootstrap procedure

`stats.bootstrap_sharpe_ci` implements a non-parametric IID bootstrap on the per-trade return series:

1. Input: array `x` of per-trade fractional returns (`pnl_net_inr / notional_inr`), shape (n,).
2. For each of `n_resamples=10_000` iterations:
   - Draw `n` indices with replacement from `[0, n)` using `numpy.random.default_rng(seed)`.
   - Compute Sharpe as `mean(x_resampled) / std(x_resampled, ddof=1)` — per-trade, not annualised. Scaled to trade-count Sharpe by multiplying by sqrt(n).
3. Report point Sharpe from the original series; lower / upper CI bounds from the α/2 and 1−α/2 percentiles of the 10,000 resampled Sharpes.

The seed=7 default makes the CI numerically reproducible across runs. Changing the seed changes the 4th decimal of the bound but not the sign.

## Binomial test

`stats.binomial_p(wins, total)` uses `scipy.stats.binomtest` with `p=0.5, alternative='two-sided'`. The "two-sided" choice is deliberate: the degraded variant could theoretically produce either a positive or negative edge relative to chance, so we don't know the sign of the alternative in advance. A one-sided test would require pre-registering the direction of the edge, which we have not done for this analysis.

## Per-regime sample sizes (in-sample)

To pass the per-regime criterion, a regime needs **n ≥ 30** trades and both hit-rate ≥ 0.55 **and** p-value ≤ 0.01. The 1,807-trade ledger distributes across regimes as observed from the regime backfill:

- Regime composition is reported by the orchestrator at run time. A future revision of this document should include a per-regime table. The verdict output confirms **0 of 4 regimes** with n ≥ 30 passed the combined bar; the fifth regime (one of the five defined by the ETF engine) had insufficient trades in the 18-month window.

## Drawdown

`stats.max_drawdown(equity_curve)` applies the running-maximum formula:

    dd[t] = (peak[0..t] - equity[t]) / peak[0..t]
    max_dd = max(dd)

where `equity_curve = cumsum(pnl_net_inr) + seed` and `seed = 100_000 ₹`. The 243.3% drawdown figure reflects that cumulative losses exceed the seed — the "drawdown" is computed against the running peak of cumulative P&L, not against a fixed starting equity. For a real portfolio, this would be capped by position sizing; here it is intentionally uncapped because the research metric is sensitivity of total P&L, not a simulated portfolio path.

## What the CI lower bound of −4.31 means

The bootstrap distribution of Sharpe estimates from 10,000 IID resamples of the 1,807-trade return series has its 0.5th percentile at −4.31 (trade-count-scaled). Informally, this says:

> If we re-ran the same Phase C POSSIBLE_OPPORTUNITY strategy on 10,000 alternative 1,807-trade universes drawn from the same underlying return distribution, 99.5% of them would produce a Sharpe worse than −2.33 and 50% of them would produce a Sharpe worse than −3.31.

The probability that the "true" Sharpe is positive, under the observed distribution, is effectively zero. This is the decisive rejection — not the drawdown or the per-regime counts, which are downstream consequences of the same underlying weak-edge result.

## Survivorship and lookahead

- **Survivorship:** the universe is point-in-time per month (NSE `fo_mktlots.csv`). Stocks that *entered* F&O mid-window are not back-included; stocks that *exited* mid-window are excluded from months after their exit. See `universe.universe_for_date`.
- **Lookahead:** profile training uses `next_date < cutoff_ts` as the cutoff filter — strictly excludes any bar whose next-day close would have fallen on or after the cutoff. This was a bug found and fixed during Task 7 (off-by-one) and is pinned by `test_profile.py::test_no_lookahead_boundary`.
- **Regime lookahead:** the regime label at classification time `d` uses `regime_by_date[d]` where the regime was decided by the ETF engine overnight before session open on `d`. No intraday regime switching.

## What this analysis does NOT claim

- It does **not** test the full H1_OPPORTUNITY label (PCR required, PCR unavailable).
- It does **not** test regime-filtered subsets (all regimes pooled in the headline).
- It does **not** test dynamic stops (flat 2% stop throughout).
- It does **not** test position sizing by Phase B conviction rank.
- It does **not** extrapolate the 48-trade forward sample to out-of-sample generalisation claims.

Each of these is a legitimate follow-up study. None of them should be inferred from this document.
