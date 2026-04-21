from __future__ import annotations
import pandas as pd
import pytest


@pytest.fixture
def sample_daily_basket_bars():
    """Two symbols, 30 trading days of synthetic OHLCV. LEADER drifts +0.5%/day,
    LAGGER drifts -0.2%/day. Perfect conditions for a long/short pair trade."""
    dates = pd.bdate_range(start="2026-01-01", periods=30)
    frames = {}
    for sym, drift in [("LEADER", 0.005), ("LAGGER", -0.002)]:
        rows, price = [], 100.0
        for d in dates:
            o = price
            c = price * (1 + drift)
            h, l = max(o, c) * 1.002, min(o, c) * 0.998
            rows.append({"date": d, "open": o, "high": h, "low": l, "close": c, "volume": 100_000})
            price = c
        frames[sym] = pd.DataFrame(rows)
    return frames


@pytest.fixture
def sample_ranker_state():
    """Minimal ranker state with 5 longs + 5 shorts in NEUTRAL regime."""
    return {
        "last_zone": "NEUTRAL",
        "last_date": "2026-04-01",
        "updated": "2026-04-01 08:00:00",
        "active_recommendations": [
            {"symbol": f"LONG{i}", "direction": "LONG", "regime": "NEUTRAL",
             "drift_5d_mean": 0.08 - i * 0.005, "hit_rate": 0.8, "episodes": 5,
             "entry_date": "2026-04-01", "expiry_date": "2026-04-08"}
            for i in range(5)
        ] + [
            {"symbol": f"SHORT{i}", "direction": "SHORT", "regime": "NEUTRAL",
             "drift_5d_mean": -0.05 + i * 0.005, "hit_rate": 0.7, "episodes": 5,
             "entry_date": "2026-04-01", "expiry_date": "2026-04-08"}
            for i in range(5)
        ],
    }
