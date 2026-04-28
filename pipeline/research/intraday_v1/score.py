"""Apply pooled weight vector to a 6-feature dict → per-instrument score.

Per spec §5: score = w · feature_vector (after z-scoring at fit time).
At runtime, features arrive as a dict from features.compute_all(); we
project them in the canonical order to multiply against the trained
weight vector.
"""
from __future__ import annotations

from typing import Dict

import numpy as np

FEATURE_ORDER = (
    "delta_pcr_2d",
    "orb_15min",
    "volume_z",
    "vwap_dev",
    "rs_vs_sector",
    "trend_slope_15min",
)


def apply(features: Dict[str, float], weights: np.ndarray) -> float:
    """Dot product. Returns NaN if any feature is NaN."""
    if len(weights) != 6:
        raise ValueError(f"Expected 6-element weight vector, got {len(weights)}")
    vec = np.array([features.get(k, np.nan) for k in FEATURE_ORDER], dtype=float)
    if not np.all(np.isfinite(vec)):
        return float("nan")
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
