# ETF v3 Research — Verdict

**Date:** 2026-04-26
**Run host:** Contabo VPS (anka@185.182.8.107)
**Code commit:** 08f6aec
**Spec:** docs/superpowers/specs/2026-04-26-etf-engine-v3-research-design.md
**Policy:** docs/superpowers/specs/anka_backtesting_policy_global_standard.md
**Data audit:** pipeline/data/research/etf_v3/2026-04-26-etf-v3-data-audit.md

---

## TL;DR

**v3 FAILS the gate ladder. The single-touch holdout was NOT consumed.**

The cleaner-methodology refit of the daily NIFTY-direction regime engine
shows **no edge over a majority-class baseline** under cross-validation, and
**cannot be distinguished from random labels** under the §12 permutation null.

By implication, v2's claimed 62.3% accuracy is now suspect: it was generated
under a single 70/30 split with no permutation null, no walk-forward, and no
fragility check. v3 used identical features minus PCR and identical model
class, evaluated under the current policy. The drop from 62.3% to ~52.8%
walk-forward test accuracy is the size of the in-sample fit advantage, not
a real edge.

**Recommendation:** do NOT swap v3 in for v2. Treat v2's published 62.3%
as a methodology-artifact number and re-evaluate v2 under the same gate
ladder before relying on its label as a regime engine. The regime label
may still have qualitative trader value (it ranks risk states), but its
**quantitative directional accuracy claim is no longer supported by the
research** under our current standards.

---

## Configuration

- **Model class:** weighted-sum + Karpathy random search, 2000 iterations, seed 42
- **Feature set:** 28 features (20 foreign-ETF 5d returns, India VIX level + 5d change, FII 5d sum, DII 5d sum, NIFTY 1d return + 5d return + 14d RSI). PCR removed.
- **Target:** sign of NEXT-day NIFTY return
- **Window:** 2021-04-23 → 2026-04-23
- **In-sample:** 2021-04-23 → 2025-12-31  (n=1146 after T-1 anchor + feature lookback)
- **Holdout:** 2026-01-01 → 2026-04-23  (n=74)  — **NOT TOUCHED**
- **Walk-forward:** 5 expanding folds inside in-sample
- **Null:** label-permutation, n=200, 50-iter inner search
- **Neighborhood:** 5 multiplicative perturbations at noise=0.10

---

## Gate-by-gate results

### §11.1 Sample adequacy
- in-sample n = 1146 ✓ adequate
- holdout n = 74 ✓ adequate for binary direction
- VERDICT: **PASS**

### §13.2 Walk-forward (5 expanding folds)

| fold | train_n / test_n | train_acc | test_acc | baseline | edge_pp | sharpe |
|---|---|---|---|---|---|---|
| 1 | 191 / 191 | 61.8% | 50.8% | 50.3% | **+0.52** | -0.20 |
| 2 | 382 / 191 | 60.5% | 56.0% | 56.0% | **+0.00** | +1.77 |
| 3 | 573 / 191 | 58.1% | 56.5% | 58.6% | **-2.09** | +2.39 |
| 4 | 764 / 191 | 58.6% | 47.6% | 50.3% | **-2.62** | -0.94 |
| 5 | 955 / 192 | 57.5% | 52.9% | 52.4% | **+0.52** | -0.23 |

Mean test acc 52.77%. Mean edge **-0.73pp** (negative). 2/5 folds worse than baseline.
Train-test gap consistently 5-15pp = severe overfit.

VERDICT: **FAIL** — strategy does not preserve edge across walk-forward folds. Per
policy §3.3 ("no single-point evidence"), in-sample-only success is insufficient.

### §12 Label-permutation null

- Real test acc (70/30 inner split): **50.58%**
- Null mean: 50.62%   |   Null std: 1.42%   |   Null p95: 52.91%
- **p-value (one-sided): 0.770**

VERDICT: **FAIL** — strategy is statistically indistinguishable from random
labels at α = 0.05. 77% of label-permuted runs produce a test accuracy at
least as high as the real one.

