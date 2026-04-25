# H-2026-04-25-001 Backtest — Design Spec

**Date:** 2026-04-25
**Author:** Bharat Ankaraju
**Hypothesis under test:** H-2026-04-25-001 (`docs/superpowers/specs/2026-04-25-earnings-decoupling-hypothesis-design.md`)
**Standards:** `backtesting-specs.txt` v1.0_2026-04-23, `anka_data_validation_policy_global_standard.md` v1.0_2026-04-25
**Target gate:** RESEARCH → PAPER-SHADOW per §15.1

This document specifies the backtest implementation. The hypothesis itself, including every threshold and window, is already pre-registered and locked. No design parameters in this document override the hypothesis spec; this is purely a build plan that consumes the locked design.

## 1. Locked decisions (2026-04-25 brainstorming session)

| # | Decision | Rationale |
|---|---|---|
| 1 | ΔPCR confirmation track is **wired but disabled** in this run; primary cohort = Variant A trigger-only | Per-ticker PCR history not available; `pipeline/data/oi_history.json` is index-level only. Spec §4.5 already declares ΔPCR a post-hoc filter, not an entry gate, so this preserves pre-registration commitments. |
| 2 | Build `pipeline/data/fno_universe_history.json` properly with **5-year monthly history** | Required by backtesting-specs §6 anyway; pays back across every future backtest; SURVIVORSHIP-UNCORRECTED waivers are not free. |
| 3 | Single fixed train/holdout split (15 mo / 3 mo); §15.4 partial-waiver covers §10.1 + §10.2 | User locked 18-month window in hypothesis spec §9; rolling walk-forward not feasible inside that window. |
| 4 | Compliance scope = RESEARCH → PAPER-SHADOW only: §1 (S0+S1), §2, §5A, §6, §7, §8, §9, §9A, §9B, §10, §11B | §11A/§11C/§12/§13 require shadow-trading history that does not yet exist. Run when shadow ledger reaches §15.1's 50-trade gate. |
| 5 | New package `pipeline/autoresearch/earnings_decoupling/` for backtest code; reuse `overshoot_compliance/` for §-numbered gates | Matches existing autoresearch convention; separates operational ingestor (`pipeline/earnings_calendar/`) from research backtest. |

## 2. Architecture

A single deterministic run transforms five inputs into a §15.1 RESEARCH → PAPER-SHADOW verdict for H-2026-04-25-001:

```
inputs:
  pipeline/data/earnings_calendar/history.parquet      (1,180 events, 18-mo window)
  pipeline/data/earnings_calendar/peers_frozen.json    (208/208 frozen ex-ante 2026-04-25)
  pipeline/data/fno_universe_history.json              (5-year monthly PIT, NEW)
  pipeline/data/sectoral_indices/*.csv                 (10 indices, 5-year daily, NEW)
  pipeline/data/fno_historical/<symbol>.csv            (existing daily stock prices)

new code:                       pipeline/autoresearch/earnings_decoupling/
reused compliance harness:      pipeline/autoresearch/overshoot_compliance/

output:
  docs/superpowers/runs/2026-04-25-earnings-decoupling-h-2026-04-25-001/
      manifest.json
      verdict.md
      trade_ledger.csv
      data_quality.md
      entry_timing_audit.csv
  hypothesis-registry.jsonl: terminal_state ∈ {PASSED, FAILED, ABANDONED}
```

The ΔPCR amplifier path (`pcr_amplifier.py`) is wired through the runner with a feature-flag default `enabled=false`; when per-ticker PCR history is later backfilled, flipping the flag re-activates the post-hoc filter without code changes.

## 3. Pre-task data foundation (gating)

These three audits are the data-validation gate per CLAUDE.md. The backtest cannot run until they are committed.

### 3.1 `nse_sectoral_indices_v1` registration (T0a)

