# Phase C Intraday Shape Audit — Design Spec

**Date:** 2026-04-25
**Status:** Sub-project 1 (SP1) of a 3-stage chain. SP1 is descriptive forensics; SP2 + SP3 are downstream and out of scope for this spec.
**Hypothesis class:** Descriptive only. **No edge claim. No new strategy file. No kill-switch trigger.**
**Author:** Claude Opus 4.7 (working session 2026-04-25 with Bharat).
**Origin:** User observation that live 3σ correlation breaks show a reverse-V intraday shape — peak within the first 15 min then fade through the day — and that this shape is *what makes the SHORT trade work*. Mirror: a V shape (trough early, recovery through the day) is what makes the LONG trade work. Track record corroborates: 36 closed Phase C trades (Apr 20–24), 35 SHORT / 1 LONG, 56.4 % blended win rate, +1.85 % avg P&L.

---

## 1. Goal

Quantify whether the intraday SHAPE of price action on a Phase C break day is what separates winning trades from losing trades. Specifically test the user-asserted mapping:

- **REVERSE_V_HIGH** (peak ∈ [09:15, 09:30) followed by sustained fade) → SHORT trade should win
- **V_LOW_RECOVERY**  (trough ∈ [09:15, 09:30) followed by sustained recovery) → LONG trade should win
- All other shapes (one-way-up, one-way-down, choppy) should not have a directional edge

If shape × side correlates with P&L outcome at material lift over the 56.4 % baseline, the result motivates SP2 (a pre-registered hypothesis tested on 5 y of F&O minute-bar data through the §1-§14 compliance gate). If shape does NOT separate, we conclude the existing track-record edge comes from something else (e.g., the residual-reversion mechanic itself) and the reverse-V observation is post-hoc pattern-matching.

## 2. Scope

**In scope (SP1, this spec):**
- All closed Phase C trades from `pipeline/data/signals/closed_signals.json` where `category == "phase_c"` (n = 36 today, will grow as more close)
- Per-trade intraday minute bars 09:15–15:30 IST, fetched once via Kite `historical_data`
- Shape-feature computation per trade, shape classification, stratified P&L analysis, simple logistic-regression model
- A verdict markdown + per-trade CSV with all features for downstream reuse

**Out of scope:**
- SP2 — applying any rule discovered here to a 5 y backtest. That is its own spec, with mandatory hypothesis registration in `docs/superpowers/hypothesis-registry.jsonl` BEFORE any backtest code, and full §1-§14 compliance.
- SP3 — wiring a forward live signal generator. Triggered only after SP2 PASSes the §15.1 gate ladder.
- Repairing the F3 forward shadow ledger (`pipeline/data/research/phase_c/live_paper_ledger.json` is missing; the live track record is being driven by `shadow_pnl.py` + `today_recommendations.json` rather than `phase_c_shadow.py`). That bug is real but separate.

## 3. Data sources

| Source | Path | Used for |
|---|---|---|
| Closed-trade ledger | `pipeline/data/signals/closed_signals.json` | trade roster (ticker, open_date, side, P&L) |
| Track-record summary | `data/track_record.json` | sanity-check totals (39 closed, 56.4 % win) |
| Kite minute bars | `kite.connect.historical_data(token, from, to, "minute")` | intraday OHLC 09:15-15:30 per trade |
| Holiday calendar | `pipeline/trading_calendar.py` | reject any open_date that's a 2026 NSE holiday (defensive — the dataset shouldn't contain any but check anyway) |

The Kite token-resolver lives in `pipeline/kite_client.py` (`fetch_ltp`, `fetch_history`). Reuse — do not write a new auth path.

**Data-validation policy alignment.** Per CLAUDE.md, no backtest may run on un-registered datasets. SP1 is *not* a backtest — it is a descriptive read of an internal source (`closed_signals.json`) plus a one-time historical fetch from a registered live-data adapter (Kite). No new dataset registration is required for SP1. SP2 will register the Kite minute-bar dataset before any backtest reads it.

## 4. Trade roster and side inference

Pulled today from `closed_signals.json`:

| Stat | Value |
|---|---|
| Total Phase C closed | 36 |
| Date range | 2026-04-20 → 2026-04-24 |
| SHORT | 35 (win rate 57.1 %, avg +1.83 %) |
| LONG | 1 — BHEL 2026-04-20 (+5.32 %) |
| Inside Kite 90-day minute-bar window? | yes (oldest is 5 days old) |

Side inference: a Phase C trade has either `long_legs` xor `short_legs` populated in the `final_pnl` dict. PAIR rows (both populated) are not in this dataset for `category == phase_c`.

