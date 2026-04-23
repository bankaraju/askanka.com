# -*- coding: utf-8 -*-
import numpy as np
import pandas as pd
import pytest

from pipeline.autoresearch.overshoot_compliance import naive_comparators as NC


def _events():
    return pd.DataFrame([
        {"ticker": "A", "z": 3.1, "next_ret": 1.0},
        {"ticker": "A", "z": 3.2, "next_ret": -0.5},
        {"ticker": "A", "z": -3.5, "next_ret": 0.8},
        {"ticker": "A", "z": -3.1, "next_ret": -0.3},
        {"ticker": "B", "z": 3.0, "next_ret": 0.2},
    ])


def test_random_direction_approaches_zero_for_symmetric_returns():
    rng = np.random.default_rng(0)
    rets = rng.normal(loc=0.0, scale=1.0, size=5000)
    events = pd.DataFrame({"next_ret": rets, "z": rng.choice([-3, 3], size=5000)})
    mean = NC.random_direction(events, seed=42)["mean_ret_pct"]
    assert abs(mean) < 0.05


def test_equal_weight_basket_uses_raw_mean():
    ev = _events()
    row = NC.equal_weight_basket(ev)
    assert row["mean_ret_pct"] == pytest.approx(float(ev["next_ret"].mean()), abs=1e-3)


def test_momentum_follow_flips_fade_sign():
    ev = _events()
    row = NC.momentum_follow(ev)
    # momentum LONG after UP, SHORT after DOWN
    # UP rows (z>0) contribute +next_ret
    # DOWN rows (z<0) contribute -next_ret
    expected = float(
        ev.loc[ev["z"] > 0, "next_ret"].sum()
        - ev.loc[ev["z"] < 0, "next_ret"].sum()
    ) / len(ev)
    assert row["mean_ret_pct"] == pytest.approx(expected, abs=1e-3)


def test_comparator_suite_returns_all_three():
    ev = _events()
    suite = NC.run_suite(ev, seed=1)
    assert set(suite.keys()) == {"random_direction", "equal_weight_basket", "momentum_follow"}
    for v in suite.values():
        assert "mean_ret_pct" in v
        assert "sharpe" in v
        assert "hit_rate" in v
