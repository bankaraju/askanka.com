"""ETF v3 — rolling weekly-refit walk-forward (matches production cadence).

The static-weights walk-forward in `etf_v3_research.py --walk-forward` froze
weights on each fold's training portion and tested on the next portion. That
is NOT how production v2 runs. v2 refits weights every Saturday on the trailing
window and uses those weights for the next week.

This module mirrors that exactly:
  - Every REFIT_INTERVAL_DAYS trading days, refit weights on the trailing
    LOOKBACK_DAYS days using the same Karpathy random search
  - Use those weights for the next REFIT_INTERVAL_DAYS days
  - Roll forward across the whole evaluation window
  - Accumulate per-day predictions and compute OOS accuracy on the full span

A model that works in production must show an aggregate OOS edge under this
rolling test. If it does, the user's intuition is supported by the data and
"refit weekly" is doing real work even if the static-weights view looked weak.
If it does NOT, the v3 verdict stands and the production engine has a real
problem.

Usage:
    python -m pipeline.autoresearch.etf_v3_rolling_refit --run \
        --refit-interval 5 --lookback-days 756 --n-iterations 2000

  refit-interval 5  = weekly refit (5 Indian trading days)
  lookback-days 756 = ~3 years (matches v2 production)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from pipeline.autoresearch.etf_v3_loader import (
    HOLDOUT_START,
    IN_SAMPLE_END,
    WINDOW_END,
    WINDOW_START,
    audit_panel,
    build_panel,
)
from pipeline.autoresearch.etf_v3_research import (
    FOREIGN_RETURN_COLS,
    build_features,
    build_target,
    fit_weights,
    _weighted_signal,
)

logger = logging.getLogger(__name__)
REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = REPO_ROOT / "pipeline" / "data" / "research" / "etf_v3"


@dataclass
class RollingRefitConfig:
    refit_interval_days: int = 5
    lookback_days: int = 756
    n_iterations: int = 2000
    seed: int = 42
    eval_start: str = "2024-04-23"   # latest possible after 3yr lookback
    eval_end: str = "2026-04-23"


def run_rolling_refit(cfg: RollingRefitConfig) -> dict:
    """Execute the rolling weekly-refit walk-forward.

    Returns aggregated OOS metrics + per-refit-window detail.
    """
    audit = audit_panel()
    if any(r.status == "fail" for r in audit):
        raise RuntimeError("audit failed — cannot proceed")
    panel = build_panel(t1_anchor=True)
    feats = build_features(panel)
    target = build_target(panel)
    common = feats.index.intersection(target.index)
    feats, target = feats.loc[common], target.loc[common]

    eval_start = pd.Timestamp(cfg.eval_start)
    eval_end = pd.Timestamp(cfg.eval_end)
    eval_dates = feats.index[(feats.index >= eval_start) & (feats.index <= eval_end)]
    if len(eval_dates) == 0:
        raise RuntimeError(f"no eval dates in [{eval_start.date()} .. {eval_end.date()}]")

    # Slice into refit windows
    refit_anchors = eval_dates[::cfg.refit_interval_days]
    logger.info("rolling refit: %d refit anchors over %d eval days",
                len(refit_anchors), len(eval_dates))

    per_window: list[dict] = []
    all_preds: list[float] = []
    all_truths: list[float] = []
    all_dates: list[pd.Timestamp] = []

    for i, anchor in enumerate(refit_anchors):
        # Training window: anchor - lookback to anchor (exclusive)
        train_start = anchor - pd.Timedelta(days=int(cfg.lookback_days * 1.5))
        train_mask = (feats.index >= train_start) & (feats.index < anchor)
        Xtr = feats.loc[train_mask].iloc[-cfg.lookback_days:]
        ytr = target.loc[Xtr.index.intersection(target.index)]
        Xtr = Xtr.loc[ytr.index]

        if len(Xtr) < 200:
            logger.warning("refit %d at %s: only %d training rows, skipping",
                           i + 1, anchor.date(), len(Xtr))
            continue

        # Prediction window: anchor through anchor + interval - 1
        next_anchor_idx = (i + 1) * cfg.refit_interval_days
        if next_anchor_idx >= len(eval_dates):
            pred_dates = eval_dates[i * cfg.refit_interval_days:]
        else:
            pred_dates = eval_dates[i * cfg.refit_interval_days: next_anchor_idx]
        Xpr = feats.loc[pred_dates].dropna()
        ypr = target.loc[Xpr.index.intersection(target.index)]
        Xpr = Xpr.loc[ypr.index]
        if len(Xpr) == 0:
            continue

        # Fit + predict
        fit = fit_weights(Xtr, ytr,
                          n_iterations=cfg.n_iterations, seed=cfg.seed + i)
        sig_pr = _weighted_signal(Xpr, fit.weights)
        pred = np.sign(sig_pr.values)
        truth = ypr.values
        correct = (pred == truth).sum()
        n_up = int((truth == 1).sum())
        baseline = max(n_up, len(truth) - n_up) / len(truth) * 100.0 if len(truth) else 0.0
        per_window.append({
            "refit_id": i + 1,
            "refit_anchor": str(anchor.date()),
            "train_n": int(len(Xtr)),
            "pred_n": int(len(Xpr)),
            "pred_acc_pct": float(correct / len(truth) * 100.0) if len(truth) else 0.0,
            "pred_baseline_pct": float(baseline),
            "pred_edge_pp": float(correct / len(truth) * 100.0 - baseline) if len(truth) else 0.0,
            "train_in_fit_acc_pct": fit.accuracy,
            "train_in_fit_sharpe": fit.sharpe,
        })
        all_preds.extend(pred.tolist())
        all_truths.extend(truth.tolist())
        all_dates.extend(pred_dates.tolist())

    # Aggregate OOS metrics across all refit windows
    arr_pred = np.asarray(all_preds)
    arr_truth = np.asarray(all_truths)
    n_total = len(arr_truth)
    n_correct = int((arr_pred == arr_truth).sum())
    overall_acc = n_correct / n_total * 100.0 if n_total else 0.0
    n_up = int((arr_truth == 1).sum())
    overall_baseline = max(n_up, n_total - n_up) / n_total * 100.0 if n_total else 0.0
    overall_edge = overall_acc - overall_baseline

    # Per-window summary
    win_accs = [w["pred_acc_pct"] for w in per_window]
    win_edges = [w["pred_edge_pp"] for w in per_window]
    n_windows_positive_edge = sum(1 for e in win_edges if e > 0)

    return {
        "config": asdict(cfg),
        "n_refit_windows": len(per_window),
        "n_total_oos_predictions": n_total,
        "overall_acc_pct": float(overall_acc),
        "overall_baseline_majority_pct": float(overall_baseline),
        "overall_edge_pp": float(overall_edge),
        "per_window_acc_mean_pct": float(np.mean(win_accs)) if win_accs else 0.0,
        "per_window_acc_std_pct": float(np.std(win_accs)) if win_accs else 0.0,
        "per_window_edge_mean_pp": float(np.mean(win_edges)) if win_edges else 0.0,
        "per_window_edge_std_pp": float(np.std(win_edges)) if win_edges else 0.0,
        "n_windows_positive_edge": int(n_windows_positive_edge),
        "fraction_windows_positive": float(n_windows_positive_edge / len(per_window)) if per_window else 0.0,
        "first_refit_date": per_window[0]["refit_anchor"] if per_window else None,
        "last_refit_date": per_window[-1]["refit_anchor"] if per_window else None,
        "per_window_detail": per_window,
    }


def _git_commit_hash() -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True,
                             text=True, cwd=REPO_ROOT, check=False, timeout=5)
        if out.returncode == 0:
            return out.stdout.strip()
    except Exception:
        pass
    return "UNKNOWN"


def main() -> int:
    parser = argparse.ArgumentParser(description="ETF v3 rolling weekly-refit walk-forward")
    parser.add_argument("--run", action="store_true", help="execute the rolling refit")
    parser.add_argument("--refit-interval", type=int, default=5,
                        help="trading days between refits (5 = weekly)")
    parser.add_argument("--lookback-days", type=int, default=756,
                        help="training window in trading days (756 = ~3yr)")
    parser.add_argument("--n-iterations", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--eval-start", default="2024-04-23",
                        help="OOS evaluation window start (must be >= window_start + lookback)")
    parser.add_argument("--eval-end", default="2026-04-23")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if not args.run:
        parser.print_help()
        return 0

    cfg = RollingRefitConfig(
        refit_interval_days=args.refit_interval,
        lookback_days=args.lookback_days,
        n_iterations=args.n_iterations,
        seed=args.seed,
        eval_start=args.eval_start,
        eval_end=args.eval_end,
    )
    result = run_rolling_refit(cfg)
    result["manifest"] = {
        "model": "etf_v3_rolling_refit",
        "code_commit": _git_commit_hash(),
        "config_hash": hashlib.sha256(
            json.dumps(asdict(cfg), sort_keys=True).encode("utf-8")
        ).hexdigest()[:16],
        "generated_at_utc": datetime.now(tz=timezone.utc).isoformat(),
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / f"etf_v3_rolling_refit_int{cfg.refit_interval_days}_lb{cfg.lookback_days}.json"
    out_path.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    logger.info("wrote %s", out_path)

    # Print summary
    print(json.dumps({
        "n_refit_windows": result["n_refit_windows"],
        "n_total_oos_predictions": result["n_total_oos_predictions"],
        "overall_acc_pct": result["overall_acc_pct"],
        "overall_baseline_pct": result["overall_baseline_majority_pct"],
        "overall_edge_pp": result["overall_edge_pp"],
        "per_window_acc_mean_pct": result["per_window_acc_mean_pct"],
        "per_window_edge_mean_pp": result["per_window_edge_mean_pp"],
        "fraction_windows_positive": result["fraction_windows_positive"],
        "first_refit": result["first_refit_date"],
        "last_refit": result["last_refit_date"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
