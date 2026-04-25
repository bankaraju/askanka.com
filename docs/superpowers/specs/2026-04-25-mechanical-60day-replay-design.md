# Mechanical 60-Day Replay — Design Spec

**Spec ID:** `mechanical_replay_v1`
**Author:** Claude (auto-mode)
**Date:** 2026-04-25
**Status:** Draft → execute on user clearance
**Type:** Forensic replay, **NOT a new hypothesis**. No edge claim, no `hypothesis-registry.jsonl` append, no kill-switch trigger. Mirrors the live engine's existing rules over a 60-day historical window to produce a per-engine P&L attribution.

## 1. Purpose

One-line trader brief:

> *"Take every signal the system fired in the last 60 calendar days. Buy at 9:30 AM IST. Apply our own ATR stops, our own trail logic, our own z-cross exits. Hard close at 2:30 PM IST. Tell me how much money each engine — Phase B basket, spread book, Phase C fades — actually made under those rules."*

The output is a single attribution table the trader desk can stand behind, replacing "we have 5 trades" with "we have N trades, here's the engine-by-engine breakdown."

## 2. Why this exists

- **SP1 (Phase C shape audit)** answered "INSUFFICIENT_N" because it filtered to the post-2026-04-23 LAG label, which only has ~2 days of forward data.
- The live `closed_signals.json` shows 36 closed Phase C trades over 60 days totaling +69%, but the legacy `OPPORTUNITY` label was deprecated, leaving the audit blind.
- **Forward live trading is making money;** we want to confirm the win is structural, not lucky, by re-running the rules mechanically against 60 days of clean canonical data.
- The canonical artifact `canonical_fno_research_v1.json` (154 tickers, dividend-adjusted, 10 sectoral indices on TR basis, registered 2026-04-25) is the single source of truth for prices.

## 3. Scope

| Item | Decision |
|---|---|
| Window | `2026-02-21 → 2026-04-22` (60 calendar days, bounded by canonical end) |
| Universe | 154 canonical tickers — anything outside dropped, count logged |
| Engines covered | Phase C breaks (LAG only), Phase B basket, spread book (best-effort) |
| Entry rule | **9:30 AM IST** for every signal that fires that day, no waiting for live trigger time |
| Exit rules (in priority order) | (1) ATR_STOP — entry-relative loss exceeds 14d ATR × 2.0; (2) Z_CROSS — Phase C only, when intraday peer-relative z-score crosses zero; (3) TRAIL — once peak ≥ trail_budget, ratchet up monotonically, fire on retracement; (4) TIME_STOP — mandatory close at **14:30 IST** |
| Sizing | Equal-weight per signal (descriptive — sizing layer is separate) |
| Costs | Apply 20 bps round-trip slippage per `backtesting-specs.txt §1` |
| Output | `trades_with_exit.csv`, per-engine summary, regime cube, the trader one-pager |

## 4. Inputs (all read-only)

| Input | Path | Purpose |
|---|---|---|
| Canonical universe | `pipeline/data/canonical_fno_research_v1.json` | Which 154 tickers are eligible; valid_from/valid_to per ticker |
| Daily bars | `pipeline/data/fno_historical/<TICKER>.csv` | ATR-14 computation; reference for 9:30 entry as fallback |
| Sectoral indices | `pipeline/data/sectoral_indices/<INDEX>_daily.csv` | Peer anchor for Phase C z-cross recompute |
| Regime tags | `pipeline/data/regime_history.csv` | Per-day regime label for stratification |
| Phase C signals | `pipeline/data/correlation_break_history.json` | Daily LAG/OVERSHOOT/POSSIBLE roster |
| Closed-trade ledger | `pipeline/data/signals/closed_signals.json` | Sanity-check the replay against live realized P&L |
| Phase B picks | `pipeline/data/regime_ranker_state.json` | Daily long/short basket (current snapshot only — historical reconstruction may be partial) |
| Spread book state | `pipeline/data/spread_*` | Open spread positions (best-effort) |
| Minute bars | Kite via `pipeline/autoresearch/phase_c_shape_audit/fetcher.py` | On-demand intraday for the 9:30 → 14:30 walk; parquet-cached at `pipeline/data/research/phase_c_shape_audit/bars/`. **Only fetched for (ticker, date) pairs that have a signal — not for every ticker every day.** |

