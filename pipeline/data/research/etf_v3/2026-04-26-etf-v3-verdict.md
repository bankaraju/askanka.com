# ETF v3 Research — REVISED Verdict (2026-04-26)

> **Status:** This document supersedes the initial v3 FAIL verdict written at 13:48 UTC.
> The first verdict was based on a 5-fold static walk-forward of v3 only, and on a
> v2-faithful test that **omitted natgas, silver, tech, and yen** (4 features that
> are weighted in production `etf_optimal_weights.json`, including natgas −8.21 and
> silver −3.26 — the 2nd and 3rd largest weights). That made the comparison
> structurally unfair to v2.
>
> This revised verdict uses (a) **rolling weekly refits** that mirror production
> cadence, and (b) the **complete 24-feature** set on both v2-faithful and v3.

**Date:** 2026-04-26
**Run host:** Contabo VPS (anka@185.182.8.107)
**Code commit:** 6b8dc5f
**Spec:** `docs/superpowers/specs/2026-04-26-etf-engine-v3-research-design.md`
**Policy:** `docs/superpowers/specs/anka_backtesting_policy_global_standard.md`
**Data audit:** `pipeline/data/research/etf_v3/2026-04-26-etf-v3-data-audit.md`
**v2 deep-read findings:** `pipeline/data/research/etf_v3/2026-04-26-v2-deep-read-findings.md`

---

## TL;DR (revised)

After a deep re-read of v2 (5 structural findings documented separately) and a
fair head-to-head with both architectures running the **same rolling-refit
walk-forward on the same 24-feature panel**:

| arch | OOS n | acc | baseline | edge_pp | bootstrap 95% CI on acc | P(acc > base) | windows pos / total |
|---|---|---|---|---|---|---|---|
| **v2-faithful** (1d returns + raw Indian levels) | 494 | **53.24%** | 51.62% | **+1.62** | [48.79%, 57.69%] | 74.1% | 11 / 99 |
| **v3** (5d returns + engineered Indian features) | 493 | **53.35%** | 51.72% | **+1.62** | [48.88%, 57.81%] | 76.5% | 7 / 99 |

**Both architectures match within bootstrap noise.** Both show a positive
point-estimate edge of 1.62pp. **Neither is statistically significant at 95%**
(both bootstrap CIs include the majority-class baseline). A one-sided binomial
read gives ~75% credibility — meaningful but not conclusive.

**The user's intuition is partially vindicated:**
- v2's production architecture is **NOT broken** under rolling weekly refit.
- The original v2 claim of 62.3% accuracy was an artifact of fitting a single
  70/30 split with the test set itself selected by Sharpe — an in-sample
  optimization. The honest production-cadence number is ~53.2%.
- v3's engineered features (5d returns, VIX 5d change, NIFTY RSI) **add no edge
  over v2's raw 1-day-returns + level features**. The two architectures finish
  in a statistical tie.

**The real concern is year-on-year decay**, not architecture choice:

| year | v2-faithful acc | v3 acc | n_pred |
|---|---|---|---|
| 2024 | 56.00% | **58.05%** | 174-175 |
| 2025 | 51.60% | 51.60% | 250 |
| 2026 (YTD) | 52.17% | 47.83% | 69 |

Edge that was clearly present in 2024 (~+5pp over a ~51.6% pooled base) has
collapsed by 2026. v3 is actually **worse** than v2-faithful in 2026 YTD.

---

## What changed since the initial verdict

The initial 13:48 UTC verdict was wrong on two specific counts:

### Mistake 1 — v3 was not a fair v2 re-test

v3 used 5d returns; v2 production uses 1d returns. v3 used engineered VIX/NIFTY
features; v2 uses raw levels joined to returns. v3 used 5y of historical Indian
features; v2 uses ~6 weeks (ffilled). I declared v2 "broken" based on v3's
walk-forward FAIL when v3 was a **different model in a different design space**.
The user pushed back: *"you have to read v2 in depth, deep enough to refute"*.
The deep read produced 5 findings (`2026-04-26-v2-deep-read-findings.md`).

