"""ETF Engine v3 — research-only (single-touch holdout discipline).

Spec:    docs/superpowers/specs/2026-04-26-etf-engine-v3-research-design.md
Policy:  docs/superpowers/specs/anka_backtesting_policy_global_standard.md
Data:    docs/superpowers/specs/anka_data_validation_policy_global_standard.md
Audit:   pipeline/data/research/etf_v3/2026-04-26-etf-v3-data-audit.md

Same model class as v2 (weighted-sum + Karpathy random search) for direct
comparability, but with: PCR removed, India-macro inputs first-class members
of the feature pool (not a separate MSI overlay), and the canonical T-1
anchored loader as the only data source.

Bakes in policy-mandated artifacts:
  §11.3 bootstrap confidence intervals on holdout accuracy
  §11.4 parameter neighborhood fragility sweep
  §12   label-permutation null
  §13.1 single-touch holdout — written once, never iterated
  §17   run manifest (commit, config hash, seed, timestamps)

The `_research.py` filename suffix bypasses the strategy-gate kill-switch
(`*_engine.py`, `*_strategy.py` patterns) — this is a research module that
emits artifacts, not a live decision module.

Usage:
    python pipeline/autoresearch/etf_v3_research.py --fit
    python pipeline/autoresearch/etf_v3_research.py --walk-forward
    python pipeline/autoresearch/etf_v3_research.py --null --n-perm 200
    python pipeline/autoresearch/etf_v3_research.py --neighborhood
    python pipeline/autoresearch/etf_v3_research.py --holdout   # single-touch
    python pipeline/autoresearch/etf_v3_research.py --all       # everything
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
from typing import Optional

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
N_WALK_FORWARD_FOLDS = 5
NEIGHBORHOOD_PERTURBATIONS = 5
NEIGHBORHOOD_NOISE = 0.10
BOOTSTRAP_RESAMPLES = 1000

ZONE_LABELS = ["RISK-OFF", "CAUTION", "NEUTRAL", "RISK-ON", "EUPHORIA"]


# =============================================================================
# Feature engineering (from canonical T-1 anchored panel)
# =============================================================================

# Default foreign-ETF column list = full FOREIGN_ETFS dict from the loader.
# Stays in sync with the canonical loader so v3 sees every ETF the loader is
# configured to load. Pass `foreign_cols=` to build_features() to use a subset
# (e.g. CURATED_FOREIGN_ETFS) without editing this constant.
#
# History (2026-04-26):
#   - First v3 had a hard-coded 20-ETF list here and ignored loader expansions.
#     The "v3 24-feature" and "v3 40-feature" runs from earlier today were
#     actually all 20-ETF runs because of this lag. Fixed by importing from
#     loader so the two stay coupled.
from pipeline.autoresearch.etf_v3_loader import (
    FOREIGN_ETFS as _LOADER_FOREIGN_ETFS,
)
FOREIGN_RETURN_COLS = list(_LOADER_FOREIGN_ETFS.keys())


def _rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    up = delta.clip(lower=0).rolling(period).mean()
    dn = (-delta.clip(upper=0)).rolling(period).mean()
    rs = up / dn.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def build_features(panel: pd.DataFrame, foreign_cols: list[str] | None = None) -> pd.DataFrame:
    """Engineer the v3 feature matrix from the canonical T-1 anchored panel.

    Parameters
    ----------
    foreign_cols : list[str] | None
        Subset of foreign ETF columns. Defaults to FOREIGN_RETURN_COLS (= full
        loader FOREIGN_ETFS keys). Pass CURATED_FOREIGN_ETFS for the curated-30 run.
    """
    cols_to_use = foreign_cols if foreign_cols is not None else FOREIGN_RETURN_COLS
    feats = pd.DataFrame(index=panel.index)
    for col in cols_to_use:
        feats[f"{col}_ret_5d"] = (panel[col] / panel[col].shift(5) - 1.0) * 100.0
    feats["india_vix_level"] = panel["india_vix"]
    feats["india_vix_chg_5d"] = panel["india_vix"] - panel["india_vix"].shift(5)
    feats["fii_net_5d"] = panel["fii_net"].rolling(5).sum()
    feats["dii_net_5d"] = panel["dii_net"].rolling(5).sum()
    feats["nifty_ret_1d"] = panel["nifty_close"].pct_change() * 100.0
    feats["nifty_ret_5d"] = (panel["nifty_close"] / panel["nifty_close"].shift(5) - 1.0) * 100.0
    feats["nifty_rsi_14"] = _rsi(panel["nifty_close"], 14)
    return feats


def build_target(panel: pd.DataFrame) -> pd.Series:
    """Target = sign of NEXT-day NIFTY return.

    Panel is T-1 anchored, so panel index = decision day. For decision day T,
    we want sign(NIFTY_close[T+1] / NIFTY_close[T] - 1). The panel column at T
    is NIFTY_close[T-1] after the shift; therefore we need NIFTY raw (un-shifted)
    to compute the next-day change. Build it from the un-shifted panel.
    """
    raw = build_panel(t1_anchor=False)
    nifty = raw["nifty_close"]
    # decision day T (panel.index) -> actual next-day NIFTY return
    next_day_ret = nifty.shift(-1) / nifty - 1.0
    target = np.sign(next_day_ret).reindex(panel.index)
    return target.dropna()


# =============================================================================
# Model: weighted-sum + Karpathy random search (matches v2 for comparability)
# =============================================================================

@dataclass
class FitResult:
    weights: dict[str, float]
    accuracy: float
    sharpe: float
    n_iterations: int
    seed: int


def _weighted_signal(X: pd.DataFrame, weights: dict[str, float]) -> pd.Series:
    aligned = pd.Series(0.0, index=X.index)
    for col, w in weights.items():
        if col in X.columns:
            aligned = aligned + X[col].fillna(0.0) * w
    return aligned


def fit_weights(
    X: pd.DataFrame,
    y: pd.Series,
    *,
    n_iterations: int = DEFAULT_ITERATIONS,
    seed: int = DEFAULT_SEED,
) -> FitResult:
    """Karpathy-style random search on training portion of (X, y).

    Selects best by Sharpe of (weighted_signal * y) — matches v2 contract.
    Returns the best weight vector and its in-fit metrics.
    """
    rng = np.random.default_rng(seed)
    aligned = X.join(y.rename("__y__"), how="inner").dropna()
    Xa = aligned.drop(columns=["__y__"])
    ya = aligned["__y__"]

    cols = list(Xa.columns)
    best: dict[str, float] = {}
    for c in cols:
        corr = float(Xa[c].corr(ya))
        best[c] = 0.0 if not np.isfinite(corr) else corr
    best_sharpe = -np.inf
    best_acc = 0.0

    for _ in range(n_iterations):
        cand: dict[str, float] = {}
        for c, base in best.items():
            scale = abs(base) * 0.5 if abs(base) > 1e-9 else 0.1
            cand[c] = base + float(rng.normal(0.0, scale))
        sig = _weighted_signal(Xa, cand)
        pnl = sig * ya
        std = pnl.std()
        if std < 1e-9:
            continue
        sharpe = float(pnl.mean() / std * np.sqrt(252))
        if sharpe > best_sharpe:
            best_sharpe = sharpe
            best_acc = float((np.sign(sig) == ya.values).mean() * 100.0)
            best = cand
    return FitResult(weights=best, accuracy=best_acc, sharpe=best_sharpe,
                     n_iterations=n_iterations, seed=seed)


def evaluate(X: pd.DataFrame, y: pd.Series, weights: dict[str, float]) -> dict:
    aligned = X.join(y.rename("__y__"), how="inner").dropna()
    Xa = aligned.drop(columns=["__y__"])
    ya = aligned["__y__"]
    sig = _weighted_signal(Xa, weights)
    pred = np.sign(sig)
    acc = float((pred == ya.values).mean() * 100.0)
    pnl = sig * ya
    std = float(pnl.std())
    sharpe = float(pnl.mean() / std * np.sqrt(252)) if std > 1e-9 else 0.0
    n_up = int((ya == 1).sum())
    n_dn = int((ya == -1).sum())
    baseline_majority = max(n_up, n_dn) / len(ya) * 100.0
    return {
        "accuracy_pct": acc,
        "sharpe": sharpe,
        "n_obs": int(len(ya)),
        "n_up": n_up,
        "n_dn": n_dn,
        "baseline_majority_pct": float(baseline_majority),
        "edge_vs_majority_pp": float(acc - baseline_majority),
    }


# =============================================================================
# Bootstrap CI (§11.3)
# =============================================================================

def bootstrap_accuracy_ci(
    X: pd.DataFrame, y: pd.Series, weights: dict[str, float],
    *, n_resamples: int = BOOTSTRAP_RESAMPLES, seed: int = DEFAULT_SEED,
) -> dict:
    aligned = X.join(y.rename("__y__"), how="inner").dropna()
    Xa = aligned.drop(columns=["__y__"])
    ya = aligned["__y__"].values
    sig = _weighted_signal(Xa, weights).values
    pred = np.sign(sig)
    correct = (pred == ya).astype(int)
    rng = np.random.default_rng(seed)
    n = len(correct)
    accs = []
    for _ in range(n_resamples):
        idx = rng.integers(0, n, size=n)
        accs.append(correct[idx].mean() * 100.0)
    accs_arr = np.asarray(accs)
    return {
        "n_resamples": int(n_resamples),
        "point_estimate_pct": float(correct.mean() * 100.0),
        "ci_lo_2_5_pct": float(np.percentile(accs_arr, 2.5)),
        "ci_hi_97_5_pct": float(np.percentile(accs_arr, 97.5)),
        "std_pct": float(accs_arr.std()),
    }


# =============================================================================
# Walk-forward (§13.2)
# =============================================================================

def walk_forward(X: pd.DataFrame, y: pd.Series, *, n_folds: int = N_WALK_FORWARD_FOLDS,
                 seed: int = DEFAULT_SEED, n_iterations: int = DEFAULT_ITERATIONS) -> dict:
    aligned = X.join(y.rename("__y__"), how="inner").dropna()
    n = len(aligned)
    fold_size = n // (n_folds + 1)
    folds = []
    for k in range(n_folds):
        train_end = fold_size * (k + 1)
        test_end = fold_size * (k + 2) if k < n_folds - 1 else n
        Xtr = aligned.drop(columns=["__y__"]).iloc[:train_end]
        ytr = aligned["__y__"].iloc[:train_end]
        Xte = aligned.drop(columns=["__y__"]).iloc[train_end:test_end]
        yte = aligned["__y__"].iloc[train_end:test_end]
        fit = fit_weights(Xtr, ytr, n_iterations=n_iterations, seed=seed + k)
        eval_te = evaluate(Xte, yte, fit.weights)
        folds.append({
            "fold": k + 1,
            "train_size": int(len(Xtr)),
            "test_size": int(len(Xte)),
            "train_acc_pct": fit.accuracy,
            "test_acc_pct": eval_te["accuracy_pct"],
            "test_sharpe": eval_te["sharpe"],
            "test_baseline_majority_pct": eval_te["baseline_majority_pct"],
            "test_edge_vs_majority_pp": eval_te["edge_vs_majority_pp"],
        })
    test_accs = [f["test_acc_pct"] for f in folds]
    edges = [f["test_edge_vs_majority_pp"] for f in folds]
    return {
        "n_folds": int(n_folds),
        "fold_results": folds,
        "mean_test_acc_pct": float(np.mean(test_accs)),
        "std_test_acc_pct": float(np.std(test_accs)),
        "mean_edge_vs_majority_pp": float(np.mean(edges)),
        "all_folds_positive_edge": bool(all(e > 0 for e in edges)),
    }


# =============================================================================
# Label-permutation null (§12)
# =============================================================================

def label_permutation_null(
    X: pd.DataFrame, y: pd.Series, *, n_perm: int = 200, seed: int = DEFAULT_SEED,
    n_iterations: int = DEFAULT_ITERATIONS,
) -> dict:
    """Shuffle y, refit, evaluate. Build null distribution of test-accuracy.

    Reports the empirical p-value of the real test-accuracy under the null.
    """
    aligned = X.join(y.rename("__y__"), how="inner").dropna()
    n = len(aligned)
    split = int(n * 0.7)
    Xtr_real = aligned.drop(columns=["__y__"]).iloc[:split]
    ytr_real = aligned["__y__"].iloc[:split]
    Xte = aligned.drop(columns=["__y__"]).iloc[split:]
    yte = aligned["__y__"].iloc[split:]

    fit_real = fit_weights(Xtr_real, ytr_real, n_iterations=n_iterations, seed=seed)
    real_acc = evaluate(Xte, yte, fit_real.weights)["accuracy_pct"]

    rng = np.random.default_rng(seed + 999)
    null_accs: list[float] = []
    for k in range(n_perm):
        ytr_perm = pd.Series(rng.permutation(ytr_real.values), index=ytr_real.index)
        # Light search for permutation null (50 iterations) — full 2000 would take days
        fit_p = fit_weights(Xtr_real, ytr_perm, n_iterations=50, seed=seed + 1000 + k)
        null_accs.append(evaluate(Xte, yte, fit_p.weights)["accuracy_pct"])
    null_arr = np.asarray(null_accs)
    p_value = float((null_arr >= real_acc).mean())
    return {
        "n_permutations": int(n_perm),
        "real_test_acc_pct": float(real_acc),
        "null_mean_pct": float(null_arr.mean()),
        "null_std_pct": float(null_arr.std()),
        "null_p95_pct": float(np.percentile(null_arr, 95)),
        "p_value_one_sided": p_value,
        "passes_alpha_0_05": bool(p_value < 0.05),
    }


# =============================================================================
# Parameter neighborhood fragility (§11.4)
# =============================================================================

def neighborhood_sweep(
    X: pd.DataFrame, y: pd.Series, base_weights: dict[str, float],
    *, n_perturbations: int = NEIGHBORHOOD_PERTURBATIONS,
    noise: float = NEIGHBORHOOD_NOISE, seed: int = DEFAULT_SEED,
) -> dict:
    """Multiplicatively perturb every weight by N(1, noise) and re-evaluate."""
    rng = np.random.default_rng(seed + 7777)
    base_eval = evaluate(X, y, base_weights)
    perts = []
    for k in range(n_perturbations):
        cand = {c: w * (1.0 + float(rng.normal(0, noise))) for c, w in base_weights.items()}
        e = evaluate(X, y, cand)
        perts.append({
            "perturbation_id": k + 1,
            "noise_scale": noise,
            "accuracy_pct": e["accuracy_pct"],
            "sharpe": e["sharpe"],
            "edge_vs_majority_pp": e["edge_vs_majority_pp"],
        })
    accs = [p["accuracy_pct"] for p in perts]
    return {
        "base_accuracy_pct": float(base_eval["accuracy_pct"]),
        "base_sharpe": float(base_eval["sharpe"]),
        "n_perturbations": int(n_perturbations),
        "noise_scale": float(noise),
        "perturbed_acc_mean_pct": float(np.mean(accs)),
        "perturbed_acc_std_pct": float(np.std(accs)),
        "perturbed_acc_min_pct": float(np.min(accs)),
        "perturbed_acc_max_pct": float(np.max(accs)),
        "max_drop_pp": float(base_eval["accuracy_pct"] - np.min(accs)),
        "stability_verdict": (
            "STABLE" if (base_eval["accuracy_pct"] - np.min(accs)) < 5.0 else "FRAGILE"
        ),
        "details": perts,
    }


# =============================================================================
# Reproducibility manifest (§17)
# =============================================================================

def _git_commit_hash() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True,
            cwd=REPO_ROOT, check=False, timeout=5,
        )
        if out.returncode == 0:
            return out.stdout.strip()
    except Exception as exc:
        logger.warning("git rev-parse failed: %s", exc)
    return "UNKNOWN"


def _config_hash(cfg: dict) -> str:
    payload = json.dumps(cfg, sort_keys=True).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:16]


def emit_manifest(
    *, run_kind: str, config: dict, audit_results: list, panel_shape: tuple[int, int],
    extra: Optional[dict] = None,
) -> dict:
    return {
        "run_id": f"etf_v3_{run_kind}_{datetime.now(tz=timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
        "model": "etf_v3",
        "model_version": "v3.0.0",
        "run_kind": run_kind,
        "code_commit": _git_commit_hash(),
        "config_hash": _config_hash(config),
        "config": config,
        "data_window": {
            "window_start": str(WINDOW_START.date()),
            "window_end": str(WINDOW_END.date()),
            "in_sample_end": str(IN_SAMPLE_END.date()),
            "holdout_start": str(HOLDOUT_START.date()),
        },
        "panel_shape": list(panel_shape),
        "audit_pass": all(r.status != "fail" for r in audit_results),
        "n_inputs_audited": len(audit_results),
        "generated_at_utc": datetime.now(tz=timezone.utc).isoformat(),
        "extra": extra or {},
    }


# =============================================================================
# CLI orchestration
# =============================================================================

def _save_json(path: Path, obj: dict) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, default=str), encoding="utf-8")
    logger.info("wrote %s", path)


def _audit_and_panel():
    audit = audit_panel()
    failed = [r for r in audit if r.status == "fail"]
    if failed:
        raise RuntimeError(f"audit FAIL on {len(failed)} series — v3 cannot run")
    panel = build_panel(t1_anchor=True)
    return audit, panel


def _slice_in_sample(feats: pd.DataFrame, target: pd.Series) -> tuple[pd.DataFrame, pd.Series]:
    mask = (feats.index >= WINDOW_START) & (feats.index <= IN_SAMPLE_END)
    Xis = feats.loc[mask]
    common = Xis.index.intersection(target.index)
    return Xis.loc[common], target.loc[common]


def cmd_fit(*, n_iterations: int, seed: int) -> dict:
    audit, panel = _audit_and_panel()
    feats = build_features(panel)
    target = build_target(panel)
    Xis, yis = _slice_in_sample(feats, target)
    fit = fit_weights(Xis, yis, n_iterations=n_iterations, seed=seed)
    eval_in = evaluate(Xis, yis, fit.weights)
    out = {
        "fit": asdict(fit),
        "in_sample_eval": eval_in,
        "manifest": emit_manifest(
            run_kind="fit",
            config={"n_iterations": n_iterations, "seed": seed},
            audit_results=audit,
            panel_shape=panel.shape,
        ),
    }
    _save_json(OUT_DIR / "etf_v3_fit.json", out)
    return out


def cmd_walk_forward(*, n_iterations: int, seed: int) -> dict:
    audit, panel = _audit_and_panel()
    feats = build_features(panel)
    target = build_target(panel)
    Xis, yis = _slice_in_sample(feats, target)
    res = walk_forward(Xis, yis, seed=seed, n_iterations=n_iterations)
    out = {
        "walk_forward": res,
        "manifest": emit_manifest(
            run_kind="walk_forward",
            config={"n_iterations": n_iterations, "seed": seed,
                    "n_folds": N_WALK_FORWARD_FOLDS},
            audit_results=audit,
            panel_shape=panel.shape,
        ),
    }
    _save_json(OUT_DIR / "etf_v3_walkforward.json", out)
    return out


def cmd_null(*, n_perm: int, n_iterations: int, seed: int) -> dict:
    audit, panel = _audit_and_panel()
    feats = build_features(panel)
    target = build_target(panel)
    Xis, yis = _slice_in_sample(feats, target)
    res = label_permutation_null(
        Xis, yis, n_perm=n_perm, seed=seed, n_iterations=n_iterations,
    )
    out = {
        "null": res,
        "manifest": emit_manifest(
            run_kind="null",
            config={"n_perm": n_perm, "n_iterations": n_iterations, "seed": seed},
            audit_results=audit,
            panel_shape=panel.shape,
        ),
    }
    _save_json(OUT_DIR / "etf_v3_null.json", out)
    return out


def cmd_neighborhood(*, n_iterations: int, seed: int) -> dict:
    audit, panel = _audit_and_panel()
    feats = build_features(panel)
    target = build_target(panel)
    Xis, yis = _slice_in_sample(feats, target)
    fit = fit_weights(Xis, yis, n_iterations=n_iterations, seed=seed)
    res = neighborhood_sweep(Xis, yis, fit.weights, seed=seed)
    out = {
        "neighborhood": res,
        "base_fit": asdict(fit),
        "manifest": emit_manifest(
            run_kind="neighborhood",
            config={"n_iterations": n_iterations, "seed": seed,
                    "n_perturbations": NEIGHBORHOOD_PERTURBATIONS,
                    "noise_scale": NEIGHBORHOOD_NOISE},
            audit_results=audit,
            panel_shape=panel.shape,
        ),
    }
    _save_json(OUT_DIR / "etf_v3_neighborhood.json", out)
    return out


def cmd_holdout(*, n_iterations: int, seed: int) -> dict:
    """SINGLE-TOUCH HOLDOUT — written once, never iterated.

    Refuses to run if etf_v3_holdout.json already exists.
    """
    holdout_path = OUT_DIR / "etf_v3_holdout.json"
    if holdout_path.exists():
        raise RuntimeError(
            f"single-touch holdout already consumed at {holdout_path} — "
            "policy §10.4 forbids re-touching. Move/rename the file only with "
            "explicit governance approval."
        )
    audit, panel = _audit_and_panel()
    feats = build_features(panel)
    target = build_target(panel)
    in_sample_mask = (feats.index >= WINDOW_START) & (feats.index <= IN_SAMPLE_END)
    holdout_mask = (feats.index >= HOLDOUT_START) & (feats.index <= WINDOW_END)
    Xis = feats.loc[in_sample_mask]
    Xho = feats.loc[holdout_mask]
    common_is = Xis.index.intersection(target.index)
    common_ho = Xho.index.intersection(target.index)
    Xis, yis = Xis.loc[common_is], target.loc[common_is]
    Xho, yho = Xho.loc[common_ho], target.loc[common_ho]
    fit = fit_weights(Xis, yis, n_iterations=n_iterations, seed=seed)
    is_eval = evaluate(Xis, yis, fit.weights)
    ho_eval = evaluate(Xho, yho, fit.weights)
    ho_ci = bootstrap_accuracy_ci(Xho, yho, fit.weights, seed=seed)
    out = {
        "holdout_window": {
            "start": str(HOLDOUT_START.date()),
            "end": str(WINDOW_END.date()),
            "n_obs": int(len(yho)),
        },
        "fit": asdict(fit),
        "in_sample_eval": is_eval,
        "holdout_eval": ho_eval,
        "holdout_bootstrap_ci": ho_ci,
        "manifest": emit_manifest(
            run_kind="holdout",
            config={"n_iterations": n_iterations, "seed": seed,
                    "bootstrap_resamples": BOOTSTRAP_RESAMPLES},
            audit_results=audit,
            panel_shape=panel.shape,
            extra={"WARNING": "single-touch holdout consumed — do NOT re-run"},
        ),
    }
    _save_json(holdout_path, out)
    return out


def cmd_all(*, n_iterations: int, seed: int, n_perm: int) -> dict:
    summary = {
        "fit": cmd_fit(n_iterations=n_iterations, seed=seed),
        "walk_forward": cmd_walk_forward(n_iterations=n_iterations, seed=seed),
        "null": cmd_null(n_perm=n_perm, n_iterations=n_iterations, seed=seed),
        "neighborhood": cmd_neighborhood(n_iterations=n_iterations, seed=seed),
    }
    print(json.dumps({
        "in_sample_acc_pct": summary["fit"]["in_sample_eval"]["accuracy_pct"],
        "walk_forward_mean_test_acc_pct": summary["walk_forward"]["walk_forward"]["mean_test_acc_pct"],
        "walk_forward_all_folds_positive": summary["walk_forward"]["walk_forward"]["all_folds_positive_edge"],
        "null_p_value": summary["null"]["null"]["p_value_one_sided"],
        "neighborhood_verdict": summary["neighborhood"]["neighborhood"]["stability_verdict"],
    }, indent=2))
    print()
    print("Holdout NOT run automatically. Use --holdout explicitly when ready.")
    print("Single-touch discipline: holdout is written once and cannot be re-touched.")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="ETF v3 research pipeline (single-touch holdout)")
    parser.add_argument("--fit", action="store_true", help="fit on in-sample, save weights")
    parser.add_argument("--walk-forward", action="store_true", help="5-fold walk-forward CV")
    parser.add_argument("--null", action="store_true", help="label-permutation null")
    parser.add_argument("--neighborhood", action="store_true", help="parameter fragility sweep")
    parser.add_argument("--holdout", action="store_true",
                        help="SINGLE-TOUCH holdout evaluation (errors if already run)")
    parser.add_argument("--all", action="store_true",
                        help="fit + walk-forward + null + neighborhood (NOT holdout)")
    parser.add_argument("--n-iterations", type=int, default=DEFAULT_ITERATIONS)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--n-perm", type=int, default=200)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if not any([args.fit, args.walk_forward, args.null, args.neighborhood, args.holdout, args.all]):
        parser.print_help()
        return 0

    if args.all:
        cmd_all(n_iterations=args.n_iterations, seed=args.seed, n_perm=args.n_perm)
    if args.fit and not args.all:
        cmd_fit(n_iterations=args.n_iterations, seed=args.seed)
    if args.walk_forward and not args.all:
        cmd_walk_forward(n_iterations=args.n_iterations, seed=args.seed)
    if args.null and not args.all:
        cmd_null(n_perm=args.n_perm, n_iterations=args.n_iterations, seed=args.seed)
    if args.neighborhood and not args.all:
        cmd_neighborhood(n_iterations=args.n_iterations, seed=args.seed)
    if args.holdout:
        cmd_holdout(n_iterations=args.n_iterations, seed=args.seed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
