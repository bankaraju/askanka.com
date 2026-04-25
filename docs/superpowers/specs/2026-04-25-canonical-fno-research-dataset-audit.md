# Canonical F&O Research Dataset — Audit + Registration

**Dataset ID:** `canonical_fno_research_v1`
**Artifact:** `pipeline/data/canonical_fno_research_v1.json`
**Fetched at:** 2026-04-25
**Status:** Approved-for-research (per `anka_data_validation_policy_global_standard.md` §6, §8, §9, §10, §11, §14)

## 1. Purpose

A long-lived, registered, point-in-time-correct universe of F&O-listed Indian stocks plus their associated price + sectoral context, used as the single canonical input panel for all backtests under `pipeline/autoresearch/` from 2026-04-25 onward.

This document fulfils the §5A precondition in `docs/superpowers/specs/backtesting-specs.txt` and the data-side gate in `CLAUDE.md`. Backtests that consume this dataset shall cite this artifact by name.

## 2. Scope

- **Time window:** 2021-04-23 → 2026-04-22 (5 years; bounded by F&O CSV availability)
- **Universe size:** 154 tickers
  - 133 "stable" F&O members (present in all 27 monthly snapshots 2024-01-31 → 2026-03-30)
  - 21 IPO late-entrants with ≥ 100 bars of history and listing > 2021-10-23
- **Excluded with reason:**
  - 1 ticker with < 100 bars: `LTM` (listed 2026-02-18, < 50 bars at audit time)
  - 8 tickers with CSV files but never appearing in any universe snapshot (recent F&O additions post 2026-03-30, or data-fetch artifacts): `ADANIPOWER`, `COCHINSHIP`, `FORCEMOT`, `GODFRYPHLP`, `HYUNDAI`, `MOTILALOFS`, `NAM-INDIA`, `VMM` — note: `HYUNDAI` and `VMM` ARE re-included via the IPO path because their CSV first-bar dates fall in the IPO cutoff window.
  - 62 tickers in universe history but with no F&O CSV file. These are historical F&O members (entered/exited the F&O universe across the panel window). Backfill task tracked separately; not blocking.

## 3. Data lineage (per §3 and §6 of the data validation policy)

| Source | Path | Window | Status | Note |
|---|---|---|---|---|
| F&O equity OHLCV | `pipeline/data/fno_historical/*.csv` | 2021-04-23 → 2026-04-22 | Approved | 213 raw CSVs; 154 enter canonical universe |
| F&O universe history (membership snapshots) | `pipeline/data/fno_universe_history.json` | 2024-01-31 → 2026-03-30 | Partial-approved | 27 monthly snapshots; pre-2024 fetch failed (NSE archive endpoints permanently 404 — see `pipeline/scripts/build_fno_universe_history.py` docstring) |
| Global ETF panel | `pipeline/data/research/phase_c/daily_bars/*.parquet` | 2018-01-02 → 2026-04-23 | Approved | 67 parquets; 28 mapped to `C.ETF_SYMBOLS` |
| NSE sectoral indices | `pipeline/data/sectoral_indices/*.csv` | 2021-03-30 → 2026-04-24 | Approved | 10 daily indices (BANKNIFTY, NIFTYAUTO, NIFTYENERGY, NIFTYFMCG, NIFTYIT, NIFTYMEDIA, NIFTYMETAL, NIFTYPHARMA, NIFTYPSUBANK, NIFTYREALTY); registered as `nse_sectoral_indices_v1` (commit `f11a403`) |
| Regime history | `pipeline/data/regime_history.csv` | 2021-04-23 → 2026-04-23 | Approved | columns: date, regime_zone, signal_score (the `regime` column required by the runner is sourced via `regime_zone` rename — see §10 below) |
| Sector mapping | `opus/artifacts/*/indianapi_stock.json` | snapshot | Approved | 211 files; 208/215 (96.7%) mapped to a sector; 7 Unmapped |

## 4. Schema contracts (per §8)

Each F&O equity CSV (per file):
```
columns: Date (datetime ISO), Close, High, Low, Open, Volume
sort: ascending by Date
sentinel: NaN forbidden in Close; non-NaN Volume guaranteed for ≥ 99% of rows
adjustment_mode: dividend-adjusted (per upstream EODHD pipeline)
```

Each sectoral index CSV:
```
columns: date (datetime ISO), open, high, low, close, volume
sort: ascending by date
adjustment_mode: total return index basis (NSE methodology)
```

