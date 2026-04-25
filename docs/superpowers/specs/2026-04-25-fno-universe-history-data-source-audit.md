# FNO Universe History data source audit

**Date:** 2026-04-25
**Dataset ID:** `fno_universe_history_v1`
**Tier:** D2
**Acceptance status:** Approved-for-research (with documented coverage gap)

## Purpose
Monthly NSE F&O membership snapshots feed point-in-time universe filtering per backtesting-specs §6.1. Required by H-2026-04-25-001 §3 universe definition.

## Source
NSE archives. Two URL patterns are referenced because NSE switched bhavcopy formats in early 2024:

1. **Legacy bhavcopy** — `https://archives.nseindia.com/products/content/derivatives/equities/fo<DDMonYYYY>bhav.csv.zip`
   - Schema: `INSTRUMENT` (FUTSTK / OPTSTK / ...), `SYMBOL`.
   - Status (probed 2026-04-25): HTTP 404 for every probed date 2021-05 through 2024-04. Effectively dead.
2. **UDiFF bhavcopy** — `https://archives.nseindia.com/content/fo/BhavCopy_NSE_FO_0_0_0_<YYYYMMDD>_F_0000.csv.zip`
   - Schema: `FinInstrmTp` (`STO`=stock options, `STF`=stock futures, `IDO`=index options, `IDF`=index futures), `TckrSymb`.
   - Live from 2024-01-02 onward.

Builder: `pipeline/scripts/build_fno_universe_history.py`. The builder tries UDiFF first, then falls back to the legacy URL. Stock-level rows are kept (`{FUTSTK, OPTSTK}` for legacy; `{STF, STO}` for UDiFF) and the symbol set is taken as the unique trimmed `SYMBOL` / `TckrSymb` values.

## Scope
**Aspiration:** 60 monthly snapshots over 5 years (2021-05 → 2026-04).
**Actual delivered (2026-04-25 build):** 27 snapshots, 2024-01-31 → 2026-03-30, all sourced from UDiFF. The 36 pre-2024 month-ends produce HTTP 404 against both URL patterns and could not be recovered from NSE public archives at this time.

The H-2026-04-25-001 backtest window (training 2024-10-25 → 2026-01-25, holdout 2026-01-26 → 2026-04-25, per the hypothesis spec §3) is fully covered by the delivered range. The pre-2024 gap is recorded as a data-policy §20 known issue and does not block H-2026-04-25-001.

## Schema
```json
{
  "snapshots": [
    {"date": "YYYY-MM-DD", "symbols": ["RELIANCE","TCS",...]},
    ...
  ],
  "source": "nseindia.com archives (UDiFF + legacy bhavcopy)",
  "fetched_at": "ISO timestamp",
  "format_counts": {"udiff": 27, "legacy": 0},
  "failed_months": ["2021-01-29", "..."]
}
```

## Cleanliness gates (policy §9) — actual results 2026-04-25
- Snapshot count: **27** (target ≥ 60; gap documented above).
- Empty `symbols` arrays: **0**.
- Duplicates within a snapshot: **0** (verified).
- Symbol-count range: **179 – 227** (expected band 150 – 250 — pass).
- `is_in_fno` PIT helper smoke-test on RELIANCE / FAKETICK: pass.

## Adjustment mode (policy §10)
N/A — universe is a categorical set; no price adjustment applies.

## Point-in-time correctness (policy §11)
`is_in_fno(symbol, event_date)` returns True iff `symbol` appears in the most-recent snapshot whose `date` is ≤ `event_date`. A symbol kicked out 2024-08-31 must NOT pass `is_in_fno("XYZ", "2024-09-15")`. Convention: events earlier than the first delivered snapshot (2024-01-31) are not PIT-checkable and shall be excluded by the consumer.

## Independent corroboration (policy §13)
The current-month `pipeline/data/fno_historical/*.csv` directory (213 ticker files) was spot-compared against the 2026-03-30 snapshot's 206 symbols; ≥ 200 of the 206 names overlap with the existing F&O ticker dump. Residual differences are SME / newly-added names, consistent with the 2025-Q4 NSE F&O additions.

## Contamination map (policy §14)
- Universe membership is a leak-free categorical at the snapshot date — no event-window contamination channel.
- The semi-annual NSE review introduces step-function changes in membership; consumers must treat these as discrete jumps rather than smooth migrations.

## Verdict
Approved-for-research, Tier D2, **for the 2024-01-31 → 2026-03-30 window only**. Eligible for H-2026-04-25-001 (whose backtest window is fully inside this range). Pre-2024 universe membership is treated as missing data per the policy §20 known-issues register; H-2026-04-25-001 must drop any event whose `event_date` is earlier than the first delivered snapshot.

## Future work
- If NSE republishes pre-2024 archive bhavcopies, re-run the builder to backfill.
- Alternative source (Wayback Machine CDX) probed 2026-04-25 — no coverage of the pre-2024 fo*bhav archive.
