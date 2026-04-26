# Gap-and-fade diagnostic on RISK-ON inversion

Source: official-zone series from Test 1 (post-alignment-fix); 
NIFTY OHLC from `pipeline/data/india_historical/indices/NIFTY_daily.csv`.

## Decomposition rules

For each decision day T:
- gap_pct      = (open[T+1] - close[T]) / close[T] x 100
- intraday_pct = (close[T+1] - open[T+1]) / open[T+1] x 100
- c2c_pct      = (close[T+1] - close[T]) / close[T] x 100

Gap-and-fade is confirmed if mean(gap) > 0 AND mean(intraday) < 0. 
True weakness if mean(gap) < 0. 
Noise if both means are within +/- 0.05 pp.

## Per-zone decomposition

| Zone | n | gap mean pp | gap pct >0 | intra mean pp | intra pct <0 | c2c mean pp | c2c pct <0 | verdict |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| EUPHORIA | 5 | +0.3670 | 20.0% | -0.1571 | 40.0% | +0.1831 | 60.0% | gap_and_fade |
| RISK-ON | 27 | -0.0758 | 51.9% | -0.1403 | 63.0% | -0.2166 | 70.4% | true_weakness |
| NEUTRAL | 409 | +0.0584 | 61.9% | -0.0100 | 53.1% | +0.0483 | 45.7% | mixed |
| CAUTION | 29 | +0.0269 | 51.7% | -0.0911 | 58.6% | -0.0637 | 51.7% | mixed |
| RISK-OFF | 19 | -0.0031 | 47.4% | -0.1235 | 63.2% | -0.1256 | 57.9% | mixed |

## RISK-ON per-event detail (n=27)

| decision date | outcome date | gap pp | intra pp | c2c pp |
|---|---|---:|---:|---:|
| 2024-05-28 | 2024-05-29 | -0.5479 | -0.2550 | -0.8015 |
| 2024-05-29 | 2024-05-30 | -0.3843 | -0.5695 | -0.9516 |
| 2024-07-10 | 2024-07-11 | +0.2964 | -0.3304 | -0.0349 |
| 2024-07-11 | 2024-07-12 | +0.2961 | +0.4683 | +0.7658 |
| 2024-07-12 | 2024-07-15 | +0.3487 | -0.0037 | +0.3451 |
| 2024-07-19 | 2024-07-22 | -0.3471 | +0.2598 | -0.0883 |
| 2024-07-22 | 2024-07-23 | +0.2434 | -0.3657 | -0.1232 |
| 2024-07-23 | 2024-07-24 | -0.1393 | -0.1287 | -0.2678 |
| 2024-10-18 | 2024-10-21 | +0.4108 | -0.7014 | -0.2935 |
| 2024-10-21 | 2024-10-22 | +0.0708 | -1.3168 | -1.2469 |
| 2024-10-22 | 2024-10-23 | -0.3839 | +0.2353 | -0.1496 |
| 2025-02-07 | 2025-02-10 | -0.0685 | -0.6889 | -0.7570 |
| 2025-02-10 | 2025-02-11 | +0.0083 | -1.3332 | -1.3250 |
| 2025-03-28 | 2025-04-01 | -0.7579 | -0.7515 | -1.5037 |
| 2025-04-01 | 2025-04-02 | +0.1161 | +0.6026 | +0.7194 |
| 2025-04-30 | 2025-05-02 | -0.0916 | +0.1431 | +0.0514 |
| 2025-05-02 | 2025-05-05 | +0.2990 | +0.1706 | +0.4701 |
| 2025-09-22 | 2025-09-23 | +0.0264 | -0.1567 | -0.1303 |
| 2025-09-23 | 2025-09-24 | -0.2414 | -0.2065 | -0.4474 |
| 2025-09-24 | 2025-09-25 | -0.0894 | -0.5738 | -0.6627 |
| 2025-11-28 | 2025-12-01 | +0.4688 | -0.5700 | -0.1038 |
| 2025-12-01 | 2025-12-02 | -0.3354 | -0.2137 | -0.5484 |
| 2025-12-02 | 2025-12-03 | -0.1049 | -0.0727 | -0.1775 |
| 2025-12-10 | 2025-12-11 | +0.0520 | +0.4934 | +0.5457 |
| 2025-12-11 | 2025-12-12 | +0.2805 | +0.2917 | +0.5730 |
| 2026-04-09 | 2026-04-10 | +0.4435 | +0.7121 | +1.1588 |
| 2026-04-10 | 2026-04-13 | -1.9168 | +1.0727 | -0.8646 |

## Decision logic

Apply the verdict from the RISK-ON row:
  - `gap_and_fade`   -> invert RISK-ON: SHORT at open[T+1], cover at close[T+1]
                       (or skip if you want OOS confirmation first)
  - `true_weakness`  -> RISK-ON correctly flags weakness; do not invert,
                       just hold the original SHORT direction (matches catalog)
  - `noise` / `mixed`-> skip RISK-ON, focus on 4 working regimes

## Verdict for RISK-ON (post-decomposition)

The user's binary framework split between "gap-and-fade" (positive gap +
negative intraday) vs "true weakness" (negative gap). The data shows a
THIRD case: **gap roughly zero, intraday clearly negative**.

  - Gap mean: -0.076 pp BUT median +0.008 pp -- mean pulled down by ONE
    4-sigma outlier (2026-04-10, gap = -1.92%). Excluding that day, gap
    mean is approximately zero.
  - Intraday mean: -0.14 pp, 63% of sessions negative.
  - C2C mean: -0.22 pp, 70.4% of sessions negative.
  - Trimmed (drop 3 best + 3 worst c2c): mean -0.21 pp, 76.2% pct_down --
    inversion gets STRONGER without tail events, so it is not driven by
    a few big-down days.

This is **intraday-fade after a roughly-flat overnight gap**, not classical
gap-and-fade. The Indian market grinds lower during the trading session on
RISK-ON days; there is no overnight-optimism gap for the market to arbitrage
away.

## Two candidate inverted strategies

  - INTRADAY SHORT: enter at open[T+1], cover at close[T+1].
    Expected: +0.14 pp/trade, 63% win rate, no overnight risk.
  - C2C SHORT: enter at close[T] (decision close), cover at close[T+1].
    Expected: +0.22 pp/trade, 70.4% win rate. Captures slight gap-down
    leg too but takes overnight exposure.

## Recommendation

Do NOT deploy live on n=27 alone. Instead:

  1. Pre-register both inverted strategies (INTRADAY SHORT and C2C SHORT)
     against the H-2026-04-26 hypothesis-registry pattern, with the smoke
     window as the in-sample evidence and a clean OOS window (Phase 3
     forward shadow, 30+ trading days from 2026-04-27) as the single-touch
     holdout.
  2. Continue Phase 2 with RISK-ON treated as "no trade" in the v3 pipeline
     (Option 2 from the user's framework). Avoids the -0.22 pp/trade drag
     without committing to the unconfirmed inversion.
  3. After Phase 3 OOS evidence, decide:
     - C2C SHORT win-rate >= 60% on >= 15 OOS RISK-ON days -> deploy inverted.
     - Otherwise -> keep RISK-ON in skip mode permanently.

This protects against the n=27 false-positive risk while preserving the
optionality if the inversion is real.