Canonical universe artifact (`canonical_fno_research_v1.json`):
```
{
  "dataset_id": "canonical_fno_research_v1",
  "fetched_at": ISO,
  "window_start": "2021-04-23",
  "window_end": "2026-04-22",
  "n_tickers": 154,
  "tickers": [str, ...],
  "per_ticker_valid_from": {ticker: ISO, ...},
  "per_ticker_valid_to":   {ticker: ISO, ...},
  "sectoral_indices": [str, ...]
}
```

Lookup contract: a ticker is in the universe at date d iff d ∈ [valid_from, valid_to].

## 5. Cleanliness gates passed (per §9)

- ✅ NaN check on Close column: 0 NaNs across 154 canonical tickers
- ✅ Date monotonicity: all CSVs sorted ascending; no duplicate dates
- ✅ Internal gap check: 1 ticker (FORCEMOT, 63-day gap; **excluded** from canonical)
- ✅ Per-ticker minimum length: ≥ 100 bars enforced at audit time (LTM excluded for failing this)
- ✅ Sectoral indices: continuous daily coverage, no gaps > 5 calendar days

## 6. Adjustment mode declaration (per §10)

| Source | Mode |
|---|---|
| F&O equity CSVs | dividend-adjusted close (EODHD) |
| Sectoral indices | total-return-index basis (NSE) |
| Global ETF panel | dividend-adjusted close |

Adjustment mode is documented at the dataset level. Models consume close-to-close returns; corporate action splits affecting volume require care if/when volume features are added beyond `volume_z_20d`.

## 7. Point-in-time correctness (per §11)

- **F&O equity bars:** correct by construction (each row is a closing bar for that date; no future leakage)
- **F&O universe membership:**
  - Post-2024-01-31: from monthly snapshots, forward-filled to daily (a stock is considered in the universe between snapshot date d_k and d_{k+1} per the snapshot at d_k)
  - Pre-2024-01-31: **inferred** from stability — the 133 "stable F&O" tickers are assumed to have been F&O members for the entire pre-2024 panel period. This introduces a small survivorship bias (stocks that were in F&O 2021-2023 but exited before 2024 are excluded). The 21 IPOs are correctly absent before their listing dates.
  - **Bias documentation:** survivorship bias bounded to "F&O members removed between 2021-04 and 2024-01 are excluded." The full list of pre-2024 F&O removals is unrecoverable per NSE archive endpoint failure.
- **Sectoral indices:** correct by construction
- **Regime labels:** correct by construction (regime engine outputs are dated)

## 8. Contamination map (per §14)

| Channel | Risk | Mitigation |
|---|---|---|
| Look-ahead via daily lookup of monthly universe snapshots | Low — snapshot dates are end-of-month, looked up as-of d ≤ snapshot date | Forward-fill from previous snapshot only |
| Survivorship bias (pre-2024 universe inferred) | Medium — bounded as in §7 | Documented; for tail-prediction the bias is unlikely to systematically align with model predictions |
| Adjustment-mode skew | Low — all consumers expect adjusted close | Single mode declared per source |
| Earnings-event leakage through daily bars | Out of scope here — handled by per-hypothesis features | N/A at dataset level |

## 9. Sectoral indices integration

The 10 NSE sectoral indices are added to the canonical dataset for two purposes:

1. **Global breadth:** Treated as additional "ETF-like" symbols in the global state vector, alongside the 28 global ETFs in `C.ETF_SYMBOLS`. The model sees India sector breadth as part of the input state.
2. **(Future)** Own-sector context: a per-stock feature that pulls the stock's own sectoral index returns/vol may be added in a follow-up hypothesis.

Sector → index mapping table (used by future own-sector features; not consumed by global-breadth integration):

| Sector bucket (from SectorMapper) | NSE sectoral index |
|---|---|
| Banks | BANKNIFTY |
| IT_Services | NIFTYIT |
| Pharma | NIFTYPHARMA |
| FMCG | NIFTYFMCG |
| Metals_Mining | NIFTYMETAL |
| Power_Utilities | NIFTYPSUBANK (proxy; NIFTYPOWER not in panel) |
| Auto_Components, Consumer_Discretionary | NIFTYAUTO (partial proxy) |
| Real_Estate | NIFTYREALTY |
| Oil_Gas | NIFTYENERGY |
| Media | NIFTYMEDIA |
| Capital_Goods, NBFC_HFC, Capital_Markets, others | (no direct match) |

Sectors without a direct match contribute via global ETF features and global breadth from sectoral indices; no own-sector feature is computed for them in v1.

## 10. Runner adapter contract (`_load_real_inputs`)

