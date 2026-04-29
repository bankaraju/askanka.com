# Data Inventory

> **Purpose:** Single source of truth for "what data do we have, how clean, since when, where."
> Read this before claiming any signal has evidence. Update this whenever a dataset lands or refreshes.

**Last revised:** 2026-04-29 (Bharat + assistant — NEUTRAL victory + 273 F&O backfill)

## How to use this doc

For each dataset row, you can answer:
- **Path:** where the data lives
- **Schema:** what columns/keys it has
- **Range:** earliest → latest record
- **Coverage:** ticker count, day count, completeness
- **Refresh:** which scheduled task writes it, how often
- **Quality gates:** known gaps, contamination, cleanliness verdict per `anka_data_validation_policy_global_standard.md`
- **Used by:** which analyses depend on this data

**Analysis Bar:** any analysis citing a dataset must satisfy the cleanliness gate (Section 9 of the data validation policy). If the gate isn't met, the analysis is research evidence of nothing.

---

## 1. Minute bars (1-min OHLCV)

**Path:** `pipeline/data/research/h_2026_04_29_intraday_v1/cache_1min/<TICKER>.parquet`

**Schema:** `timestamp` (tz-aware Asia/Kolkata) · `open` · `high` · `low` · `close` · `volume`

**Source:** Kite Connect `historical_data(interval='minute')` — 60-day rolling, 7-day pages.

**Coverage as of 2026-04-29:**
- 273 canonical F&O tickers (per `canonical_fno_research_v3.json`)
- Plus 11 NIFTY indices (NIFTY 50, NIFTY BANK, NIFTY AUTO, NIFTY ENERGY, NIFTY FIN SERVICE, NIFTY FMCG, NIFTY IT, NIFTY METAL, NIFTY PHARMA, NIFTY REALTY, +1)
- 60 calendar days = ~44 trading days × 375 min/day = ~16,500 candles per ticker

**Known holes (historical):**
- 2026-03-03 and 2026-03-26 had partial dropouts during initial FETCH_FAILED bug (since fixed). Retroactive backfill recovered most. New caches built post-2026-04-29 do not have these holes.

**Refresh:**
- `AnkaIntradayV1LoaderRefresh` daily 04:30 IST — delta-refresh for the V1 instrument set (60 names initially)
- Manual ad-hoc: `python -m pipeline.research.intraday_v1.loader` for any single ticker

**Used by:**
- `pipeline.research.intraday_v1.discover_v2` (V2 discovery)
- `pipeline.research.intraday_v1.walkforward_v2` (V2 walk-forward)
- `pipeline.research.intraday_v1.cohort_attribution`
- `pipeline.research.neutral_cohort_tracker` (NEUTRAL filter cells)
- `pipeline.research.vwap_filter` (live H-001 VWAP-deviation tag)

**Quality gate:** PASS (per §9 cleanliness — every parquet has consistent schema, no NaN volumes, sorted timestamps).

---

## 2. Daily TA historical (5-year)

**Path:** `pipeline/data/ta_historical/<TICKER>.parquet`

**Schema:** `Date` · `Open` · `High` · `Low` · `Close` · `Volume`

**Source:** EODHD (split-adjusted) with Kite fallback for non-EODHD names.

**Coverage:**
- 213 F&O tickers
- ~1,239 trading days each (~5 years)

**Refresh:**
- `AnkaTAScorerFit` weekly Sunday 01:30 IST — refits the TA Coincidence Scorer
- `AnkaPatternScannerFit` weekly Sunday 02:00 IST — 5y pattern fit

**Used by:**
- TA Fingerprint engine (`ta_fingerprint.py`)
- Pattern Scanner (`technical_scanner.py`)
- TA Coincidence Scorer (FCS)
- TA-Karpathy v1 holdout (just opened 2026-04-29)

**Quality gate:** PASS (split-adjusted, 5y stable).

---

## 3. PCR archive (Put-Call Ratio per ticker per date)

**Path:** `pipeline/data/research/phase_c/pcr_history/<YYYY-MM-DD>/<TICKER>.parquet` (381 files)

**Schema:** Per-strike OI, computed PCR for next-month options.

**Source:** Kite options chain at EOD.

