# Appendix — Data

## Sources

| Dataset | Provider | Granularity | Window used | Coverage |
|---|---|---|---|---|
| Daily OHLCV | Zerodha Kite Connect | 1 day | 2022-03-07 → 2026-04-20 | 14 of 15 requested NSE F&O stocks (HDFC, TATAMOTORS returned 0 bars) |
| 1-minute OHLCV | Zerodha Kite Connect | 1 minute | 2026-02-20 → 2026-04-20 (Kite retention window) | 14 stocks × ~60 sessions |
| F&O universe | NSE `fo_mktlots.csv` | 1 month | 2024-10 → 2026-04 | ~215 symbols / month, snapshotted monthly |
| Per-stock PCR | NSE F&O bhavcopy (archives) | 1 day | 2024-10-01 → 2026-04-20 | 381 business days, median 213 stocks/day |
| Regime labels | ETF regime engine (Anka) | 1 day | 2022-10-01 → 2026-04-20 (backfilled +lookback) | 100% of business days |

## Universe size by year

The point-in-time F&O universe was queried per trade month from NSE's `fo_mktlots.csv`. Typical sizes:

| year | F&O single stocks |
|---:|---:|
| 2022 | ~185 |
| 2023 | ~200 |
| 2024 | ~210 |
| 2025 | ~215 |
| 2026 | ~215 |

The full NSE universe was fetched and cached but the mid-size replay used an explicit 15-symbol subset (`--symbols` flag) to keep the wall-time manageable for documentation runs. A full-universe run is bounded by the same Kite rate limits (~30s per 215 symbols for daily, ~5 min for intraday) and was kicked off separately.

## Cache layout

All caches live under `pipeline/data/research/phase_c/`:

```
phase_c/
├── daily_bars/            # <symbol>.parquet — one file per symbol, all history
├── minute_bars/           # <symbol>_<date>.parquet — one file per symbol per session
├── fno_universe_history/  # <YYYY-MM>.json — monthly F&O symbol list snapshots
├── phase_a_profiles/      # profile_<cutoff>.json — walk-forward training outputs
├── pcr_history/           # <date>.parquet — per-stock PCR from NSE bhavcopy
└── regime_backfill.json   # date → regime label map
```

Every cache is content-addressable by its filename and reproducible — deleting a file triggers refetch on the next run. Corrupt caches are auto-detected and re-fetched (guarded by JSONDecodeError / parquet read failure try/except in the respective loader).

## Disk footprint

| Cache | Size (approx) |
|---|---:|
| `daily_bars/` | ~5 MB (14 symbols × 1 KB/row × 1,000 rows) |
| `minute_bars/` | ~120 MB (14 × 60 × 150 KB) |
| `fno_universe_history/` | <100 KB total |
| `phase_a_profiles/` | ~2 MB (6 cutoffs × ~350 KB JSON) |
| `pcr_history/` | ~8 MB (381 files × ~20 KB parquet) |
| **Total** | **~135 MB** |

Artifacts under `docs/research/phase-c-validation/` (the research document set):

| Artifact | Size |
|---|---:|
| `in_sample_ledger.parquet` | ~50 KB (630 rows × 14 cols) |
| `forward_ledger.parquet` | ~10 KB (21 rows × 14 cols) |
| `in_sample_equity.png` | ~30 KB (matplotlib 800×400) |
| `forward_equity.png` | ~20 KB |
| 10 markdown sections | ~50 KB |

## Schema notes

**In-sample ledger (EOD simulator):**
```
entry_date, exit_date, symbol, side, entry_px, exit_px, exit_reason,
notional_inr, pnl_gross_inr, pnl_net_inr, z_score
```
`exit_reason ∈ {TARGET, STOP, TIME_STOP}`. `TIME_STOP` corresponds to next-day close.

**Forward ledger (intraday simulator):**
```
entry_time, exit_time, symbol, side, entry_px, exit_px, exit_reason,
notional_inr, pnl_gross_inr, pnl_net_inr, signal_time, z_score
```
`exit_time` is the minute-level timestamp. `exit_reason` same set, with `TIME_STOP = 14:30 IST mechanical close`. The `entry_date` column is synthesised from `entry_time[:10]` at report-rendering time (see `run_backtest.py::main`) because the report renderers expect the EOD schema.

## Data-quality caveats

- **Delisted / restructured tickers.** `HDFC` (merged 2023) and `TATAMOTORS` (DVR/ordinary restructure 2025) returned 0 bars from Kite. The `profile.train_profile` empty-bars guard prevents these from aborting the run; they simply contribute zero trades. A future revision should use the post-restructure ticker variants (`HDFCBANK`, `TATAMOTORS-EQ`) explicitly.
- **NSE archive holidays.** Of the ~411 business days in the backfill window, 381 were successfully fetched. The ~30 missing days are Indian market holidays where NSE publishes no bhavcopy. The classifier treats missing PCR as NEUTRAL — so on a holiday following day, PCR-dependent OPPORTUNITY signals cannot fire (no signal is emitted, rather than being silently miscategorised).
- **1-minute bar retention.** Kite's 1-minute retention is ~60 sessions. Attempting to fetch minute bars older than that returns an empty result; the simulator falls back to the daily close and logs a warning.
- **Survivorship filter.** The universe is point-in-time monthly, so stocks that exited F&O mid-window are correctly excluded from subsequent months. Stocks that *entered* mid-window are not back-included.

## Reproducibility

- All stats functions take `seed` or `random_state` and default to fixed values.
- All caches are content-addressed; deleting the cache and re-running produces byte-identical ledgers given the same Kite API responses.
- Kite responses are themselves deterministic for historical data (unlike live minute bars, which may be revised intraday).
- The commits referenced in `10-appendix-reproduction.md` pin the exact orchestrator and dependency versions used for this document.
