"""Diagnostic battery for the kickoff fit — runs after weight refit.

Stages 7 + 9 of `docs/superpowers/specs/autonomous_intraday_research_framework.md`,
adapted to the V1 in-sample window. Outputs:

1. Per-feature contribution to score dispersion (z-scored basis)
2. Ablation: zero each weight, measure objective drop
3. Leave-one-feature-out: refit excluding each feature
4. Sign consistency across 5 seeds
5. Walk-forward OOS: train first 12 days, score on last 5

The output is a JSON report at
``pipeline/data/research/h_2026_04_29_intraday_v1/diagnostics/kickoff_2026_04_29.json``
PLUS a concise console summary suitable for a verdict decision.

Run::

    python -m pipeline.research.intraday_v1.diagnose_kickoff
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, List

import numpy as np
import pandas as pd

from pipeline.research.intraday_v1 import in_sample_panel, karpathy_fit, runner

log = logging.getLogger("intraday_v1.diagnose")
logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

DIAG_DIR = runner.DATA_DIR / "diagnostics"
KICKOFF_REPORT = DIAG_DIR / "kickoff_2026_04_29.json"


# ---------------------------------------------------------------- helpers ---

def _load_panel_and_weights():
    df_raw = in_sample_panel.assemble_for_pool("stocks")
    weights_path = runner.WEIGHTS_DIR / "latest_stocks.json"
    payload = json.loads(weights_path.read_text(encoding="utf-8"))
    return df_raw, payload


def _z_score_panel(df_raw, means, stds):
    return karpathy_fit.apply_zscore(df_raw, means, stds)


# --------------------------------------------------------- diagnostic #1 ---

def diag_score_dispersion(df_z: pd.DataFrame, weights: List[float], names: List[str]) -> Dict:
    """Per-feature contribution to score variance.

    var(w_i z_i) / sum_j var(w_j z_j) — interpreted as "share of score
    spread driven by this feature". A balanced fit has each feature
    contributing ~17%; volume dominance shows up as one feature near 1.0.
    """
    contributions: List[float] = []
    for col, w in zip(karpathy_fit.FEATURE_COLS, weights):
        contributions.append(float(np.var(df_z[col] * w, ddof=0)))
    total = sum(contributions)
    if total == 0:
        return {"contributions": {n: 0.0 for n in names}, "total_variance": 0.0}
    shares = {n: c / total for n, c in zip(names, contributions)}
    return {"contributions": shares, "total_variance": total}


# --------------------------------------------------------- diagnostic #2 ---

def diag_ablation(
    df_z: pd.DataFrame,
    weights: np.ndarray,
    names: List[str],
    rolling_window_days: int,
    base_objective: float,
) -> Dict:
    """Zero each weight in turn and measure objective drop.

    A feature that was load-bearing shows a large NEGATIVE delta
    (objective drops when removed). A feature contributing noise
    shows ~0 delta or even POSITIVE (removing noise improves J).
    """
    results: List[Dict] = []
    for i, name in enumerate(names):
        w_ablated = weights.copy()
        w_ablated[i] = 0.0
        j_ablated = karpathy_fit.objective(
            w_ablated, df_z, rolling_window_days=rolling_window_days,
        )
        results.append({
            "feature": name,
            "objective_with_feature": float(base_objective),
            "objective_without_feature": float(j_ablated),
            "delta": float(j_ablated - base_objective),
        })
    return {"per_feature": results, "base_objective": float(base_objective)}


# --------------------------------------------------------- diagnostic #3 ---

def diag_leave_one_out(
    df_raw: pd.DataFrame,
    rolling_window_days: int,
    seed: int,
    n_iters: int,
    names: List[str],
) -> Dict:
    """For each feature, refit with that feature's column zeroed out.

    Reports the objective achievable by the OTHER 5 features. If LOO
    objectives are similar to or higher than the full fit, the dropped
    feature is non-essential.
    """
    full = karpathy_fit.run(
        df_raw, seed=seed, n_iters=n_iters, rolling_window_days=rolling_window_days,
    )
    full_obj = float(full["objective"])
    results: List[Dict] = []
    for col, name in zip(karpathy_fit.FEATURE_COLS, names):
        df_loo = df_raw.copy()
        df_loo[col] = 0.0
        fit_loo = karpathy_fit.run(
            df_loo, seed=seed, n_iters=n_iters, rolling_window_days=rolling_window_days,
        )
        results.append({
            "removed_feature": name,
            "objective_without": float(fit_loo["objective"]),
            "objective_full":    full_obj,
            "delta":             float(fit_loo["objective"] - full_obj),
            "weights_remaining": [float(x) for x in fit_loo["weights"]],
        })
    return {"per_feature": results, "full_fit_objective": full_obj}


# --------------------------------------------------------- diagnostic #4 ---

def diag_sign_consistency(
    df_raw: pd.DataFrame,
    rolling_window_days: int,
    n_iters: int,
    names: List[str],
    seeds=(42, 1, 7, 100, 2024),
) -> Dict:
    """Refit with multiple seeds; for each feature, count sign agreement.

    A feature whose sign flips between seeds is being driven by noise.
    A feature whose sign is consistent across all 5 seeds is a real direction.
    """
    seed_results: List[Dict] = []
    weight_grid = np.zeros((len(seeds), 6))
    for i, s in enumerate(seeds):
        fit = karpathy_fit.run(
            df_raw, seed=int(s), n_iters=n_iters,
            rolling_window_days=rolling_window_days,
        )
        weight_grid[i] = fit["weights"]
        seed_results.append({
            "seed": int(s),
            "objective": float(fit["objective"]),
            "weights": [float(x) for x in fit["weights"]],
        })
    sign_grid = np.sign(weight_grid)  # shape (n_seeds, 6)
    consistency: List[Dict] = []
    for j, name in enumerate(names):
        signs = sign_grid[:, j]
        n_pos = int((signs > 0).sum())
        n_neg = int((signs < 0).sum())
        n_zero = int((signs == 0).sum())
        # Fraction agreeing with the majority sign
        majority = max(n_pos, n_neg)
        consistency.append({
            "feature": name,
            "n_positive": n_pos,
            "n_negative": n_neg,
            "n_zero":     n_zero,
            "majority_share": majority / len(seeds),
            "weights_across_seeds": [float(weight_grid[i, j]) for i in range(len(seeds))],
        })
    return {
        "seeds": list(seeds),
        "per_seed_fits": seed_results,
        "per_feature_sign_consistency": consistency,
    }


# --------------------------------------------------------- diagnostic #5 ---

def diag_walk_forward(
    df_raw: pd.DataFrame,
    rolling_window_days: int,
    seed: int,
    n_iters: int,
    train_frac: float = 0.70,
) -> Dict:
    """Train on the first ``train_frac`` of days; score the held-out tail.

    Walk-forward OOS *within* the in-sample window. Cannot replace the
    real holdout (single-touch §10.4) but does check whether the model
    holds together when fit on a subset and evaluated on another subset.
    """
    dates = sorted(df_raw["date"].unique())
    n = len(dates)
    n_train = max(int(n * train_frac), karpathy_fit.ROLLING_WINDOW_DAYS + 1)
    if n_train >= n - 1:
        return {
            "status": "INSUFFICIENT_DAYS",
            "n_total": n,
            "n_train": n_train,
            "reason": "not enough in-sample days to leave a non-trivial OOS tail",
        }
    train_dates = set(dates[:n_train])
    oos_dates   = set(dates[n_train:])
    df_train = df_raw[df_raw["date"].isin(train_dates)].copy()
    df_oos   = df_raw[df_raw["date"].isin(oos_dates)].copy()

    # Train: full Karpathy fit on the first n_train days
    train_window = min(rolling_window_days, max(3, n_train // 3))
    fit = karpathy_fit.run(
        df_train, seed=seed, n_iters=n_iters,
        rolling_window_days=train_window,
    )

    # Score the OOS tail using the train-time z-stats and weights
    df_oos_z = karpathy_fit.apply_zscore(df_oos, fit["feature_means"], fit["feature_stds"])
    weights = fit["weights"]

    # Build the same long-short basket return per day in OOS using
    # train-fit thresholds at quantiles 0.7 / 0.3 — but on z-scored OOS scores.
    feat_oos = df_oos_z[karpathy_fit.FEATURE_COLS].to_numpy()
    df_oos_z["score"] = feat_oos @ weights
    daily = []
    for _, group in df_oos_z.groupby("date", sort=True):
        if group.empty:
            continue
        long_q = group["score"].quantile(0.7)
        short_q = group["score"].quantile(0.3)
        longs = group[group["score"] >= long_q]
        shorts = group[group["score"] <= short_q]
        long_ret = float(longs["next_return_pct"].mean()) if not longs.empty else 0.0
        short_ret = float(shorts["next_return_pct"].mean()) if not shorts.empty else 0.0
        daily.append(long_ret - short_ret)
    daily_arr = np.array(daily) if daily else np.array([0.0])
    oos_mean = float(daily_arr.mean())
    oos_std  = float(daily_arr.std(ddof=0))
    oos_sharpe = oos_mean / (oos_std + 1e-9)

    return {
        "status": "OK",
        "train_days": n_train,
        "oos_days":   n - n_train,
        "train_window_used": train_window,
        "train_objective":   float(fit["objective"]),
        "oos_daily_returns": [float(x) for x in daily],
        "oos_mean_daily":    oos_mean,
        "oos_std_daily":     oos_std,
        "oos_sharpe_simple": oos_sharpe,
        "oos_cum_return":    float(daily_arr.sum()),
        "weights_train":     [float(x) for x in fit["weights"]],
        "feature_means_train": fit["feature_means"],
        "feature_stds_train":  fit["feature_stds"],
    }


# ----------------------------------------------------------------- main ----

def run_all() -> Dict:
    df_raw, payload = _load_panel_and_weights()
    means = payload["feature_means"]
    stds = payload["feature_stds"]
    names = payload["feature_names"]
    weights = np.array(payload["weights"], dtype=float)
    rolling = int(payload["rolling_window_days"])
    df_z = _z_score_panel(df_raw, means, stds)

    print(f"In-sample: {df_raw['date'].nunique()} days × {df_raw['instrument'].nunique()} instruments = {len(df_raw)} rows")
    print(f"Base objective (post-z-score): {payload['objective']:+.6f}")
    print()

    out: Dict = {
        "pool":              "stocks",
        "weights":           [float(x) for x in weights],
        "feature_names":     names,
        "long_threshold":    payload["long_threshold"],
        "short_threshold":   payload["short_threshold"],
        "rolling_window_days": rolling,
        "n_in_sample_days":  payload["n_in_sample_days"],
        "n_in_sample_rows":  payload["n_in_sample_rows"],
    }

    # 1. Score dispersion
    print("=== Diagnostic 1: Score dispersion contribution ===")
    disp = diag_score_dispersion(df_z, [float(w) for w in weights], names)
    out["score_dispersion"] = disp
    for n, share in disp["contributions"].items():
        bar = "#" * int(share * 50)
        print(f"  {n:22s} {share*100:5.1f}%  {bar}")
    print()

    # 2. Ablation
    print("=== Diagnostic 2: Ablation (zero each weight) ===")
    abl = diag_ablation(df_z, weights, names, rolling, payload["objective"])
    out["ablation"] = abl
    for r in abl["per_feature"]:
        print(f"  {r['feature']:22s}  J w/o = {r['objective_without_feature']:+.4f}   delta = {r['delta']:+.4f}")
    print()

    # 3. Leave-one-out (slow — 6 fits)
    print("=== Diagnostic 3: Leave-one-feature-out (refit ×6, may take ~3 min) ===")
    loo = diag_leave_one_out(df_raw, rolling, seed=42, n_iters=2000, names=names)
    out["leave_one_out"] = loo
    for r in loo["per_feature"]:
        print(f"  removed {r['removed_feature']:18s}  J = {r['objective_without']:+.4f}   delta = {r['delta']:+.4f}")
    print()

    # 4. Sign consistency (slow — 5 fits)
    print("=== Diagnostic 4: Sign consistency across 5 seeds (refit ×5, may take ~3 min) ===")
    sc = diag_sign_consistency(df_raw, rolling, n_iters=2000, names=names)
    out["sign_consistency"] = sc
    for r in sc["per_feature_sign_consistency"]:
        print(f"  {r['feature']:22s}  +{r['n_positive']} -{r['n_negative']}  majority {r['majority_share']*100:.0f}%")
    print()

    # 5. Walk-forward OOS
    print("=== Diagnostic 5: Walk-forward OOS within in-sample (70/30 split) ===")
    wf = diag_walk_forward(df_raw, rolling, seed=42, n_iters=2000)
    out["walk_forward"] = wf
    if wf.get("status") == "OK":
        print(f"  train days       : {wf['train_days']}")
        print(f"  oos days         : {wf['oos_days']}")
        print(f"  train J          : {wf['train_objective']:+.4f}")
        print(f"  oos mean daily   : {wf['oos_mean_daily']:+.4f}")
        print(f"  oos std daily    : {wf['oos_std_daily']:.4f}")
        print(f"  oos simple sharpe: {wf['oos_sharpe_simple']:+.4f}")
        print(f"  oos cum return   : {wf['oos_cum_return']:+.4f}")
    else:
        print(f"  {wf}")
    print()

    DIAG_DIR.mkdir(parents=True, exist_ok=True)
    KICKOFF_REPORT.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(f"Diagnostic report written to {KICKOFF_REPORT}")
    return out


if __name__ == "__main__":
    run_all()
