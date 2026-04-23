"""Section 9A parameter-fragility sweep for H-2026-04-24-003 (v2 axis).

27 neighborhood points over {alpha_scale} x {z_threshold_current} x
{z_threshold_prior}. persistence_days is pinned at 2. Verdict is STABLE if
>=22/27 agree on the sign of the base-fit (model - strongest_naive) margin,
else PARAMETER-FRAGILE.

The caller (runner.py) is responsible for driving each point through
event_filter + feature_builder + fit_lasso + naive-margin computation;
this module owns the grid definition and verdict logic.
"""
from __future__ import annotations

from itertools import product

import numpy as np


ALPHA_SCALES = (0.8, 1.0, 1.2)
Z_THRESHOLD_CURRENT_GRID = (2.5, 3.0, 3.5)
Z_THRESHOLD_PRIOR_GRID = (1.5, 2.0, 2.5)
SIGN_AGREEMENT_FLOOR = 22  # of 27


def neighborhood(base_alpha: float) -> list[dict]:
    return [
        {"alpha": float(base_alpha * s),
         "z_threshold_current": float(zc),
         "z_threshold_prior": float(zp)}
        for s, zc, zp in product(ALPHA_SCALES, Z_THRESHOLD_CURRENT_GRID, Z_THRESHOLD_PRIOR_GRID)
    ]


def evaluate_sweep(rows: list[dict], *, base_margin_sign: int) -> dict:
    """Given 27 rows each with a 'margin' float, verdict by sign agreement."""
    assert len(rows) == 27, f"expected 27 rows, got {len(rows)}"
    signs = np.array([np.sign(r["margin"]) for r in rows])
    n_same = int((signs == base_margin_sign).sum())
    verdict = "STABLE" if n_same >= SIGN_AGREEMENT_FLOOR else "PARAMETER-FRAGILE"
    return {
        "rows": rows,
        "n_same_sign": n_same,
        "floor_required": SIGN_AGREEMENT_FLOOR,
        "base_margin_sign": int(base_margin_sign),
        "verdict": verdict,
    }