**Audit doc:** `docs/superpowers/specs/2026-04-25-nse-sectoral-indices-data-source-audit.md`
**Tier:** D2 (decision-supporting; research-class backtest input)
**Symbols:** 10 NSE sectoral indices required by hypothesis spec §3:

| Sector | Hypothesis ticker | Kite alias | yfinance alias |
|---|---|---|---|
| Bank | NIFTY Bank | `NSE:NIFTY BANK` | `^NSEBANK` |
| IT | NIFTY IT | `NSE:NIFTY IT` | `^CNXIT` |
| Pharma | NIFTY Pharma | `NSE:NIFTY PHARMA` | `^CNXPHARMA` |
| Auto | NIFTY Auto | `NSE:NIFTY AUTO` | `^CNXAUTO` |
| FMCG | NIFTY FMCG | `NSE:NIFTY FMCG` | `^CNXFMCG` |
| Metal | NIFTY Metal | `NSE:NIFTY METAL` | `^CNXMETAL` |
| Energy | NIFTY Energy | `NSE:NIFTY ENERGY` | `^CNXENERGY` |
| PSU Bank | NIFTY PSU Bank | `NSE:NIFTY PSU BANK` | `^CNXPSUBANK` |
| Realty | NIFTY Realty | `NSE:NIFTY REALTY` | `^CNXREALTY` |
| Media | NIFTY Media | `NSE:NIFTY MEDIA` | `^CNXMEDIA` |

