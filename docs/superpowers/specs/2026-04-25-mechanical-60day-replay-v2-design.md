# Mechanical 60-Day Replay v2 — Full Deterministic Reconstruction

**Spec ID:** `mechanical_replay_v2`
**Date:** 2026-04-25
**Status:** Draft → execute on user clearance
**Type:** Forensic replay (descriptive). Same governance posture as v1: NO hypothesis-registry append, NO kill-switch trigger, NO PASS/FAIL gating.

## 1. Why v2

v1 (commits `2c293f7..081b360`) shipped the 09:30/14:30 minute-bar walk + ATR/trail/slippage exits — that part is solid. But it **read the live engine's stored state** (`correlation_break_history.json`, `regime_history.csv`) instead of regenerating it, and it never replayed Phase B basket or the spread book. That means:

- The replay can't claim independence from live engine state. If the live engine had a bug or relabel mid-window, the replay inherits it.
- We can't measure "what would the live system have made on day X under our rules?" for any day where the live engine wasn't running, was misconfigured, or used a different label set.
- Phase B basket and spread book — the two engines that ship the bulk of the live P&L — are unmeasured.
- Z_CROSS exit channel is wired but not fed (would need per-minute peer-residual recompute).

v2 closes all four gaps.

## 2. What "deterministic reconstruction" means here

For every trading day `D` in the window, v2 does *not* read any live engine output. It re-runs each engine's trigger logic against canonical historical inputs (daily bars, sectoral indices, frozen trust scores, ETF panel) to produce the same daily roster the live engine would have produced *if* it had been pointed at the canonical dataset. Then v1's simulator runs on top.

The acid test: if `correlation_break_history.json` were deleted from disk, v2's outputs should not change. v1 fails this test; v2 passes it.

## 3. Scope

| Item | v1 | v2 |
|---|---|---|
| Window | 60 calendar days bounded by canonical end | Same |
| Universe | canonical_fno_research_v1 (154 tickers) | Same |
| Roster source — Phase C | Read from `correlation_break_history.json` | **Re-run `break_signal_generator` against canonical bars** |
| Roster source — Phase B | _not run_ | **Re-run `regime_ranker.rank_today` against canonical bars + frozen trust scores** |
| Roster source — Spread | _not run_ | **Re-run pair-z + regime gate against canonical bars** |
| Regime tag | Read from `regime_history.csv` | **Re-run `regime_engine` against canonical ETF + Indian-data inputs** |
| Z_CROSS exit | Wired, not populated | **Per-minute peer-residual recompute against sectoral indices** |
| Intraday walk | 09:30→14:30 minute walk, ATR/Trail/Time | Same (reuses v1 simulator) |
| Output | Markdown one-pager + per-engine summary + per-trade narration | Same, plus per-engine roster CSV (Phase B / spread / Phase C) |

## 4. Modules

```
pipeline/autoresearch/mechanical_replay/
├── (existing v1 modules unchanged)
├── reconstruct/
│   ├── __init__.py
│   ├── regime.py          # NEW — rerun ETF regime engine per (date) → regime tag
│   ├── phase_c.py         # NEW — rerun break_signal_generator per (date) → Phase C roster
│   ├── phase_b.py         # NEW — rerun regime_ranker per (date) → Phase B basket
│   ├── spread.py          # NEW — rerun pair-z + regime gate per (date) → spread book
│   └── zcross.py          # NEW — per-minute peer-residual recompute → Z_CROSS exit time
└── runner_v2.py           # NEW — drives all four reconstructions, then v1 simulator
```

Existing v1 modules (`canonical_loader`, `atr`, `roster`, `simulator`, `report`, `runner`) stay; v2 adds a `reconstruct/` subpackage and a separate `runner_v2.py` so v1 keeps working as a thin baseline.

## 5. The four reconstructions

### 5.1 Regime regeneration (`reconstruct/regime.py`)

