"""H-2026-04-29-ta-karpathy-v1 fit runner.

Per-stock per-direction Lasso L1 logistic with 4-fold walk-forward + 10k-shuffle
permutation null + BH-FDR correction across the 20 (ticker x direction) cells.

Spec ref: docs/superpowers/specs/2026-04-29-ta-karpathy-v1-design.md sections 8, 9, 14.

Outputs (under pipeline/data/research/h_2026_04_29_ta_karpathy_v1/):
  - manifest.json -- run config + per-cell summary
  - walk_forward_results.json -- per-cell per-fold AUC + selected alphas
  - permutation_null.json -- raw + BH-FDR adjusted p-values per cell
  - feature_matrices/<TICKER>.parquet -- the full feature matrix (per-stock)
  - models/<TICKER>_<DIRECTION>.pkl -- frozen final models for forward predict

Usage:
  # Smoke (RELIANCE long only, 200 perms):
  python -m pipeline.ta_scorer.karpathy_runner --tickers RELIANCE --directions long --n-permutations 200

  # Full run (10 stocks x 2 dirs x 10k perms):
  python -m pipeline.ta_scorer.karpathy_runner --n-permutations 10000

  # VPS background:
  nohup python -m pipeline.ta_scorer.karpathy_runner --n-permutations 10000 > fit.log 2>&1 &
"""
from __future__ import annotations

import argparse
import json
import logging
import pickle
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from .karpathy_data import (
    INDIAVIX_SYMBOL, NIFTY_SYMBOL, NIFTY_TOP_10, SECTOR_MAP,
    fetch_macro, fetch_one,
)
from .karpathy_features import (
    FEATURE_COLUMNS, build_feature_matrix, make_labels,
)
from .karpathy_metrics import stability_penalty
from .karpathy_model import fit_lasso_cv
from .karpathy_walk_forward import (
    bh_fdr, evaluate_cell, fold_summary, walk_forward,
)

log = logging.getLogger("karpathy.runner")

REPO_ROOT = Path(__file__).resolve().parents[2]
RUN_ROOT = REPO_ROOT / "pipeline" / "data" / "research" / "h_2026_04_29_ta_karpathy_v1"

# Spec section 7: training cutoff (in-sample holdout starts here)
TRAIN_END = pd.Timestamp("2025-10-25")
# Spec section 7: in-sample holdout end (the day before forward holdout opens)
IN_SAMPLE_HOLDOUT_END = pd.Timestamp("2026-04-25")


