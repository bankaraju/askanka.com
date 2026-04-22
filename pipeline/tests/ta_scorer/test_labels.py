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


def test_stop_loss_clips_realized_to_stop_pct():
    # Entry 100, next bar close 98.0 but low 98.5 — low above stop (99), realized = close pct (−0.02)
    # Wait: we want low BELOW stop to fire stop logic. Use low=97.5 with close=98.0.
    prices = pd.DataFrame({
        "date": ["2024-01-01", "2024-01-02"],
        "open": [100.0, 99.0], "high": [100.5, 99.5],
        "low": [99.5, 97.5], "close": [100.0, 98.0],
        "volume": [1_000_000, 1_000_000],
    })
    res = labels.make_label(prices, entry_date="2024-01-01", horizon_days=1,
                            win_threshold=0.008, daily_stop_pct=-0.01)
    assert res is not None
    assert res["realized_pct"] == -0.01  # clipped to stop
    assert res["y"] == 0


def test_nan_in_exit_row_returns_none():
    import numpy as np
    prices = pd.DataFrame({
        "date": ["2024-01-01", "2024-01-02"],
        "open": [100.0, 101.0], "high": [100.5, 101.5],
        "low": [99.5, np.nan], "close": [100.0, 101.0],
        "volume": [1_000_000, 1_000_000],
    })
    res = labels.make_label(prices, entry_date="2024-01-01", horizon_days=1)
    assert res is None
