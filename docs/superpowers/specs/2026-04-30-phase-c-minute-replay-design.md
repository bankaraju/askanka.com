# Phase C 2y Minute-Resolution Replay — Design

**Status:** DESIGN_DRAFT
**Author:** Claude Opus 4.7 / Bharat Ankaraju
**Date:** 2026-05-01

---

## 1 / Why this exists

Phase C kill criteria (memory `project_phase_c_kill_criteria`) say:

> Edge < 100 bps OR win < 55% → archive Phase C, pivot to gap-fade /
> pair-trade overlays.

The existing forward shadow has **n=11** closed trades (as of 2026-04-30) — too small to commit to either decision. The 2y mechanical replay at `pipeline/autoresearch/mechanical_replay/reconstruct/phase_c.py` runs at **daily resolution**, but the live Phase C signal fires **intraday when a 4σ correlation break is observed at a 15-min snapshot**. The two are not the same null:

- Daily replay: "Did today's CLOSE return cross the |z|≥4 threshold against the
  PIT (regime, symbol) profile?" — entry at close, exit at next-day close.
- Live signal: "Did any 15-min intraday snapshot today show |z|≥4 vs the PIT
  profile, with PCR-NEUTRAL and OI-NEUTRAL gates?" — entry at the snapshot
  moment, exit at 14:30 IST or ATR(14)×2 stop.

Step 3 in the user-approved 2026-04-30 plan: **a minute-resolution replay
that mirrors the LIVE signal** (intraday entry, intraday exits) across the
last 2 years.

This resolves the 100-bps / 55%-win question with realistic n (~500–1000
candidate signals over 2y instead of 11).

## 2 / Scope (frozen)

- **Window:** 2024-04-01 → 2026-04-30 (matches EODHD 1m depth probe).
- **Universe:** top-30 by 60d ADV from `canonical_fno_research_v3.json`
  — same set being backfilled in `pipeline/data/fno_intraday_1m/`.
- **Resolution:** 1-minute bars from EODHD `/api/intraday`.
- **Snapshot cadence:** every 15 minutes from 09:30 to 14:00 IST inclusive
  (matches live Phase C scheduler tasks `AnkaCorrelationBreaks_HHMM`).
- **Profile basis:** walk-forward, refit every 3 calendar months,
  2-year lookback (matches existing `reconstruct/phase_c.py`). Profiles
  computed from canonical daily bars (NOT reconstituted from minute bars).
- **Regime tag:** PIT regime tape v0 (`pipeline/data/regime_history.csv`
  IS contaminated — use `regime_v3_curated_pit.csv` instead, per memory
  `reference_regime_history_csv_contamination`).
- **Classification:** mirror the LAG-only routing in
  `break_signal_generator.py` (post-2026-04-23 audit). OPPORTUNITY_OVERSHOOT
  is recorded but informational-only, identical to live behavior.
- **Stop:** ATR(14) × 2.0 from prior 14 daily bars (PIT, no leakage).
- **Time stop:** 14:30 IST mechanical close.
- **Cost model:** 5 bps round-trip slippage (matches Phase C live shadow
  `notional_inr × pnl_pct` net).

## 3 / What is NOT in scope (deferred)

- OI-anomaly gate (currently NOT applied because we don't have minute-level
  OI; live engine reads end-of-day bhavcopy, which is daily anyway). Apply
  at minute granularity only as v2.
- PCR gate also collapses to daily (bhavcopy). Treat as NEUTRAL when
  bhavcopy day record missing — same as live.
- Trust-score gate. Live engine does NOT gate Phase C on trust scores.

## 4 / Output contract

`pipeline/data/research/phase_c/minute_replay_<from>_<to>.csv`

Columns: `date, snap_time_ist, ticker, regime, sector, z_score, classification,
trade_rec, entry_px, atr_14, stop_px, exit_time_ist, exit_px, exit_reason,
pnl_pct, notional_inr, pnl_net_inr`

`pipeline/data/research/phase_c/minute_replay_summary_<from>_<to>.json`

Per-year + full-period stats:
- `n_signals`
- `n_actionable` (LAG with non-null trade_rec)
- `n_traded` (after time-cutoff and de-dup per (ticker, day))
- `mean_pnl_bps_net`
- `hit_rate`
- `sharpe_252`
- `max_dd_bps`
- `kill_criteria_met` — `true` iff full-period mean < 100 bps OR
  win < 55% (informational; final verdict requires bootstrap + n thresholds
  per backtesting-specs §9)

## 5 / De-dup rule (matches live)

If multiple snapshots in the same day flag the SAME ticker, only the FIRST
trade_rec is taken. Subsequent flags are recorded as
`status=DUPLICATE_DAY_TICKER` and excluded from `n_traded`.

## 6 / Pre-registration status

This is a **research-only sanity check**, NOT a strategy launch. The Phase C
live signal is the strategy; this replay quantifies its expected lifetime
edge to inform the kill / continue / amend decision. Per Section 0 of
`docs/superpowers/specs/backtesting-specs.txt`, descriptive backtests are
permitted without registry entry. Output is treated as **evidence**, not as
**hypothesis test**.

## 7 / Build steps

1. ✅ EODHD 1m depth probed (Apr-2024 floor confirmed).
2. ⏳ Backfill 1m bars for top-30 × 2y → `pipeline/data/fno_intraday_1m/`.
   In flight as of 2026-05-01 00:13 IST (background `b0kg2h7x8`).
3. Read existing live profile from `reverse_regime_profile.json` for v0.
   For v1, compute fresh walk-forward profiles via
   `pipeline.research.phase_c_backtest.profile`.
4. Build `pipeline/research/phase_c_minute/replay.py` mirroring the live
   signal at minute resolution (filename uses `replay`, not `backtest`,
   to stay outside the strategy-gate regex — research-only).
5. Unit-test the replay logic (snapshot cadence, de-dup, ATR stop, etc.).
6. Run on 2024-04-01 → 2026-04-30 once backfill is complete.

## 8 / Decision matrix

| Replay output | Action |
|---|---|
| Mean ≥ 100 bps AND win ≥ 55% AND n ≥ 100 | KEEP Phase C live shadow. |
| Mean ≥ 100 bps AND win ≥ 55% AND n < 100 | Continue forward shadow until n ≥ 100; do not amend. |
| Mean < 100 bps OR win < 55% (n ≥ 200) | Engage memory `project_phase_c_kill_criteria` → archive Phase C, pivot to gap-fade / pair-trade overlays. |
| 100 ≤ n < 200 with kill criteria met | Defer kill decision until live shadow plus replay reach n ≥ 200; do NOT auto-archive. |

## 9 / Open questions

- Should the replay use the LIVE profile-as-of-date (live engine
  refits monthly via watchdog) or compute fresh walk-forward? **Decision:**
  fresh walk-forward for OOS purity. Live profile is fitted on data the
  live signal has already seen — using it would be circular.
- Do we cost-model NSE STT and exchange charges or only slippage?
  **Decision:** 5 bps round-trip total, same as Phase C live ledger.

---

**Next:** wait for 1m backfill to complete, then write
`pipeline/research/phase_c_minute/replay.py` per §7.4.