The 35-SHORT / 1-LONG imbalance means SP1's LONG-side stratification is statistically empty (n = 1) and the verdict will report the LONG hypothesis as "untested for lack of n" rather than confirmed or rejected. SP2's larger universe will fix this.

## 5. Per-trade pipeline

For each closed trade `(ticker, open_date, side, final_pnl_pct)`:

1. **Fetch minute bars.** `fetch_history(ticker, from=open_date 09:15 IST, to=open_date 15:30 IST, interval="minute")`. Cache to `pipeline/data/research/phase_c_shape_audit/bars/<ticker>_<open_date>.parquet` so the script is idempotent (no second Kite hit on re-run).
2. **Validate the bar set.**
   - Must have ≥ 350 minute bars between 09:15 and 15:30 (375 is the full session; allow up to 25 bars missing for transient gaps)
   - First bar at-or-near 09:15 (first-bar-time ≤ 09:18 to allow Kite's open-tick latency)
   - Last bar at-or-near 15:30 (last-bar-time ≥ 15:25)
   - If a trade fails validation, tag it `BARS_INSUFFICIENT` and exclude from the stratified analysis but keep in the per-trade CSV with the failure reason.
3. **Compute shape features per trade:**
   - `open_price` = open of 09:15 bar
   - `peak_price`, `peak_minute` = max(close), arg-max in minutes from 09:15
   - `trough_price`, `trough_minute` = min(close), arg-min in minutes from 09:15
   - `close_price_15_30` = close of 15:30 bar (or last bar if 15:30 missing)
   - `price_at_14_30` = close of 14:30 bar (or nearest minute ≥ 14:30)
   - `peak_pct = 100 × (peak_price − open_price) / open_price`
   - `trough_pct = 100 × (trough_price − open_price) / open_price`
   - `close_pct = 100 × (close_price_15_30 − open_price) / open_price`
   - `pct_at_14_30 = 100 × (price_at_14_30 − open_price) / open_price`
   - `range_first_15min = max(high) − min(low) over [09:15, 09:30)` as % of open
   - `range_first_30min` similarly over [09:15, 09:45)
   - `peak_in_first_15min = (peak_minute < 15)`
   - `trough_in_first_15min = (trough_minute < 15)`
4. **Classify shape (categorical):**
   - **REVERSE_V_HIGH**: `peak_in_first_15min` AND `peak_pct ≥ 0.5 %` AND `close_pct ≤ peak_pct / 2` (peak is real and price gave back at least half)
   - **V_LOW_RECOVERY**: `trough_in_first_15min` AND `trough_pct ≤ −0.5 %` AND `close_pct ≥ trough_pct / 2` (trough is real and price recovered at least half)
   - **ONE_WAY_UP**: `close_pct > peak_pct − 0.5` AND `close_pct ≥ 0.5` (close near max, monotone-ish climb)
   - **ONE_WAY_DOWN**: `close_pct < trough_pct + 0.5` AND `close_pct ≤ −0.5` (close near min)
   - **CHOPPY**: anything else
   - Mutually exclusive — first match wins, in the order listed.

## 6. Analysis

The audit script outputs three tables:

**Table A — Win rate × shape × side.** Cross-tab with cells `(n, win_rate, avg_pnl_pct)`. The user's hypothesis predicts:
- (REVERSE_V_HIGH, SHORT) cell shows materially higher win rate than the SHORT baseline
- (V_LOW_RECOVERY, LONG) cell — likely n = 0 or 1 in SP1 dataset; report as INSUFFICIENT_N
- Other (shape, side) cells should NOT show edge

**Table B — Logistic regression.** Fit `win ~ peak_in_first_15min + peak_pct + trough_pct + close_pct + side` over the full set of valid trades. Report coefficients, p-values, McFadden pseudo-R². Use this to surface any non-obvious feature that separates wins from losses.

**Table C — The candidate equation.** Pick the strongest single classifier from Table A and Table B and write it as a one-line decision rule, e.g. `if (peak_in_first_15min) and (peak_pct >= 0.5) and (close_pct <= peak_pct/2): SHORT`. Compute its win rate and avg P&L on the SP1 set as the proposed SP2 hypothesis.

## 7. Verdict thresholds

The verdict is one of:

- **CONFIRMED**: shape × side cell with `n ≥ 10` AND `win_rate ≥ 70 %` AND a one-sided binomial p-value < 0.05 against the 56.4 % baseline. Recommend SP2.
- **WEAK_SIGNAL**: cell with `n ≥ 10` AND `win_rate` between 60 % and 70 %. Defer SP2; collect more forward data.
- **NULL**: no cell or coefficient is materially better than baseline. The reverse-V observation is descriptive but not predictive; the existing track-record edge must come from something else.
- **INSUFFICIENT_N**: not enough trades survived `BARS_INSUFFICIENT` to compute any cell with `n ≥ 10`. Re-run weekly until n permits.

The verdict goes in the report header so the read of the SP2-trigger decision is immediate.

## 8. Outputs

| Path | Contents |
|---|---|
| `docs/research/phase_c_shape_audit/2026-04-25-shape-audit.md` | Verdict, three tables, candidate equation, narrative |
| `pipeline/data/research/phase_c_shape_audit/trades_with_shape.csv` | Per-trade row: signal_id, ticker, open_date, side, all shape features, shape class, win flag, final_pnl_pct, validation status |
| `pipeline/data/research/phase_c_shape_audit/bars/<ticker>_<date>.parquet` | Cached minute bars per trade (one-shot fetch) |

## 9. Components and file layout

Single-purpose package, mirrors the forensics structure:

```
pipeline/autoresearch/phase_c_shape_audit/
    __init__.py
    fetcher.py    # _fetch_minute_bars(ticker, date) -> DataFrame, cached to parquet
    features.py   # compute_shape_features(bars) -> dict ; classify_shape(features) -> str
    runner.py     # main entry: pull trades, fetch bars, compute, write outputs
    tests/
        test_features.py    # synthetic bars → known shape labels (TDD)
```

`runner.py` is invoked as `python -m pipeline.autoresearch.phase_c_shape_audit.runner`. No scheduled-task wiring (this is a one-shot research run; rerun manually after each weekly refresh).

**Critical:** none of these files match the kill-switch hook patterns (`*_strategy.py`, `*_signal_generator.py`, `*_backtest.py`, `*_ranker.py`, `*_engine.py`). The audit produces NO trade rule and NO signal — it only describes properties of trades that already happened in the live shadow ledger.

## 10. Testing

- `test_features.py` builds three synthetic minute-bar frames (one reverse-V, one V, one one-way-up) and asserts the right shape label and feature values. Pytest, ~10 cases.
- Smoke test: run `runner.py` on the live closed_signals.json, verify the per-trade CSV has 36 rows and the report markdown is generated.
- No live network test in CI (Kite requires session cookie); the CI path uses the cached parquets.

## 11. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Kite session expired when fetching | Reuse `pipeline.kite_client.fetch_history`; fail loudly with the same auth-refresh advice the rest of the system uses |
| Minute-bar gaps for thin/halted tickers | `BARS_INSUFFICIENT` tag excludes from stratified analysis; counted in verdict denominator |
| Multiple trades per ticker per day (PFC ×4, ABCAPITAL ×2, etc.) | Each trade gets its own row keyed by signal_id; the bar fetch is shared via the cache |
| n = 1 for LONG side | Reported as INSUFFICIENT_N for the V_LOW_RECOVERY hypothesis. Acceptable for SP1; SP2 fixes via 5 y backtest |
| §5A blind spot (per Wave C audit) on holiday rows | Defensive `is_trading_day(open_date)` reject (using `pipeline/trading_calendar.py`); Apr 20-24 are all valid trading days so no impact today |
| User changes the shape-class definitions later | Definitions are in `features.py` constants — single edit point; re-run regenerates outputs |

## 12. Hand-off to SP2 (out of scope, here for visibility)

If SP1 returns CONFIRMED:

1. Pre-register the candidate equation as a hypothesis in `docs/superpowers/hypothesis-registry.jsonl`. Include the explicit decision rule, the SP1 win-rate + n, the universe scope (F&O), the test horizon (5 y), the family-size declaration (Section 14.5), and the §15.1 promotion criterion.
2. Build the SP2 backtest under `pipeline/autoresearch/<HID>/` re-using the existing compliance harness (`overshoot_compliance/runner.py`).
3. Run §5A, §1, §9B (≥ 100 k permutations), §9A, §11B, §15.1 gate. The current `compliance_H-2026-04-23-001` baseline is AUTO-FAIL at 10.35 % impaired_pct — SP2's data-cleanliness must clear the §5A gate first or the run is research-only.

If SP1 returns NULL: park, don't escalate. The existing track-record edge stands on its current footing (residual-reversion + Z-cross stop) without a shape-confluence filter.

---

## Self-review (inline)

- **Placeholders:** none. All thresholds, paths, and column names are concrete.
- **Internal consistency:** SP1's outputs feed SP2's hypothesis registration; SP2's compliance gate is referenced explicitly. No contradictions.
- **Scope:** focused on n = 36 today's data. Decomposition into SP1/SP2/SP3 is explicit; SP1 alone is one implementation plan.
- **Ambiguity:** shape definitions are deterministic (mutually exclusive, first-match-wins). Win-rate baseline is the 56.4 % from track_record, stated explicitly.
