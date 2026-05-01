"""Karpathy 6-of-8 random-search runner — runs ONCE at registration freeze.

Spec section 8. Grid: 28 feature subsets * 4 alpha values * 4 thresholds = 448 cells.
Selection: highest in-sample Sharpe (post-S1) AND BH-FDR adjusted p < 0.05.
Fragility: post-S1 Sharpe >= 0.5 in BOTH calendar halves of training window.
Margin: chosen cell must beat regime-gated-no-Karpathy baseline by >= 0.3 Sharpe.

Training window: 2021-05-01 -> 2024-04-30 (3 years, locked at registration).

Output: pipeline/research/h_2026_05_01_phase_c_mr_karpathy/karpathy_chosen_cell.json
- feature_subset (list of 6 names)
- coefficients (Lasso L1 fit on the chosen subset)
- intercept
- threshold (qualifier cutoff)
- chosen_at (timestamp)

This is intended for execution on Contabo VPS (per the laptop=context, VPS=execution
architectural rule). On laptop it can be tested with --max-cells <N> for a smoke check;
the full grid is heavy.
"""
from __future__ import annotations

import argparse
import itertools
import json
import logging
import math
import statistics
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from .candidate_loader import (
    TRAIN_CLOSE,
    TRAIN_OPEN,
    Candidate,
    load_candidates,
    split_by_half,
)
from .feature_builder import (
    CACHE_PATH as FEATURE_CACHE_PATH,
    build_feature_cache,
    load_feature_cache,
    save_feature_cache,
)
from .feature_library import FEATURE_NAMES
from .mr_signal_generator import feature_subset_size

log = logging.getLogger("anka.h_2026_05_01.karpathy_search")

OUT_PATH = Path(__file__).resolve().parent / "karpathy_chosen_cell.json"
LOG_PATH = Path(__file__).resolve().parent / "karpathy_search_log.json"

ALPHA_GRID: tuple[float, ...] = (0.001, 0.01, 0.1, 1.0)
THRESHOLD_GRID: tuple[float, ...] = (0.0, 0.1, 0.2, 0.3)
TRAIN_HALF_SPLIT: str = "2022-10-31"
BH_FDR_ALPHA: float = 0.05
FRAGILITY_HALF_SHARPE_MIN: float = 0.5
MARGIN_DELTA_SHARPE_MIN: float = 0.3
COST_BPS_S1_PER_SIDE: float = 15.0
N_PERMUTATIONS: int = 10_000


def feature_subset_combinations() -> list[tuple[str, ...]]:
    """All C(8, 6) = 28 ordered subsets of FEATURE_NAMES."""
    return [tuple(sub) for sub in itertools.combinations(FEATURE_NAMES, feature_subset_size())]


def grid_size() -> int:
    return len(feature_subset_combinations()) * len(ALPHA_GRID) * len(THRESHOLD_GRID)


@dataclass
class CellResult:
    feature_subset: tuple[str, ...]
    alpha: float
    threshold: float
    n: int
    sharpe_S1: float
    p_value: float
    sharpe_first_half: float
    sharpe_second_half: float
    coefficients: dict[str, float] = field(default_factory=dict)
    intercept: float = 0.0


# ---------------- shared helpers --------------------------------------------

def _sharpe_per_trade_to_annualized(values: np.ndarray) -> float:
    if values.size < 2:
        return 0.0
    mean = float(values.mean())
    sd = float(values.std(ddof=1))
    if sd <= 0:
        return 0.0
    return mean / sd * math.sqrt(252.0)


def _post_s1_pnl(pnl_pct_net_replay: float) -> float:
    """Convert replay's pnl_pct_net (5 bps single-side cost) to S1 (15 bps single-side).

    The replay subtracts COST_BPS=5 on a single side. To restore gross then re-apply
    S1 single-side 15 bps total round-trip 30 bps, we add back 5 bps and subtract 30 bps.
    Net delta = -25 bps converted to fraction.
    """
    return pnl_pct_net_replay + (5.0 / 1e4) - (30.0 / 1e4)


