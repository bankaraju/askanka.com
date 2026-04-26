# ETF v3 60-day forward — picks/P&L vs production v2 (cadence=1)

**Generated:** 2026-04-26T19:44:16
**Rolling refit:** `etf_v3_rolling_refit_int1_lb756_curated_60d.json`
**Replay parquet:** `intraday_break_replay_60d_v0.1_ungated.parquet`

## Setup

- v3 zone reconstructed per trading day from rolling-refit per-window weights
- v3 zone thresholds: center=322.23, band=265.83 (from production reoptimizer)
- Replay cohort: 696 ungated 4-sigma breaks over 27 trading days, entries/exits via Kite minute bars
- v2 gate: `regime != NEUTRAL` (regime column = production v2's zone at trigger time)
- v3 gate: `v3_zone != NEUTRAL` (reconstructed)

## Cohort comparison

| Cohort | n trades | n dates | avg gross bps | cluster mean ± SE bps | n clusters | hit rate |
|---|---|---|---|---|---|---|
| **ALL** | 682 | 26 | +28.8 | +4.0 ± 12.2 | 26 | 55.9% |
| **v2_pass** | 627 | 22 | +33.2 | +7.9 ± 14.0 | 22 | 56.6% |
| **v3_pass** | 23 | 1 | -19.8 | -19.8 ± 0.0 | 1 | 56.5% |
| **both_pass** | 23 | 1 | -19.8 | -19.8 ± 0.0 | 1 | 56.5% |
| **v3_only** | 0 | 0 | — | — | 0 | — |
| **v2_only** | 604 | 21 | +35.2 | +9.2 ± 14.7 | 21 | 56.6% |
| **neither** | 55 | 4 | -21.3 | -17.5 ± 15.2 | 4 | 47.3% |

## Direction breakdown

| Cohort | LONG n | LONG bps | SHORT n | SHORT bps |
|---|---|---|---|---|
| **ALL** | 202 | -5.3 | 480 | +43.2 |
| **v2_pass** | 185 | -7.7 | 442 | +50.4 |
| **v3_pass** | 0 | +0.0 | 23 | -19.8 |
| **both_pass** | 0 | +0.0 | 23 | -19.8 |
| **v2_only** | 185 | -7.7 | 419 | +54.2 |
| **neither** | 17 | +20.5 | 38 | -40.0 |

## Daily breakdown

| date | v3_zone | v2_regimes | breaks | v2 pass | v3 pass | both | v3-only | v2-only | v3 P&L bps | v2 P&L bps |
|---|---|---|---|---|---|---|---|---|---|---|
| 2026-03-12 | NEUTRAL | RISK-OFF | 19 | 19 | 0 | 0 | 0 | 19 | +0 | -610 |
| 2026-03-13 | NEUTRAL | NEUTRAL | 7 | 0 | 0 | 0 | 0 | 0 | +0 | +0 |
| 2026-03-16 | NEUTRAL | EUPHORIA | 30 | 30 | 0 | 0 | 0 | 30 | +0 | +878 |
| 2026-03-17 | NEUTRAL | RISK-ON | 14 | 14 | 0 | 0 | 0 | 14 | +0 | -6 |
| 2026-03-18 | NEUTRAL | RISK-OFF | 44 | 44 | 0 | 0 | 0 | 44 | +0 | +2157 |
| 2026-03-19 | NEUTRAL | RISK-ON | 14 | 14 | 0 | 0 | 0 | 14 | +0 | +184 |
| 2026-03-20 | NEUTRAL | RISK-OFF | 92 | 92 | 0 | 0 | 0 | 92 | +0 | +24116 |
| 2026-03-23 | NEUTRAL | EUPHORIA | 70 | 70 | 0 | 0 | 0 | 70 | +0 | -2253 |
| 2026-03-24 | NEUTRAL | CAUTION | 11 | 11 | 0 | 0 | 0 | 11 | +0 | -294 |
| 2026-03-25 | NEUTRAL | RISK-ON | 17 | 17 | 0 | 0 | 0 | 17 | +0 | +309 |
| 2026-03-27 | NEUTRAL | RISK-OFF | 14 | 14 | 0 | 0 | 0 | 14 | +0 | -774 |
| 2026-03-30 | NEUTRAL | EUPHORIA | 38 | 38 | 0 | 0 | 0 | 38 | +0 | -173 |
| 2026-04-01 | NEUTRAL | RISK-ON | 32 | 32 | 0 | 0 | 0 | 32 | +0 | +1573 |
| 2026-04-02 | NEUTRAL | NEUTRAL | 19 | 0 | 0 | 0 | 0 | 0 | +0 | +0 |
| 2026-04-06 | NEUTRAL | NEUTRAL | 17 | 0 | 0 | 0 | 0 | 0 | +0 | +0 |
| 2026-04-07 | NEUTRAL | CAUTION | 32 | 32 | 0 | 0 | 0 | 32 | +0 | -2313 |
| 2026-04-08 | NEUTRAL | EUPHORIA | 19 | 19 | 0 | 0 | 0 | 19 | +0 | +36 |
| 2026-04-09 | NEUTRAL | EUPHORIA | 16 | 16 | 0 | 0 | 0 | 16 | +0 | +554 |
| 2026-04-10 | NEUTRAL | EUPHORIA | 13 | 13 | 0 | 0 | 0 | 13 | +0 | -291 |
| 2026-04-13 | NEUTRAL | RISK-ON | 46 | 46 | 0 | 0 | 0 | 46 | +0 | -2022 |
| 2026-04-15 | RISK-ON | CAUTION | 23 | 23 | 23 | 23 | 0 | 0 | -456 | -456 |
| 2026-04-16 | NEUTRAL | CAUTION | 12 | 12 | 0 | 0 | 0 | 12 | +0 | +431 |
| 2026-04-17 | NEUTRAL | CAUTION | 23 | 23 | 0 | 0 | 0 | 23 | +0 | +523 |
| 2026-04-20 | NEUTRAL | NEUTRAL | 12 | 0 | 0 | 0 | 0 | 0 | +0 | +0 |
| 2026-04-21 | NEUTRAL | CAUTION | 30 | 30 | 0 | 0 | 0 | 30 | +0 | -331 |
| 2026-04-22 | NEUTRAL | CAUTION | 18 | 18 | 0 | 0 | 0 | 18 | +0 | -401 |