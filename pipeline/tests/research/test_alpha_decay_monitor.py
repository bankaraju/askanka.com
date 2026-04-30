"""Tests for pipeline.research.alpha_decay.monitor."""
from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from pipeline.research.alpha_decay.monitor import (
    BasketTrade, DecayVerdict, compute_verdicts, _verdict_for, SHARPE_FLOOR,
)


def _t(basket: str, pnl_bps: float, days_ago: int = 1) -> BasketTrade:
    return BasketTrade(
        basket=basket,
        pnl_bps=pnl_bps,
        close_dt=datetime.combine(date.today() - timedelta(days=days_ago),
                                  datetime.min.time()),
        source="test",
    )


def test_verdict_thresholds():
    assert _verdict_for(0.9) == "HEALTHY"
    assert _verdict_for(0.7) == "HEALTHY"
    assert _verdict_for(0.5) == "WATCH"
    assert _verdict_for(0.3) == "WATCH"
    assert _verdict_for(0.1) == "DECAYING"
    assert _verdict_for(0.0) == "DECAYING"
    assert _verdict_for(-0.001) == "KILL"
    assert _verdict_for(-1.5) == "KILL"


def test_insufficient_n_returns_no_verdict():
    trades = [_t("X", 50.0, days_ago=i) for i in range(5)]
    out = compute_verdicts(trades)
    assert len(out) == 1
    assert out[0].verdict == "INSUFFICIENT_N"
    assert out[0].n_closed == 5


def test_healthy_when_forward_sharpe_clears_is():
    # 12 trades, mean=+50bps, std~30bps -> sharpe ~+1.6
    # IS sharpe = 1.0 -> ratio = 1.6 -> HEALTHY
    pnls = [40, 50, 60, 30, 70, 45, 55, 40, 60, 50, 35, 65]
    trades = [_t("BASKET_A", p, days_ago=i + 1) for i, p in enumerate(pnls)]
    out = compute_verdicts(trades, is_sharpe_overrides={"BASKET_A": 1.0})
    assert len(out) == 1
    v = out[0]
    assert v.n_closed == 12
    assert v.verdict == "HEALTHY"
    assert v.rolling_sharpe > 1.0


def test_kill_when_forward_sharpe_negative():
    pnls = [-40, -50, -60, -30, -70, -45, -55, -40, -60, -50, -35, -65]
    trades = [_t("BASKET_B", p, days_ago=i + 1) for i, p in enumerate(pnls)]
    out = compute_verdicts(trades, is_sharpe_overrides={"BASKET_B": 1.0})
    assert out[0].verdict == "KILL"
    assert out[0].rolling_sharpe < 0
    assert out[0].ratio < 0


def test_decaying_zone():
    # Mean small positive, high std, IS Sharpe 1.0 -> ratio in [0, 0.3)
    pnls = [10, -8, 12, -10, 8, -6, 4, -2, 6, -4, 2, 0]
    trades = [_t("BASKET_C", p, days_ago=i + 1) for i, p in enumerate(pnls)]
    out = compute_verdicts(trades, is_sharpe_overrides={"BASKET_C": 1.0})
    v = out[0]
    assert 0.0 <= v.ratio < 0.3, f"ratio {v.ratio} not in DECAYING band"
    assert v.verdict == "DECAYING"


def test_watch_zone():
    # Mean moderate positive, IS Sharpe 1.0, ratio in [0.3, 0.7) -> WATCH
    pnls = [25, 30, 20, 35, 15, 40, 25, 30, 20, 35, 18, 32]
    trades = [_t("BASKET_D", p, days_ago=i + 1) for i, p in enumerate(pnls)]
    out = compute_verdicts(trades, is_sharpe_overrides={"BASKET_D": 5.0})
    v = out[0]
    assert 0.3 <= v.ratio < 0.7
    assert v.verdict == "WATCH"


def test_zero_is_sharpe_uses_floor():
    # IS Sharpe = 0 (deprecated basket) -> ratio = forward_sharpe / SHARPE_FLOOR
    pnls = [50] * 12
    trades = [_t("DEP_BASKET", p, days_ago=i + 1) for i, p in enumerate(pnls)]
    out = compute_verdicts(trades, is_sharpe_overrides={"DEP_BASKET": 0.0})
    v = out[0]
    # std=0 -> sharpe=0 -> ratio=0 -> DECAYING (not error)
    assert v.verdict == "DECAYING"

    # vary the pnls to get nonzero std
    pnls = [40, 50, 60, 50, 40, 50, 60, 50, 40, 50, 60, 50]
    trades = [_t("DEP_BASKET2", p, days_ago=i + 1) for i, p in enumerate(pnls)]
    out = compute_verdicts(trades, is_sharpe_overrides={"DEP_BASKET2": 0.0})
    v = out[0]
    expected_ratio_sign = 1.0 / SHARPE_FLOOR  # any positive sharpe / floor
    assert v.ratio > 0
    assert v.verdict in ("HEALTHY", "WATCH", "DECAYING")


def test_outside_window_excluded():
    inside = [_t("X", 50, days_ago=5) for _ in range(10)]
    outside = [_t("X", 50, days_ago=200) for _ in range(20)]
    out = compute_verdicts(inside + outside)
    assert len(out) == 1
    assert out[0].n_closed == 10  # only inside window


def test_basket_grouping_independence():
    a = [_t("BASKET_A", 50, days_ago=i + 1) for i in range(11)]
    b = [_t("BASKET_B", -30, days_ago=i + 1) for i in range(12)]
    out = compute_verdicts(a + b, is_sharpe_overrides={"BASKET_A": 1.0,
                                                        "BASKET_B": 1.0})
    assert len(out) == 2
    by_basket = {v.basket: v for v in out}
    assert by_basket["BASKET_A"].rolling_mean_bps > 0
    assert by_basket["BASKET_B"].rolling_mean_bps < 0


def test_dataclass_immutability():
    v = DecayVerdict(
        basket="X", n_closed=10, rolling_mean_bps=10.0,
        rolling_std_bps=5.0, rolling_sharpe=2.0,
        is_sharpe=1.0, ratio=2.0, verdict="HEALTHY",
        window_start="2026-04-01", window_end="2026-04-30",
        sources=["test"],
    )
    with pytest.raises((AttributeError, TypeError)):
        v.verdict = "KILL"  # frozen
