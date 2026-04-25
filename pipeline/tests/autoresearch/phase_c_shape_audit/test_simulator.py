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
