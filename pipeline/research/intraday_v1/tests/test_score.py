"""Tests score.py — apply pooled weight vector to feature dict."""
from __future__ import annotations

import numpy as np
import pytest

from pipeline.research.intraday_v1 import score


def test_apply_weights_dot_product():
    feat = {
        "delta_pcr_2d":     0.5,
        "orb_15min":        0.01,
        "volume_z":         1.5,
        "vwap_dev":         -0.005,
        "rs_vs_sector":     0.002,
        "trend_slope_15min": 0.0001,
    }
    weights = np.array([1.0, 50.0, 0.5, 100.0, 200.0, 1000.0])
    s = score.apply(feat, weights)
    expected = (1.0*0.5 + 50.0*0.01 + 0.5*1.5 + 100.0*-0.005 + 200.0*0.002 + 1000.0*0.0001)
    assert s == pytest.approx(expected)


def test_apply_weights_returns_nan_when_any_feature_nan():
    feat = {
        "delta_pcr_2d":     0.5,
        "orb_15min":        float("nan"),
        "volume_z":         1.5,
        "vwap_dev":         -0.005,
        "rs_vs_sector":     0.002,
        "trend_slope_15min": 0.0001,
    }
    weights = np.array([1.0, 50.0, 0.5, 100.0, 200.0, 1000.0])
    s = score.apply(feat, weights)
    assert np.isnan(s)


def test_decision_long_short_skip():
    assert score.decision(1.5, long_threshold=1.0, short_threshold=-1.0) == "LONG"
    assert score.decision(-1.5, long_threshold=1.0, short_threshold=-1.0) == "SHORT"
    assert score.decision(0.5, long_threshold=1.0, short_threshold=-1.0) == "SKIP"
    assert score.decision(float("nan"), long_threshold=1.0, short_threshold=-1.0) == "SKIP"
