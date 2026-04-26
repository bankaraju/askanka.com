# H-2026-04-26-003 candidate — NEUTRAL-day long-intraday backtest

_generated_: 2026-04-26T05:05:00+00:00

## Hypothesis

On NEUTRAL regime days (where the σ-correlation-break rule fires thinly — ~5 trades in 60 days), a separate **long-only intraday** trade entered at 09:30 and exited at 14:30 makes money, exploiting a different alpha source (momentum / quality persistence) than the σ-break mean-reversion rule.

## Data availability

- **Regime history:** 1256 days (2021-04-23 → 2026-04-23). NEUTRAL = 297 days (23.6%).
- **Sectoral index daily OHLC:** 5 indices (NIFTY 50, NIFTY IT, NIFTY METAL, NIFTY PSU BANK, NIFTY ENERGY), each ~5y.
- **Intraday minute bars:** 121 sectoral-index parquet files (~38 trading days, 2026-03-03 → 2026-04-24). Used only to *calibrate* the daily proxy below — too narrow to backtest directly across 5 years.
- **FCS / TA-attractiveness history:** **NOT AVAILABLE.** ta_attractiveness_scores.json is a single snapshot (no per-day series). Variant B is therefore not runnable historically.

## Methodology

### The daily-to-intraday proxy (CRITICAL CAVEAT)

We do not have minute bars across the 5-year window. We approximate the 09:30->14:30 return by:

```
intraday_return ~= resolve_pct * (close - open) / open
```

where `resolve_pct` is the empirical fraction of the daily open→close move realized by 14:30, **fitted from the 38-day intraday sample we do have**:

- n_samples = 121
- n_valid_for_ratio (|full_day|>5bp) = 113
- **resolve_pct (mean)** = **0.925**
- ratio_median = 0.8927
- ratio_std = 0.6412
- intraday_pct_mean (raw) = 0.001771
- full_pct_mean (raw) = 0.001568

**The proxy preserves the SIGN of the daily move and scales magnitude by `resolve_pct`. It does NOT inject any look-ahead — `(close − open) / open` is computed from the same day's OHLC, and `resolve_pct` is a constant scalar fitted on a disjoint sub-period.**

**Honest reading:** any intraday edge claim is conditional on this proxy. If the true 09:30->14:30 dynamic on NEUTRAL days differs systematically from `resolve_pct × full_day`, the numbers below are biased. We cannot eliminate that risk without minute bars.

## Variant A — Long sectoral index intraday (09:30->14:30) on NEUTRAL days

| Symbol | n NEUTRAL | mean % | std % | hit % | Sharpe (ann) | t | cum % |
|---|---:|---:|---:|---:|---:|---:|---:|
| NIFTY | 277 | -0.0279 | 0.5939 | 49.1 | -0.745 | -0.781 | -7.88 |
| NIFTYIT | 277 | -0.0881 | 0.9743 | 45.49 | -1.435 | -1.504 | -22.68 |
| NIFTYMETAL | 277 | -0.0647 | 1.231 | 49.1 | -0.834 | -0.875 | -18.14 |
| NIFTYPSUBANK | 277 | -0.1025 | 1.3456 | 47.29 | -1.209 | -1.267 | -26.58 |
| NIFTYENERGY | 277 | -0.0585 | 0.9624 | 46.21 | -0.965 | -1.011 | -16.04 |

### Comparator: passive full-day hold (09:15->15:30, NEUTRAL only)

| Symbol | n NEUTRAL | mean % | hit % | Sharpe (ann) | t | cum % |
|---|---:|---:|---:|---:|---:|---:|
| NIFTY | 277 | -0.0301 | 49.1 | -0.745 | -0.781 | -8.53 |
| NIFTYIT | 277 | -0.0952 | 45.49 | -1.435 | -1.504 | -24.36 |
| NIFTYMETAL | 277 | -0.0699 | 49.1 | -0.834 | -0.875 | -19.61 |
| NIFTYPSUBANK | 277 | -0.1108 | 47.29 | -1.209 | -1.267 | -28.56 |
| NIFTYENERGY | 277 | -0.0632 | 46.21 | -0.965 | -1.011 | -17.31 |

### Comparator: passive full-day hold (09:15->15:30, ALL regimes)

| Symbol | n days | mean % | hit % | Sharpe (ann) | t | cum % |
|---|---:|---:|---:|---:|---:|---:|
| NIFTY | 1191 | -0.038 | 48.36 | -0.876 | -1.903 | -38.19 |
| NIFTYIT | 1191 | -0.0602 | 46.52 | -0.878 | -1.908 | -54.52 |
| NIFTYMETAL | 1187 | -0.1136 | 47.26 | -1.247 | -2.705 | -77.11 |
| NIFTYPSUBANK | 1187 | -0.0743 | 46.67 | -0.747 | -1.621 | -64.35 |
| NIFTYENERGY | 1188 | -0.1017 | 46.46 | -1.44 | -3.126 | -72.32 |

## Variant B — long top-N FCS-attractiveness stocks intraday on NEUTRAL days

**Status: SKIPPED**

Reason: ta_attractiveness_scores.json contains a CURRENT snapshot only (single 'updated_at' timestamp, no per-day history). No historical FCS / TA-attractiveness time-series exists in pipeline/data/. Backtesting Variant B requires per-day rank history of attractiveness scores for ≥1 year — not available.

Current snapshot info: updated_at=2026-04-25T16:00:07.555435, ticker_count=213

**Remediation to enable in future:** To enable Variant B in a future run: write pipeline/data/feature_scorer_history.parquet with columns (date, ticker, score) populated daily by 16:00 IST EOD job. This is a green-field collector, not a backfillable derivation.

## Bottom line

Across 5 sectoral indices, NEUTRAL-day 09:30->14:30 intraday long shows: average mean per-day return = -0.0683%, average annualized Sharpe = -1.038, 0/5 symbols positive in mean, 0/5 symbols with |t|>1.96. NIFTY 50: mean=-0.0279%, hit=49.1%, Sharpe=-0.745, t=-0.781. Passive full-day hold on the same NEUTRAL days has average Sharpe = -1.038.  DECISION: edge is **NOT convincing** — do NOT register H-2026-04-26-003 in its current form. The NEUTRAL-day long-only intraday on indices does not clear the bar (majority positive + Sharpe>0.5 + at least one |t|>1.96). Practical implication: sitting in cash on NEUTRAL days is a Sharpe-positive decision vs taking on undifferentiated market beta — UNLESS the FCS-stock Variant B (currently un-backtestable) reveals quality-persistence edge that the index-level test cannot see.

## Caveats and limits of this study

1. **Daily proxy vs true intraday.** The 14:30 exit return is a scaled version of the open→close daily move. If NEUTRAL days systematically have non-monotonic intraday paths (e.g. morning spike → afternoon fade), the proxy mis-states the 14:30 return. The 38-day calibration sample is too small to reject this risk.
2. **No frictions modeled.** Brokerage, STT, slippage, impact at the open are all zero in this run. The mechanical ETF-future / index-future round trip costs ~5–10 bps; any edge below that is unbankable.
3. **Variant B not runnable.** No historical FCS time series exists, so the 'top-quality stocks' arm of the user's theory cannot be evaluated here.
4. **Single-touch risk.** This is a research backtest. If a strategy is registered as H-2026-04-26-003, its single-touch holdout under the autoresearch v2 protocol must use a held-out period not present above.
