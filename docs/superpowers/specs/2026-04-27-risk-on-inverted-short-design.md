# H-2026-04-27 — RISK-ON inverted SHORT (v3-CURATED regime)

**Status:** PRE_REGISTERED
**Registered:** 2026-04-27 (same day as Phase 2 Test 1c diagnostic)
**Single-touch holdout window:** 2026-04-27 → 2026-12-31 (long enough to accumulate n ≥ 10 OOS RISK-ON days at the ~5.5% in-sample base rate)
**Sister hypotheses:** H-2026-04-27-001 (INTRADAY SHORT), H-2026-04-27-002 (C2C SHORT) — same signal stream, two execution variants

---

## 1 — Background and motivation

The Phase 2 Test 1 evaluator (commit `43afb37`) established that the v3-CURATED
ETF regime engine, run as a 5-zone classifier (EUPHORIA / RISK-ON / NEUTRAL /
CAUTION / RISK-OFF) with the production 2-day hysteresis rule, produces
**directionally-correct outcomes for 4 of 5 zones** but **anti-predictive
outcomes for RISK-ON**:

| Zone | n | mean NIFTY next-day pp | pct down |
|---|---:|---:|---:|
| EUPHORIA | 5 | +0.18 | 60% |
| **RISK-ON** | **27** | **-0.22** | **70.4%** |
| NEUTRAL | 412 | +0.05 | 45.9% |
| CAUTION | 29 | -0.06 | 51.7% |
| RISK-OFF | 19 | -0.13 | 57.9% |

The Test 1c gap-and-fade diagnostic (commit `f9d7963`) decomposed RISK-ON
outcomes into gap, intraday, and close-to-close legs:

| Leg | mean pp | median | adverse share |
|---|---:|---:|---:|
| Gap (close[T] → open[T+1]) | -0.076 | +0.008 | 51.9% positive |
| Intraday (open → close on T+1) | -0.140 | -0.157 | 63.0% negative |
| C2C (close[T] → close[T+1]) | -0.217 | -0.150 | 70.4% negative |

Trimmed analysis (drop 3 best + 3 worst c2c, n = 21): mean -0.21pp,
**76.2% pct_down** — the inversion is structural, not driven by a few
big-down events.

**Mechanism:** the Indian market grinds lower *during the trading session*
on RISK-ON-labelled days. There is no overnight optimism gap to arbitrage
away (median gap ≈ 0). This is intraday-fade after a flat overnight gap,
not classical gap-and-fade.

**Hypothesis:** the model's regime label is empirically miscalibrated —
"RISK-ON" by the v3-CURATED signal corresponds to a session in which
Indian equities are systematically weak. **Inverting the trade direction
turns RISK-ON from a -0.22 pp drag into a +0.22 pp/trade SHORT signal.**

n = 27 in-sample is too small to commit to the inversion; the hypothesis
is pre-registered for OOS forward-shadow confirmation per the
single-touch discipline (`backtesting-specs.txt §10.4`).

## 2 — Locked decisions (no parameter changes during holdout)

### 2.1 Signal source
- **Engine:** `pipeline.autoresearch.etf_v3_curated_signal.compute_daily_signal`
  (production v3-CURATED daily refit + zone classifier).
- **Zone of interest:** RISK-ON only.
- **Hysteresis:** the production 2-day hysteresis rule applies. Official RISK-ON
  is declared on the second consecutive trading session in raw RISK-ON.
- **Decision time:** at the close of decision day T (i.e., once today's zone
  is locked at end-of-day).

### 2.2 H-2026-04-27-001 — INTRADAY SHORT
- **Entry:** Sell NIFTY at the open of T+1 (09:15 IST market open).
- **Exit:** Buy back at the close of T+1 (15:30 IST close).
- **No stops, no trail, no intraday triggers.** Mechanical open-to-close short.
- **In-sample evidence:** mean +0.140 pp / trade, win rate 63.0%, n = 27.

### 2.3 H-2026-04-27-002 — C2C SHORT
- **Entry:** Sell NIFTY at the close of decision day T.
- **Exit:** Buy back at the close of T+1.
- **Captures the slight gap-down leg too,** at the cost of overnight risk.
- **In-sample evidence:** mean +0.217 pp / trade, win rate 70.4%, n = 27.

### 2.4 Instrument
- **NIFTY index** (cash market for accounting; live execution would use
  NIFTY index futures — H-2026-04-27-001 same-day NRML, H-2026-04-27-002 NRML
  carry overnight).
- Slippage assumption (per Backtest-Spec §1-§3): 0.05% per side, 0.10% round-trip.

### 2.5 Decision filter
- Only consider days where `official_zone == "RISK-ON"` per the
  v3-CURATED daily classifier with 2-day hysteresis applied.
- No additional gates (no PCR, no sector overlay, no marker stack).
  This is the bare-bones inversion test.

## 3 — Holdout claim (single-touch)

**Window:** 2026-04-27 → 2026-12-31 (~ 170 trading days; expected ~ 9 OOS
RISK-ON days at the 5.5% in-sample base rate; window auto-extends to
2027-04-27 if n < 10 by year-end).