### Mistake 2 — the v2-faithful replicator omitted critical features

The first v2-faithful run used 20 foreign ETFs but missed **tech, natgas,
silver, and yen** — features that ARE in production's `GLOBAL_ETFS` dict and
carry meaningful weight (`natgas = −8.21`, `silver = −3.26` in current
`etf_optimal_weights.json`). That run produced 51.42% accuracy / **−0.20pp
edge**, which I read as "v2 has zero edge". With the 4 features added back, the
same architecture produces **53.24% / +1.62pp** — the +1.82pp jump is the
contribution those features were making in production all along.

This was a **data-faithfulness failure** in my replicator, not a finding about
the v2 architecture. Cleanup commit: `6b8dc5f`.

---

## Methodology — the corrected protocol

### Common to both architectures

- **Window:** 2021-04-23 → 2026-04-23 (1,236 NIFTY trading days, audited PASS)
- **Eval window:** 2024-04-23 → 2026-04-23 (494 trading days OOS)
- **Refit cadence:** every 5 NIFTY trading days (weekly, matches production)
- **Lookback:** 756 days (3 years, matches production v2)
- **Optimizer:** Karpathy random search, 2000 iterations, seed=42+window_id
- **Target:** `sign(NIFTY.shift(-1))` — same as v2 production
- **Per refit:** fit on prior 756d, predict next 5d, append to OOS pool
- **Aggregation:** pooled OOS accuracy (the per-window baselines shown in some
  detail JSONs are inflated because n=5 per window forces a high majority share;
  the **pooled overall baseline** is the right comparator)

### v2-faithful (production architecture)

- **Foreign features (24):** 1-day pct_change of `sp500, treasury, dollar, gold,
  crude_oil, copper, brazil, china_etf, korea_etf, japan_etf, developed, em,
  euro, high_yield, financials, industrials, kbw_bank, agriculture, global_bonds,
  india_etf, tech, natgas, silver, yen`
- **Indian features (4):** raw levels of `india_vix, fii_net, dii_net,
  nifty_close`
- **Joined via** `ffill().bfill().fillna(0)` — exact match for production
  `etf_reoptimize.py` line 316
- **T-1 anchored** in this run (production v2 isn't explicit about T-1 but the
  yfinance source IS T-1 by construction, so this matches in spirit)

### v3 (engineered architecture)

- **Foreign features (24):** 5-day returns of the same 24 ETF closes
  (`(close / close.shift(5) - 1) * 100`)
- **Indian features (5):** VIX level + VIX 5d change, FII 5d sum, DII 5d sum,
  NIFTY 1d return + 5d return + 14d RSI
- **T-1 anchored** by canonical loader

---

## Gate-by-gate results (rolling-refit protocol)

### §11.1 Sample adequacy

- v2-faithful: 99 refits, 494 OOS predictions ✓
- v3: 99 refits, 493 OOS predictions ✓
- **VERDICT: PASS**

### §13.2 Walk-forward (rolling weekly refit, 99 windows each)

| | v2-faithful | v3 |
|---|---|---|
| pooled accuracy | 53.24% | 53.35% |
| pooled baseline | 51.62% | 51.72% |
| pooled edge | **+1.62pp** | **+1.62pp** |
| windows positive (per-window comparison)* | 11 / 99 | 7 / 99 |
| 2024 acc | 56.00% | **58.05%** |
| 2025 acc | 51.60% | 51.60% |
| 2026 acc | **52.17%** | 47.83% |

*per-window edge counts are noisy because a 5-day window has a 60% baseline by
mechanical accident if 3 out of 5 days are up. Don't read these as "the
architecture only worked 11% of the time" — read the pooled metric.

**VERDICT: BORDERLINE.** Both architectures show positive pooled edge but it is
not statistically significant by binomial bootstrap (CIs include baseline).

### §11.3 Bootstrap CI on pooled accuracy

