# Phase 2 Smoke Diagnostic — wf_lb756_u126_seed0

Source: `runs_smoke/wf_lb756_u126_seed0/rolling_refit.json` (99 windows, 493 OOS predictions)

## Q1 — Per-window prediction-count distribution

| pred_n | n_windows |
|---:|---:|
| 4 | 2 |
| 5 | 97 |

- median pred_n: **5**
- mean pred_n:   **4.98**
- max pred_n:    **5**

**Interpretation.** With median pred_n ≈ 5, each window's edge is dominated by a 0/5 vs 5/5 binary noise floor (any single bad prediction swings the per-window edge by 20pp). The aggregate edge weighted by pred_n is the only reliable summary; the per-window edge mean is essentially un-interpretable.

## Q2 — Positive-edge windows: dates and weights

- positive-edge windows: **3 / 99** (3.0%)
- zero-edge windows:     **41** (41.4%)
- negative-edge windows: **55** (55.6%)

Positive-edge windows (date, n, edge_pp):

- `2024-05-08` n=5 edge=+40.0pp
- `2024-10-30` n=5 edge=+20.0pp
- `2025-11-18` n=5 edge=+20.0pp

**Interpretation.** Positive-edge windows are the ones to examine for marker-gating opportunities. If they cluster on a few dates / regimes, the marker stack might rescue edge.

## Q3 — Cluster-robust SE on aggregate edge vs GLOBAL baseline

**Important:** The JSON's `pred_edge_pp` field is per-window edge
vs LOCAL baseline (the majority class within each 5-prediction
window). The §15.1 gates test edge vs the GLOBAL majority (51.72%). All numbers below are vs GLOBAL.

Predictions-weighted aggregate edge (overall_acc - global_baseline): **0.609 pp**

(A) Per-window-edge expanded by pred_n, clustered by window:

- mean: **0.609 pp**  (= overall_edge_pp ✓)
- cluster-robust SE: **2.269 pp**
- t-stat: **0.27**
- 95% CI: **[-3.839, 5.056] pp**

(B) True per-prediction binary outcomes (correct vs wrong - global_baseline), clustered by window — the methodologically correct estimator:

- mean: **0.609 pp**
- cluster-robust SE: **2.269 pp**
- t-stat: **0.27**
- 95% CI: **[-3.839, 5.056] pp**
- two-sided p-value (t-distribution, df=98): see t-stat above; |t|<2.0 → p>0.05

Equal-weighted per-window edge vs GLOBAL (each window = 1 obs):

- per-window mean edge: **0.55 pp**
- per-window SD edge:   **22.55 pp**
- per-window SE:        **2.27 pp**
- t-stat:               **0.24**

**Interpretation.** Estimator (B) is the right one for §15.1; it
treats each prediction as a binary outcome and clusters at refit
window. The cluster-robust SE absorbs the within-window correlation
(predictions sharing a model-fit are not independent).

## Q4 — In-fit Sharpe sanity (does the model fit anything?)

- mean in-fit Sharpe: **2.558**
- median in-fit Sharpe: **2.599**
- SD in-fit Sharpe: **0.518**

**Interpretation.** An in-fit Sharpe ≫ OOS edge indicates overfitting. A near-zero in-fit Sharpe means the model isn't learning at all and the OOS edge is just noise around baseline.

## Recommendation for the full grid

**Key observation about `n_iterations`.** In the underlying
`RollingRefitConfig`, `n_iterations` is the per-window bootstrap
iteration count, not the number of refit windows or predictions.
Increasing n_iterations from 100 → 2000 will NOT add new
predictions and will NOT shrink the cluster-robust SE on the
aggregate edge (which is fixed by the 99 windows / 493
predictions of the eval window). The full-grid compute will
therefore not change the t-statistic seen here — it would only
tighten downstream bootstrap-derived stability metrics that are
not load-bearing for §15.1.

**Universe note.** u126 and u273 share the same ETF-feature
model and produce IDENTICAL `rolling_refit.json` results for
any given lookback. The universe only differs at the downstream
marker / replay step (which tickers to trade on the model's
regime call). The +0.6pp ± 2.3pp aggregate edge measured here
is the model's predictive ceiling regardless of universe.

**Verdict: STOP**

Per-prediction cluster-robust t-stat = 0.27 (|t| < 2.0) on edge of 0.609 pp ± 2.269 pp. The 95% CI straddles zero. The full grid will NOT change this — n_iterations doesn't add predictions, and the 99-cluster SE is already at its asymptotic floor. The marker stack can only re-slice this 493-prediction pool into smaller subsets, which will WIDEN the SE further. Recommend writing a NEGATIVE result memo and rethinking the model form before any further compute. The +0.6pp aggregate edge is consistent with the in-fit-Sharpe-of-2.56 being overfit to training noise.