def _permutation_p_value(values: np.ndarray, n_perms: int = N_PERMUTATIONS) -> float:
    """Two-sided permutation test on mean(values) by random sign-flip.

    Sign-flip is equivalent to LONG/SHORT label permutation within the (date, regime)
    bucket convention used in the spec section 12.
    """
    if values.size < 5:
        return 1.0
    observed = float(values.mean())
    rng = np.random.default_rng(20260501)
    null = np.empty(n_perms, dtype=np.float64)
    for i in range(n_perms):
        signs = rng.choice([-1.0, 1.0], size=values.size)
        null[i] = float((values * signs).mean())
    p = float((np.abs(null) >= abs(observed)).sum() + 1) / (n_perms + 1)
    return p


def _bh_fdr_pass(p_values: np.ndarray, alpha: float = BH_FDR_ALPHA) -> np.ndarray:
    """Benjamini-Hochberg adjustment. Returns boolean mask of cells that pass."""
    m = p_values.size
    if m == 0:
        return np.array([], dtype=bool)
    order = np.argsort(p_values)
    ranked = p_values[order]
    thresholds = np.arange(1, m + 1) / m * alpha
    passing = ranked <= thresholds
    if not passing.any():
        return np.zeros(m, dtype=bool)
    last_pass_idx = int(np.where(passing)[0].max())
    mask_in_rank = np.zeros(m, dtype=bool)
    mask_in_rank[: last_pass_idx + 1] = True
    out = np.zeros(m, dtype=bool)
    out[order] = mask_in_rank
    return out


# ---------------- core search -----------------------------------------------

def _materialize_features(rows: list[dict], subset: tuple[str, ...]) -> tuple[np.ndarray, np.ndarray, list[int]]:
    """Build (X, y, kept_idx) for the given feature subset.

    Drops events where any feature in the subset is None / NaN.
    """
    X_list: list[list[float]] = []
    y_list: list[float] = []
    kept: list[int] = []
    for i, row in enumerate(rows):
        vals = []
        ok = True
        for f in subset:
            v = row.get(f)
            if v is None or (isinstance(v, float) and v != v):
                ok = False
                break
            vals.append(float(v))
        if not ok:
            continue
        X_list.append(vals)
        y_list.append(_post_s1_pnl(row["pnl_pct_net"]))
        kept.append(i)
    if not X_list:
        return np.empty((0, len(subset))), np.empty(0), []
    return np.array(X_list), np.array(y_list), kept


def _evaluate_cell(
    rows: list[dict],
    subset: tuple[str, ...],
    alpha: float,
    threshold: float,
    *,
    half_split_date: str,
) -> CellResult:
    """Lasso-fit + threshold filter + Sharpe + fragility halves + permutation test."""
    from sklearn.linear_model import Lasso

    X, y, kept_idx = _materialize_features(rows, subset)
    if X.shape[0] < 10:
        return CellResult(
            feature_subset=subset, alpha=alpha, threshold=threshold,
            n=0, sharpe_S1=0.0, p_value=1.0,
            sharpe_first_half=0.0, sharpe_second_half=0.0,
        )
    fit = Lasso(alpha=alpha, max_iter=20000)
    fit.fit(X, y)
    scores = fit.predict(X)
    keep_mask = scores >= threshold
    if keep_mask.sum() < 5:
        return CellResult(
            feature_subset=subset, alpha=alpha, threshold=threshold,
            n=int(keep_mask.sum()), sharpe_S1=0.0, p_value=1.0,
            sharpe_first_half=0.0, sharpe_second_half=0.0,
            coefficients={f: float(c) for f, c in zip(subset, fit.coef_)},
            intercept=float(fit.intercept_),
        )
    kept_pnls = y[keep_mask]
    sharpe = _sharpe_per_trade_to_annualized(kept_pnls)
    p = _permutation_p_value(kept_pnls)

    # Halves for fragility
    kept_dates = [rows[kept_idx[i]]["date"] for i in np.where(keep_mask)[0]]
    first_pnls = np.array([
        kept_pnls[i] for i in range(len(kept_pnls))
        if kept_dates[i] <= half_split_date
    ])
    second_pnls = np.array([
        kept_pnls[i] for i in range(len(kept_pnls))
        if kept_dates[i] > half_split_date
    ])
    sh1 = _sharpe_per_trade_to_annualized(first_pnls)
    sh2 = _sharpe_per_trade_to_annualized(second_pnls)

    return CellResult(
        feature_subset=subset, alpha=alpha, threshold=threshold,
        n=int(keep_mask.sum()),
        sharpe_S1=sharpe,
        p_value=p,
        sharpe_first_half=sh1,
        sharpe_second_half=sh2,
        coefficients={f: float(c) for f, c in zip(subset, fit.coef_)},
        intercept=float(fit.intercept_),
    )


