# ETF v3 60-day Forward — Stocks Selected vs Production v2 (cadence=5)

**Generated:** 2026-04-26 19:30 IST
**Feature set:** CURATED-30
**Cadence:** 5 days (production weekly Saturday refit)
**Lookback:** 756 trading days
**Eval window:** 2025-12-01 → 2026-04-22 (95 v3-zone days, 27 actual replay trade-dates)
**Origin:** User asked "ideally we should have data set 2 months ago for ETF and then recalibrate all the way to the last 60 days of trading using the kite 1 minute data… the stock that we get in that run must be compared to the current in use v2 model… i suspect there will be none [differences]..lets still try."

## Setup

- v3 zones reconstructed per trading day from rolling-refit per-window weights (`etf_v3_rolling_refit_int5_lb756_curated_60d.json`)
- v3 zone thresholds calibrated from this run's own pooled signal distribution: center=4.88, band=8.58 (mean ± std)
  - Production reoptimizer thresholds (center=322, band=266) are mis-scaled for rolling-refit weight magnitudes; rolling refit produces signals ~30x smaller because seed-varied independent fits don't converge to the same weight scale as a single-fit reoptimizer
  - Self-calibration reproduces the production NEUTRAL frequency (~75-83%) which is the model's design intent
- Replay cohort: 696 ungated 4σ correlation breaks over 27 trade-dates (2026-03-12 → 2026-04-23), entries/exits already replayed via Kite minute bars (`intraday_break_replay_60d_v0.1_ungated.parquet`)
- v2 gate: `regime != NEUTRAL` (regime column = production v2's actual zone label at trigger time)
- v3 gate: `v3_zone != NEUTRAL` (reconstructed)

## Headline result

**v3 picks ~5% as often as v2, and v3 is a strict subset of v2 (zero v3-only picks).**

| Cohort | n trades | n dates | avg gross bps | cluster mean ± SE bps | hit rate |
|---|---|---|---|---|---|
| v2 pass | 627 | 22 | +33.2 | +7.9 ± 14.0 | 56.6% |
| v3 pass | 35 | 2 | +27.2 | +29.3 ± 6.6 | 71.4% |
| both pass | 35 | 2 | +27.2 | +29.3 ± 6.6 | 71.4% |
| v3-only | 0 | 0 | — | — | — |
| v2-only | 592 | 20 | +33.6 | +5.7 ± 15.4 | 55.7% |
| neither (both NEUTRAL) | 55 | 4 | -21.3 | -17.5 ± 15.2 | 47.3% |

## Three findings

### 1. v3 is much more conservative than v2 — by design

v3 fired non-NEUTRAL on 16/95 days (16.8%); v2 production fired non-NEUTRAL on 22/27 dates that had breaks (81.5%). On the 27 trade-dates in the replay window, v3's gate let through trades on **only 2 days** (2026-04-16 EUPHORIA, 2026-04-17 CAUTION) while v2 let through trades on 22 days.

v3's NEUTRAL-heavy posture matches its calibration intent (per memory: "NEUTRAL 75% of last 60 days"). On 23 of the 27 replay days, v3 said "stand down."

### 2. The user's "i suspect there will be none [differences]" prediction is half-right

There ARE differences in stocks selected — v3 picks 35 trades vs v2's 627. But every v3 pick is also a v2 pick (v3-only = 0). So the engines agree on direction, with v3 being a strict pruning of v2's selections.

This means swapping v2 → v3 in production would NOT add new trade ideas. It would only filter v2's existing ideas down by ~95%.

### 3. v3's 2-day "win" is too small to be statistically meaningful

On the 2 active days (2026-04-16, 2026-04-17), v3's 35 trades returned +29.3 bps cluster mean (71.4% hit rate). On the same days, v2's gate also let through the same 35 trades (subset relationship). v3 didn't pick differently on those days — v3 just chose to trade those days at all.

With n_clusters=2, the cluster-robust SE is essentially uninformative. The "+29 bps" result reflects favorable luck on 2 specific days, not credible alpha.

The cleaner read: v3 sat out 92.6% of the 27 days. v2 traded most of them at +5.7 bps cluster mean (~zero edge after costs). v3's approach (mostly NEUTRAL) avoided the modest-but-noisy cohort v2 routinely picks.

### 4. The "neither" cohort confirms both engines correctly skip dud days

55 trades on 4 dates where BOTH v2 and v3 said NEUTRAL: cluster mean −17.5 bps, hit rate 47.3%. Skipping these days was the right call.

## Direction asymmetry

| Cohort | LONG n | LONG bps | SHORT n | SHORT bps |
|---|---|---|---|---|
| v2 pass | 185 | -7.7 | 442 | +50.4 |
| v3 pass | 1 | +22.2 | 34 | +27.4 |
| v2 only | 184 | -7.8 | 408 | +52.3 |

Mechanical sigma-break SHORT trades carry the P&L (+50 bps avg gross under v2). LONG trades net negative across the board. This matches H-2026-04-26-001's design: 4σ overshoots fade better on the SHORT side because Indian retail crowd-buys positive sigma overshoots.

## Caveats

1. **Rolling-refit weights ≠ production weights.** The rolling refit fits independently at each anchor with seed=42+window_id; production fits once on the full 2-year eval window. Magnitudes differ by ~30x. Self-calibrated thresholds restore the NEUTRAL frequency but do NOT make the rolling-refit signal directly comparable to production v3.
2. **n_clusters_v3 = 2.** Any v3 P&L claim from this window is one good week away from being noise. Need 30+ trade-eligible days before drawing P&L conclusions on v3.
3. **Production v2 zone labels in the replay parquet ARE the ones production v2 emitted at trigger time** (not hindsight-fit per `regime_history.csv` contamination). Apples-to-apples on the v2 side.
4. **Sector-confirmation gate already applied to gated cohort.** This study compares the REGIME gate on top of an already-gated cohort. v2 production uses BOTH the sector gate (5.2 in spec) and a regime label; v3 candidate would replace the regime gate only.
5. **27 trade-dates < 60 days.** The "60d replay" parquet covers 27 distinct trading days due to ticker availability. The full forward shadow needed to discriminate v2 vs v3 on P&L grounds is ~60-90 trading days. Today's run is a directional signal, not a verdict.

## Operational implications

**v3 cutover risk profile:**
- Going hard-cutover to v3 would reduce trade frequency by ~95% in the H-001 mechanical engine
- The trades v3 KEEPS appear to be the better-quality subset (71% hit rate vs 57% for v2)
- BUT n=2 trade-eligible days is far too small to commit to this finding
- Sidecar parallel for 4-6 weeks is the conservative path

**The 5% trade frequency reduction matches the tradeoff design:** v3's NEUTRAL-heavy posture means more "stand down" days. The mechanical engine will fire less often but each firing should have a higher posterior probability of edge. This is consistent with v3's higher honest-OOS accuracy (53.55% vs v2's 47.17% per cycle-3 verdict).

## Files

- Headline result: `pipeline/data/research/etf_v3/60d_zone_pnl_int5.md`
- Full daily breakdown JSON: `pipeline/data/research/etf_v3/60d_zone_pnl_int5.json`
- Per-day v3 zones CSV: `pipeline/data/research/etf_v3/60d_zones_int5.csv`
- Rolling refit JSON (with weights): `pipeline/data/research/etf_v3/etf_v3_rolling_refit_int5_lb756_curated_60d.json`
- Comparison code: `pipeline/autoresearch/etf_v3_60d_zone_pnl.py`
- Cycle-3 verdict (foundation): `pipeline/data/research/etf_v3/2026-04-26-etf-v3-verdict.md`
- Cadence sweep verdict (cadence=5 production lock): `pipeline/data/research/etf_v3/2026-04-26-cadence-sweep-verdict.md`

## Open threads

- cadence=1 (daily refit) 60-day comparison still running; appended on completion
- v2-faithful cadence=5 honest comparison run not yet executed (would replace `parquet.regime` with v2-faithful's reconstructed zone — needed if we suspect production v2's regime labels are not what an honest v2 would emit)
- 30+ day forward shadow on v3-curated CURATED-30 is the right next step before any production cutover commitment