To consume this canonical dataset, `pipeline/autoresearch/etf_stock_tail/runner.py:_load_real_inputs` must:

1. Read `pipeline/data/canonical_fno_research_v1.json` and use it as the source-of-truth for the universe (instead of `fno_universe_history.json` directly).
2. Build a daily-keyed `universe: dict[str, list[str]]` from the canonical artifact:
   - For each ticker `t` in canonical, mark `t` as in-universe for every date in `[per_ticker_valid_from[t], per_ticker_valid_to[t]]`.
   - For dates after the last monthly snapshot, continue using the canonical valid-to as the upper bound.
3. Read regime history with the column rename `regime_zone → regime`.
4. Load both the 28 global ETF parquets AND the 10 sectoral index CSVs, concatenated into a single `etf_panel: DataFrame[date, etf, close]` where `etf` ∈ {28 global ETFs} ∪ {10 sectoral indices}.
5. Set `C.ETF_SYMBOLS` (or an equivalent extended list) to the union of 28 ETFs + 10 sectoral indices for downstream feature computation.

## 11. Re-audit cadence

This dataset is registered for the period 2026-04-25 → 2026-07-25 (90-day cadence per data validation policy §22). Any of the following triggers an immediate re-audit:
- Universe history snapshot fetcher recovers any pre-2024 month
- Backfill task for the 62 universe-only-no-CSV tickers completes
- New sectoral indices added to NSE
- Adjustment mode change in upstream data source
- A real point-in-time FII/DII history is acquired (triggers `fii_dii_v2` versioning — see §13)

## 12. Approved consumers

- H-2026-04-25-002 etf-coefficient-stock-tail-classifier (Amendment 1 sectoral indices, Amendment 2 synthetic FII/DII waiver)
- All future hypotheses under `pipeline/autoresearch/` shall cite `canonical_fno_research_v1` by name.

## 13. FII/DII synthetic waiver (added 2026-04-25 per H-2026-04-25-002 Amendment A1.4)

The `fii_net_daily` and `dii_net_daily` parquets under `pipeline/data/research/phase_c/daily_bars/` are **synthetic** — generated by cycle-replicating a real 19-day Trendlyne snapshot (25 Mar → 24 Apr 2026) across the canonical Indian trading-day index. Both are 1236 rows.

**What this is:**
- A scaffold to keep the global-state-vector schema complete so panel assembly does not drop every row on `dropna(how="any")`.
- A best-effort assumption that FII/DII flows over a one-month window are representative enough to use as feature-vector placeholders. User-authorized: "I gave you one month — we can assume the same trend for the last 2 months (worst case scenario), replicate it."

**What this is NOT:**
- A real point-in-time FII/DII history.
- A basis for any narrative about FII/DII behaviour, regime detection, or flow-driven alpha.

**Policy waiver scope:** Any model coefficient on `fii_*` or `dii_*` features is uninterpretable for downstream attribution. The waiver expires when a real source (NSE/SEBI bhavcopy with FII/DII columns, paid Trendlyne API, or alternative provider) is acquired. At that point:
1. Dataset versions to `fii_dii_v2` (real data).
2. The model is re-fit on `fii_dii_v2` panel.
3. The re-fit is **not** a §10.4 re-touch, because the input dataset has materially changed.

**Best-effort search log (2026-04-25):** IndianStockAPI (no FII/DII endpoint), EODHD (US-only flow data), NSE archives (only rolling-today CSVs, no date-range endpoint), Wayback Machine (~9 captures across 5 years, insufficient for daily history), Trendlyne web (only 30-day HTML snapshot rendered). Conclusion: no free 5-year FII/DII history exists in any source we have access to. See `memory/reference_nse_bulk_deals_history_unavailable.md` for the parallel finding on bulk-deals history.

## 14. Regime taxonomy alignment (added 2026-04-25 per H-2026-04-25-002 Amendment A1.5)

`regime_history.csv` and `regime_cutpoints.json` are produced by the **V4 regime engine** under `pipeline/regime/` and emit the label set `{CAUTION, NEUTRAL, RISK-ON, EUPHORIA, RISK-OFF}` plus the sentinel `UNKNOWN`. This dataset registration supersedes any prior reference to the V5 zone taxonomy (`{DEEP_PAIN, PAIN, NEUTRAL, EUPHORIA, MEGA_EUPHORIA}`) which is no longer produced.

**Consumer guidance:** Any consumer that performs a regime-coverage check must derive the expected label set from the train window data, not from a hardcoded list. See `pipeline/autoresearch/etf_stock_tail/splits.py:check_regime_coverage` for the canonical pattern.
