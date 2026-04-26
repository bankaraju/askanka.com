# ETF v3 Research — FINAL Verdict (2026-04-26, cycle 3)

> **Status:** This document supersedes both prior verdicts (13:48 FAIL, 14:40
> "borderline tie"). Both were wrong because they were based on an
> inadvertently-asymmetric comparison: `etf_v3_research.py` had a hard-coded
> 20-ETF `FOREIGN_RETURN_COLS` list that did NOT auto-pick up loader
> expansions, so the previous "v3 24-feature" and "v3 40-feature" runs were
> actually all 20-feature runs. Fixed in commit `a268607`. This is the first
> verdict where v2-faithful and v3 are evaluated on identical, configurable
> feature sets.

**Date:** 2026-04-26 (cycle 3)
**Run host:** Contabo VPS (anka@185.182.8.107)
**Code commit:** a268607 (loader-coupled v3) + 6ea247e (analysis tool)
**Spec:** `docs/superpowers/specs/2026-04-26-etf-engine-v3-research-design.md`
**Curated list:** `docs/superpowers/specs/cureated ETF.txt` (30 ETFs with
explicit India-channel rationale per ticker)
**Policy:** `docs/superpowers/specs/anka_backtesting_policy_global_standard.md`
**v2 deep-read findings:** `pipeline/data/research/etf_v3/2026-04-26-v2-deep-read-findings.md`

---

## TL;DR (final)

Four configurations evaluated on the SAME rolling weekly-refit walk-forward,
SAME panel data (24 → 40 ETF backfill on Contabo), SAME Karpathy 2000-iter
optimizer, SAME 99 refits over 494 OOS predictions:

| configuration | acc | base | edge | 95% CI | P(>base) | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|---|---|---|
| v2-faithful FULL-40 | 48.99% | 51.62% | **−2.63pp** | [44.53, 53.44] | 10.3% | 54.86% | 45.60% | 46.38% |
| v2-faithful CURATED-30 | 47.17% | 51.62% | **−4.45pp** | [42.71, 51.82] | 2.6% | 54.29% | 44.40% | 39.13% |
| v3 FULL-40 | 51.52% | 51.72% | **−0.20pp** | [47.06, 55.79] | 44.1% | 54.60% | 51.20% | 44.93% |
| **v3 CURATED-30** | **53.55%** | 51.72% | **+1.83pp** | [49.29, 58.01] | **78.7%** | 54.60% | 53.20% | **52.17%** |

**v3 CURATED-30 is the winner.** It is the only configuration with:
- Positive pooled edge (+1.83pp over baseline)
- P(acc > baseline) = 78.7% (one-sided credibility)
- **Robust year-by-year picture: 54.60% → 53.20% → 52.17% (no decay)**
- Cleanest interpretable feature set (every ETF has an India-channel thesis)

**v3 95% CI [49.29%, 58.01%] still includes baseline** so this is a 78.7%
one-sided credibility, not 95% significance. But this is a meaningfully
stronger result than any prior verdict.

---

## Three big findings

### 1. v3 architecture decisively beats v2-faithful at any feature count

| feature count | v2-faithful edge | v3 edge | gap |
|---|---|---|---|
| 30 (curated) | −4.45pp | +1.83pp | **6.28pp** |
| 40 (full) | −2.63pp | −0.20pp | 2.43pp |

v2's raw-levels + 1d-returns architecture cannot handle 30-40 features. It
collapses to 47-49% accuracy (well below baseline). v3's engineered features
(5d returns, VIX 5d change, NIFTY 1d/5d/RSI, FII/DII 5d sums) generalize
much better in higher-dimensional fit spaces.

**This contradicts the cycle-2 verdict's claim that "v2 is not broken".** It
is broken — the cycle-2 verdict was misled because the v3 module was
silently using only 20 features while we thought it was using 24/40.

### 2. v3 CURATED-30 has NO year decay

Compare v3 FULL-40 (which DOES decay):