**Coverage:** Sparse — built on-demand for backtests; not a full universe daily snapshot.

**Refresh:** No scheduled refresh; populated lazily by `pipeline.autoresearch.mechanical_replay.reconstruct.pcr` when a backtest needs it.

**Used by:**
- Mechanical replay v2 (`reconstruct/zcross.py`)
- V1 panel builder (`in_sample_panel.py` → delta_pcr_2d feature)

**Quality gate:** PARTIAL — sufficient for backtest reconstruction, not a clean live feed. Treat as research artifact, not production data.

---

## 4. OI archive (intraday + EOD)

**Path:** `pipeline/data/oi_archive/<YYYY-MM>/...` (intraday snapshots + EOD)

**Schema:** Per-strike OI, near + next expiry, max-pain, pin level.

**Source:** Kite via `oi_scanner.py`.

**Coverage:** All 215 F&O stocks (memory says 215; canonical v3 has 273 — gap to investigate).

**Refresh:**
- `AnkaIntraday####` every 15 min (calls oi_scanner)
- `oi_scanner --archive-only` at 16:00 IST EOD

**Used by:**
- Spread intelligence
- Phase C OI delta features
- Display-only on terminal

**Quality gate:** PARTIAL — coverage drift between 215 (oi_scanner) and 273 (canonical) needs reconciliation. Forward-only since launch.

---

## 5. ETF regime tape

**Path:** `pipeline/data/today_regime.json` (live) + `pipeline/data/regime_history.csv` (history)

**WARNING:** `regime_history.csv` is built with HINDSIGHT v2 weights, NOT a production audit trail. See `memory/reference_regime_history_csv_contamination.md`. Do NOT use for OOS comparisons.

**Live source of truth:** `today_regime.json`, written by `AnkaETFSignal` at 04:45 IST.

**Coverage:** Daily; 5+ years if you add the v3-CURATED forward shadow (started 2026-04-27).

**Used by:**
- Every regime-conditional analysis (Phase C, H-001, NEUTRAL cohort tracker)
- Spread intelligence regime gate

**Quality gate:** PASS for `today_regime.json` (live ground truth). FAIL for `regime_history.csv` (contaminated).

---

## 6. H-001 forward paper ledger (sigma-break mechanical)

**Path:** `pipeline/data/research/h_2026_04_26_001/recommendations.csv`

**Schema:** signal_id, ticker, date, sigma_bucket, regime, sectoral_index, side, classification, regime_gate_pass, entry/exit times, entry/exit px, atr_14, stop_px, trail_arm_px, trail_dist_pct, exit_reason, pnl_pct, status, **vwap_dev_signed_pct**, **filter_tag** (added 2026-04-29).

**Coverage as of 2026-04-29:** 105 CLOSED rows (Apr 27, 28, 29 — all NEUTRAL).

**Refresh:**
- `AnkaH20260426001PaperOpen` daily 09:30 IST
- `AnkaH20260426001PaperClose` daily 14:30 IST

**Used by:**
- `pipeline.research.neutral_cohort_tracker` (105-row NEUTRAL sample)
- Terminal LIVE tab

**Quality gate:** PASS — single-touch holdout window 2026-04-27 → 2026-05-26 strict. Forward-only.

---

## 7. Phase C forensic ledgers

**7a. Live shadow (futures-leg paper):**
- Path: `pipeline/data/research/phase_c/live_paper_ledger.json`
- 11 OPEN, 0 CLOSED as of 2026-04-29
- Forensic-only, descriptive

**7b. Paired ATM-options sidecar:**
- Path: `pipeline/data/research/phase_c/live_paper_options_ledger.json`
- 12 rows since launch 2026-04-22:
  - 4 OPEN
  - 7 SKIPPED_LIQUIDITY (wide bid-ask spread on the option)
  - 1 ERROR (module-not-found, since fixed)
  - **0 CLOSED**
- High SKIPPED rate is a known issue — many F&O options have wide spreads at the strikes the engine picks.