For each `D` in window:
- Load **frozen ETF weights** as-of `D` (weekly reoptimization log → ETF weights effective on `D`).
- Load canonical ETF closes through `D-1`.
- Compute the regime score by applying the live regime formula (see `pipeline/regime_engine.py::compute_regime`).
- Emit `(date, regime_zone, signal_score)`.

**Frozen-input policy:** ETF weights MUST be the weights that were live on `D`, not the current weights. If we don't have a weight log, the spec's `§14 contamination map` records this as the dominant uncertainty source.

### 5.2 Phase C reconstruction (`reconstruct/phase_c.py`)

For each `D` in window, for each ticker `T` in canonical universe at `D`:
- Compute the rolling correlation residual against `T`'s sector peer index over the lookback window.
- Compute z-score of today's residual vs the rolling distribution.
- If `|z| > 3.0` and the configured regime gate is open, emit a `LAG` or `OVERSHOOT` row depending on direction & geometry (mirrors `pipeline/break_signal_generator.py::classify_break`).
- Emit `(date, ticker, classification, z_score, trade_rec, regime, sector)`.

**Trade direction (`trade_rec`):** derived from the same `direction_tested` logic the live engine uses post-2026-04-23 (LAG = follow peer; OVERSHOOT = fade overshoot).

### 5.3 Phase B reconstruction (`reconstruct/phase_b.py`)

For each `D` in window:
- Load frozen trust scores as-of `D` (or "best-known" if no daily snapshot exists — record as a §14 contamination).
- Load canonical bars through `D-1`.
- Run the live `regime_ranker.rank_today` logic against the regenerated regime tag from §5.1.
- Emit the daily long basket + short basket as one row per (date, ticker, side).

**Trust-score archival** is the open data dependency. Acceptable v2 fallback: use the current trust scores and flag the contamination explicitly. Trust-score-versioning is a separate v3 dataset job.

### 5.4 Spread reconstruction (`reconstruct/spread.py`)

For each `D` in window, for each pair `P` in `pipeline/config/spreads.json`:
- Load canonical bars for both legs through `D-1`.
- Compute the rolling spread z-score over the configured lookback.
- Apply the regime gate from §5.1.
- If `|z| > entry_threshold` AND gate is green → enter at 09:30 on `D` (long the cheap leg, short the rich leg).
- Emit `(date, pair_id, leg_long, leg_short, entry_z, regime, gate_status)`.

### 5.5 Z_CROSS exit (`reconstruct/zcross.py`)

For each Phase C trade, for each minute bar in the 09:30→14:30 walk:
- Recompute the peer-relative z-score against the sectoral index using the same rolling window as the daily detector but extended to minute resolution.
- If z crosses zero (sign change from entry sign) at minute `M`, return `M` as the Z_CROSS exit time.

The simulator already accepts a `zcross_time` parameter. v2 just populates it.

## 6. Output schema additions

Per-engine roster CSVs (one per engine):
```
pipeline/data/research/mechanical_replay/v2/
├── regime_reconstructed.csv      # date, regime_zone, signal_score
├── phase_c_roster.csv             # date, ticker, classification, z, trade_rec, regime, sector
├── phase_b_roster.csv             # date, ticker, side, score, regime
├── spread_roster.csv              # date, pair_id, leg_long, leg_short, entry_z, regime
├── zcross_times.csv               # signal_id, ticker, date, zcross_time, z_at_entry, z_at_cross
└── trades_with_exit.csv           # all engines, same schema as v1, joined narration column
```

## 7. Data dependencies

| Dependency | Status | Notes |
|---|---|---|
| Canonical 154-ticker daily bars | ✅ registered | dataset_id `canonical_fno_research_v1` |
| Canonical sectoral indices (10) | ✅ registered | TR basis, dividend-adjusted |
| ETF weights time-series | ⚠ partial | Need weekly snapshot log; current state is "as of last reopt only" |
| Trust score time-series | ❌ not archived | Use current snapshot, flag §14 contamination |
| Spread config history | ✅ git history | `pipeline/config/spreads.json` is versioned |
| Minute bars (Kite cache) | ✅ on-demand | Existing parquet cache from SP1 fetcher |

