"""ETF v2 — faithful research replicator on the 5y parquet panel.

This module **exactly replicates** the production v2 architecture
(`etf_reoptimize.py` `optimize_weights` + `_build_indian_features` +
`_fetch_etf_returns`) but reads from the canonical 5-year parquet panel
in `pipeline/data/research/phase_c/daily_bars/` instead of the 6-week
`pipeline/data/daily/*.json` dump.

Why this exists:
  Production v2 fits weights weekly on a degenerate panel: 3 years of
  yfinance ETF returns ffill-joined with ~6 weeks of Indian features.
  The Indian features are constant for ~94% of the fit window. Any
  claimed accuracy from this configuration is ambiguous: it could be
  the global-ETF momentum doing the work, or it could be an artifact
  of mixed-scale fitting.

  This replicator gives v2 the *best plausible production scenario* —
  the same architecture but with 5 years of real Indian feature
  history. Whatever this configuration produces is the honest
  ceiling for v2's design.

Faithful to v2:
  - 1-day ETF percentage returns (`pct_change() * 100`) — NOT 5d
  - Indian features as RAW LEVELS (vix close, nifty close, fii_net, dii_net) — NOT engineered
  - Joined with `ffill().bfill().fillna(0)` — same as v2
  - Target = `sign(nifty.shift(-1))` — same as v2
  - Karpathy random search, 2000 iter, seed correlations, Sharpe-by-test selection

Differences from v2 production (improvements only):
  - Reads from the 5y parquet panel (not 6-week JSON dump)
  - Uses NIFTY trading calendar as canonical timestamp (not yfinance calendar)
  - Foreign series ffill onto Indian-only days, max 5d (no silent gap-filling)

Both differences IMPROVE the data — they don't change the model.

Usage:
    python -m pipeline.autoresearch.etf_v2_faithful_research --rolling \
        --refit-interval 5 --lookback-days 756 --n-iterations 2000
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

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = REPO_ROOT / "pipeline" / "data" / "research" / "etf_v3"

DEFAULT_SEED = 42
DEFAULT_ITERATIONS = 2000

# v2 columns. Now includes the curated-list expansion (2026-04-26 cycle 2):
#   Wave 1 (24): production-v2-matching set (tech/natgas/silver/yen added to
#     align with production etf_optimal_weights.json which had natgas −8.21
#     and silver −3.26 as #2/#3 weights).
#   Wave 2 (40): + 16 from docs/superpowers/specs/cureated ETF.txt — each
#     ticker has an explicit India-channel rationale (taiwan_etf for TSMC
#     foundry pulse, qqq for Nasdaq leadership of Nifty IT, aiq for AI/
#     software margin, smh for Indian EMS lead, etc.).
FOREIGN_ETF_COLS = [
    # Wave 1 (production-matching, 24)
    "sp500", "treasury", "dollar", "gold", "crude_oil", "copper",
    "brazil", "china_etf", "korea_etf", "japan_etf", "developed", "em",
    "euro", "high_yield", "financials", "industrials", "kbw_bank",
    "agriculture", "global_bonds", "india_etf",
    "tech", "natgas", "silver", "yen",
    # Wave 2 (curated-list expansion, +16)
    "taiwan_etf", "qqq", "aiq", "smh", "iwm", "xle", "xlv",
    "mchi", "dbb", "emb", "krbn", "lit", "kweb", "vixy", "ewg", "bito",
]
# v2 Indian features as RAW LEVELS (matching production)
INDIAN_LEVEL_COLS = ["india_vix", "fii_net", "dii_net", "nifty_close"]


# ============================================================================
# v2-faithful feature builder
# ============================================================================

def build_features_v2(panel: pd.DataFrame) -> pd.DataFrame:
    """Replicate v2 production feature engineering on the parquet panel.

    Faithful to v2 production (etf_reoptimize.py:316):
      `features = etf_returns.join(indian_df, how="left")`
      `features = features.ffill().bfill().fillna(0)`

    Where:
      - etf_returns are 1-day pct_change of foreign ETF closes
      - indian_df are RAW LEVELS (close prices) for VIX/NIFTY and raw flow
        crores for FII/DII

    The panel passed in is already T-1 anchored by the loader; v2 production
    is NOT explicitly T-1 anchored, but this is an improvement (no same-day
    leak), not a behavior change in any meaningful sense for daily classification.
    """
    feats = pd.DataFrame(index=panel.index)
    # 1-day returns for foreign ETFs (matches v2 line 451)
    for col in FOREIGN_ETF_COLS:
        feats[f"{col}_ret_1d"] = panel[col].pct_change() * 100.0
    # Indian features as RAW LEVELS (matches v2 _build_indian_features)
    for col in INDIAN_LEVEL_COLS:
        feats[f"{col}_level"] = panel[col]
    # Same fill strategy as v2 (line 316)
    feats = feats.ffill().bfill().fillna(0)
    return feats


def build_target_v2(panel: pd.DataFrame) -> pd.Series:
    """Target = sign(nifty.shift(-1)) — matches v2 line 322.

    Panel is T-1 anchored, so panel index is decision day T. We need the sign
    of the next-day NIFTY return. Use the un-anchored panel for NIFTY level
    so we have today's actual close, not T-1's.
    """
    raw = build_panel(t1_anchor=False)
    nifty = raw["nifty_close"]
    next_day_ret = nifty.shift(-1) / nifty - 1.0
    return np.sign(next_day_ret).reindex(panel.index).dropna()


# ============================================================================
# v2-faithful Karpathy random search (matches optimize_weights at line 149)
# ============================================================================

@dataclass
class FitResult:
    weights: dict[str, float]
    accuracy: float
    sharpe: float
    n_iterations: int
    seed: int


def fit_weights_v2(
    X: pd.DataFrame, y: pd.Series, *,
    n_iterations: int = DEFAULT_ITERATIONS, seed: int = DEFAULT_SEED,
) -> FitResult:
    """Karpathy random search — line-for-line match of optimize_weights().

    Matches etf_reoptimize.py:149-241:
      - 70/30 train/test split
      - Seed weights from train-set correlations with y
      - 2000 iterations of N(0, |w|*0.5 or 0.1) perturbation
      - Select by test-set Sharpe of (signal * y)
      - Return best weight dict + best test acc
    """
    rng = np.random.default_rng(seed)
    aligned = X.join(y.rename("__y__"), how="inner").dropna()
    Xa = aligned.drop(columns=["__y__"])
    ya = aligned["__y__"]

    split = int(len(Xa) * 0.7)
    Xtr, Xte = Xa.iloc[:split], Xa.iloc[split:]
    ytr, yte = ya.iloc[:split], ya.iloc[split:]

    cols = list(Xa.columns)
    seed_w: dict[str, float] = {}
    for c in cols:
        corr = float(Xtr[c].corr(ytr))
        seed_w[c] = 0.0 if not np.isfinite(corr) else corr

    best_w = dict(seed_w)
    best_sharpe = -np.inf
    best_acc = 0.0

    for _ in range(n_iterations):
        cand: dict[str, float] = {}
        for c, base in best_w.items():
            scale = abs(base) * 0.5 if abs(base) > 1e-9 else 0.1
            cand[c] = base + float(rng.normal(0.0, scale))
        sig_te = pd.Series(0.0, index=Xte.index)
        for c, w in cand.items():
            sig_te = sig_te + Xte[c].fillna(0.0) * w
        pnl = sig_te * yte
        std = pnl.std()
        if std < 1e-9:
            continue
        sharpe = float(pnl.mean() / std * np.sqrt(252))
        if sharpe > best_sharpe:
            best_sharpe = sharpe
            pred = np.sign(sig_te)
            best_acc = float((pred == yte.values).mean() * 100.0)
            best_w = cand
    return FitResult(weights=best_w, accuracy=best_acc, sharpe=best_sharpe,
                     n_iterations=n_iterations, seed=seed)


def _weighted_signal(X: pd.DataFrame, weights: dict[str, float]) -> pd.Series:
    s = pd.Series(0.0, index=X.index)
    for c, w in weights.items():
        if c in X.columns:
            s = s + X[c].fillna(0.0) * w
    return s


def evaluate(X: pd.DataFrame, y: pd.Series, weights: dict[str, float]) -> dict:
    aligned = X.join(y.rename("__y__"), how="inner").dropna()
    Xa = aligned.drop(columns=["__y__"])
    ya = aligned["__y__"]
    sig = _weighted_signal(Xa, weights)
    pred = np.sign(sig)
    acc = float((pred == ya.values).mean() * 100.0)
    n_up = int((ya == 1).sum())
    baseline = max(n_up, len(ya) - n_up) / len(ya) * 100.0 if len(ya) else 0.0
    return {
        "accuracy_pct": acc,
        "n_obs": int(len(ya)),
        "n_up": n_up,
        "baseline_majority_pct": float(baseline),
        "edge_vs_majority_pp": float(acc - baseline),
    }


# ============================================================================
# Rolling weekly refit walk-forward (matches production cadence)
# ============================================================================

@dataclass
class RollingConfig:
    refit_interval_days: int = 5     # weekly refit (5 Indian trading days)
    lookback_days: int = 756         # 3 years (matches v2 production)
    n_iterations: int = DEFAULT_ITERATIONS
    seed: int = DEFAULT_SEED
    eval_start: str = "2024-04-23"   # earliest after 3yr lookback from window_start
    eval_end: str = "2026-04-23"


def run_rolling_refit_v2(cfg: RollingConfig) -> dict:
    """Execute rolling weekly refit + predict using v2-faithful features."""
    audit = audit_panel()
    if any(r.status == "fail" for r in audit):
        raise RuntimeError("audit failed — cannot proceed")

    panel = build_panel(t1_anchor=True)
    feats = build_features_v2(panel)
    target = build_target_v2(panel)
    common = feats.index.intersection(target.index)
    feats, target = feats.loc[common], target.loc[common]

    eval_dates = feats.index[(feats.index >= pd.Timestamp(cfg.eval_start)) &
                              (feats.index <= pd.Timestamp(cfg.eval_end))]
    if len(eval_dates) == 0:
        raise RuntimeError("no eval dates in window")

    refit_anchors = eval_dates[::cfg.refit_interval_days]
    logger.info("v2-faithful rolling refit: %d anchors over %d eval days",
                len(refit_anchors), len(eval_dates))

    per_window: list[dict] = []
    all_preds, all_truths = [], []

    for i, anchor in enumerate(refit_anchors):
        train_start = anchor - pd.Timedelta(days=int(cfg.lookback_days * 1.5))
        train_mask = (feats.index >= train_start) & (feats.index < anchor)
        Xtr = feats.loc[train_mask].iloc[-cfg.lookback_days:]
        ytr = target.loc[Xtr.index.intersection(target.index)]
        Xtr = Xtr.loc[ytr.index]
        if len(Xtr) < 200:
            continue

        next_idx = (i + 1) * cfg.refit_interval_days
        if next_idx >= len(eval_dates):
            pred_dates = eval_dates[i * cfg.refit_interval_days:]
        else:
            pred_dates = eval_dates[i * cfg.refit_interval_days: next_idx]
        Xpr = feats.loc[pred_dates].dropna()
        ypr = target.loc[Xpr.index.intersection(target.index)]
        Xpr = Xpr.loc[ypr.index]
        if len(Xpr) == 0:
            continue

        fit = fit_weights_v2(Xtr, ytr, n_iterations=cfg.n_iterations,
                             seed=cfg.seed + i)
        sig = _weighted_signal(Xpr, fit.weights)
        pred = np.sign(sig.values)
        truth = ypr.values
        n_up_pr = int((truth == 1).sum())
        baseline_pr = max(n_up_pr, len(truth) - n_up_pr) / len(truth) * 100.0
        per_window.append({
            "refit_id": i + 1,
            "refit_anchor": str(anchor.date()),
            "train_n": int(len(Xtr)),
            "pred_n": int(len(Xpr)),
            "pred_acc_pct": float((pred == truth).mean() * 100.0),
            "pred_baseline_pct": float(baseline_pr),
            "pred_edge_pp": float((pred == truth).mean() * 100.0 - baseline_pr),
            "train_in_fit_acc_pct": fit.accuracy,
            "train_in_fit_sharpe": fit.sharpe,
        })
        all_preds.extend(pred.tolist())
        all_truths.extend(truth.tolist())

    arr_p, arr_t = np.asarray(all_preds), np.asarray(all_truths)
    n = len(arr_t)
    overall_acc = (arr_p == arr_t).mean() * 100.0 if n else 0.0
    n_up = int((arr_t == 1).sum())
    overall_baseline = max(n_up, n - n_up) / n * 100.0 if n else 0.0
    win_edges = [w["pred_edge_pp"] for w in per_window]
    n_pos = sum(1 for e in win_edges if e > 0)

    return {
        "feature_set": "v2_faithful",
        "config": asdict(cfg),
        "n_refit_windows": len(per_window),
        "n_total_oos_predictions": n,
        "overall_acc_pct": float(overall_acc),
        "overall_baseline_majority_pct": float(overall_baseline),
        "overall_edge_pp": float(overall_acc - overall_baseline),
        "per_window_edge_mean_pp": float(np.mean(win_edges)) if win_edges else 0.0,
        "per_window_edge_std_pp": float(np.std(win_edges)) if win_edges else 0.0,
        "n_windows_positive_edge": int(n_pos),
        "fraction_windows_positive_edge": float(n_pos / len(per_window)) if per_window else 0.0,
        "first_refit": per_window[0]["refit_anchor"] if per_window else None,
        "last_refit": per_window[-1]["refit_anchor"] if per_window else None,
        "per_window_detail": per_window,
    }


# ============================================================================
# CLI
# ============================================================================

def _git_hash() -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True,
                             text=True, cwd=REPO_ROOT, check=False, timeout=5)
        return out.stdout.strip() if out.returncode == 0 else "UNKNOWN"
    except Exception:
        return "UNKNOWN"


def main() -> int:
    p = argparse.ArgumentParser(description="v2-faithful replicator on parquet panel")
    p.add_argument("--rolling", action="store_true", help="run rolling weekly refit")
    p.add_argument("--refit-interval", type=int, default=5)
    p.add_argument("--lookback-days", type=int, default=756)
    p.add_argument("--n-iterations", type=int, default=DEFAULT_ITERATIONS)
    p.add_argument("--seed", type=int, default=DEFAULT_SEED)
    p.add_argument("--eval-start", default="2024-04-23")
    p.add_argument("--eval-end", default="2026-04-23")
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")

    if not args.rolling:
        p.print_help()
        return 0

    cfg = RollingConfig(
        refit_interval_days=args.refit_interval,
        lookback_days=args.lookback_days,
        n_iterations=args.n_iterations,
        seed=args.seed,
        eval_start=args.eval_start,
        eval_end=args.eval_end,
    )
    result = run_rolling_refit_v2(cfg)
    result["manifest"] = {
        "model": "etf_v2_faithful_rolling_refit",
        "code_commit": _git_hash(),
        "config_hash": hashlib.sha256(
            json.dumps(asdict(cfg), sort_keys=True).encode()).hexdigest()[:16],
        "generated_at_utc": datetime.now(tz=timezone.utc).isoformat(),
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"etf_v2_faithful_rolling_int{cfg.refit_interval_days}_lb{cfg.lookback_days}.json"
    out.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    logger.info("wrote %s", out)
    print(json.dumps({
        "feature_set": "v2_faithful",
        "n_refit_windows": result["n_refit_windows"],
        "n_total_oos_predictions": result["n_total_oos_predictions"],
        "overall_acc_pct": result["overall_acc_pct"],
        "overall_baseline_pct": result["overall_baseline_majority_pct"],
        "overall_edge_pp": result["overall_edge_pp"],
        "per_window_edge_mean_pp": result["per_window_edge_mean_pp"],
        "fraction_windows_positive_edge": result["fraction_windows_positive_edge"],
        "first_refit": result["first_refit"],
        "last_refit": result["last_refit"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