**7c. Mechanical replay (60-day historical):**
- Path: `pipeline/data/research/mechanical_replay/v2/trades_with_exit.csv` (canonical, with Z_CROSS exits)
- Path: `pipeline/data/research/mechanical_replay/v2/trades_no_zcross.csv` (HINDSIGHT variant)
- 388 phase_c trades, 248 FETCH_FAILED dropouts, 60 phase_b trades
- See `memory/project_phase_c_track_record_audit_2026_04_29.md` — 93% headline is from the hindsight variant

**Quality gate:** Live (7a, 7b) PASS — forward-only. Replay (7c) PASS as research artifact, FAIL as forward edge claim.

---

## 8. Track record (public-facing)

**Path:** `pipeline/data/track_record.json` + `data/track_record.json` (deployed)

**WARNING:** This file shows the HINDSIGHT NO_Z_CROSS variant performance, NOT a forward live record. Per `memory/project_phase_c_track_record_audit_2026_04_29.md`, the canonical engine (with Z_CROSS) shows 66.67% at >=2σ, not 93%.

**Refresh:** `AnkaEODTrackRecord` daily 16:15 IST — derives from `mechanical_replay/v2/trades_no_zcross.csv` filtered to abs_z >= 2.0.

**Used by:** Public website (currently MUTED per `memory/feedback_website_trade_publish_blocked.md`)

**Quality gate:** FAIL — variant choice not surfaced to consumer; the 93% headline misleads.

**Action required:** Replace with regime-conditional table per `memory/project_neutral_cohort_filter_2026_04_29.md`.

---

## 8a. Intraday panel v1 (descriptive, all-F&O)

**Path:** `pipeline/data/research/intraday_panel_v1/{panel,cells,summary}_<date>.{parquet,csv,json}`

**Schema (panel):** ticker, date, open_px, orb_close_px (09:45), exit_px (14:30), orb_15min_pct, vwap_dev_pct, intraday_slope_pct, volume_z, hold_pct.

**Schema (cells):** cell, N, win_pct, mean_pnl_pct, median_pnl_pct, status, rule (follow|fade).

**Source:** Aggregation of §1 minute bars over 273 F&O tickers × ~38 trading days.

**Refresh:** On-demand via `python -m pipeline.research.intraday_panel_v1 --print`. Re-run after each minute-bar cache refresh.

**Used by:**
- `docs/ANALYSIS_CATALOG.md` §A.4 — universe-level baseline that contextualizes H-001 NEUTRAL filter cells

**Quality gate:** PASS as research artifact. FAIL as a forward edge claim — not pre-registered, not regime-conditioned (regime_history.csv contamination), no costs/slippage. Treat as descriptive only.

---

## 9. Other ledgers (lower priority)

- **SECRSI** (`h_2026_04_27_secrsi/recommendations.csv`) — sector-RS market-neutral pair, holdout 2026-04-28 → 2026-07-31
- **Scanner paired** — Top-10 patterns, paired shadow, T+1 → 15:30 close
- **TA-Karpathy v1** — 10-stock pilot, holdout 2026-04-29 → 2026-05-28

Each has its own ledger CSV; document fully when N >= 30 closed.

---

## Refresh cadence summary

| Source | Cadence | Owner task | Last verified clean |
|---|---|---|---|
| Minute bars | Daily 04:30 + on-demand | LoaderRefresh | 2026-04-29 (273 F&O backfill) |
| Daily TA historical | Weekly Sunday | TAScorerFit / PatternScannerFit | 2026-04-26 (canonical v3) |
| OI archive | Every 15 min + EOD | Intraday#### | 2026-04-29 |
| PCR archive | On-demand | (lazy) | 2026-04-29 |
| Regime tape (today) | Daily 04:45 | ETFSignal | 2026-04-29 |
| H-001 ledger | Daily 09:30 + 14:30 | H20260426001Paper | 2026-04-29 |
| Phase C ledgers | Daily | PhaseC* | 2026-04-29 |

---

## Adding a new dataset to this inventory

1. Land the data + write the schema + check it loads
2. Add a section here with all 7 fields (Path, Schema, Source, Coverage, Refresh, Used by, Quality gate)
3. If the dataset feeds a backtest, also write a `<dataset>-data-source-audit.md` per CLAUDE.md
4. Update `pipeline/config/anka_inventory.json` if a new scheduled task ships

**Never run an analysis on a dataset that isn't in this inventory.**