**Backfill:** 5-year daily bars via `pipeline/research/phase_c_v5/data_prep/backfill_indices.py::backfill_daily`.
**Output:** `pipeline/data/sectoral_indices/<INDEX>_daily.csv` schema `(date,open,high,low,close,volume)`.
**Cleanliness gates:** §9 ≥99% non-stale rows; §10 unadjusted convention (indices need no split adjustment); §11 PIT-correct (each row's `date` is the trade date).

### 3.2 `fno_universe_history_v1` (T0b)

**Audit doc:** `docs/superpowers/specs/2026-04-25-fno-universe-history-data-source-audit.md`
**Tier:** D2
**Source:** NSE monthly F&O lists (NSE archives — public CSVs).
**Scope:** 5-year monthly snapshots, ending the most recent month-end before the run.
**Output:** `pipeline/data/fno_universe_history.json` with shape:

```json
{
  "snapshots": [
    {"date": "2021-04-30", "symbols": ["RELIANCE", "TCS", ...]},
    {"date": "2021-05-31", "symbols": [...]},
    ...
    {"date": "2026-04-30", "symbols": [...]}
  ],
  "source": "nseindia.com archives",
  "fetched_at": "2026-04-25T...IST"
}
```

**Use:** `is_in_fno(symbol, date)` resolves membership at the most recent `snapshots[i].date <= date`.
**Cleanliness gates:** §9 ≥99% snapshots present; §11 PIT-correct (a symbol that was kicked out on 2024-08-31 must NOT be admitted on a 2024-09-15 event_date).

### 3.3 §15.4 partial-waiver doc (T0c)

**Path:** `docs/superpowers/waivers/2026-04-25-h-2026-04-25-001-partial-oos.md`
**Sections waived:** §10.1 (17% holdout vs 20% bar), §10.2 (single fixed split vs rolling walk-forward).
**Justification:** 18-month window locked in hypothesis spec §9; rolling 3-year walk-forward impossible. Partial waiver is consistent with §10.1's "research only, cannot size aggressively" interpretation since the verdict targets RESEARCH → PAPER-SHADOW only.
**Expiry:** at next backtest of the strategy under a longer window. Waiver does not propagate to PAPER-SHADOW → LIVE-FRAGILE promotion.

### 3.4 Spec addendum (T0d)

Append to `docs/superpowers/specs/2026-04-25-earnings-decoupling-hypothesis-design.md`:

```markdown
## 11. Backtest-time addendum (2026-04-25)

ΔPCR confirmation deferred for the first backtest run because per-ticker daily
PCR history is not currently stored (`pipeline/data/oi_history.json` is index-level
only). Per spec §4.5 Variant A, ΔPCR is a post-hoc cohort filter, not an entry
gate, so disabling it for this run does NOT modify the entry rule and does NOT
require a new hypothesis version. The amplifier code path is wired with a
feature flag and will be re-enabled in a separate run when per-ticker PCR
history is backfilled.
```

## 4. Backtest core — `pipeline/autoresearch/earnings_decoupling/`

| File | Responsibility |
|---|---|
| `__init__.py` | package marker |
| `peer_residuals.py` | pure: `compute_residual_panel(prices_panel, peers_map, calendar) → DataFrame[date,symbol,epsilon]` |
| `trigger.py` | pure: `compute_trigger_z(residual_panel, event_date, symbol) → float \| None` (None for insufficient baseline / zero variance) |
| `macro_filter_adapter.py` | thin shim wrapping `pipeline/earnings_calendar/macro_filter.is_macro_excluded` for sectoral-index returns + VIX z |
| `event_ledger.py` | for each event row in `history.parquet`: PIT membership check → trigger_z → macro filter → direction → entry/exit timestamps; emits `candidate_trades.parquet` |
| `simulator.py` | MODE A entry/exit at 15:20-29 VWAP per backtesting-specs §7.1; runs S0/S1/S2/S3 cost grid; emits `trade_ledger.csv` per slippage level |
| `pcr_amplifier.py` | stub: `apply_pcr_filter(trade_ledger, enabled=False) → trade_ledger` returns input unchanged when disabled, with `pcr_track="deferred"` recorded in manifest |
| `runner.py` | orchestrates peer_residuals → trigger → event_ledger → simulator → pcr_amplifier → overshoot_compliance.runner.run; writes manifest + verdict; appends to hypothesis-registry |

All files target ≤300 lines; split if growing.

## 5. Data flow

```
1. earnings_calendar/history.parquet (1,180 events in 18-mo window)
2. → fno_universe_history filter (drops events where symbol not in F&O on event_date)
3. → peer_residuals.compute_residual_panel: for each (date, symbol), epsilon = log_return(symbol) - mean(log_return(peers[symbol]))
4. → trigger.compute_trigger_z per event: cum_residual(T-7→T-3); z-score against trailing 252d ending T-8
5. → macro_filter_adapter: drops events where |sector_index_return| ≥ 1.5% on T or T+1 OR VIX_z(60d) ≥ 2 on T
6. → event_ledger constructs candidate trades: direction = sign(trigger_z); entry_timestamp = T-3 close (15:20-29 VWAP); exit_timestamp = T-1 close (15:20-29 VWAP); hold = 2 trading days
7. → simulator applies S0/S1/S2/S3 cost grid; per-trade P&L
8. → pcr_amplifier (disabled): trade ledger passes through unchanged; manifest records pcr_track="deferred"
9. → overshoot_compliance.runner.run consumes trade_ledger.csv + writes manifest + runs §1, §2, §5A, §6, §7, §8, §9, §9A, §9B, §10, §11B
10. → verdict_report.md per §15.1 gate ladder
11. → hypothesis-registry append: terminal_state = PASSED | FAILED | ABANDONED with reason
```

## 6. Error handling

| Condition | Disposition | Manifest field |
|---|---|---|
| Symbol not in F&O on event_date | drop, count | `n_dropped_pit_miss` |
| <200 valid baseline days | drop, count | `n_dropped_insufficient_baseline` |
| σ_s(T) ≤ 0 | drop, count | `n_dropped_zero_variance` |
| Macro filter T sector | drop, count, log reason | `n_excluded_sector_t` |
| Macro filter T+1 sector | drop, count, log reason | `n_excluded_sector_t1` |
| Macro filter VIX shock | drop, count, log reason | `n_excluded_vix_shock` |
| Raw-bar canonicity §5A.5 violation in [T-3, T-1] | invalidate trade | `n_dropped_bar_canonicity` |
| Sectoral-index gap on T-7..T-1 | drop, count | `n_dropped_index_gap` |
| Insufficient liquidity (60d ADV < 10× ₹5L) | tag, do not drop | recorded per §11.1 in manifest |

## 7. Testing strategy

TDD red→green→commit per task.

**Unit tests:**
- `test_peer_residuals.py` — synthetic 5-symbol × 30-day panel; verify ε_s(t) matches hand-computed values
- `test_trigger.py` — synthetic residual panel where trigger_z is computable by inspection; verify σ ≤ 0 and < 200 baseline drops
- `test_macro_filter_adapter.py` — already covered by `pipeline/tests/earnings_calendar/test_macro_filter.py`; new shim test confirms wiring
- `test_event_ledger.py` — verifies PIT membership filter, drop counts, direction sign
- `test_simulator.py` — verifies entry/exit timestamps, cost-grid arithmetic at S0/S1/S2/S3
- `test_pcr_amplifier.py` — verifies disabled passthrough + manifest field
- `test_runner.py` — synthetic end-to-end (10-event panel) producing a verdict.md

**Integration test:**
- `test_end_to_end_synthetic.py` — hand-built 10-event synthetic with known trigger z values; runner produces a deterministic verdict; both pass and fail paths exercised.

**Holdout single-touch enforcement:**
- `runner.py` records holdout-touch count to `docs/superpowers/runs/.../holdout_touch_log.json`; on second touch in same `run_id`, raises `HoldoutAlreadyTouchedError` per §10.4.

## 8. Reporting / handoff

```
docs/superpowers/runs/2026-04-25-earnings-decoupling-h-2026-04-25-001/
├── manifest.json              # §13A.1 — git_commit, config_hash, data SHA-256s
├── verdict.md                 # §15.1 gate ladder pass/fail summary
├── trade_ledger.csv           # all trades at S0/S1/S2/S3
├── data_quality.md            # §5A audit per slippage level
├── entry_timing_audit.csv     # §7.3 lag log per trade
├── permutation_null.json      # §9B.2 — ≥100k label permutations, primary metric tail
├── fragility_grid.csv         # §9A — neighborhood metrics
├── beta_regression.json       # §11B — β to NIFTY 50, residual Sharpe
└── holdout_touch_log.json     # §10.4 single-touch enforcement
```

**Hypothesis registry update:**
On run completion, append to `docs/superpowers/hypothesis-registry.jsonl`:
```json
{"hypothesis_id":"H-2026-04-25-001","terminal_state":"PASSED|FAILED|ABANDONED","run_id":"...","verdict_path":"docs/superpowers/runs/2026-04-25-.../verdict.md","completed_at":"..."}
```

**Memory:**
Update `project_earnings_decoupling_h_2026_04_25_001.md` with terminal state and pointer to verdict.

**Telegram:**
Post terminal state + verdict link to operator chat per existing pipeline conventions.

## 9. Scope guard (NOT in this plan)

- Per-ticker PCR backfill — separate sub-project; pipes from `oi_scanner.py` archive
- Live shadow trading for the strategy — next gate after this run, requires §15.1 RESEARCH → PAPER-SHADOW pass
- §11A (impl-risk), §11C (portfolio corr), §12 (CUSUM), §13 (drift) — require shadow history
- ΔPCR amplifier evaluation — disabled in this run, re-enabled when per-ticker PCR is available
- Mode-2 re-entry, deployment promotion, capacity sizing — downstream gates

## 10. Status and lifecycle

| Field | Value |
|---|---|
| Hypothesis status | PRE_REGISTERED, awaiting backtest |
| Backtest design | This document |
| Backtest plan | TBD via `superpowers:writing-plans` after this spec is approved |
| Target gate | RESEARCH → PAPER-SHADOW per §15.1 |
| Data-validation gate | T0a/T0b/T0c/T0d audits required before backtest run |
| Compliance harness | reused from `pipeline/autoresearch/overshoot_compliance/` |
