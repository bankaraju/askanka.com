# Robustness Checks (OPPORTUNITY variant)

All sweeps operate on the `OPPORTUNITY`-variant in-sample trade ledger (`in_sample_ledger.parquet`, 630 trades, 14 symbols, 2024-10 → 2026-03). Only the cost or the per-day cap changes. The verdict is robust only if the headline loss is insensitive to reasonable parameter choices — i.e. the strategy doesn't "work" for some cherry-picked slippage or top-N that the backtest happened to default to.

## Slippage sweep

Round-trip slippage assumptions in basis points, re-costed post-hoc via `cost_model.round_trip_cost_inr`:

| slippage (bps) | trades | total net P&L (₹) | avg net P&L (₹) | hit rate |
|---:|---:|---:|---:|---:|
| 3 | 630 | −45,027 | −71.5 | 45.1% |
| 5 (baseline) | 630 | −51,327 | −81.5 | 43.5% |
| 7 | 630 | −57,627 | −91.5 | 43.0% |
| 10 | 630 | −67,077 | −106.5 | 41.6% |

**Reading:** at the most favourable assumption (3 bps), total P&L is still −₹45,027 with a 45.1% hit rate. Losses scale linearly with slippage, but the strategy is *never* positive across the range. A reviewer who argues "your 5 bps slippage is too punitive" should note that the 3 bps variant still loses.

The OPPORTUNITY variant shows smaller sensitivity than the degraded run (₹6,300 per 2 bps vs ₹18,000 per 2 bps) because it trades ~3× less often, so each cost increment touches fewer trades.

## Top-N per-day cap

`top_n` caps how many Phase C trades enter per day, ranked by `|z_score|` with ties broken by symbol (deterministic). The baseline run caps at 5.

| top_n | trades | total net P&L (₹) | avg net P&L (₹) | hit rate |
|---:|---:|---:|---:|---:|
| 1 | 267 | −18,868 | −70.7 | 44.6% |
| 3 | 535 | −41,489 | −77.6 | 44.3% |
| 5 (baseline) | 630 | −51,327 | −81.5 | 43.5% |
| 10 | 630 | −51,327 | −81.5 | 43.5% |
| 15 | 630 | −51,327 | −81.5 | 43.5% |

**Reading:** top_n=1 (highest-conviction z-score per day) has the *best* avg P&L and hit rate — but at 44.6% hit rate it's still losing. Unlike the degraded variant where top-N conviction made the strategy *worse*, OPPORTUNITY shows a monotonic improvement as we tighten the filter, consistent with real (but negative) signal in the z-score.

Counts saturate at 1,807 because the filtered signal set already has ≤ 5 entries on every trade day in the 14-symbol universe; top_n ≥ 5 is effectively uncapped.

## Sharpe point estimate and confidence interval

Bootstrap on `pnl_net_inr / notional_inr` with 10,000 IID resamples, fixed seed=7, α=0.01 (99% two-sided):

| leg | n | raw mean | raw std | per-trade Sharpe | bootstrap point | 99% CI |
|---|---:|---:|---:|---:|---:|---:|
| In-sample | 630 | −0.163% | 1.081% | −0.151 | **−1.973** | [−3.586, −0.351] |
| Forward | 21 | +0.367% | 0.492% | +0.746 | **+7.217** | [−2.020, +41.404] |

**In-sample:** the 99% CI upper bound is −0.35, so zero edge is rejected at 99% confidence in the *wrong* direction. This is a decisive finding.

**Forward:** the point Sharpe of +7.22 is consistent with a real intraday edge, but the CI straddles zero (lower bound −2.02) — 21 trades is not enough sample to reject "lucky draw." The two bounds are *not* contradictory: they reflect two windows of different lengths, different vol regimes, and different trade mechanics (EOD surrogate vs true intraday exit).

## Regime breakdown

The `degraded_ablation_positive` criterion and the regime-by-regime bar both fail — no regime has ≥ 30 in-sample trades *and* ≥ 55% hit rate *and* binomial p ≤ 0.01.

Regime distribution of the 630 in-sample trades is reported by the orchestrator at run time. A future revision of this document should include a per-regime hit-rate table; the orchestrator already computes this internally for the verdict check. The headline is **0 of 4 regimes with n ≥ 30** cleared the combined bar.

## What would change the verdict

1. **Larger forward sample.** The live shadow ledger (F3 leg) starting today should accumulate 100–150 trades over six months. If the forward 76.2% hit rate is stable at that sample size, the binomial p drops below 0.001 and the verdict flips on the forward leg alone.
2. **Per-(symbol, regime) stops.** Current flat 2% stop ignores the stored `std_return`. A dynamic stop sized to each symbol's historical volatility is the highest-ROI follow-up.
3. **Regime-filtered strategy.** If one regime (e.g. NEUTRAL) accounts for the positive forward P&L and the others are noise, a regime-filtered variant could pass where the pooled strategy fails.
4. **OI anomaly signal.** Currently not fed to the classifier (empty dict). Wiring per-stock OI anomalies from the NSE bhavcopy (day-over-day OI change > 2σ) would add a second derivatives-market input and could promote some `POSSIBLE_OPPORTUNITY` rows to `OPPORTUNITY`.

None of these are applied to this run's verdict. They are the **follow-up** agenda, not caveats that would flip the current result.
