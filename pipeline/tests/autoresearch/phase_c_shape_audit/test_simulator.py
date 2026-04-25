"""Simulator TDD — synthetic minute-bar paths for each exit reason."""
from __future__ import annotations

from datetime import time, datetime

import numpy as np
import pandas as pd
import pytest

from pipeline.autoresearch.phase_c_shape_audit import simulator


def _make_bars_from_path(prices: list[float], start_hour: int = 9, start_minute: int = 15) -> pd.DataFrame:
    """Build minute bars where each bar's H/L = close * (1.001, 0.999)
    and open = previous close."""
    rows = []
    base = datetime(2026, 4, 22, start_hour, start_minute)
    prev = prices[0]
    for i, p in enumerate(prices):
        rows.append({
            "timestamp_ist": base + pd.Timedelta(minutes=i),
            "open": prev,
            "high": max(prev, p) * 1.001,
            "low": min(prev, p) * 0.999,
            "close": p,
            "volume": 1000,
        })
        prev = p
    return pd.DataFrame(rows)


def test_short_hits_stop_loss_at_minute_30() -> None:
    """Open at 09:15 entry @ 100, drift up to 103.5 by minute 30 -> SHORT loses 3.5%
    triggers 3% stop. Walk forward only — assume entry at 09:15."""
    prices = [100.0] * 30 + [103.5] + [100.0] * 320
    bars = _make_bars_from_path(prices)

    result = simulator.simulate_grid(bars=bars, side="SHORT", entry_grid=(time(9, 15),))

    leg = result["09:15"]
    assert leg["exit_reason"] == "STOPPED"
    assert leg["pnl_pct"] == pytest.approx(-3.0)
    assert leg["exit_minute"] == 30


def test_short_hits_target_at_minute_60() -> None:
    """Open at 09:15 entry @ 100, drift down to 95 at minute 60 -> SHORT wins 5%
    triggers 4.5% target."""
    prices = [100.0] * 60 + [95.0] + [97.0] * 290
    bars = _make_bars_from_path(prices)
    result = simulator.simulate_grid(bars=bars, side="SHORT", entry_grid=(time(9, 15),))
    leg = result["09:15"]
    assert leg["exit_reason"] == "TARGETED"
    assert leg["pnl_pct"] == pytest.approx(4.5)
    assert leg["exit_minute"] == 60


def test_long_trails_after_arm_then_retraces() -> None:
    """LONG: open=100, MFE 102.5 (2.5%) at minute 60, retraces to 100.7 by minute 120
    (1.8% drop from peak — exceeds 1.5% trail-drop) -> exit at MFE - 1.5 = 1.0%."""
    prices = [100.0] * 60 + [102.5] + [101.5] * 30 + [100.7] + [100.5] * 280
    bars = _make_bars_from_path(prices)
    result = simulator.simulate_grid(bars=bars, side="LONG", entry_grid=(time(9, 15),))
    leg = result["09:15"]
    assert leg["exit_reason"] == "TRAILED"
    assert leg["pnl_pct"] == pytest.approx(1.0, abs=0.15)  # 0.15 accounts for ±0.1% H/L spread in helper


def test_drifts_to_time_close() -> None:
    """SHORT, never hits stop/target/trail, drifts to +0.8% by 14:30."""
    n = 315  # bars from 09:15 to 14:30 inclusive
    prices = list(np.linspace(100.0, 99.2, n))
    bars = _make_bars_from_path(prices)
    result = simulator.simulate_grid(bars=bars, side="SHORT", entry_grid=(time(9, 15),))
    leg = result["09:15"]
    assert leg["exit_reason"] == "TIME"
    assert leg["pnl_pct"] == pytest.approx(0.8, abs=0.1)


def test_single_bar_with_both_stop_and_target_picks_stop() -> None:
    """SHORT, single bar where high - open = +5% (stop) and low - open = -5% (target).
    Conservative rule: STOP fires first."""
    base = datetime(2026, 4, 22, 9, 15)
    bars = pd.DataFrame([
        {"timestamp_ist": base, "open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0, "volume": 0},
        {"timestamp_ist": base + pd.Timedelta(minutes=1),
         "open": 100.0, "high": 105.0, "low": 95.0, "close": 100.0, "volume": 1000},
    ])
    result = simulator.simulate_grid(bars=bars, side="SHORT", entry_grid=(time(9, 15),))
    leg = result["09:15"]
    assert leg["exit_reason"] == "STOPPED"
    assert leg["pnl_pct"] == pytest.approx(-3.0)