- **v2-faithful:** point 53.24%, 95% CI [48.79%, 57.69%], n=494
- **v3:** point 53.35%, 95% CI [48.88%, 57.81%], n=493
- Both CIs **include** the respective baselines (51.62% / 51.72%)
- **VERDICT: not statistically significant at 95% confidence**
- One-sided P(acc > baseline) is 74.1% (v2-faithful) and 76.5% (v3) — the
  evidence leans toward edge but doesn't clear the 95% bar

### §11.4 Parameter-neighborhood fragility (v3 only, from initial run)

- Base test acc 56.63%; perturbed [55.93%, 56.89%]; max drop 0.70pp
- **VERDICT: STABLE** under noise=0.10 multiplicative perturbation of seed weights

### §12 Label-permutation null (v3 only, from initial run)

- Real test acc (single 70/30 split): 50.58%
- Null mean 50.62%, std 1.42%, p95 52.91%
- one-sided p-value **0.770**
- **VERDICT: not distinguishable from random** under the static-split protocol;
  this run was on the v3 features only and would benefit from a re-run on the
  rolling-refit protocol with both architectures, but is consistent with the
  bootstrap-CI finding above

### §13.1 Single-touch holdout (2026-01-01 → 2026-04-23, n=74)

- **NOT CONSUMED.** Per policy §10.4, the holdout is reserved for a hypothesis
  the in-sample evidence credibly supports. Neither architecture clears 95%
  significance — touching the holdout would burn a single-use resource on a
  borderline case.
- File `etf_v3_holdout.json` does not exist. Slot remains reserved.

---

## What this means for production v2

Production v2 (`pipeline/autoresearch/etf_reoptimize.py` + `etf_daily_signal.py`)
is **not broken**. Specifically:

1. **The architecture is fine.** v2's 1-day-returns + raw-levels feature space,
   joined with `ffill().bfill().fillna(0)` and Karpathy-fit on a 70/30 split,
   produces the same +1.62pp edge under rolling weekly refit as v3's
   engineered alternative. The engineering effort in v3 added no edge.

2. **The 62.3% claim was inflated.** It came from a single 70/30 split where the
   test-set Sharpe was the selection criterion (i.e. test set was used to pick
   weights, so it was effectively in-sample). Under proper rolling refit, the
   honest number is **~53.2%** with a 95% CI of [48.79%, 57.69%].

3. **Three structural bugs identified** in v2 production code (deep-read findings):
   - **Silent weight drop** in `etf_daily_signal.py` — Indian feature weights
     stored in `etf_optimal_weights.json` are silently zeroed at decision time
     because `_fetch_latest_returns` only iterates `GLOBAL_ETFS` keys. Currently
     0.1% of weight mass is dropped, but will grow if a future Saturday refit
     puts more weight on Indian features. **Mitigation committed today**: warning
     log when stored weights contain unfetchable keys.
   - **Mixed-scale fitting** in optimizer — Indian features are joined as raw
     levels (NIFTY ~20,000, FII flows ~±5,000) to ETF returns (~±5%) without
     standardization. Karpathy fit handles this by driving large-scale weights
     tiny (NIFTY weight is ~1e-4 in current `etf_optimal_weights.json`), but
     the structure is fragile.
   - **PCR was never an optimizer feature.** The docstring on `load_indian_data`
     claimed PCR was loaded; in reality `positioning.json` is per-stock with no
     market-level PCR field, and the historical builder `_build_indian_features`
     never extracted PCR. The user's question "would PCR help v3" is unanswerable
     from current data — there is no historical PCR time series. Building one
     would require a 5-year backfill from a different source.

4. **Year-on-year decay is the most concerning signal.** Both architectures hit
   ~56-58% in 2024 and have decayed to 47-52% in 2026. This isn't an
   architecture problem — it's an information-decay problem (or: 2024 was an
   easy regime year). If decay continues, the +1.62pp full-window edge is
   already mostly historical.

---

## What this means for v3

v3 is not a clear winner over v2. Specifically:

- v3's pooled edge (+1.62pp) matches v2-faithful's pooled edge (+1.62pp) within
  rounding noise. v3 is nominally 0.11pp better at the point estimate.
