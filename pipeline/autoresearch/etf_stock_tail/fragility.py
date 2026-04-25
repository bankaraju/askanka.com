# pipeline/autoresearch/etf_stock_tail/fragility.py
"""6-perturbation fragility sweep + STABLE/FRAGILE verdict."""
from __future__ import annotations

from pipeline.autoresearch.etf_stock_tail import constants as C


# Locked at registration — 6 perturbations only.
PERTURBATIONS: list[dict] = [
    {"name": "dropout_minus_10pct",      "field": "dropout",      "value": C.DROPOUT * 0.9},
    {"name": "dropout_plus_10pct",       "field": "dropout",      "value": C.DROPOUT * 1.1},
    {"name": "weight_decay_minus_20pct", "field": "wd",           "value": C.WEIGHT_DECAY_TRUNK * 0.8},
    {"name": "weight_decay_plus_20pct",  "field": "wd",           "value": C.WEIGHT_DECAY_TRUNK * 1.2},
    {"name": "sigma_1_0",                "field": "sigma",        "value": 1.0},
    {"name": "sigma_2_0",                "field": "sigma",        "value": 2.0},
]


def fragility_verdict(base_holdout_ce: float, runs: list[dict]) -> dict:
    """Verdict STABLE iff >= FRAGILITY_MIN_PASSING runs are within +-FRAGILITY_TOL_PCT of base CE."""
    tol = C.FRAGILITY_TOL_PCT * base_holdout_ce
    n_passing = 0
    enriched: list[dict] = []
    for run in runs:
        within = abs(run["holdout_ce"] - base_holdout_ce) <= tol
        n_passing += int(within)
        enriched.append({**run, "within_tolerance": within, "tol_used": tol})
    return {
        "verdict": "STABLE" if n_passing >= C.FRAGILITY_MIN_PASSING else "FRAGILE",
        "n_passing": n_passing,
        "n_total": len(runs),
        "tol_pct": C.FRAGILITY_TOL_PCT,
        "min_passing_required": C.FRAGILITY_MIN_PASSING,
        "base_holdout_ce": base_holdout_ce,
        "runs": enriched,
    }