**No second cache, no parallel fetcher.** SP1's existing minute-bar fetcher and parquet cache are extended; daily bars come from the canonical CSVs registered in the audit doc.

## 5. The rules — verbatim from live engine

### 5.1 ATR-based stop (per ticker, per day)

```
atr_14 = mean(true_range over last 14 trading days)
stop_pct = (atr_14 × 2.0) / entry_price
stop_price_long  = entry_price × (1 - stop_pct)
stop_price_short = entry_price × (1 + stop_pct)
```

This mirrors `pipeline/break_signal_generator.py::_compute_atr_stop` and the `_atr_stop` field persisted on every live signal post-2026-04-22.

### 5.2 Z-cross exit (Phase C only)

Recompute the live Phase C z-score every minute using sector-peer index returns. The signal carries the sector tag (set at fire time); peer index is its `NIFTY*` mapping per the audit doc §9 sector→index table. Exit when |z| dips below zero (sign change from entry).

### 5.3 Trail logic — ratcheted

```
days_held = bars_elapsed / 375  (fractional intraday for sub-day holds)
trail_budget = avg_favorable_move × sqrt(days_held)
peak_pnl_pct = max(running pnl_pct so far)
trail_armed = peak_pnl_pct >= trail_budget
trail_stop_pct = max(prev_trail_stop_pct, peak_pnl_pct - trail_budget)  # monotonic ratchet
fire if trail_armed AND current_pnl_pct < trail_stop_pct
```

`avg_favorable_move` per ticker comes from the live `spread_statistics` if available, else 1-month historical peak-pnl mean. Trail logic mirrors `pipeline/signal_tracker.py::check_signal_status` post-2026-04-22 (B9 + B10 fixes).

### 5.4 Daily stop — inert once trail armed

```
daily_stop_pct = -(avg_favorable_move × 0.50)
fire if (NOT trail_armed) AND current_pnl_pct < daily_stop_pct
```

### 5.5 Time stop

Hard close at **14:30 IST**. No exceptions.

## 6. Modules

```
pipeline/autoresearch/mechanical_replay/
├── __init__.py
├── constants.py           # rules from §5 + paths
├── canonical_loader.py    # reads canonical artifact + daily CSVs + sectoral CSVs (single accessor)
├── atr.py                 # 14-day ATR per (ticker, date) → stop_pct
├── roster.py              # per-day signal roster (Phase C / Phase B / spread)
├── simulator.py           # 9:30 entry → minute walk → exit reason + pnl_pct
├── report.py              # trader one-pager + regime cube
├── runner.py              # CLI orchestration
└── tests/
    ├── test_canonical_loader.py
    ├── test_atr.py
    ├── test_roster.py
    ├── test_simulator.py
    └── test_report.py
```

The simulator reuses SP1's `fetcher.fetch_minute_bars` for minute data — passthrough, no fork.

## 7. Outputs

| Output | Path |
|---|---|
| Per-trade ledger | `pipeline/data/research/mechanical_replay/trades_with_exit.csv` |
| Per-engine summary | `pipeline/data/research/mechanical_replay/engine_summary.json` |
| Trader one-pager | `docs/research/mechanical_replay/2026-04-25-replay-60day.md` |

The one-pager carries the canonical attribution table (per-engine, per-regime, per-exit-reason) plus a sanity-check section comparing replay totals to live `closed_signals.json` totals over the same window.

## 8. Verdict semantics

This is **descriptive forensics, not an edge test.** The output is a number, not a verdict. Consumers of the output can ask:

- *"Does engine X make money under our rules?"* — read the engine summary.
- *"Which exit reason dominates?"* — read the exit-reason breakdown.
- *"Does Phase C still work post-relabel?"* — replay the legacy OPPORTUNITY label with current rules; compare to live realized.

