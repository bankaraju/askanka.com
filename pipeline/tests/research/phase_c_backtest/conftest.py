from __future__ import annotations
import pandas as pd
import pytest
from datetime import datetime


@pytest.fixture
def sample_daily_bars():
    """30 trading days of synthetic OHLCV for one symbol."""
    dates = pd.bdate_range(start="2026-01-01", periods=30)
    rows = []
    price = 100.0
    for d in dates:
        o = price
        c = price * (1 + 0.01)
        h = max(o, c) * 1.005
        l = min(o, c) * 0.995
        rows.append({"date": d.strftime("%Y-%m-%d"), "open": o, "high": h, "low": l, "close": c, "volume": 100000})
        price = c
    return pd.DataFrame(rows)


@pytest.fixture
def sample_minute_bars():
    """One trading day, 09:15-15:30 IST, 1-min bars for one symbol."""
    start = datetime(2026, 4, 18, 9, 15)
    end = datetime(2026, 4, 18, 15, 30)
    minutes = pd.date_range(start=start, end=end, freq="1min")
    rows = []
    price = 100.0
    for m in minutes:
        o = price
        c = price * 1.0001
        h = max(o, c) * 1.0005
        l = min(o, c) * 0.9995
        rows.append({"date": m.strftime("%Y-%m-%d %H:%M:%S"), "open": o, "high": h, "low": l, "close": c, "volume": 1000})
        price = c
    return pd.DataFrame(rows)