def _baseline_sharpe(rows: list[dict]) -> float:
    """No-Karpathy baseline = post-S1 Sharpe across all in-sample candidates."""
    pnls = np.array([_post_s1_pnl(r["pnl_pct_net"]) for r in rows])
    return _sharpe_per_trade_to_annualized(pnls)


# ---------------- public runner --------------------------------------------

def write_chosen_cell(result: CellResult, *, baseline_sharpe: float) -> None:
    """Persist the chosen cell. Called by run() once selection is done."""
    payload = {
        "hypothesis_id": "H-2026-05-01-phase-c-mr-karpathy-v1",
        "chosen_at": datetime.now(timezone.utc).isoformat(),
        "feature_subset": list(result.feature_subset),
        "alpha": result.alpha,
        "threshold": result.threshold,
        "coefficients": result.coefficients,
        "intercept": result.intercept,
        "in_sample_n": result.n,
        "in_sample_sharpe_S1": result.sharpe_S1,
        "in_sample_p_value": result.p_value,
        "fragility_first_half_sharpe": result.sharpe_first_half,
        "fragility_second_half_sharpe": result.sharpe_second_half,
        "baseline_sharpe_no_karpathy": baseline_sharpe,
        "margin_delta_sharpe": result.sharpe_S1 - baseline_sharpe,
        "training_window": [TRAIN_OPEN, TRAIN_CLOSE],
        "training_half_split": TRAIN_HALF_SPLIT,
        "alpha_grid": list(ALPHA_GRID),
        "threshold_grid": list(THRESHOLD_GRID),
        "grid_size": grid_size(),
        "bh_fdr_alpha": BH_FDR_ALPHA,
        "fragility_half_sharpe_min": FRAGILITY_HALF_SHARPE_MIN,
        "margin_delta_sharpe_min": MARGIN_DELTA_SHARPE_MIN,
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    log.info("wrote chosen cell -> %s", OUT_PATH)


def write_search_log(all_results: list[CellResult], *, baseline_sharpe: float, summary: dict) -> None:
    payload = {
        "hypothesis_id": "H-2026-05-01-phase-c-mr-karpathy-v1",
        "logged_at": datetime.now(timezone.utc).isoformat(),
        "baseline_sharpe_no_karpathy": baseline_sharpe,
        "summary": summary,
        "all_cells": [
            {
                "feature_subset": list(r.feature_subset),
                "alpha": r.alpha,
                "threshold": r.threshold,
                "n": r.n,
                "sharpe_S1": r.sharpe_S1,
                "p_value": r.p_value,
                "sharpe_first_half": r.sharpe_first_half,
                "sharpe_second_half": r.sharpe_second_half,
            }
            for r in all_results
        ],
    }
    LOG_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    log.info("wrote search log -> %s", LOG_PATH)


def run(*, rebuild_features: bool = False, max_cells: int | None = None) -> dict:
    """Drive the 448-cell search and write the winner.

    `rebuild_features=True` re-runs feature_builder; otherwise reuses cache.
    `max_cells` truncates the grid for smoke tests on laptop. Set to None for
    the full search (intended for VPS).
    """
    universe_path = Path(__file__).resolve().parent / "universe_frozen.json"
    universe = list(json.loads(universe_path.read_text(encoding="utf-8"))["tickers"])
    sector_map_path = Path(__file__).resolve().parent / "sector_map_frozen.json"
    sector_map = dict(json.loads(sector_map_path.read_text(encoding="utf-8"))["sector_map"])

    log.info("loading candidates...")
    candidates = load_candidates()
    log.info("in-sample candidates: %d", len(candidates))

    if not candidates:
        raise RuntimeError("no in-sample candidates after gate filters — abort")

    cache_rows = None if rebuild_features else load_feature_cache()
    if cache_rows is None or len(cache_rows) != len(candidates):
        log.info("computing features for %d candidates (this is heavy)...", len(candidates))
        cache_rows = build_feature_cache(candidates, universe, sector_map=sector_map)
        save_feature_cache(cache_rows)
    else:
        log.info("reusing feature cache (%d rows)", len(cache_rows))

    baseline = _baseline_sharpe(cache_rows)
    log.info("regime-gated no-Karpathy baseline Sharpe S1 = %.3f", baseline)

    subsets = feature_subset_combinations()
    cells: list[tuple] = [
        (subset, alpha, threshold)
        for subset in subsets
        for alpha in ALPHA_GRID
        for threshold in THRESHOLD_GRID
    ]
    if max_cells is not None:
        cells = cells[:max_cells]
    log.info("evaluating %d cells (full grid = %d)", len(cells), grid_size())

    results: list[CellResult] = []
    for i, (subset, alpha, threshold) in enumerate(cells, 1):
        try:
            res = _evaluate_cell(
                cache_rows, subset, alpha, threshold,
                half_split_date=TRAIN_HALF_SPLIT,
            )
        except Exception as exc:
            log.warning("cell %d failed: %s", i, exc)
            continue
        results.append(res)
        if i % 25 == 0:
            log.info("cell %d / %d — best so far Sharpe = %.3f",
                     i, len(cells), max((r.sharpe_S1 for r in results), default=0.0))

    if not results:
        raise RuntimeError("no cell survived evaluation (all dropped due to NaN features)")

    p_values = np.array([r.p_value for r in results])
    bh_pass = _bh_fdr_pass(p_values)
    survivors_after_bh = [r for r, ok in zip(results, bh_pass) if ok]
    log.info("BH-FDR survivors: %d / %d", len(survivors_after_bh), len(results))

    survivors = [
        r for r in survivors_after_bh
        if r.sharpe_first_half >= FRAGILITY_HALF_SHARPE_MIN
        and r.sharpe_second_half >= FRAGILITY_HALF_SHARPE_MIN
    ]
    log.info("fragility survivors: %d", len(survivors))

    survivors = [
        r for r in survivors
        if (r.sharpe_S1 - baseline) >= MARGIN_DELTA_SHARPE_MIN
    ]
    log.info("margin survivors: %d", len(survivors))

    summary = {
        "n_cells_evaluated": len(results),
        "n_after_bh_fdr": len(survivors_after_bh),
        "n_after_fragility": sum(
            1 for r in survivors_after_bh
            if r.sharpe_first_half >= FRAGILITY_HALF_SHARPE_MIN
            and r.sharpe_second_half >= FRAGILITY_HALF_SHARPE_MIN
        ),
        "n_after_margin": len(survivors),
        "baseline_sharpe": baseline,
    }

    if not survivors:
        log.warning("no cell survived all gates — registration FAILS, predecessor stays live")
        write_search_log(results, baseline_sharpe=baseline, summary={**summary, "decision": "REGISTRATION_FAIL"})
        return {**summary, "decision": "REGISTRATION_FAIL"}

    chosen = max(survivors, key=lambda r: r.sharpe_S1)
    log.info("CHOSEN: subset=%s alpha=%g threshold=%g  Sharpe=%.3f  p=%.4f  margin=%.3f",
             chosen.feature_subset, chosen.alpha, chosen.threshold,
             chosen.sharpe_S1, chosen.p_value, chosen.sharpe_S1 - baseline)
    write_chosen_cell(chosen, baseline_sharpe=baseline)
    write_search_log(results, baseline_sharpe=baseline, summary={**summary, "decision": "REGISTERED"})
    return {**summary, "decision": "REGISTERED", "chosen": {
        "feature_subset": list(chosen.feature_subset),
        "alpha": chosen.alpha,
        "threshold": chosen.threshold,
        "sharpe_S1": chosen.sharpe_S1,
        "n": chosen.n,
    }}


def _cli(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rebuild-features", action="store_true",
                    help="Rebuild feature cache from scratch.")
    ap.add_argument("--max-cells", type=int, default=None,
                    help="Truncate grid for smoke tests (full = 448).")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    summary = run(rebuild_features=args.rebuild_features, max_cells=args.max_cells)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
