from __future__ import annotations
import numpy as np
import pandas as pd
import pytest
from pipeline.research.phase_c_v5 import hedge_math as hm


def test_ols_beta_matches_numpy():
    rng = np.random.default_rng(0)
    x = rng.normal(size=60)
    y = 1.2 * x + rng.normal(scale=0.1, size=60)
    beta = hm.ols_beta(y, x)
    assert 1.1 <= beta <= 1.3


def test_rolling_beta_respects_window():
    dates = pd.date_range("2026-01-01", periods=100, freq="D")
    stock = pd.Series(np.cumprod(1 + np.random.default_rng(1).normal(0, 0.01, 100)), index=dates)
    index = pd.Series(np.cumprod(1 + np.random.default_rng(2).normal(0, 0.008, 100)), index=dates)
    betas = hm.rolling_ols_beta(stock, index, window=60)
    assert len(betas) == 100
    # First 59 entries must be NaN (insufficient window)
    assert betas.iloc[:59].isna().all()
    assert not betas.iloc[60:].isna().any()


def test_beta_clamped_to_range():
    assert hm.clamp_beta(2.5) == 1.5
    assert hm.clamp_beta(0.2) == 0.5
    assert hm.clamp_beta(1.0) == 1.0
    assert hm.clamp_beta(-0.5) == 0.5  # negative beta clamped up (no hedge inversion)
