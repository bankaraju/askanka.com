"""V2 walk-forward: does per-name dispersion survive a train/test split?

Methodology (matches autonomous_intraday_research_framework Stage 9 OOS):
1. Sort the in-sample panel by date.
2. Split into train (first 70%) and test (last 30%) by date — no leakage.
3. Refit pooled weights on TRAIN ONLY (z-stats from train, optimizer over train).
4. Apply train weights + train z-stats to TEST to score test rows.
5. Compute per-name long-short P&L slice on each half.
6. Compare rank ordering: Spearman correlation, top-K overlap.

Stop conditions:
- If top-13 train survivors and top-13 test survivors overlap by >=8 names,
  AND Spearman rank correlation across all instruments >= 0.30, the per-name
  dispersion is structurally stable. PROCEED to forward-only single-touch
  holdout per §10.4.
- If overlap <8 OR Spearman <0.30, the in-sample dispersion is noise.
  DROP the idea, do not pre-register.

Note on small-n: train=11, test=6 days. The Spearman test has weak power
at n=50 instruments x 6 test days, so a marginal Spearman should not be
treated as definitive — pair with the overlap count.
"""
from __future__ import annotations

import argparse
import json
import logging
import math
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from pipeline.research.intraday_v1 import (
    discover_v2, in_sample_panel, karpathy_fit
)

PIPELINE_ROOT = Path(__file__).resolve().parents[2]
WALKFORWARD_DIR = (
    PIPELINE_ROOT / "data" / "research" / "h_2026_04_29_intraday_v1" / "walkforward"
)
IST = timezone(timedelta(hours=5, minutes=30))

OVERLAP_THRESHOLD = 8   # of top-13 surviving sets
SPEARMAN_THRESHOLD = 0.30
TOP_K = 13              # 23 in-sample survivors > 1.8; pick top-K=13 to compare

log = logging.getLogger("intraday_v1.walkforward_v2")


def _split_dates(df: pd.DataFrame, train_frac: float = 0.70) -> Tuple[List[str], List[str]]:
    dates = sorted(df["date"].unique())
    cut = max(2, int(len(dates) * train_frac))
    return dates[:cut], dates[cut:]


def _per_name_metrics_subset(scored: pd.DataFrame) -> pd.DataFrame:
    """Run the discover_v2 baskets+metrics on a pre-scored subset df."""
    tagged = discover_v2._per_day_baskets(scored)
    return discover_v2._per_name_metrics(tagged)