- v3 generalizes slightly better in 2024 (58.05% vs 56.00%) but underperforms
  v2-faithful in 2026 YTD (47.83% vs 52.17%).
- v3 has a slightly tighter train-test gap (engineered features carry less raw
  noise) but the edge isn't bigger.
- **v3's holdout slot remains reserved.** Touching it now would consume a
  single-use resource on a borderline case.

**Recommendation:** do NOT ship v3 as a replacement for v2 today. The two
architectures are statistically indistinguishable. v3's engineering-cleanliness
benefits (T-1 anchor, better Indian feature scaling, larger Indian history) are
real but not edge-producing.

---

## Future feature candidates (deferred, not in this verdict)

User flagged 2026-04-26 — to investigate in the next research cycle:

- **AIQ** (Global X AI & Tech ETF) — adds pure-play AI/software exposure that's
  distinct from `tech` (XLK = mega-cap tech, dominated by AAPL/MSFT/NVDA). Thesis:
  AI/software has different beta profile from broad US tech and may capture the
  AI-capex/software-margin trade-off. **Action:** backfill 2018-04 → present,
  add to FOREIGN_ETFS, re-run.
- **FXI** — already in via `china_etf` (parquet matches FXI price exactly).
  Currently zero-weighted in `etf_optimal_weights.json` because Karpathy didn't
  find signal. Will be re-evaluated on each refit.
- **PCR** — the user's question "would PCR help" is structurally unanswerable
  from current data. To honestly test: build a 5-year market-level PCR time
  series from NSE bhavcopy historical archives (separate research task).

---

## What I owe the user — followup items

1. **Documentation hygiene** — completed in this commit cycle:
   - `etf_reoptimize.py` docstrings now honest about `load_indian_data` having
     no callers and PCR/RSI/breadth fields being typically null
   - `etf_daily_signal.py` warns when stored weights are silently dropped
   - `SYSTEM_OPERATIONS_MANUAL.md` updated to reflect that the 62.3% claim is
     superseded by rolling-refit ~53.2%
2. **No production change.** Production v2 keeps running. The marketing claim
   "62.3% directional accuracy" should be replaced with "53.2% directional
   accuracy under rolling weekly refit (95% CI [48.8%, 57.7%], not significant
   at 95%, +1.6pp edge over majority-class baseline)" if the engine's accuracy
   is referenced externally.
3. **AIQ task** registered as task #44 for the next cycle.
4. **Holdout NOT consumed.** Slot reserved for a materially different model
   (e.g. classifier-framed v4 or regime-switching).
5. **Year-decay investigation** is the most actionable open thread. If 2024 was
   a regime where ETF momentum was clearly informative for next-day NIFTY, and
   2025-2026 is not, that's a structural change worth understanding before
   trusting any quantitative-accuracy claim from this engine.

---

## Files produced

- `pipeline/data/research/etf_v3/etf_v2_faithful_rolling_int5_lb756.json` — v2-faithful 24-feature rolling-refit result
- `pipeline/data/research/etf_v3/etf_v3_rolling_refit_int5_lb756.json` — v3 24-feature rolling-refit result
- `pipeline/data/research/etf_v3/etf_v3_fit.json` — initial v3 in-sample fit (deprecated; superseded by rolling)
- `pipeline/data/research/etf_v3/etf_v3_walkforward.json` — initial v3 5-fold static (deprecated; rolling is the right protocol)
- `pipeline/data/research/etf_v3/etf_v3_null.json` — label-permutation null (v3 features, static split)
- `pipeline/data/research/etf_v3/etf_v3_neighborhood.json` — fragility sweep
- `pipeline/data/research/etf_v3/2026-04-26-etf-v3-data-audit.md` — data audit
- `pipeline/data/research/etf_v3/2026-04-26-v2-deep-read-findings.md` — 5 v2 structural findings
- `pipeline/data/research/etf_v3/2026-04-26-etf-v3-verdict.md` — this document

Holdout file `etf_v3_holdout.json` intentionally absent — single-touch slot reserved.