No PASS/FAIL. No promotion. The replay informs the operator's confidence in the live system; it does not gate any deployment decision (governance ladder per `backtesting-specs.txt` is unchanged).

## 9. Compliance and bias declarations

- **Survivorship bias:** inherited from canonical — F&O members removed pre-2024 are excluded. Bounded per audit doc §7. For a 60-day forward replay starting 2026-02-21, the bias contribution is negligible (no removals expected in the window).
- **Look-ahead:** none. Daily bars and minute bars are point-in-time; canonical valid_from/valid_to enforce universe membership at trade date.
- **Adjustment mode:** dividend-adjusted close (canonical §6). Replay returns close-to-close on adjusted basis; corporate actions in window logged separately.
- **Slippage:** 20 bps round-trip (§1 of backtesting spec).
- **Strategy gate:** no new `*_strategy.py / *_signal_generator.py / *_backtest.py / *_engine.py` file is introduced. The `simulator.py / runner.py / report.py` filenames are intentionally **not** in the kill-switch trigger list. This is forensics, not a new trading rule.

## 10. Sanity checks (required before reporting)

The replay output is rejected if any of the following fail:

1. **Coverage:** ≥ 95% of Phase C signals in `correlation_break_history.json` for the window match a (ticker, date) pair the replay processed. Missing rows logged with reason (ticker not in canonical / minute-bar fetch failed / zero-volume bar).
2. **Live cross-check:** for actual closed Phase C trades in the window where the replay also has a row, replay realized pnl_pct must be within ±2pp of live `final_pnl.spread_pnl_pct` ≥ 80% of the time. Wider divergence triggers an investigation note in the report (likely entry-time mismatch — live enters at signal time, replay at 09:30).
3. **Regime balance:** every regime present in `regime_history.csv` window must have ≥ 1 row in the replay output. Missing regimes logged.

## 11. Window math

```
end:    2026-04-22 (canonical window_end)
start:  2026-04-22 - 60 calendar days = 2026-02-21
```

Trading days in window: ~40 (60 calendar days × 5/7 minus holidays).

## 12. Re-run cadence

Ad-hoc. Re-run when:
- A new canonical version ships (`canonical_fno_research_v2`, etc.)
- Live execution rules change (new ATR multiplier, new trail formula, etc.)
- The operator wants the rolling 60-day attribution refreshed

## 13. Out of scope (v1)

- Spread engine replay beyond best-effort — full pair-leg reconstruction requires historical spread state snapshots which may not be persisted.
- Sizing layer — current scope is equal-weight; any sizing study is a v2 spec.
- Multi-day holding period — replay is intraday-only by mandate.
- Regime-conditional rule tuning — rules are frozen at live settings; the replay does not search for better rules.

## 14. Acceptance

- Spec committed and reviewable.
- All 9 modules under `pipeline/autoresearch/mechanical_replay/` implemented with TDD.
- Smoke run on 2026-02-21 → 2026-04-22 window completes without errors.
- Sanity checks (§10) pass.
- Trader one-pager committed to `docs/research/mechanical_replay/`.
- `SYSTEM_OPERATIONS_MANUAL.md` updated with the new sub-section.
- Memory file `project_mechanical_60day_replay.md` written; index updated.

## 15. References

- Canonical dataset: `docs/superpowers/specs/2026-04-25-canonical-fno-research-dataset-audit.md`
- Live ATR stop logic: `pipeline/break_signal_generator.py::_compute_atr_stop`
- Live trail/stop logic: `pipeline/signal_tracker.py::check_signal_status` (B9 + B10 fixes, 2026-04-22)
- SP1 minute-bar fetcher: `pipeline/autoresearch/phase_c_shape_audit/fetcher.py`
- Backtesting standards: `docs/superpowers/specs/backtesting-specs.txt`
- Data validation policy: `docs/superpowers/specs/anka_data_validation_policy_global_standard.md`