**Verdict gate (per variant, computed at end of holdout):**

| Verdict | Conditions |
|---|---|
| **PASS** | n ≥ 10 RISK-ON days AND net-of-slippage mean ≥ +0.15 pp/trade AND win rate ≥ 60% AND one-sided binomial p-value ≤ 0.05 |
| **FAIL** | n ≥ 10 days AND any condition above missed |
| **DEFERRED** | n < 10 days at 2027-04-27; window closes, single-touch consumed, hypothesis archived as "insufficient sample" |

**On PASS:** ratify the inversion. Modify v3 production to invert the
RISK-ON trade direction. Continue to forward-monitor — first 60 days of
live trading must maintain mean ≥ 0 to avoid disablement.

**On FAIL:** retire the inversion permanently. Continue treating RISK-ON
as "no trade" in the v3 pipeline. The model's edge comes from EUPHORIA /
NEUTRAL-sector / CAUTION / RISK-OFF only.

**On DEFERRED:** archive without verdict; can re-test only with a fresh
hypothesis ID (no parameter re-tuning permitted — different evidence
window required to avoid double-dipping).

## 4 — In-sample evidence locked

Source: `pipeline/data/research/etf_v3_evaluation/phase_2_backtest/runs_smoke/wf_lb756_u126_seed0/`

- `test_1_raw_zones.csv` — daily zone labels with hysteresis applied
- `test_1c_gap_fade_per_day.csv` — per-event gap / intraday / c2c decomposition
- `test_1c_gap_fade_summary.csv` — per-zone aggregate stats

Smoke run: 99 weekly refits, 493 OOS predictions, lookback 756d, n_iter 100,
seed 0. Eval window 2024-04-23 → 2026-04-23. Code commit: `c93488b` (run),
diagnostic commits `43afb37` (alignment fix) and `f9d7963` (gap-fade
decomposition). 27 RISK-ON official days fall in 11 distinct runs spanning
2024-05-28 → 2026-04-10.

## 5 — Negative-control diagnostics (in-sample)

Three sanity checks that ruled out alternative explanations for the
inversion:

| Check | Result | Conclusion |
|---|---|---|
| Date-alignment bug | Confirmed and fixed (commit `43afb37`); RISK-ON pct_down moved 81.5% → 70.4% after fix, 4 of 5 other zones moved to directionally-correct sign | Bug accounts for some inversion magnitude but residual remains |
| Hysteresis lag direction | Code traces verified: official zone flips ON the 2nd consecutive raw day, not 2 days later. 31 unit tests pass | Not the cause |
| Per-window weight sign convention | VIXY consistently negative (correct), dollar mostly negative (correct), SP500/industrials mostly positive (correct), treasury slightly positive at 1e-3 magnitude (small mis-orientation, too small to drive 70% inversion) | Not the cause |
| RISK-ON cluster contamination | 27 days span 11 distinct runs over 2024-05 to 2026-04; 8/11 runs have 0% pct_up; trimmed analysis (drop 3 best + 3 worst) shows pct_down RISES to 76.2% | Inversion is structural, not concentrated |

## 6 — What this hypothesis is NOT

- **Not a regime-engine fix.** The v3-CURATED model is left UNCHANGED. Only
  the trade direction *applied to* the RISK-ON label is inverted.
- **Not a sector strategy.** Trades NIFTY index, not sector indices or
  individual stocks. Sector-level decomposition of NEUTRAL days is a
  separate work-stream (Task #107).
- **Not a marker overlay.** Does NOT use ZCROSS, sector_overlay,
  coef_delta_marker, or any other marker. Bare-bones inversion only.
- **Not a multi-zone modification.** The other 4 zones keep their
  hypothesised directions (EUPHORIA fade, CAUTION/RISK-OFF short,
  NEUTRAL no trade per regime, sector-overlaid only).

## 7 — Reasonable failure modes

If the holdout shows OOS RISK-ON behaving like a 50/50 coin flip (p > 0.20),
the in-sample inversion was a sampling artifact and should not be acted on.

If the holdout shows OOS RISK-ON behaving as the *original* +1 hypothesis
(majority up days), the in-sample inversion was driven by transient regime
characteristics (e.g., the 2024-2025 RBI rate-cut cycle and Indian-specific
flow conditions) that have since shifted.

Either failure case retires the inversion permanently. The conservative
"skip RISK-ON" policy stays in force.

## 8 — Operational notes

- This spec ships with the registry entry in the same commit (per CLAUDE.md
  hypothesis-registration discipline).
- No new `*_strategy.py` / `*_engine.py` file is created today; this is a
  pre-registration without code. Live shadow execution requires a separate
  module + a separate commit gated by the registry kill switch hook.
- The v3-CURATED daily classifier (`etf_v3_curated_signal.py`) and its
  weights file (`etf_v3_curated_optimal_weights.json`) are FROZEN at the
  state in commit `c93488b` for the duration of the holdout. Any reoptimize
  during the holdout creates a new hypothesis ID; the original
  H-2026-04-27-001/002 verdict remains tied to the frozen weights.
