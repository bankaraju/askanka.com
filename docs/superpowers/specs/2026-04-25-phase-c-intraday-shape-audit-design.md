# Phase C Intraday Shape Audit — Design Spec

**Date:** 2026-04-25 (rev 4 same day — extended window to last 60 calendar days of potential trades, regime as a stratification axis on top of rev 2's entry-time grid + counterfactual replay)
**Status:** Sub-project 1 (SP1) of a 3-stage chain. SP1 is descriptive forensics; SP2 + SP3 are downstream and out of scope for this spec.
**Hypothesis class:** Descriptive only. **No edge claim. No new strategy file. No kill-switch trigger.**
**Author:** Claude Opus 4.7 (working session 2026-04-25 with Bharat).
**Origin:** User observation that live 3σ correlation breaks show a reverse-V intraday shape — peak within the first 15 min then fade through the day — and that this shape is *what makes the SHORT trade work*. Mirror: a V shape (trough early, recovery through the day) is what makes the LONG trade work. Track record corroborates: 36 closed Phase C trades (Apr 20–24), 35 SHORT / 1 LONG, 56.4 % blended win rate, +1.85 % avg P&L. **User reality-check (rev 2):** in the actual trade ledger entries did NOT happen at the 09:30 plan-time — they fired between 09:42 and 16:01 IST, so the plan must be tested against a grid of candidate entry times rather than a single anchor. Also the plan-time 2:30 PM hard close was NOT applied (most trades exited next-day on Z-cross), and stop-loss / trailing-stop discipline was not enforced — so the audit must counterfactually replay each trade under the **stated** rules to separate "what we did" from "what we should have done." **User reality-check (rev 3 + rev 4):** the period when these signals fired had a specific market regime context — Apr 20-24 carried a mix of CAUTION / RISK-OFF / NEUTRAL daily regime tags. The reverse-V shape may be regime-conditional — the same shape in EUPHORIA could mean the opposite thing. To separate regime from shape AND to get a useful sample, the audit must (a) tag every row with that day's daily regime zone from `pipeline/data/regime_history.csv` and (b) extend the window from the 5-day Apr 20-24 burst to the **last 60 calendar days** of Phase C OPPORTUNITY signals. That window is comfortably inside Kite's ~90-trading-day minute-bar retention and produces an order-of-magnitude larger n that supports regime × shape × side stratification with cells that can clear `n ≥ 10`.

---

## 1. Goal

Quantify whether the intraday SHAPE of price action on a Phase C break day is what separates winning trades from losing trades, conditional on the daily market regime, and whether the user-stated execution rules (entry near open, 14:30 hard close, 3 % stop / 4.5 % target / 2 % trail-arm / 1.5 % trail-drop) would have produced an edge over the SHAPE × SIDE × REGIME matrix that the actual ad-hoc execution did not capture.

Specifically test, conditional on daily regime ∈ {RISK-ON, RISK-OFF, NEUTRAL, CAUTION, EUPHORIA}:

- **REVERSE_V_HIGH** (peak ∈ [09:15, 09:30) followed by sustained fade) → SHORT trade should win
- **V_LOW_RECOVERY**  (trough ∈ [09:15, 09:30) followed by sustained recovery) → LONG trade should win
- All other shapes (one-way-up, one-way-down, choppy) should not have a directional edge

If shape × side correlates with P&L outcome at material lift over the 56.4 % baseline AND the counterfactual (entry-grid + 14:30 close + intraday stops/trails) confirms the result AND the lift survives regime stratification, SP2 is motivated. If shape does NOT separate, or the counterfactual P&L collapses below the actual P&L, or the lift only appears in one regime that happened to dominate the sample, we conclude the existing track-record edge comes from something else (or is regime-luck).

## 2. Scope

**In scope (SP1, this spec):**
- **All Phase C OPPORTUNITY / OPPORTUNITY_LAG / OPPORTUNITY_OVERSHOOT / POSSIBLE_OPPORTUNITY rows in `pipeline/data/correlation_break_history.json` from the last 60 calendar days** (window: 2026-02-25 → 2026-04-25 inclusive). Collapsed to one row per `(ticker, date, classification)` tuple. Expected n in the high hundreds based on Apr 20-24 cadence (~17 distinct tuples per trading day × ~42 trading days).
- All closed Phase C trades from `pipeline/data/signals/closed_signals.json` where `category == "phase_c"` and the open_date falls in the same 60-day window. Joined onto the OPPORTUNITY roster on `(ticker, open_date)` so each row carries `source ∈ {actual, missed}` and (for actual rows) the realized `actual_pnl_pct`, `actual_open_time_ist`, `actual_close_time_ist`.
- **Daily regime tag per row** from `pipeline/data/regime_history.csv` joined on `date`. The regime is the daily zone in {RISK-ON, RISK-OFF, NEUTRAL, CAUTION, EUPHORIA} valid as of that date's 04:45 IST recompute (i.e., the regime live during the trade day).
- Per-trade intraday minute bars 09:15–15:30 IST, fetched once via Kite `historical_data`
- Shape-feature computation per trade, shape classification
- **Entry-time grid simulation:** 09:15, 09:20, 09:25, 09:30, 09:45 IST candidate entries with the user-stated execution rules (14:30 hard close, 3 % stop, 4.5 % target, 2 % arm / 1.5 % drop trail)
- Stratified P&L analysis (actual vs counterfactual) across regime × shape × side, plus a logistic-regression model with regime as a categorical
- A verdict markdown + per-trade CSV with all features for downstream reuse

**Out of scope:**
- SP2 — applying any rule discovered here to a 5 y backtest. That is its own spec, with mandatory hypothesis registration in `docs/superpowers/hypothesis-registry.jsonl` BEFORE any backtest code, and full §1-§14 compliance.
- SP3 — wiring a forward live signal generator. Triggered only after SP2 PASSes the §15.1 gate ladder.
- Repairing the F3 forward shadow ledger (`pipeline/data/research/phase_c/live_paper_ledger.json` is missing). That bug is real but separate.
- Investigating why the missed signals were missed (gateway / cooldown / manual skip / trust-score gate). The audit treats them as eligible-but-untraded; a separate ticket can root-cause.

## 3. Data sources

| Source | Path | Used for |
|---|---|---|
| Closed-trade ledger | `pipeline/data/signals/closed_signals.json` | actual-trade roster (ticker, open_date, side, P&L) — 36 rows in window |
| Phase C signal history | `pipeline/data/correlation_break_history.json` | full 60-day OPPORTUNITY signal universe — provides `trade_rec`, `z_score`, `regime`, `expected_return`, `actual_return`, `pcr`, `pcr_class`, `oi_anomaly`, `classification` per row |
| Phase A profile (reference only) | `pipeline/autoresearch/reverse_regime_profile.json` | the `stats` source the engine reads to compute `expected_return` / `expected_std`. Not consumed by SP1 directly (we trust the persisted z_score) — referenced here for SP2 reproducibility |
| Daily regime archive | `pipeline/data/regime_history.csv` | (date, regime_zone, signal_score) per trading day — joined onto each row to confirm regime tag |
| Track-record summary | `data/track_record.json` | sanity-check totals (39 closed, 56.4 % win) |
| Kite minute bars | `kite.connect.historical_data(token, from, to, "minute")` | intraday OHLC 09:15-15:30 per trade |
| Holiday calendar | `pipeline/trading_calendar.py` | reject any open_date that's a 2026 NSE holiday (defensive — Apr 20-24 are all valid trading days) |

The Kite token-resolver lives in `pipeline/kite_client.py` (`fetch_ltp`, `fetch_history`). Reuse — do not write a new auth path.

**Side inference for missed signals — must match the live engine's contract.** Phase C's authoritative side is the `trade_rec` field written by `enrich_break_with_direction` in `pipeline/autoresearch/reverse_regime_breaks.py:207-243`. The audit MUST consume `trade_rec` directly, not re-derive side from `direction` or `z_score` sign:

- `classification == "OPPORTUNITY_LAG"`: `trade_rec ∈ {LONG, SHORT}` per `LONG if expected_return > 0 else SHORT`. These are the actionable rows.
- `classification == "OPPORTUNITY_OVERSHOOT"`: `trade_rec = None` (alert-only until H-2026-04-23-003 passes). **Excluded from side-stratified tables**, kept in the per-trade CSV with `side = NA`.
- `classification == "POSSIBLE_OPPORTUNITY"` and other non-actionable labels: `trade_rec = None`. Same handling — descriptive only.

This matches how the live engine reasons about side and avoids inventing a new mapping in the audit (which would be a kill-switch concern).

### 3.1 σ-scoring algorithm — replication contract

The user asked to confirm we replicate σ the same way the live engine does. We do NOT recompute σ in SP1 — we read the engine's persisted `z_score` field from `correlation_break_history.json` directly. For documentation and for SP2's eventual reuse, the canonical algorithm in `pipeline/autoresearch/reverse_regime_breaks.py:380-454` is:

```
expected_return  = stats["avg_drift_1d"]                  * 100      # decimal -> percent
drift_5d_std     = stats["std_drift_5d"]                              # 5d rolling std (decimal)
expected_std     = (drift_5d_std / sqrt(5))               * 100      # daily-equivalent sigma in percent
actual_return    = (current_price / today_open - 1)       * 100      # from-OPEN, not from prev close
deviation        = actual_return - expected_return
z_score          = deviation / expected_std       if expected_std > 0.1 else 0
break detected   = abs(z_score) > Z_THRESHOLD     where Z_THRESHOLD = 1.5
```

Lookups: `stats` is `profile["stock_profiles"][SYMBOL]["by_transition"]["FROM->TO"]` from `pipeline/autoresearch/reverse_regime_profile.json`, where `TO == current_regime` from `pipeline/data/regime_ranker_state.json`. `current_price` and `today_open` come from yfinance `period="1d"` history (Close[-1] / Open[-1]).

**Anchor coherence:** the audit's `open_price` (open of 09:15 minute bar) MUST be the same anchor the engine uses for `actual_return`. yfinance's `period="1d"` Open is the official NSE 09:15 open print, so the anchors line up. If a Kite minute bar's 09:15 Open ever drifts more than 0.05 % from the persisted day-open in `correlation_break_history.json` row, flag it `OPEN_PRICE_MISMATCH` and exclude from analysis — that's a sign of a corrupted bar or a Kite/yf data discrepancy that breaks the σ-replication assumption.

Note that "σ" in the user's "3σ / 4σ correlation break" vocabulary is THIS z_score (deviation in units of expected daily-equivalent regime-conditional drift std), not a generic intraday return std. Higher-σ rows in correlation_break_history.json are simply rows where `abs(z_score)` is larger.

**Data-validation policy alignment.** Per CLAUDE.md, no backtest may run on un-registered datasets. SP1 is *not* a backtest — it is a descriptive read of two internal sources plus a one-time historical fetch from a registered live-data adapter (Kite). No new dataset registration is required for SP1. SP2 will register the Kite minute-bar dataset before any backtest reads it.

## 4. Trade roster — last 60 calendar days

**Date range:** 2026-02-25 → 2026-04-25 (inclusive). ~42 trading days. Inside Kite's ~90-trading-day minute-bar retention window with comfortable headroom.

**Roster build steps:**

1. Read `correlation_break_history.json`, filter to rows where `date ∈ [2026-02-25, 2026-04-25]` and `classification ∈ {OPPORTUNITY_LAG, OPPORTUNITY_OVERSHOOT, POSSIBLE_OPPORTUNITY}`.
2. Collapse to one row per `(ticker, date, classification)` by keeping the row with the largest `abs(z_score)` (intra-day re-fires of the same classification deduplicated to the strongest hit).
3. Read `closed_signals.json`, filter `category == "phase_c"` rows where `open_date ∈ [2026-02-25, 2026-04-25]`. Match onto the roster on `(ticker, open_date)`.
4. Tag each row `source ∈ {actual, missed}` based on whether the closed-signals match exists.
5. Read `regime_history.csv`, join `regime_zone` per `date`. Cross-check against the per-row `regime` field from correlation_break_history; if they disagree, log the mismatch and prefer the regime_history.csv value as canonical (regime_history is the daily archive; per-row regime tags can have caching artefacts — see pending task #110 in the trading-day cleanup list).

**Per-row schema:**

| column | source | notes |
|---|---|---|
| `signal_id` | derived | real id when actual, synthetic `MISSED-YYYY-MM-DD-TICKER-CLASSIFICATION` when missed |
| `source` | derived | `actual` \| `missed` |
| `ticker`, `date` | history | |
| `classification` | history | `OPPORTUNITY_LAG` \| `OPPORTUNITY_OVERSHOOT` \| `POSSIBLE_OPPORTUNITY` |
| `trade_rec` | history | `LONG` \| `SHORT` \| `null` (LAG only has a real side; OVERSHOOT and POSSIBLE are NEUTRAL by engine contract) |
| `z_score` | history | the engine's persisted σ at scan time |
| `expected_return`, `actual_return` | history | percent, anchored on day-open |
| `regime` | regime_history.csv ∩ history | canonical from regime_history if mismatch |
| `pcr`, `pcr_class`, `oi_anomaly` | history | for confluence stratification (Table G below) |
| `actual_pnl_pct` | closed_signals (actual only) | from `final_pnl.spread_pnl_pct` |
| `actual_open_time_ist`, `actual_close_time_ist` | closed_signals | timing of the realized trade |

**Side resolution rule.** Per the §3 contract, `trade_rec` is the engine's authoritative side. The audit:
- Includes LAG rows with `trade_rec ∈ {LONG, SHORT}` in side-stratified Tables.
- Includes OVERSHOOT and POSSIBLE rows in the per-trade CSV with `side = NA`. They appear in the shape-distribution Table A and the regime-only Table F but not in side-conditional analyses.
- Closed-signals rows that are not LAG (e.g., a closed trade that came from POSSIBLE) get their realized side preserved (from `final_pnl` long_legs/short_legs) and contribute to actual-vs-counterfactual P&L tables but not to `trade_rec`-conditional stats.

**Expected n.** Apr 20-24 produced ~84 distinct (date, ticker, classification) tuples over 5 trading days (≈17/day). Extrapolating to ~42 trading days suggests **~700 roster rows**. Some will fail the §5.2 bar-validation gate; conservatively assume 600 valid rows. Of those, the LAG subset (the tradeable one) is roughly 30-50 % historically, giving ~200-300 rows with a real side — comfortably above the `n ≥ 10` per-cell threshold for shape × side × regime stratification.

## 5. Per-trade pipeline

For each row `(ticker, open_date, source, side)`:

### 5.1 Fetch minute bars (one-shot, cached)

`fetch_history(ticker, from=open_date 09:15 IST, to=open_date 15:35 IST, interval="minute")`. Cache to `pipeline/data/research/phase_c_shape_audit/bars/<ticker>_<open_date>.parquet` so the script is idempotent.

### 5.2 Validate the bar set

- Must have ≥ 350 minute bars between 09:15 and 15:30 (375 is the full session; allow up to 25 missing)
- First bar at-or-near 09:15 (≤ 09:18 to allow Kite open-tick latency)
- Last bar at-or-near 15:30 (≥ 15:25)
- If a trade fails validation, tag it `BARS_INSUFFICIENT` and exclude from stratified analysis but keep in the per-trade CSV with the failure reason.

### 5.3 Compute shape features per trade

- `open_price` = open of 09:15 bar
- `peak_price`, `peak_minute` = max(close), arg-max in minutes from 09:15
- `trough_price`, `trough_minute` = min(close), arg-min in minutes from 09:15
- `close_price_15_30` = close of 15:30 bar (or last bar if 15:30 missing)
- `price_at_14_30` = close of 14:30 bar (or nearest minute ≥ 14:30)
- `peak_pct = 100 × (peak_price − open_price) / open_price`
- `trough_pct = 100 × (trough_price − open_price) / open_price`
- `close_pct = 100 × (close_price_15_30 − open_price) / open_price`
- `pct_at_14_30 = 100 × (price_at_14_30 − open_price) / open_price`
- `range_first_15min` = max(high) − min(low) over [09:15, 09:30) as % of open
- `range_first_30min` similarly over [09:15, 09:45)
- `peak_in_first_15min = (peak_minute < 15)`
- `trough_in_first_15min = (trough_minute < 15)`

### 5.4 Classify shape (categorical, mutually exclusive, first-match wins)

- **REVERSE_V_HIGH**: `peak_in_first_15min` AND `peak_pct ≥ 0.5 %` AND `close_pct ≤ peak_pct / 2`
- **V_LOW_RECOVERY**: `trough_in_first_15min` AND `trough_pct ≤ −0.5 %` AND `close_pct ≥ trough_pct / 2`
- **ONE_WAY_UP**: `close_pct > peak_pct − 0.5` AND `close_pct ≥ 0.5`
- **ONE_WAY_DOWN**: `close_pct < trough_pct + 0.5` AND `close_pct ≤ −0.5`
- **CHOPPY**: anything else

### 5.5 Counterfactual entry-time grid simulator (NEW in rev 2)

For each row, simulate the user-stated execution rules across an entry-time grid `T_ENTRY ∈ {09:15, 09:20, 09:25, 09:30, 09:45}`. Produce one `cf_entry_<HHMM>_pnl_pct` column per grid point.

**Execution rules per (row, T_ENTRY):**

```
entry_price = close of T_ENTRY-minute bar
side ∈ {SHORT, LONG} from inferred_side
STOP_LOSS_PCT = 3.0       # adverse move from entry
TARGET_PCT    = 4.5       # favorable move from entry
TRAIL_ARM_PCT = 2.0       # arm trail when MFE ≥ 2.0%
TRAIL_DROP_PCT = 1.5      # then exit when price retraces 1.5% from peak/trough
HARD_CLOSE_TIME = 14:30 IST

walk minute bars from T_ENTRY+1 to 14:30:
  pnl_now = signed_return(entry_price, bar_close, side)
  mfe = running max of pnl_now
  if pnl_now <= -STOP_LOSS_PCT  -> exit STOPPED, exit_pnl = -3.0
  elif pnl_now >= TARGET_PCT    -> exit TARGETED, exit_pnl = +4.5
  elif mfe >= TRAIL_ARM_PCT and (mfe - pnl_now) >= TRAIL_DROP_PCT -> exit TRAILED, exit_pnl = mfe - TRAIL_DROP_PCT
  else continue
on bar 14:30: exit TIME, exit_pnl = pnl_now
```

`signed_return(entry, exit, side) = 100 × (exit − entry) / entry` for LONG, `100 × (entry − exit) / entry` for SHORT.

Tie-break on a single bar: a bar's H/L can hit both stop and target — the simulator uses the **conservative** rule (assume stop hits first; SHORT uses high-then-low, LONG uses low-then-high) which under-states P&L slightly but is what the live engine would do.

Per-trade output columns:
- `cf_entry_HHMM_pnl_pct` × 5 (one per grid point)
- `cf_entry_HHMM_exit_reason` × 5 (`STOPPED` | `TARGETED` | `TRAILED` | `TIME`)
- `cf_entry_HHMM_exit_minute` × 5
- `cf_best_grid_entry`, `cf_best_grid_pnl_pct` — grid argmax
- `cf_grid_avg_pnl_pct` — mean across the 5 grid points (the unbiased report)

## 6. Analysis

The audit script outputs seven tables:

**Table A — Shape × side × source distribution.** Counts of (REVERSE_V_HIGH, SHORT) etc. across actual vs missed buckets. Sanity check that the dataset has signal in the cells we want to test.

**Table B — Win rate × shape × side, three views:**
- B-actual: actual P&L from `closed_signals.json` (only the actually-traded rows, source=`actual`)
- B-cf-grid-avg: counterfactual mean across entry-time grid (all valid LAG rows with `trade_rec` set)
- B-cf-best-grid: counterfactual P&L at the per-trade best grid point (look-ahead — diagnostic only, not a tradeable result)

The user's hypothesis predicts:
- (REVERSE_V_HIGH, SHORT) cell shows materially higher win rate than the SHORT baseline in B-cf-grid-avg
- (V_LOW_RECOVERY, LONG) cell — with the 60-day window the LONG sample should be material; report n and lift over LONG baseline
- Other (shape, side) cells should NOT show edge

**Table C — Entry-time grid sensitivity.** For each grid point (09:15…09:45), report mean cf P&L, win rate, and exit-reason mix (STOPPED / TARGETED / TRAILED / TIME). Answers: is there a best entry time, or does the edge hold across the open window?

**Table D — Logistic regression.** Fit `cf_pnl_grid_avg > 0 ~ peak_in_first_15min + peak_pct + trough_pct + close_pct + side + range_first_15min + C(regime)` over the full set of valid trades. Report coefficients, p-values, McFadden pseudo-R². Regime enters as a categorical so its effect is separated from shape.

**Table E — Actual vs counterfactual delta.** For the actually-traded rows, compute `actual_pnl_pct − cf_grid_avg_pnl_pct`. Negative delta means the actual ad-hoc execution captured *less* than the user-stated rules would have. Positive delta means the actual execution did better than the rules. The mean delta is the most actionable single number in the audit — it tells us whether tightening discipline to the stated rules would have helped or hurt.

**Table F — Regime × shape × side cross-tab.** The 5-regime × 5-shape × 2-side cube (50 cells max, many empty). Cells with `n ≥ 10` get `(n, win_rate, avg_cf_pnl)`; cells below threshold are reported as `n only`. This is the table that answers "is the reverse-V edge regime-conditional?" — the user's rev-3 concern.

**Table G — Confluence stratification.** Within each (regime, shape, side) cell that survives the n threshold, sub-stratify on whether `pcr_class ∈ {agreeing, disagreeing, neutral}` and whether `oi_anomaly` is True. This tells us whether the edge concentrates in confluence-confirmed rows (which is what a future SP3 live signal generator would actually trade) versus the unfiltered set. Reported as a side-bar table next to F, not a primary verdict driver — the verdict still uses the unconditional F cells.

## 7. Verdict thresholds

The verdict is one of:

- **CONFIRMED**: a (shape, side) cell with `n ≥ 10` AND `cf_grid_avg win_rate ≥ 70 %` AND one-sided binomial p < 0.05 against the 56.4 % baseline AND `mean(actual − cf) ≤ 0` AND the lift survives in at least 2 of the 5 regimes when the cell is split via Table F (so we're not seeing a regime-luck artefact). Recommend SP2.
- **REGIME_CONDITIONAL_CONFIRMED**: same as CONFIRMED but the lift only survives in 1 regime. Report explicitly which regime and recommend SP2 with the hypothesis pre-registered as `<shape>×<side>|regime=<R>` rather than as an unconditional rule.
- **WEAK_SIGNAL**: cell with `n ≥ 10` AND `cf_grid_avg win_rate` between 60 % and 70 %. Defer SP2; collect more forward data.
- **DISCIPLINE_ONLY**: actual-execution win rate is at baseline but `mean(cf − actual) > 1 pp`, i.e. the stated execution rules outperform the ad-hoc execution even WITHOUT a shape edge. Action: tighten live execution to the stated rules, re-run audit after n more trades.
- **NULL**: no shape × side cell or coefficient is materially better than baseline AND the cf vs actual delta is ≈ 0. The reverse-V observation is descriptive but not predictive.
- **INSUFFICIENT_N**: not enough trades survived `BARS_INSUFFICIENT` or `OPEN_PRICE_MISMATCH` to compute any cell with `n ≥ 10`. Re-run weekly until n permits.

The verdict goes in the report header so the SP2-trigger decision is immediate.

## 8. Outputs

| Path | Contents |
|---|---|
| `docs/research/phase_c_shape_audit/2026-04-25-shape-audit.md` | Verdict, all tables, candidate equation, narrative |
| `pipeline/data/research/phase_c_shape_audit/trades_with_shape.csv` | Per-trade row: signal_id, source, ticker, open_date, side, all shape features, shape class, win flag, actual_pnl_pct, cf_entry_<HHMM>_pnl_pct ×5, cf_entry_<HHMM>_exit_reason ×5, cf_grid_avg, cf_best_grid, validation status |
| `pipeline/data/research/phase_c_shape_audit/missed_signals.csv` | The 50 missed-signal rows (debug — the audit's view of what should have traded but didn't) |
| `pipeline/data/research/phase_c_shape_audit/bars/<ticker>_<date>.parquet` | Cached minute bars per trade |

## 9. Components and file layout

Single-purpose package, mirrors the forensics structure:

```
pipeline/autoresearch/phase_c_shape_audit/
    __init__.py
    roster.py     # build_roster() -> DataFrame; merges closed_signals.json + correlation_break_history.json
    fetcher.py    # _fetch_minute_bars(ticker, date) -> DataFrame, cached to parquet
    features.py   # compute_shape_features(bars) -> dict ; classify_shape(features) -> str
    simulator.py  # simulate_grid(bars, side, grid) -> dict[entry_HHMM -> {pnl_pct, exit_reason, exit_minute}]
    runner.py     # main entry: pull roster, fetch bars, compute features + counterfactual, write outputs
    tests/
        test_features.py     # synthetic bars -> known shape labels (TDD)
        test_simulator.py    # synthetic bars -> known exit-reason / pnl (TDD on STOP / TARGET / TRAIL / TIME paths)
        test_roster.py       # fixture closed_signals + history -> expected union with `source` tagging
```

`runner.py` is invoked as `python -m pipeline.autoresearch.phase_c_shape_audit.runner`. No scheduled-task wiring (one-shot research run; rerun manually after each weekly refresh).

**Critical:** none of these files match the kill-switch hook patterns (`*_strategy.py`, `*_signal_generator.py`, `*_backtest.py`, `*_ranker.py`, `*_engine.py`). The audit produces NO trade rule and NO signal — it only describes properties of trades that already happened (or should have) in the live shadow ledger and counterfactually replays them under stated rules.

## 10. Testing

- **`test_features.py`**: three synthetic minute-bar frames (one reverse-V, one V, one one-way-up) → assert shape label and feature values. ~10 cases.
- **`test_simulator.py`**: synthetic minute-bar frames that hit each exit path:
  1. SHORT, hits 3 % stop at minute 30 → exit_reason=STOPPED, pnl=−3.0
  2. SHORT, hits 4.5 % target at minute 90 → exit_reason=TARGETED, pnl=+4.5
  3. LONG, MFE 2.5 % at minute 60 then retrace 1.5 % at 120 → exit_reason=TRAILED, pnl=+1.0
  4. SHORT, drifts to +0.8 % by 14:30 → exit_reason=TIME, pnl=+0.8
  5. SHORT, single bar where high triggers stop and low touches target → assert STOPPED (conservative tie-break)
  ~8 cases.
- **`test_roster.py`**: fixture with 2 closed_signals rows + 4 correlation_break_history rows (1 overlap) → expected output 5 rows, 2 actual + 3 missed, dedup keyed on (ticker, open_date). 1 case.
- Smoke test: run `runner.py` on the live data, verify the per-trade CSV has 86 rows (36 actual + 50 missed) and the report markdown is generated.
- No live network test in CI (Kite requires session cookie); CI uses cached parquets.

## 11. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Kite session expired when fetching | Reuse `pipeline.kite_client.fetch_history`; fail loudly with the same auth-refresh advice the rest of the system uses |
| Minute-bar gaps for thin/halted tickers | `BARS_INSUFFICIENT` tag excludes from stratified analysis; counted in verdict denominator |
| Multiple trades per ticker per day (PFC ×4, ABCAPITAL ×2) | Each trade gets its own row keyed by signal_id; bar fetch shared via cache. Dedup of missed-signal rows is on `(ticker, open_date)` which collapses intra-day re-fires of the same OPPORTUNITY into one row |
| n = 1 for LONG side in actually-traded | 60-day window plus missed-signal subset materially increases LONG sample (LAG rows with `expected_return < 0` give SHORT, with `> 0` give LONG). If union still < 10, V_LOW_RECOVERY is reported INSUFFICIENT_N |
| Regime stratification thins cells below n=10 | Reported in Table F as `n only` for thin cells; verdict thresholds require n≥10 in the unconditional cell (Table B) before checking regime survival in Table F. Avoids data-mining a single regime cell |
| `trade_rec` is missing for OVERSHOOT/POSSIBLE rows | These rows are kept in shape and regime tables but excluded from side-stratified Tables — matches the engine's NEUTRAL contract. Documented in §4 |
| Regime tag mismatch between `regime_history.csv` and per-row `regime` in history (existing pending task #110) | Audit prefers regime_history.csv; logs mismatch count in the report header. Doesn't gate the run |
| §3.1 σ-replication: Phase A profile may have been re-fit during the 60-day window | The persisted z_score in correlation_break_history is the engine's value at scan time — that's what we use. We do not recompute. Re-fits are part of the scan-time signal, not a contamination |
| §5A blind spot (per Wave C audit) on holiday rows | Defensive `is_trading_day(open_date)` reject (using `pipeline/trading_calendar.py`); Apr 20-24 are all valid trading days |
| Grid simulator look-ahead bias on `cf_best_grid` | Reported as diagnostic only; the headline metric is `cf_grid_avg_pnl_pct` (unbiased mean across grid points). Verdict thresholds use grid_avg, not best |
| Tie-break in single-bar stop-vs-target hit | Conservative rule (stop fires first) — under-states P&L slightly, matches what live engine would do |
| Missed-signal P&L is hypothetical (we don't know if user would have actually taken these trades) | Reported separately in B-cf-grid-avg using `source` tag; CONFIRMED verdict can be requested on actual-only subset OR full union — both reported |
| Shape-class definitions tweaked later | Definitions are constants in `features.py` — single edit point; rerun regenerates everything |

## 12. Hand-off to SP2 (out of scope, here for visibility)

If SP1 returns CONFIRMED:

1. Pre-register the candidate equation as a hypothesis in `docs/superpowers/hypothesis-registry.jsonl`. Include the explicit decision rule, the SP1 win-rate + n, the universe scope (F&O), the test horizon (5 y), the family-size declaration (Section 14.5), and the §15.1 promotion criterion.
2. Build the SP2 backtest under `pipeline/autoresearch/<HID>/` re-using the existing compliance harness (`overshoot_compliance/runner.py`).
3. Run §5A, §1, §9B (≥ 100 k permutations), §9A, §11B, §15.1 gate. The current `compliance_H-2026-04-23-001` baseline is AUTO-FAIL at 10.35 % impaired_pct — SP2's data-cleanliness must clear the §5A gate first or the run is research-only.

If SP1 returns DISCIPLINE_ONLY: park the shape hypothesis, but raise a separate ticket to harden the live execution path (entry near 09:30 anchor, 14:30 hard close, intraday stops/trails). This is an ops fix, not a new strategy.

If SP1 returns NULL: park, don't escalate. The existing track-record edge stands on its current footing without a shape-confluence filter.

---

## Self-review (inline)

- **Placeholders:** none. All thresholds, paths, column names, grid points, exit-rule constants, and the regime cube dimensions are concrete.
- **Internal consistency (rev 4):**
  - §1 goal expanded to counterfactual + regime-conditional
  - §2 scope: 60-day window, all OPPORTUNITY classes, regime tag, entry grid, counterfactual replay
  - §3 data sources: closed_signals + correlation_break_history + regime_history.csv + Phase A profile (reference); §3.1 documents the σ-scoring algorithm we replicate
  - §4 roster: ~700 rows projected, 5-step build, schema with `trade_rec` as canonical side
  - §5 per-trade pipeline: bars + features + shape classification + entry-time grid simulator with explicit exit rules
  - §6 analysis: Tables A-G covering distribution, win-rate, grid sensitivity, logistic regression, actual-vs-cf delta, regime cube, confluence stratification
  - §7 verdict: 6 outcomes including REGIME_CONDITIONAL_CONFIRMED and DISCIPLINE_ONLY
  - §8 outputs: report markdown + per-trade CSV + missed-signals CSV + cached parquets
  - §9 components: roster.py, fetcher.py, features.py, simulator.py, runner.py + 3 test files
  - §10 testing: features + simulator + roster TDD
  - §11 risks: 8 risk rows including 3 new ones for regime + trade_rec + regime-tag mismatch
  - §12 hand-off to SP2 unchanged
- **Scope:** still SP1, still descriptive. No edge claim, no new live signal, no kill-switch trigger. Counterfactual replay is research, not a backtest of a registered hypothesis. σ-scoring is read from persisted engine output, not recomputed.
- **Ambiguity:** simulator rules (§5.5) are deterministic with explicit tie-break. Verdict thresholds are numeric. Grid points enumerated. Side-inference rule is pinned to the engine's `trade_rec` field per §4 with explicit handling for `null` cases.