def walk_forward(pool: str = "stocks", train_frac: float = 0.70,
                  n_iters: int = 2000, seed: int = 42) -> Dict:
    df = in_sample_panel.assemble_for_pool(pool)
    if df.empty:
        raise RuntimeError(f"in_sample_panel for pool={pool} is EMPTY")
    train_dates, test_dates = _split_dates(df, train_frac)
    log.info(f"split: train={len(train_dates)} days, test={len(test_dates)} days")
    if len(train_dates) < 5 or len(test_dates) < 3:
        raise RuntimeError(f"insufficient days for walk-forward: train={len(train_dates)}, test={len(test_dates)}")

    train_df = df[df["date"].isin(train_dates)].reset_index(drop=True)
    test_df = df[df["date"].isin(test_dates)].reset_index(drop=True)

    # Refit on TRAIN only — z-stats and weights are train-side artifacts.
    fit = karpathy_fit.run(
        train_df, seed=seed, n_iters=n_iters,
        rolling_window_days=min(karpathy_fit.ROLLING_WINDOW_DAYS, len(train_dates) - 1),
    )
    weights = np.asarray(fit["weights"], dtype=float)
    means = fit["feature_means"]
    stds = fit["feature_stds"]

    # Apply train z-stats + train weights to BOTH halves (no leakage).
    train_z = karpathy_fit.apply_zscore(train_df, means, stds)
    test_z = karpathy_fit.apply_zscore(test_df, means, stds)
    train_z = train_z.copy()
    test_z = test_z.copy()
    train_z["score"] = train_z[list(karpathy_fit.FEATURE_COLS)].to_numpy() @ weights
    test_z["score"] = test_z[list(karpathy_fit.FEATURE_COLS)].to_numpy() @ weights

    train_metrics = _per_name_metrics_subset(train_z)
    test_metrics = _per_name_metrics_subset(test_z)

    # Align on common instruments only (instruments with at least one trade
    # on each side count; missing names get NaN sharpe and are dropped from
    # the rank correlation only).
    merged = train_metrics[["instrument", "sharpe_ann"]].rename(
        columns={"sharpe_ann": "sharpe_train"}
    ).merge(
        test_metrics[["instrument", "sharpe_ann"]].rename(columns={"sharpe_ann": "sharpe_test"}),
        on="instrument", how="outer"
    )

    # Spearman across instruments where both halves produced a finite Sharpe
    spear_subset = merged.dropna(subset=["sharpe_train", "sharpe_test"])
    if len(spear_subset) >= 4:
        rho, p = spearmanr(spear_subset["sharpe_train"], spear_subset["sharpe_test"])
    else:
        rho, p = float("nan"), float("nan")

    # Top-K overlap
    train_top = set(
        train_metrics.dropna(subset=["sharpe_ann"])
                     .nlargest(TOP_K, "sharpe_ann")["instrument"].tolist()
    )
    test_top = set(
        test_metrics.dropna(subset=["sharpe_ann"])
                    .nlargest(TOP_K, "sharpe_ann")["instrument"].tolist()
    )
    train_bot = set(
        train_metrics.dropna(subset=["sharpe_ann"])
                     .nsmallest(TOP_K, "sharpe_ann")["instrument"].tolist()
    )
    test_bot = set(
        test_metrics.dropna(subset=["sharpe_ann"])
                    .nsmallest(TOP_K, "sharpe_ann")["instrument"].tolist()
    )
    top_overlap = len(train_top & test_top)
    bot_overlap = len(train_bot & test_bot)

    # Verdict
    overlap_pass = top_overlap >= OVERLAP_THRESHOLD
    spear_pass = (not math.isnan(rho)) and rho >= SPEARMAN_THRESHOLD
    verdict = (
        "PROCEED" if overlap_pass and spear_pass
        else "DROP"
    )

    WALKFORWARD_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.now(IST).strftime("%Y_%m_%d")
    train_csv = WALKFORWARD_DIR / f"per_name_train_{pool}_{today}.csv"
    test_csv = WALKFORWARD_DIR / f"per_name_test_{pool}_{today}.csv"
    train_metrics.to_csv(train_csv, index=False, float_format="%.4f")
    test_metrics.to_csv(test_csv, index=False, float_format="%.4f")

    summary = {
        "pool": pool,
        "train_dates": train_dates, "test_dates": test_dates,
        "train_n_days": len(train_dates), "test_n_days": len(test_dates),
        "train_objective": float(fit["objective"]),
        "train_weights": weights.tolist(),
        "feature_names": list(karpathy_fit.FEATURE_NAMES),
        "spearman_rho_train_test": None if math.isnan(rho) else float(rho),
        "spearman_p": None if math.isnan(p) else float(p),
        "top_k": TOP_K,
        "top_overlap_count": top_overlap,
        "bottom_overlap_count": bot_overlap,
        "train_top_set": sorted(train_top),
        "test_top_set": sorted(test_top),
        "train_bottom_set": sorted(train_bot),
        "test_bottom_set": sorted(test_bot),
        "overlap_threshold": OVERLAP_THRESHOLD,
        "spearman_threshold": SPEARMAN_THRESHOLD,
        "overlap_pass": bool(overlap_pass),
        "spearman_pass": bool(spear_pass),
        "verdict": verdict,
        "train_csv": str(train_csv),
        "test_csv": str(test_csv),
        "as_of": datetime.now(IST).isoformat(),
    }
    with (WALKFORWARD_DIR / f"summary_{pool}_{today}.json").open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, default=str)
    return summary


def _print_summary(s: Dict) -> None:
    print(f"=== V2 Walk-Forward — pool={s['pool']} ===")
    print(f"split: train={s['train_n_days']} days, test={s['test_n_days']} days")
    print(f"train objective (refit): {s['train_objective']:+.4f}")
    print()
    rho_str = f"{s['spearman_rho_train_test']:+.3f}" if s['spearman_rho_train_test'] is not None else "n/a"
    p_str = f"{s['spearman_p']:.3f}" if s['spearman_p'] is not None else "n/a"
    print(f"Spearman rho (train Sharpe vs test Sharpe across instruments): {rho_str}  p={p_str}")
    print(f"  threshold: rho >= {s['spearman_threshold']:+.2f}  -> {'PASS' if s['spearman_pass'] else 'FAIL'}")
    print()
    print(f"Top-{s['top_k']} overlap (winners): {s['top_overlap_count']} / {s['top_k']}")
    print(f"  threshold: overlap >= {s['overlap_threshold']}  -> {'PASS' if s['overlap_pass'] else 'FAIL'}")
    print(f"  train top: {s['train_top_set']}")
    print(f"  test  top: {s['test_top_set']}")
    print()
    print(f"Bottom-{s['top_k']} overlap (losers): {s['bottom_overlap_count']} / {s['top_k']}")
    print(f"  train bot: {s['train_bottom_set']}")
    print(f"  test  bot: {s['test_bottom_set']}")
    print()
    print(f"VERDICT: {s['verdict']}")
    print()
    print(f"per-name train CSV: {s['train_csv']}")
    print(f"per-name test  CSV: {s['test_csv']}")


def main() -> None:
    parser = argparse.ArgumentParser(description="V2 walk-forward — does per-name dispersion survive train/test split?")
    parser.add_argument("--pool", default="stocks", choices=("stocks", "indices"))
    parser.add_argument("--train-frac", type=float, default=0.70)
    parser.add_argument("--n-iters", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    s = walk_forward(pool=args.pool, train_frac=args.train_frac, n_iters=args.n_iters, seed=args.seed)
    _print_summary(s)


if __name__ == "__main__":
    main()
