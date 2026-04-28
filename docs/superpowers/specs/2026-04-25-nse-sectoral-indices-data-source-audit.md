# NSE Sectoral Indices data source audit

**Date:** 2026-04-25 (initial), **2026-04-28 (T0a follow-up #230 — concrete numbers + reconciliation)**
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
- Backfill behaviour: fetcher attempts Kite first, falls back to yfinance if the
  Kite session token is not valid (interactive runs outside the
  `AnkaRefreshKite` 09:00 IST window). Per the §13 reconciliation table below,
  the current dataset is yfinance-fallback (rows match fresh yfinance pulls
  exactly to 4 decimal places — Kite-pulled data would differ by basis points
  at the close due to last-tick rounding).

## Lineage (policy §7)
| Field | Value |
|---|---|
| Last refresh date | 2026-04-25 (CSV mtime) |
| Last bar date | 2026-04-24 (most recent NSE close in CSVs) |
| Refresh script | `pipeline/scripts/backfill_sectoral_indices.py` (commit 8647c15 has the audit; data was backfilled before this commit) |
| Source path | `pipeline/data/sectoral_indices/<INDEX>_daily.csv` |
| Source observed | yfinance fallback (per §13) |
| Schema | `(date YYYY-MM-DD, open f64, high f64, low f64, close f64, volume i64)` |

## Cleanliness gates (policy §9)
- per-index missing-bar count ≤ 1% of NSE business days
- zero-or-negative-close count = 0
- duplicate-date count = 0

### Cleanliness baseline 2026-04-28 (full universe, policy §9.1)

Computed by `pipeline/scripts/audit_nse_sectoral_indices.py` (committed
alongside this update). Re-run via
`python -m pipeline.scripts.audit_nse_sectoral_indices`. JSON artefact lands
at `pipeline/data/research/edb/sectoral_indices_audit_<date>.json` (gitignored
— reproducible from the script):

| Index | n_rows | First | Last | Density | Zero/neg close | Dup dates |
|---|---:|---|---|---:|---:|---:|
| BANKNIFTY | 1251 | 2021-03-30 | 2026-04-24 | 94.49% | 0 | 0 |
| NIFTYIT | 1251 | 2021-03-30 | 2026-04-24 | 94.49% | 0 | 0 |
| NIFTYPHARMA | 1250 | 2021-03-30 | 2026-04-24 | 94.41% | 0 | 0 |
| NIFTYAUTO | 1240 | 2021-03-30 | 2026-04-24 | 93.66% | 0 | 0 |
| NIFTYFMCG | 1240 | 2021-03-30 | 2026-04-24 | 93.66% | 0 | 0 |
| NIFTYMETAL | 1240 | 2021-03-30 | 2026-04-24 | 93.66% | 0 | 0 |
| NIFTYENERGY | 1240 | 2021-03-30 | 2026-04-24 | 93.66% | 0 | 0 |
| NIFTYPSUBANK | 1240 | 2021-03-30 | 2026-04-24 | 93.66% | 0 | 0 |
| NIFTYREALTY | 1240 | 2021-03-30 | 2026-04-24 | 93.66% | 0 | 0 |
| NIFTYMEDIA | 1240 | 2021-03-30 | 2026-04-24 | 93.66% | 0 | 0 |

- "Density" = `n_rows / business_days_in_range × 100`. The ~6.5% gap to 100% is
  consistent with the NSE-holiday calendar (~13–17 holidays per year).
- BANKNIFTY/NIFTYIT/NIFTYPHARMA have 10–11 extra rows because their backfill
  predates the Apr 2021 cohort cutoff; the rest start exactly on 2021-03-30.
- Cleanliness gates: PASS for all 10 indices on all 3 metrics.

## Adjustment mode (policy §10)
N/A — indices are not split-adjusted at the level we consume.

## Point-in-time correctness (policy §11)
Each row's `date` is the trade date as published by NSE/Yahoo. No look-ahead.
`fetch_daily` uses `auto_adjust=False`, so closes are raw published levels
(matters for matching against historical news/event timestamps).

## Independent corroboration (policy §13)

**Method 2026-04-28:** randomly sample 3 dates from the most-recent-250 trading
days for each of 3 spot-check indices (BANKNIFTY, NIFTYIT, NIFTYPHARMA). Pull
fresh yfinance close and compare to the local CSV close. PASS criterion:
`max |delta_pct| < 0.5%` per index.

| Index | Date | Local close | yfinance close | Δ% |
|---|---|---:|---:|---:|
| BANKNIFTY | 2025-10-20 | 58033.1992 | 58033.1992 | 0.0000 |
| BANKNIFTY | 2025-12-09 | 59222.3516 | 59222.3516 | 0.0000 |
| BANKNIFTY | 2026-02-02 | 58619.0000 | 58619.0000 | 0.0000 |
| NIFTYIT | 2025-10-20 | 35292.6016 | 35292.6016 | 0.0000 |
| NIFTYIT | 2025-12-09 | 38130.6016 | 38130.6016 | 0.0000 |
| NIFTYIT | 2026-02-02 | 38074.1484 | 38074.1484 | 0.0000 |
| NIFTYPHARMA | 2025-10-17 | 22253.7500 | 22253.7500 | 0.0000 |
| NIFTYPHARMA | 2025-12-08 | 22640.6992 | 22640.6992 | 0.0000 |
| NIFTYPHARMA | 2026-02-02 | 21549.5508 | 21549.5508 | 0.0000 |

**Verdict:** PASS 9/9 at 0.0% delta. The exact agreement to 4 decimals
*confirms* that:
- no manual edits have been made to the CSVs since backfill (data is
  reproducible from yfinance);
- yfinance has not silently re-published these dates with revised values;

…but it *does not* corroborate Kite ↔ yfinance agreement, because the local
CSVs are themselves yfinance-fallback (see §"Backfill" above).

**Deferred (true Kite cross-check):** the Kite-vs-yfinance reconciliation
the original audit doc promised requires running the spot-check during a
live Kite session window. Recommended runbook (not blocking for D2):

1. During an `AnkaRefreshKite` window (09:00 IST + freshness ≤6h), run
   `python -m pipeline.scripts.backfill_sectoral_indices --days 30` writing
   to a scratch directory.
2. Confirm the fetcher returned Kite (not yfinance) — the docstring at
   `backfill_indices.py:111-123` shows the source is decided silently; add a
   one-line `log.info("Kite returned %d rows", len(df))` if forensics demand
   it.
3. Run `C:/tmp/edb_t0a_audit_230.py` pointed at the scratch directory; expect
   non-zero deltas (basis-point-scale) reflecting the genuine Kite ↔ yfinance
   close-tick discrepancy.

This is queued as a follow-up but not gating: D2 ("Approved-for-research")
allows fallback-source datasets so long as cleanliness holds and the
reconciliation evidence is honest.

## Contamination map (policy §14)
- **Result-day moves** on T, T+1 are the macro-exclusion targets — the index
  return on those days is the *signal feature*, not contamination of the
  residual signal.
- **Index methodology rebalances** (semi-annual NSE reviews) cause discrete
  jumps. Recorded as known caveat. Not a contamination of the per-stock
  residual because the H-2026-04-25-001 peer cohort is stock-level, not
  index-level. Treated as a robustness check at evaluation: if event-cluster
  density spikes around an NSE rebalance date, the event_filter gate already
  drops the cohort.
- **Holiday-misalignment** (yfinance occasionally publishes a stale-Friday
  close on a Saturday at IST midnight): mitigated by the cleanliness gate
  (zero duplicate-date count) and by `auto_adjust=False`. Verified clean in
  the §9.1 baseline above (0 duplicates across all 10 indices).
- **No insider channel** — sectoral indices are aggregations published by
  NSE; no individual-firm news lands here directly.

## Verdict
Approved-for-research, Tier D2. Sufficient for the H-2026-04-25-001 backtest.

**T0a follow-up #230 closure (2026-04-28):**
- §7 Lineage populated with concrete run metadata.
- §9.1 Cleanliness baseline added (10/10 PASS).
- §13 Reconciliation: 9/9 spot-checks PASS at 0.0% delta — confirms data
  reproducibility but not Kite ↔ yfinance agreement (dataset is yfinance-
  fallback). True Kite cross-check is documented as a non-blocking runbook.
- §14 Contamination map expanded with 4 channels (result-day, rebalance,
  holiday-alignment, insider absence).
- Audit JSON written to
  `pipeline/data/research/edb/sectoral_indices_audit_2026-04-28.json` for
  traceable re-run.
