# NSE Sectoral Indices data source audit

**Date:** 2026-04-25
**Dataset ID:** `nse_sectoral_indices_v1`
**Tier (proposed):** D2
**Owner:** Bharat Ankaraju
**Acceptance status:** Approved-for-research, Tier D2

## Purpose
10-index daily-bar history feeds H-2026-04-25-001 §3 macro-exclusion filter (sector-index returns on T, T+1) and §4 peer cohort audit (peer-cohort sanity checks against parent index returns).

## Source
Primary: Kite (NSE) via `pipeline/research/phase_c_backtest/fetcher.py::fetch_daily`.
Fallback: yfinance (`^NSEBANK`, `^CNXIT`, ...).
Both implementations live in `pipeline/research/phase_c_v5/data_prep/backfill_indices.py`.

## Symbols
| Hypothesis name | Kite alias | yfinance alias |
|---|---|---|
| NIFTY Bank | NSE:NIFTY BANK | ^NSEBANK |
| NIFTY IT | NSE:NIFTY IT | ^CNXIT |
| NIFTY Pharma | NSE:NIFTY PHARMA | ^CNXPHARMA |
| NIFTY Auto | NSE:NIFTY AUTO | ^CNXAUTO |
| NIFTY FMCG | NSE:NIFTY FMCG | ^CNXFMCG |
| NIFTY Metal | NSE:NIFTY METAL | ^CNXMETAL |
| NIFTY Energy | NSE:NIFTY ENERGY | ^CNXENERGY |
| NIFTY PSU Bank | NSE:NIFTY PSU BANK | ^CNXPSUBANK |
| NIFTY Realty | NSE:NIFTY REALTY | ^CNXREALTY |
| NIFTY Media | NSE:NIFTY MEDIA | ^CNXMEDIA |

## Backfill
- Command: `python -m pipeline.scripts.backfill_sectoral_indices --days 1825`
- Output: `pipeline/data/sectoral_indices/<INDEX>_daily.csv` schema `(date,open,high,low,close,volume)`
- Invocation evidence: see Task 0a Step 4 below.

## Cleanliness gates (policy §9)
- per-index missing-bar count ≤ 1% of NSE business days
- zero-or-negative-close count = 0
- duplicate-date count = 0

## Adjustment mode (policy §10)
N/A — indices are not split-adjusted at the level we consume.

## Point-in-time correctness (policy §11)
Each row's `date` is the trade date as published by NSE/Yahoo. No look-ahead.

## Independent corroboration (policy §13)
Kite-vs-yfinance agreement spot-check on 3 random dates per index, max diff < 0.5%.

## Contamination map (policy §14)
- Result-day moves on T, T+1 are the macro-exclusion targets — no contamination of features.
- Index methodology rebalances (semi-annual NSE reviews) cause discrete jumps; recorded as known caveat, not a contamination of the residual signal because peer cohorts are stock-level not index-level.

## Verdict
Approved-for-research, Tier D2. Sufficient for the H-2026-04-25-001 backtest.
