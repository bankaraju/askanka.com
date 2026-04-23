import numpy as np
import pandas as pd

from pipeline.autoresearch.phase_c_cross_sectional.naive_adapters import (
    always_fade, always_follow, buy_and_hold, summarize_naive,
)


def _events():
    return pd.DataFrame([
        # Event 1: residual > 0 -> always-fade SHORT -> -1 * next_ret
        {"ticker": "A", "next_ret": 1.0, "expected_return_pct": 0.3,
         "actual_return_pct": 4.0, "today_resid": 3.7},
        # Event 2: residual < 0 -> always-fade LONG -> +1 * next_ret
        {"ticker": "B", "next_ret": -0.5, "expected_return_pct": -0.2,
         "actual_return_pct": -4.1, "today_resid": -3.9},
    ])


def test_always_fade_signs():
    ev = _events()
    s = always_fade(ev)
    # Event 1: fade sign = -sign(3.7) = -1 -> -1 * 1.0 = -1.0
    assert s.iloc[0] == -1.0
    # Event 2: fade sign = -sign(-3.9) = +1 -> +1 * -0.5 = -0.5
    assert s.iloc[1] == -0.5


def test_always_follow_signs():
    ev = _events()
    s = always_follow(ev)
    # Event 1: follow sign = sign(+0.3) = +1 -> +1 * 1.0 = +1.0
    assert s.iloc[0] == 1.0
    # Event 2: follow sign = sign(-0.2) = -1 -> -1 * -0.5 = +0.5
    assert s.iloc[1] == 0.5


def test_buy_and_hold_sign():
    ev = _events()
    s = buy_and_hold(ev)
    # +1 * next_ret always
    assert s.iloc[0] == 1.0
    assert s.iloc[1] == -0.5


def test_summarize_naive_suite_picks_strongest():
    ev = _events()
    summary = summarize_naive(ev)
    assert set(summary.keys()) == {"always_fade", "always_follow", "buy_and_hold"}
    for k in summary:
        assert "sharpe" in summary[k]
        assert "mean_ret_pct" in summary[k]
        assert "n_trades" in summary[k]
    # Each summary row references its signed returns
    assert summary["always_follow"]["n_trades"] == 2