def _prep_panel(ticker: str, macro: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Build the full date-aligned panel of features + labels for one stock.

    Drops rows where any feature is NaN (warmup) or label is NaN (last bar).
    """
    bars = fetch_one(ticker)
    feat = build_feature_matrix(
        bars=bars,
        nifty=macro[NIFTY_SYMBOL][["date", "close"]],
        vix=macro[INDIAVIX_SYMBOL][["date", "close"]],
        sector=macro[SECTOR_MAP[ticker]][["date", "close"]],
        regime=pd.DataFrame({"date": pd.to_datetime([]), "regime": []}),
    )
    labels = make_labels(bars)
    df = feat.merge(labels, on="date", how="inner")
    df = df.dropna(subset=FEATURE_COLUMNS + ["y_long", "y_short"])
    df = df.sort_values("date").reset_index(drop=True)
    return df


def _train_slice(panel: pd.DataFrame) -> pd.DataFrame:
    """Spec section 7: train slice ends at TRAIN_END (last training day)."""
    return panel[panel["date"] <= TRAIN_END].reset_index(drop=True)


def _in_sample_holdout_slice(panel: pd.DataFrame) -> pd.DataFrame:
    """Spec section 7: in-sample holdout TRAIN_END+1d to IN_SAMPLE_HOLDOUT_END."""
    return panel[
        (panel["date"] > TRAIN_END) & (panel["date"] <= IN_SAMPLE_HOLDOUT_END)
    ].reset_index(drop=True)


def fit_one_cell(
    ticker: str,
    direction: str,
    panel: pd.DataFrame,
    *,
    n_permutations: int,
    rng_seed: int,
) -> dict:
    """Fit + walk-forward + permutation null for one (ticker, direction) cell.

    Returns dict with cell summary + holds the final model + standardiser
    in `_artifacts` for downstream serialisation.
    """
    label_col = "y_long" if direction == "long" else "y_short"
    train = _train_slice(panel)
    isho = _in_sample_holdout_slice(panel)

    X_tr = train[FEATURE_COLUMNS]
    y_tr = train[label_col].astype(int)
    dates_tr = train["date"]

    # Walk-forward + perm null (uses train slice only -- in-sample holdout is
    # NOT touched here)
    cell_res = evaluate_cell(
        ticker=ticker, direction=direction,
        X=X_tr, y=y_tr, dates=dates_tr,
        n_permutations=n_permutations, rng_seed=rng_seed,
    )

    # Final model: refit on train+isho with median alpha across folds
    final_X = pd.concat([train[FEATURE_COLUMNS], isho[FEATURE_COLUMNS]],
                        ignore_index=True)
    final_y = pd.concat([train[label_col].astype(int),
                         isho[label_col].astype(int)],
                        ignore_index=True)
    if final_y.nunique() < 2:
        log.warning("%s/%s: only one class in final fit set -- skipping",
                    ticker, direction)
        return {
            "ticker": ticker, "direction": direction,
            "cell": cell_res, "_artifacts": None,
        }

    selected_alphas = [f.selected_alpha for f in cell_res.fold_results
                       if not np.isnan(f.selected_alpha)]
    median_alpha = float(np.median(selected_alphas)) if selected_alphas else 1.0
    final_clf, final_stats, _, _ = fit_lasso_cv(final_X, final_y)

    # In-sample holdout score (for spec section 9 qualifier)
    isho_X = isho[FEATURE_COLUMNS]
    isho_y = isho[label_col].astype(int).values
    isho_p = final_clf.predict_proba(final_stats.transform(isho_X).values)[:, 1]
    isho_auc = float("nan")
    n_pred_pos_days = 0
    if len(np.unique(isho_y)) >= 2 and len(isho) > 0:
        from sklearn.metrics import roc_auc_score
        isho_auc = float(roc_auc_score(isho_y, isho_p))
        n_pred_pos_days = int((isho_p >= 0.6).sum())

    stab = stability_penalty([f.test_auc for f in cell_res.fold_results])

    return {
        "ticker": ticker,
        "direction": direction,
        "cell": cell_res,
        "median_walk_forward_alpha": median_alpha,
        "in_sample_holdout_auc": isho_auc,
        "in_sample_holdout_n_pred_pos_days": n_pred_pos_days,
        "stability": float(stab) if not np.isnan(stab) else None,
        "_artifacts": {
            "final_clf": final_clf,
            "final_stats": final_stats,
            "feature_columns": FEATURE_COLUMNS,
        },
    }


def write_outputs(
    cell_results: list[dict],
    *,
    out_root: Path,
    n_permutations: int,
    panels: dict[str, pd.DataFrame],
):
    """Write all artefacts under out_root."""
    out_root.mkdir(parents=True, exist_ok=True)
    (out_root / "feature_matrices").mkdir(exist_ok=True)
    (out_root / "models").mkdir(exist_ok=True)

    # Walk-forward results JSON
    wf_rows = []
    for c in cell_results:
        cell = c["cell"]
        for f in cell.fold_results:
            wf_rows.append({
                "ticker": c["ticker"], "direction": c["direction"],
                "fold_idx": f.fold_idx,
                "train_start": f.train_start.isoformat(),
                "train_end": f.train_end.isoformat(),
                "test_start": f.test_start.isoformat(),
                "test_end": f.test_end.isoformat(),
                "n_train": f.n_train, "n_test": f.n_test,
                "selected_alpha": f.selected_alpha,
                "train_auc": f.train_auc, "test_auc": f.test_auc,
                "n_features_nonzero": f.n_features_nonzero,
            })
    (out_root / "walk_forward_results.json").write_text(
        json.dumps({"folds": wf_rows}, default=str, indent=2)
    )

    # Permutation null JSON (with BH-FDR adjusted p-values)
    p_raw = [c["cell"].perm_p_value for c in cell_results]
    sig, p_adj = bh_fdr(p_raw, alpha=0.05)
    perm_rows = []
    for c, p, p_a, s in zip(cell_results, p_raw, p_adj, sig):
        perm_rows.append({
            "ticker": c["ticker"], "direction": c["direction"],
            "perm_p_value_raw": p,
            "perm_p_value_bh_fdr_adj": p_a,
            "bh_fdr_significant_at_0.05": s,
        })
    (out_root / "permutation_null.json").write_text(
        json.dumps({
            "n_permutations": n_permutations,
            "n_cells": len(cell_results),
            "cells": perm_rows,
        }, indent=2)
    )

    # Per-stock feature matrix parquet (de-duplicate -- one per stock not per dir)
    seen_tickers = set()
    for c in cell_results:
        if c["ticker"] not in seen_tickers and c["ticker"] in panels:
            panels[c["ticker"]].to_parquet(
                out_root / "feature_matrices" / f"{c['ticker']}.parquet",
                index=False,
            )
            seen_tickers.add(c["ticker"])

    # Frozen models per cell
    for c in cell_results:
        if c.get("_artifacts") is None:
            continue
        a = c["_artifacts"]
        with (out_root / "models" / f"{c['ticker']}_{c['direction']}.pkl").open("wb") as f:
            pickle.dump({
                "ticker": c["ticker"], "direction": c["direction"],
                "feature_columns": a["feature_columns"],
                "stats_mean": a["final_stats"].mean.to_dict(),
                "stats_std": a["final_stats"].std.to_dict(),
                "coef": a["final_clf"].coef_[0].tolist(),
                "intercept": float(a["final_clf"].intercept_[0]),
                "fitted_at": datetime.now().isoformat(),
            }, f)

    # Manifest
    manifest = {
        "hypothesis_id": "H-2026-04-29-ta-karpathy-v1",
        "spec_version": "v1.1",
        "spec_ref": "docs/superpowers/specs/2026-04-29-ta-karpathy-v1-design.md",
        "fitted_at": datetime.now().isoformat(),
        "n_tickers": len({c["ticker"] for c in cell_results}),
        "n_cells": len(cell_results),
        "n_permutations": n_permutations,
        "qualifier_summary_per_cell": [
            {
                "ticker": c["ticker"],
                "direction": c["direction"],
                "mean_fold_auc": c["cell"].mean_fold_auc,
                "fold_auc_std": c["cell"].fold_auc_std,
                "in_sample_holdout_auc": c.get("in_sample_holdout_auc"),
                "in_sample_holdout_n_pred_pos_days": c.get(
                    "in_sample_holdout_n_pred_pos_days"
                ),
                "perm_p_value_raw": c["cell"].perm_p_value,
                "perm_p_value_bh_fdr_adj": p_a,
                "bh_fdr_significant_at_0.05": s,
                "stability": c.get("stability"),
                "median_walk_forward_alpha": c.get("median_walk_forward_alpha"),
                "qualifier_pass": (
                    not np.isnan(c["cell"].mean_fold_auc)
                    and c["cell"].mean_fold_auc >= 0.55
                    and c["cell"].fold_auc_std <= 0.05
                    and (c.get("in_sample_holdout_auc") is not None
                         and not np.isnan(c.get("in_sample_holdout_auc"))
                         and c.get("in_sample_holdout_auc") >= 0.55)
                    and (c.get("in_sample_holdout_n_pred_pos_days") or 0) >= 3
                    and bool(s)
                ),
            }
            for c, p_a, s in zip(cell_results, p_adj, sig)
        ],
    }
    (out_root / "manifest.json").write_text(json.dumps(manifest, default=str, indent=2))


def run(
    tickers: list[str],
    directions: list[str],
    *,
    n_permutations: int = 10000,
    rng_seed: int = 42,
    out_root: Path = RUN_ROOT,
):
    log.info("starting karpathy fit: tickers=%s directions=%s n_permutations=%d",
             tickers, directions, n_permutations)
    t0 = time.time()
    macro = fetch_macro()
    log.info("loaded macro indices in %.1fs", time.time() - t0)

    panels: dict[str, pd.DataFrame] = {}
    cell_results: list[dict] = []

    for ti, ticker in enumerate(tickers):
        t1 = time.time()
        log.info("[%d/%d] %s: loading panel ...", ti + 1, len(tickers), ticker)
        panel = _prep_panel(ticker, macro)
        panels[ticker] = panel
        log.info("[%d/%d] %s: panel n=%d  %s -> %s  (%.1fs)",
                 ti + 1, len(tickers), ticker, len(panel),
                 panel["date"].min().date(), panel["date"].max().date(),
                 time.time() - t1)

        for direction in directions:
            t2 = time.time()
            log.info("  fitting %s/%s (n_perm=%d) ...", ticker, direction, n_permutations)
            res = fit_one_cell(
                ticker, direction, panel,
                n_permutations=n_permutations, rng_seed=rng_seed,
            )
            cell_results.append(res)
            cell = res["cell"]
            log.info("  %s/%s done (%.1fs)  mean_auc=%.3f std=%.3f  perm_p=%s",
                     ticker, direction, time.time() - t2,
                     cell.mean_fold_auc, cell.fold_auc_std, cell.perm_p_value)

    log.info("writing artefacts to %s ...", out_root)
    write_outputs(
        cell_results, out_root=out_root,
        n_permutations=n_permutations, panels=panels,
    )
    log.info("DONE in %.1fs total", time.time() - t0)
    return cell_results


def main():
    p = argparse.ArgumentParser(description="H-2026-04-29 karpathy fit runner")
    p.add_argument("--tickers", nargs="+", default=list(NIFTY_TOP_10))
    p.add_argument("--directions", nargs="+", default=["long", "short"])
    p.add_argument("--n-permutations", type=int, default=10000)
    p.add_argument("--rng-seed", type=int, default=42)
    p.add_argument("--out-root", type=Path, default=RUN_ROOT)
    args = p.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    run(
        tickers=args.tickers,
        directions=args.directions,
        n_permutations=args.n_permutations,
        rng_seed=args.rng_seed,
        out_root=args.out_root,
    )


if __name__ == "__main__":
    main()
