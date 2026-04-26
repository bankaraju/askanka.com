"""Compute head-to-head bootstrap CIs + year breakdown for the 4 ETF v3 results.

Run on Contabo (or laptop with parquet panel) after all 4 rolling-refit results
have been written. Outputs a clean comparison table.
"""
import json
import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
ETF_DIR = REPO_ROOT / "pipeline" / "data" / "research" / "etf_v3"


def bootstrap_acc_ci(per_window_detail, n_iter=2000, seed=42):
    rng = np.random.default_rng(seed)
    flat = []
    for w in per_window_detail:
        n = w["pred_n"]
        acc = w["pred_acc_pct"]
        s = round(n * acc / 100.0)
        flat.extend([1] * s + [0] * (n - s))
    arr = np.asarray(flat)
    if len(arr) == 0:
        return None
    overall = arr.mean() * 100
    boot = np.array([
        arr[rng.integers(0, len(arr), len(arr))].mean() * 100
        for _ in range(n_iter)
    ])
    return overall, np.percentile(boot, 2.5), np.percentile(boot, 97.5), len(arr), boot


def year_break(per_window_detail):
    out = {}
    for yr in ["2024", "2025", "2026"]:
        yws = [w for w in per_window_detail if w["refit_anchor"].startswith(yr)]
        if not yws:
            continue
        n_pred = sum(w["pred_n"] for w in yws)
        n_correct = sum(round(w["pred_n"] * w["pred_acc_pct"] / 100) for w in yws)
        out[yr] = (len(yws), n_pred,
                   n_correct / max(n_pred, 1) * 100)
    return out


def main():
    runs = [
        ("v2-faithful FULL-40", "etf_v2_faithful_rolling_int5_lb756.json"),
        ("v2-faithful CURATED-30", "etf_v2_faithful_rolling_int5_lb756_curated.json"),
        ("v3 FULL-40", "etf_v3_rolling_refit_int5_lb756.json"),
        ("v3 CURATED-30", "etf_v3_rolling_refit_int5_lb756_curated.json"),
    ]
    print(f"{'configuration':<25} {'acc':>7} {'base':>7} {'edge':>7}  "
          f"{'95% CI':<18} {'P>base':>7}  {'2024':>7} {'2025':>7} {'2026':>7}  refits")
    print("-" * 130)
    for name, fname in runs:
        path = ETF_DIR / fname
        if not path.exists():
            print(f"{name:<25} MISSING {path.name}")
            continue
        d = json.loads(path.read_text())
        overall_acc = d["overall_acc_pct"]
        base = d.get("overall_baseline_majority_pct") or d.get("overall_baseline_pct") or 0.0
        edge = d["overall_edge_pp"]
        n_refits = d.get("n_refit_windows")
        pwd = d["per_window_detail"]
        result = bootstrap_acc_ci(pwd)
        if result is None:
            print(f"{name:<25} no per-window detail")
            continue
        pt, lo, hi, n, b = result
        p_above = float((b > base).mean())
        yr = year_break(pwd)
        yr_str = " ".join(
            f"{yr.get(y, (0, 0, 0))[2]:>6.2f}%" for y in ["2024", "2025", "2026"]
        )
        ci_str = f"[{lo:.2f}, {hi:.2f}]"
        print(f"{name:<25} {overall_acc:>6.2f}% {base:>6.2f}% {edge:>+6.2f}pp  "
              f"{ci_str:<18} {p_above*100:>5.1f}%  {yr_str}  {n_refits:>3}")


if __name__ == "__main__":
    sys.exit(main())