**Blocker** for full v2 acceptance: ETF-weight history archival (~1 week of work to backfill from weekly reopt logs). Trust-score history is a softer constraint — v2 can ship with the contamination flagged, then upgrade later.

## 8. Acceptance gates

Same §10 gates from v1, but with stricter coverage thresholds because v2 reconstructs the full roster:

- **Coverage:** ≥95% of regenerated Phase C signals match a (ticker, date) the v2 simulator could process. (v1 was constrained by missing trade_rec on POSSIBLE rows; v2 reconstructs trade_rec from the live formula, so coverage should approach 100%.)
- **Live cross-check (Phase C only, where live ledger has a row):** ≥80% of replay vs live realized P&L within ±2pp **after subtracting the systematic 09:30-vs-signal-time entry difference** (compute the median entry-time gap across overlapping rows, apply as a single shift, then check tolerance).
- **Roster cross-check (NEW for v2):** ≥95% of regenerated Phase C signals must also appear in the live `correlation_break_history.json` for the same (ticker, date) — proving the reconstruction matches live behavior. Mismatches logged with diff (bar quality / threshold sensitivity / regime tag drift).
- **Regime cross-check (NEW for v2):** ≥98% of regenerated daily regime tags must match the live `regime_history.csv` value over the same window.

## 9. Build sequencing (proposed)

```
v2 T0   spec (this file) + plan
v2 T1   reconstruct/regime.py + tests + cross-check vs regime_history.csv
v2 T2   reconstruct/phase_c.py + tests + cross-check vs correlation_break_history.json
v2 T3   reconstruct/phase_b.py + tests
v2 T4   reconstruct/spread.py + tests
v2 T5   reconstruct/zcross.py + tests + plumb into simulator
v2 T6   runner_v2.py orchestration
v2 T7   per-engine roster CSV writers (extend report.py)
v2 T8   first full v2 run + artifact + cross-check report
v2 T9   docs sync (SOM + memory + index)
```

T0 is this spec. T1 (regime regen) is the highest-leverage starting point — it unblocks T2/T3/T4 since all three need the regime tag.

## 10. Compliance and bias declarations (v2)

Inherits v1's declarations. Additional v2 items:

- **Frozen-input bias:** ETF weights and trust scores are "best-known historical" not "as-of-D". The v2 contamination map quantifies the bias by re-running with current vs. historical weights and reporting the spread.
- **Threshold sensitivity:** the live engine's `|z| > 3.0` Phase C threshold may have drifted across the 60-day window. v2 cross-checks against the live roster — material divergence triggers a fragility sweep at `±0.25` around 3.0.
- **Coverage of Z_CROSS:** if the per-minute peer-residual recompute is too expensive to run on every day in the window, v2 may default to a "computed only for Phase C trades that opened" optimization. Document explicitly.

## 11. References

- v1 spec: `docs/superpowers/specs/2026-04-25-mechanical-60day-replay-design.md`
- Live regime engine: `pipeline/regime_engine.py`
- Live Phase C engine: `pipeline/break_signal_generator.py`
- Live Phase B ranker: `pipeline/regime_ranker.py`
- Live spread config: `pipeline/config/spreads.json`
- Canonical dataset: `docs/superpowers/specs/2026-04-25-canonical-fno-research-dataset-audit.md`
- Backtesting standards: `docs/superpowers/specs/backtesting-specs.txt`
- Data validation policy: `docs/superpowers/specs/anka_data_validation_policy_global_standard.md`

## 12. Out of scope (v2)

- **Full minute-by-minute replay of the entire 154-ticker universe** every day for 60 days. v2 still fetches minute bars only for (ticker, date) pairs that have a regenerated signal. A full universe scan is a hypothetical v3 study.
- **Hypothesis-registry append.** v2 stays descriptive forensics. If a regenerated engine's P&L profile is interesting enough to warrant edge testing, that's a separate hypothesis with its own pre-registration.
- **Live promotion.** No ladder advancement, no kill-switch interaction.