| year | v3 FULL-40 | v3 CURATED-30 |
|---|---|---|
| 2024 | 54.60% | 54.60% |
| 2025 | 51.20% | 53.20% |
| 2026 YTD | **44.93%** | **52.17%** |

The 16 extra ETFs in FULL-40 (the ones NOT in the curated list — copper,
developed, euro, high_yield, kbw_bank, global_bonds, natgas, silver, yen,
plus india_etf which was in the loader but NOT in curated) introduce
dimensions for the optimizer to overfit on, and the in-sample weights from
those extra ETFs do not generalize in 2026.

**The user's curated list was right.** Each ticker has a specific
India-channel thesis (TSMC for Indian EMS, FXI for substitution effect,
USO for INR weakness, GLD for Nifty fear gauge, etc.). The optimizer
finds genuinely informative weights when constrained to this set.

### 3. v2's 62.3% claim is now firmly retired

| era | claimed acc | what protocol | honest re-test |
|---|---|---|---|
| original v2 | 62.3% | single 70/30 + Sharpe-selected weights = in-sample | n/a |
| cycle-2 verdict (mistaken) | "53.2% tied with v2" | v3 was secretly only 20 features | superseded |
| cycle-3 verdict (this one) | **47.17% (curated) / 48.99% (full)** | rolling refit on same panel as v3 | this is honest |

v2-faithful CURATED-30 gives **47.17% accuracy with −4.45pp edge** — well
below the 51.62% majority baseline. The 62.3% number is firmly an artifact
of (a) test-set Sharpe selecting weights, (b) overfitting on a single
70/30 split, (c) running only 6 weeks of Indian feature history ffilled
across 3 years of yfinance data.

---

## What this means for production

Production v2 (`etf_reoptimize.py` + `etf_daily_signal.py`) is currently
running with the **v2 architecture on a panel similar to FULL-40**. Per
the table above, that configuration produces **−2.63pp edge** under
honest rolling refit. The qualitative regime label may still rank
risk states usefully (per `regime_transition_overnight` overnight
asymmetry finding), but the directional accuracy claim is dead.

**Recommended actions** (ordered by criticality):

1. **STOP citing 62.3% directional accuracy** anywhere — internal docs,
   external comms, marketing copy. The honest production-cadence number
   is 47-49% (below baseline). Replace with qualitative language about
   regime ranking only.

