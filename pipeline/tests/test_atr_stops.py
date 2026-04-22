import sys
from pathlib import Path
from unittest.mock import patch
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import atr_stops


def _fake_ohlc(high, low, close, n=20):
    """Return a DataFrame with columns High/Low/Close, n rows, constant values.
    Makes ATR computation deterministic: ATR = max(H-L, |H-prevC|, |L-prevC|)."""
    return pd.DataFrame({"High": [high]*n, "Low": [low]*n, "Close": [close]*n})


def test_long_stop_is_entry_minus_2_atr():
    df = _fake_ohlc(high=105, low=100, close=102, n=20)  # TR=5 every day, ATR=5
    with patch("atr_stops._fetch_ohlc", return_value=df):
        r = atr_stops.compute_atr_stop("BHEL", direction="LONG", window=14, mult=2.0)
    # close=102, ATR=5, stop = close - 2*5 = 92
    assert r["atr_14"] == 5.0
    assert r["stop_price"] == 92.0
    # stop_pct = (92 - 102) / 102 * 100
    assert r["stop_pct"] == round((92 - 102) / 102 * 100, 2)
    assert r["stop_source"] == "atr_14"


def test_short_stop_is_entry_plus_2_atr():
    df = _fake_ohlc(high=105, low=100, close=102, n=20)
    with patch("atr_stops._fetch_ohlc", return_value=df):
        r = atr_stops.compute_atr_stop("YESBANK", direction="SHORT", window=14, mult=2.0)
    # stop_price = 102 + 2*5 = 112
    assert r["stop_price"] == 112.0
    # SHORT stop_pct is the P&L impact — price moving UP is a loss for a short,
    # so stop_pct is negative.
    assert r["stop_pct"] == round(-(112 - 102) / 102 * 100, 2)


def test_fallback_when_fetch_fails():
    with patch("atr_stops._fetch_ohlc", side_effect=RuntimeError("yf 502")):
        r = atr_stops.compute_atr_stop("NOPE", direction="LONG")
    assert r["stop_source"] == "fallback"
    assert r["stop_pct"] == -1.0
    assert r["atr_14"] is None


def test_fallback_when_empty_dataframe():
    with patch("atr_stops._fetch_ohlc", return_value=pd.DataFrame()):
        r = atr_stops.compute_atr_stop("TEST", direction="LONG")
    assert r["stop_source"] == "fallback"


def test_fallback_when_fewer_than_window_bars():
    df = _fake_ohlc(high=105, low=100, close=102, n=5)  # <14
    with patch("atr_stops._fetch_ohlc", return_value=df):
        r = atr_stops.compute_atr_stop("TEST", direction="LONG", window=14)
    assert r["stop_source"] == "fallback"
