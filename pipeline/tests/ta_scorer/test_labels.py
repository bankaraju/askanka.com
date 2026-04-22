import pandas as pd
from pipeline.ta_scorer import labels


def _prices(closes, date_start="2024-01-01"):
    dates = pd.date_range(date_start, periods=len(closes), freq="B")
    return pd.DataFrame({
        "date": dates.strftime("%Y-%m-%d"),
        "open": closes, "high": [c + 0.5 for c in closes],
        "low": [c - 0.5 for c in closes], "close": closes,
        "volume": 1_000_000,
    })


def test_rising_1d_is_win():
    # Enter at index 0 close=100, next bar close=102 → +2% > 0.8% threshold
    prices = _prices([100.0, 102.0, 103.0])
    res = labels.make_label(prices, entry_date=prices["date"].iloc[0],
                            horizon_days=1, win_threshold=0.008)
    assert res is not None
    assert res["y"] == 1
    assert res["realized_pct"] >= 0.008


def test_falling_1d_is_loss():
    prices = _prices([100.0, 98.0, 97.0])
    res = labels.make_label(prices, entry_date=prices["date"].iloc[0],
                            horizon_days=1, win_threshold=0.008)
    assert res is not None
    assert res["y"] == 0


def test_entry_at_end_returns_none():
    prices = _prices([100.0, 101.0])
    res = labels.make_label(prices, entry_date=prices["date"].iloc[-1],
                            horizon_days=1, win_threshold=0.008)
    assert res is None
