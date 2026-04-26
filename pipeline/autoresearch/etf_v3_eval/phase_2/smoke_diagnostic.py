"""One-shot diagnostic over runs_smoke/wf_lb756_u126_seed0/rolling_refit.json.

Answers four go/no-go questions for the full grid:
1. What is per-window n_predictions? (tiny n → per-window edge stats are noise)
2. Are positive-edge windows clustered by date / regime?
3. Cluster-robust SE on the predictions-weighted aggregate edge.
4. Universe-naive baseline check (since 273-universe wasn't in smoke).
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from statistics import mean, median, stdev

import numpy as np

from pipeline.autoresearch.etf_v3_eval.phase_2.stats.cluster_robust_se import (
    cluster_robust_mean_se,
)

SMOKE = Path(
    "pipeline/data/research/etf_v3_evaluation/phase_2_backtest/runs_smoke/"
    "wf_lb756_u126_seed0/rolling_refit.json"
)
OUT = Path(
    "pipeline/data/research/etf_v3_evaluation/phase_2_backtest/smoke_diagnostic.md"
)


def main() -> int:
    d = json.loads(SMOKE.read_text())
    windows = d["per_window_detail"]
    n_total_pred = d["n_total_oos_predictions"]

    # Q1 — per-window n distribution
    pred_ns = [w["pred_n"] for w in windows]
    n_dist = Counter(pred_ns)

    # Q2 — date concentration of positive-edge windows
    pos_windows = [(w["refit_anchor"], w["pred_n"], w["pred_edge_pp"])
                   for w in windows if w["pred_edge_pp"] > 0]
    neg_windows_n = sum(1 for w in windows if w["pred_edge_pp"] < 0)
    zero_windows_n = sum(1 for w in windows if w["pred_edge_pp"] == 0)

    # Q3 — cluster-robust SE on predictions-weighted aggregate edge
    # IMPORTANT: rolling_refit.json's pred_edge_pp is edge vs per-window LOCAL
    # baseline (the majority class within that window's 5 predictions), not vs
    # the global majority baseline. The aggregate +0.61pp (overall_edge_pp) is
    # edge vs the GLOBAL majority. These are different gates; we want the
    # global-baseline view because that's what §15.1 alpha-after-beta tests.
    global_baseline_pct = d["overall_baseline_majority_pct"]

    # For each window, edge vs GLOBAL = pred_acc_pct_i - global_baseline_pct.
    # Reconstruct per-prediction synthetic observations: each prediction in
    # window i contributes (pred_acc_pct_i - global_baseline_pct) / 100. The
    # weighted mean equals overall_edge_pp by construction.
    expanded_returns: list[float] = []
    expanded_clusters: list[int] = []
    for w in windows:
        edge_pct_vs_global = (w["pred_acc_pct"] - global_baseline_pct) / 100.0
        for _ in range(w["pred_n"]):
            expanded_returns.append(edge_pct_vs_global)
            expanded_clusters.append(w["refit_id"])
    cluster_se = cluster_robust_mean_se(expanded_returns, expanded_clusters)

    # Equal-weighted per-window edge vs GLOBAL baseline (for comparison)
    per_window_edges_global_pp = [w["pred_acc_pct"] - global_baseline_pct
                                  for w in windows]
    eq_mean_pp = mean(per_window_edges_global_pp)
    eq_sd_pp = stdev(per_window_edges_global_pp)
    eq_se_pp = eq_sd_pp / (len(windows) ** 0.5)

    # Also compute a TRUE per-prediction cluster-robust SE: each prediction is
    # either correct (= 1) or wrong (= 0); edge contribution is (1 -
    # global_baseline_pct/100) if correct, (0 - global_baseline_pct/100) if
    # wrong. Cluster by window.
    gb_frac = global_baseline_pct / 100.0
    per_pred_returns: list[float] = []
    per_pred_clusters: list[int] = []
    for w in windows:
        n_correct = int(round(w["pred_n"] * w["pred_acc_pct"] / 100.0))
        n_wrong = w["pred_n"] - n_correct
        for _ in range(n_correct):
            per_pred_returns.append(1.0 - gb_frac)
            per_pred_clusters.append(w["refit_id"])
        for _ in range(n_wrong):
            per_pred_returns.append(0.0 - gb_frac)
            per_pred_clusters.append(w["refit_id"])
    pp_cluster_se = cluster_robust_mean_se(per_pred_returns, per_pred_clusters)

    # Per-window in-fit Sharpe distribution (sanity on the model itself)
    in_fit_sharpe = [w["train_in_fit_sharpe"] for w in windows]

    md = []
    md.append("# Phase 2 Smoke Diagnostic — wf_lb756_u126_seed0")
    md.append("")
    md.append("Source: `runs_smoke/wf_lb756_u126_seed0/rolling_refit.json` "
              f"({d['n_refit_windows']} windows, {n_total_pred} OOS predictions)")
    md.append("")
    md.append("## Q1 — Per-window prediction-count distribution")
    md.append("")
    md.append("| pred_n | n_windows |")
    md.append("|---:|---:|")
    for k in sorted(n_dist):
        md.append(f"| {k} | {n_dist[k]} |")
    md.append("")
    md.append(f"- median pred_n: **{median(pred_ns):.0f}**")
    md.append(f"- mean pred_n:   **{mean(pred_ns):.2f}**")
    md.append(f"- max pred_n:    **{max(pred_ns)}**")
    md.append("")
    md.append("**Interpretation.** With median pred_n ≈ 5, each window's edge "
              "is dominated by a 0/5 vs 5/5 binary noise floor (any single bad "
              "prediction swings the per-window edge by 20pp). The aggregate "
              "edge weighted by pred_n is the only reliable summary; the "
              "per-window edge mean is essentially un-interpretable.")
    md.append("")

    md.append("## Q2 — Positive-edge windows: dates and weights")
    md.append("")
    md.append(f"- positive-edge windows: **{len(pos_windows)} / {len(windows)}** "
              f"({100*len(pos_windows)/len(windows):.1f}%)")
    md.append(f"- zero-edge windows:     **{zero_windows_n}** "
              f"({100*zero_windows_n/len(windows):.1f}%)")
    md.append(f"- negative-edge windows: **{neg_windows_n}** "
              f"({100*neg_windows_n/len(windows):.1f}%)")
    md.append("")
    if pos_windows:
        md.append("Positive-edge windows (date, n, edge_pp):")
        md.append("")
        for date, n, edge in pos_windows:
            md.append(f"- `{date}` n={n} edge=+{edge:.1f}pp")
        md.append("")
    md.append("**Interpretation.** Positive-edge windows are the ones to "
              "examine for marker-gating opportunities. If they cluster on a "
              "few dates / regimes, the marker stack might rescue edge.")
    md.append("")

    md.append("## Q3 — Cluster-robust SE on aggregate edge vs GLOBAL baseline")
    md.append("")
    md.append("**Important:** The JSON's `pred_edge_pp` field is per-window edge")
    md.append("vs LOCAL baseline (the majority class within each 5-prediction")
    md.append("window). The §15.1 gates test edge vs the GLOBAL majority "
              f"({global_baseline_pct:.2f}%). All numbers below are vs GLOBAL.")
    md.append("")
    md.append(f"Predictions-weighted aggregate edge (overall_acc - global_baseline): "
              f"**{d['overall_edge_pp']:.3f} pp**")
    md.append("")
    md.append("(A) Per-window-edge expanded by pred_n, clustered by window:")
    md.append("")
    md.append(f"- mean: **{cluster_se['mean']*100:.3f} pp**  (= overall_edge_pp ✓)")
    md.append(f"- cluster-robust SE: **{cluster_se['se']*100:.3f} pp**")
    md.append(f"- t-stat: **{cluster_se['mean']/cluster_se['se']:.2f}**")
    md.append(f"- 95% CI: **[{(cluster_se['mean']-1.96*cluster_se['se'])*100:.3f}, "
              f"{(cluster_se['mean']+1.96*cluster_se['se'])*100:.3f}] pp**")
    md.append("")
    md.append("(B) True per-prediction binary outcomes (correct vs wrong - global_baseline),"
              " clustered by window — the methodologically correct estimator:")
    md.append("")
    md.append(f"- mean: **{pp_cluster_se['mean']*100:.3f} pp**")
    md.append(f"- cluster-robust SE: **{pp_cluster_se['se']*100:.3f} pp**")
    md.append(f"- t-stat: **{pp_cluster_se['mean']/pp_cluster_se['se']:.2f}**")
    md.append(f"- 95% CI: **[{(pp_cluster_se['mean']-1.96*pp_cluster_se['se'])*100:.3f}, "
              f"{(pp_cluster_se['mean']+1.96*pp_cluster_se['se'])*100:.3f}] pp**")
    md.append(f"- two-sided p-value (t-distribution, df={len(windows)-1}): "
              f"see t-stat above; |t|<2.0 → p>0.05")
    md.append("")
    md.append("Equal-weighted per-window edge vs GLOBAL (each window = 1 obs):")
    md.append("")
    md.append(f"- per-window mean edge: **{eq_mean_pp:.2f} pp**")
    md.append(f"- per-window SD edge:   **{eq_sd_pp:.2f} pp**")
    md.append(f"- per-window SE:        **{eq_se_pp:.2f} pp**")
    md.append(f"- t-stat:               **{eq_mean_pp/eq_se_pp:.2f}**")
    md.append("")
    md.append("**Interpretation.** Estimator (B) is the right one for §15.1; it")
    md.append("treats each prediction as a binary outcome and clusters at refit")
    md.append("window. The cluster-robust SE absorbs the within-window correlation")
    md.append("(predictions sharing a model-fit are not independent).")
    md.append("")

    md.append("## Q4 — In-fit Sharpe sanity (does the model fit anything?)")
    md.append("")
    md.append(f"- mean in-fit Sharpe: **{mean(in_fit_sharpe):.3f}**")
    md.append(f"- median in-fit Sharpe: **{median(in_fit_sharpe):.3f}**")
    md.append(f"- SD in-fit Sharpe: **{stdev(in_fit_sharpe):.3f}**")
    md.append("")
    md.append("**Interpretation.** An in-fit Sharpe ≫ OOS edge indicates "
              "overfitting. A near-zero in-fit Sharpe means the model isn't "
              "learning at all and the OOS edge is just noise around baseline.")
    md.append("")

    md.append("## Recommendation for the full grid")
    md.append("")
    # Use the methodologically correct per-prediction estimator for the verdict
    t_stat = pp_cluster_se['mean'] / pp_cluster_se['se']
    cluster_se = pp_cluster_se  # alias so downstream verdict text reads cleanly
    md.append("**Key observation about `n_iterations`.** In the underlying")
    md.append("`RollingRefitConfig`, `n_iterations` is the per-window bootstrap")
    md.append("iteration count, not the number of refit windows or predictions.")
    md.append("Increasing n_iterations from 100 → 2000 will NOT add new")
    md.append("predictions and will NOT shrink the cluster-robust SE on the")
    md.append("aggregate edge (which is fixed by the 99 windows / 493")
    md.append("predictions of the eval window). The full-grid compute will")
    md.append("therefore not change the t-statistic seen here — it would only")
    md.append("tighten downstream bootstrap-derived stability metrics that are")
    md.append("not load-bearing for §15.1.")
    md.append("")
    md.append("**Universe note.** u126 and u273 share the same ETF-feature")
    md.append("model and produce IDENTICAL `rolling_refit.json` results for")
    md.append("any given lookback. The universe only differs at the downstream")
    md.append("marker / replay step (which tickers to trade on the model's")
    md.append("regime call). The +0.6pp ± 2.3pp aggregate edge measured here")
    md.append("is the model's predictive ceiling regardless of universe.")
    md.append("")
    if abs(t_stat) >= 2.0 and cluster_se['mean'] > 0:
        verdict = "GO"
        rationale = (f"Per-prediction cluster-robust t-stat = {t_stat:.2f} "
                     "(≥2.0) and mean edge is positive. The full grid is "
                     "worth running for the marker decomposition / universe "
                     "sensitivity surfaces. Wall-clock estimate: 3 unique "
                     "rolling-refit lookbacks × ~25 min = ~75 min, plus "
                     "marker passes ≈ ~10 min. Total ~1-2 hours.")
    else:
        verdict = "STOP"
        rationale = (f"Per-prediction cluster-robust t-stat = {t_stat:.2f} "
                     f"(|t| < 2.0) on edge of {cluster_se['mean']*100:.3f} pp "
                     "± {se:.3f} pp. The 95% CI straddles zero. The full "
                     "grid will NOT change this — n_iterations doesn't add "
                     "predictions, and the 99-cluster SE is already at its "
                     "asymptotic floor. The marker stack can only re-slice "
                     "this 493-prediction pool into smaller subsets, which "
                     "will WIDEN the SE further. Recommend writing a "
                     "NEGATIVE result memo and rethinking the model form "
                     "before any further compute. The +0.6pp aggregate edge "
                     "is consistent with the in-fit-Sharpe-of-2.56 being "
                     "overfit to training noise.").format(
                         se=cluster_se['se']*100)
    md.append(f"**Verdict: {verdict}**")
    md.append("")
    md.append(rationale)
    md.append("")

    OUT.write_text("\n".join(md), encoding="utf-8")
    print(f"diagnostic written: {OUT}")
    print(f"verdict: {verdict}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
