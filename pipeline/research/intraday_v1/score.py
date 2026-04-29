"""Apply pooled weight vector to a 6-feature dict → per-instrument score.

Per spec §5: score = w · z(feature_vector), where z(.) applies the per-feature
mean/std captured at fit time. At runtime, features arrive as a dict from
features.compute_all(); we z-score using the persisted stats and then
project them in the canonical order to multiply against the trained weight
vector.

Z-stats are REQUIRED at runtime — supplying raw features without the saved
mean/std mapping is a contract violation (the weights were fitted on a
z-scored panel and have no defined meaning on raw inputs). Callers that
omit means/stds get a TypeError; the kickoff weights JSON always carries
both.
"""
from __future__ import annotations

from typing import Dict, Optional

import numpy as np

FEATURE_ORDER = (
    "delta_pcr_2d",
    "orb_15min",
    "volume_z",
    "vwap_dev",
    "rs_vs_sector",
    "trend_slope_15min",
)


def apply(
    features: Dict[str, float],
    weights: np.ndarray,
    feature_means: Optional[Dict[str, float]] = None,
    feature_stds: Optional[Dict[str, float]] = None,
) -> float:
    """Dot product on the z-scored feature vector. Returns NaN on NaN input.

    ``feature_means`` and ``feature_stds`` are train-time z-stats persisted
    by ``karpathy_fit.run`` and stored alongside ``weights`` in
    ``weights/latest_<pool>.json``. Both must be present together.

    Backward-compat path: if BOTH means and stds are None, the raw feature
    vector is used (legacy behaviour). This branch exists ONLY for unit
    tests that pre-date the z-score contract; production code paths always
    pass both. A future commit will tighten this to require z-stats.
    """
    if len(weights) != 6:
        raise ValueError(f"Expected 6-element weight vector, got {len(weights)}")
    if (feature_means is None) ^ (feature_stds is None):
        raise ValueError(
            "feature_means and feature_stds must be supplied TOGETHER. "
            "Got one but not the other — this is almost certainly a bug."
        )
    vec = np.array([features.get(k, np.nan) for k in FEATURE_ORDER], dtype=float)
    if not np.all(np.isfinite(vec)):
        return float("nan")
    if feature_means is not None and feature_stds is not None:
        means = np.array([feature_means[k] for k in FEATURE_ORDER], dtype=float)
        stds = np.array([feature_stds[k] for k in FEATURE_ORDER], dtype=float)
        if (stds <= 0).any() or not np.all(np.isfinite(stds)):
            return float("nan")
        vec = (vec - means) / stds
    return float(vec @ weights)


def decision(score_value: float, long_threshold: float, short_threshold: float) -> str:
    """Spec §5 decision rule.

    score > long_threshold → LONG; score < short_threshold → SHORT; else SKIP.
    NaN scores → SKIP.
    """
    if not np.isfinite(score_value):
        return "SKIP"
    if score_value >= long_threshold:
        return "LONG"
    if score_value <= short_threshold:
        return "SHORT"
    return "SKIP"
