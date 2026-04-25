import numpy as np
import pandas as pd

from pipeline.autoresearch.earnings_decoupling.naive_comparators import run_suite


def test_run_suite_returns_three_named_comparators():
    rng = np.random.default_rng(0)
    events = pd.DataFrame({
        "ticker": ["A"] * 50,
        "z": rng.choice([-2.0, 2.0], size=50),
        "next_ret": rng.normal(0, 1, 50),
    })
    out = run_suite(events, seed=42)
    assert set(out.keys()) == {"random_direction", "equal_weight_basket", "fade_inverse"}
    for name in out:
        assert "mean_ret_pct" in out[name]
        assert "sharpe" in out[name]
        assert "n_trades" in out[name]


def test_fade_inverse_negates_sign_of_z():
    events = pd.DataFrame({
        "ticker": ["A", "B"],
        "z": [2.0, -2.0],
        "next_ret": [1.0, -1.0],
    })
    out = run_suite(events)
    # fade_inverse signs as -sign(z): [-1, 1] × [1, -1] = [-1, -1] → mean -1
    assert out["fade_inverse"]["mean_ret_pct"] == -1.0