### §11.4 Parameter-neighborhood fragility

- Base acc 56.63%; perturbed range [55.93%, 56.89%]; max drop 0.70pp
- VERDICT: **STABLE** — but this is moot when the underlying edge does not exist.

### §13.1 Single-touch holdout
- **NOT CONSUMED.** Per policy §10.4, the holdout is only used when the
  in-sample evidence credibly supports the claim. Walk-forward + null already
  show no edge — touching the holdout would consume a single-use resource on
  a hypothesis we already know is dead, and risk false positives on a 74-day
  sample.
- File `etf_v3_holdout.json` does **NOT** exist. The single-touch slot remains
  reserved for a future, materially different model design (e.g. classifier-
  framed v3.1, regime-switching v4).

---

## Root cause analysis

The drop from v2's claimed 62.3% to v3's walk-forward 52.77% is explained by:

1. **Single-split overfit unmasked.** v2 used one 70/30 split. With 28 features
   and a Karpathy random search of 2000 iterations, the model can fit the
   training half well; the test half is not a true out-of-sample because the
   weights were selected by the test-set Sharpe (not a held-out fold). v3
   tested across 5 expanding folds — the apparent edge collapsed.

2. **Class imbalance shifts the baseline.** NIFTY is up ~54% of days in the
   v3 in-sample window. A trivial "always predict up" classifier scores
   ~54%. v2's "62.3%" was 8pp above this trivial baseline; v3's walk-forward
   52.77% is *below* it.

3. **PCR was not the culprit.** Removing PCR from the feature pool did not
   degrade performance materially (we'd need to re-run v2 with PCR included,
   under v3 methodology, to be sure). The methodology change is doing all
   the work; the feature change is incidental.

4. **The signal-class itself may not predict next-day direction.** Daily NIFTY
   direction is a notoriously hard target — efficient at the 1-day horizon
   for a liquid index. The fact that v2 appeared to clear it under the old
   protocol may have been the protocol, not the signal.

---

## Implications for production v2

Per policy §16.3 (edge decay) and §18 (independent validation), v2 should be:

1. **Re-evaluated under the v3 gate ladder** on the same window, with PCR
   included to test (3) above. Estimated effort: 1 hour (re-use v3 module
   with v2's full feature pool). This produces a defensible v2 number.
2. **Demoted from any quantitative-accuracy claim** until that re-evaluation
   completes. The label may still be useful as a *qualitative* risk-state
   ranker (it has worked in identifying overnight tail-risk per the
   `regime_transition_overnight` study), but a directional accuracy
   percentage cannot be reported.
3. **No production change** today. v2 keeps running as the live regime
   engine; trading rules that consume the regime label are not affected.
   Only the marketing claim "62.3% directional accuracy" is impaired.

---

## Recommendation: queue for the user

1. Authorize a v2 re-evaluation under the v3 gate ladder (~1 hour Contabo
   run) so the production engine has a defensible number — or a clear
   negative finding that informs how it should be presented externally.
2. Do NOT alter the production v2 weights or any downstream consumer
   today.
3. Do NOT touch the v3 holdout.
4. Treat the `regime_transition_overnight` finding (RISK-OFF +0.18%
   overnight loss, EUPHORIA +0.27% gain, etc.) as the more credible
   regime-label utility evidence. That study is qualitative and survives.

---

## Files produced

- `pipeline/data/research/etf_v3/etf_v3_fit.json` — in-sample fit + manifest
- `pipeline/data/research/etf_v3/etf_v3_walkforward.json` — 5-fold CV results
- `pipeline/data/research/etf_v3/etf_v3_null.json` — label-permutation null
- `pipeline/data/research/etf_v3/etf_v3_neighborhood.json` — fragility sweep
- `pipeline/data/research/etf_v3/2026-04-26-etf-v3-data-audit.md` — data audit
- `pipeline/data/research/etf_v3/2026-04-26-etf-v3-verdict.md` — this document

Holdout file `etf_v3_holdout.json` intentionally absent — single-touch slot reserved.