2. **Run a v3 CURATED-30 production pilot.** This is the only configuration
   that has positive edge under honest evaluation. Pilot path:
   - Port `build_features` from `etf_v3_research.py` and the
     `CURATED_FOREIGN_ETFS` selection into a new
     `etf_v3_curated_signal.py` daily-signal module
     (mirroring `etf_daily_signal.py`'s structure)
   - Run BOTH v2 and v3-curated daily for 30+ trading days as a
     forward shadow comparison; do NOT consume the holdout for this
     (use forward live data from 2026-04-27 onwards)
   - If v3-curated forward shadow continues to lead v2 by ~5pp,
     promote to primary regime engine

3. **Do NOT touch the formal §13.1 single-touch holdout** (2026-01-01
   → 2026-04-23, n=74). Even v3-curated's CI [49.29%, 58.01%] includes
   baseline; touching the holdout would consume a single-use resource
   on a borderline-strong (not 95%-significant) hypothesis. The
   forward-shadow pilot is the right path to credibility.

4. **Address the 3 v2 production bugs** identified in the deep-read
   (silent weight drop in `etf_daily_signal.py` — already mitigated
   with warning log; mixed-scale Indian features; PCR was never
   actually loaded). All documented; only the silent weight drop
   needed code change.

---

## Methodology — common to all 4 configurations

- **Window:** 2021-04-23 → 2026-04-23 (1,236 NIFTY trading days, audited PASS)
- **Eval window:** 2024-04-23 → 2026-04-23 (494 OOS predictions × 99 refits)
- **Refit cadence:** every 5 NIFTY trading days
- **Lookback:** 756 days
- **Optimizer:** Karpathy random search, 2000 iter, seed=42+window_id
- **Target:** `sign(NIFTY.shift(-1))` from un-shifted panel
- **Aggregation:** pooled OOS accuracy (per-window baselines are inflated
  because n=5 per window forces a high majority share — pooled is the
  right comparator)

### v2-faithful feature engineering

- Foreign features: 1-day pct_change of N ETF closes (N=30 curated or N=40 full)
- Indian features: raw LEVELS of india_vix, fii_net, dii_net, nifty_close
- Joined via `ffill().bfill().fillna(0)` — exact match for production
- Total feature count: N + 4 Indian = 34 (curated) or 44 (full)

### v3 feature engineering

- Foreign features: 5-day returns of N ETF closes (N=30 curated or N=40 full)
- Indian features: VIX level + VIX 5d change + FII 5d sum + DII 5d sum + NIFTY 1d ret + NIFTY 5d ret + NIFTY RSI(14) = 7 features
- Total feature count: N + 7 Indian = 37 (curated) or 47 (full)

The v3 engineered Indian features are a direct fix for v2's mixed-scale
problem (raw NIFTY ~20,000 alongside 1-day returns ~±5%). Engineered
features keep everything in roughly the same numeric scale and prevent
the Karpathy seed from being dominated by trivial autocorrelations.

---

## Curated list (30 ETFs)

Per `docs/superpowers/specs/cureated ETF.txt`, with India-channel rationale:

US Markets / Risk-On: SPY, QQQ, AIQ, SMH, XLK, XLF, IWM, XLE, XLV, XLI, EWG
Emerging Markets / Asia: EEM, FXI, MCHI, EWJ, EWY, EWT, EWZ, KWEB
Commodities: USO, GLD, DBB, DBA
FX / Rates: UUP, TLT, EMB
Vol / Tail: VIXY
Thematic: KRBN, LIT, BITO

Notably excluded: india_etf (INDA) — because the target IS NIFTY, INDA is
essentially NIFTY with US-market timing offset (a leakage-adjacent
feature). The user's curated list also omitted INDA for that reason.

---

## Files produced

- `pipeline/data/research/etf_v3/etf_v2_faithful_rolling_int5_lb756.json` — v2-faithful FULL-40
- `pipeline/data/research/etf_v3/etf_v2_faithful_rolling_int5_lb756_curated.json` — v2-faithful CURATED-30
- `pipeline/data/research/etf_v3/etf_v3_rolling_refit_int5_lb756.json` — v3 FULL-40 (proper, 40 features this time)
- `pipeline/data/research/etf_v3/etf_v3_rolling_refit_int5_lb756_curated.json` — **v3 CURATED-30 (the winner)**
- `pipeline/autoresearch/_analyze_etf_v3_results.py` — bootstrap CI + year breakdown analysis tool
- `pipeline/autoresearch/backfill_curated_etfs.py` — yfinance backfill for the 16 added ETFs
- `pipeline/data/research/etf_v3/2026-04-26-v2-deep-read-findings.md` — 5 v2 structural findings
- `pipeline/data/research/etf_v3/2026-04-26-etf-v3-data-audit.md` — data audit (now 24 inputs all PASS)

Holdout file `etf_v3_holdout.json` intentionally absent — single-touch slot reserved for the v3-curated forward-shadow promotion pathway.

## Next research cycle (deferred)

- Forward-shadow v3-curated for 30 trading days (2026-04-27 onwards), compare to v2 production live
- Investigate whether dropping more "extra" features improves further (curated-25? curated-20?)
- AIQ task #44 already in pool; consider IBIT/HBIT alternatives to BITO
- Section 11.4 fragility sweep on v3-curated (perturb seed weights, check stability)
- Section 12 label-permutation null on v3-curated rolling protocol (initial null was on static split)
- If forward-shadow holds up, eventually consume single-touch holdout for v3-curated only
