"""Pattern detector tests on synthetic OHLC fixtures."""
from datetime import date
import pandas as pd
import pytest
from pipeline.pattern_scanner.detect import detect_patterns_for_ticker, PatternFlag


def _build_bars(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    return df.set_index("date")


def _downtrend_then_hammer() -> pd.DataFrame:
    """Last bar is a textbook bullish hammer."""
    rows = []
    px = 100.0
    for i in range(70):
        rows.append({"date": f"2026-01-{i+1:02d}" if i < 31 else f"2026-02-{i-30:02d}" if i < 59 else f"2026-03-{i-58:02d}",
                     "open": px, "high": px + 0.5,
                     "low": px - 1.0, "close": px - 0.8})
        px -= 0.3
    # textbook hammer: small body, long lower shadow, near top of range
    rows.append({"date": "2026-03-13", "open": px, "high": px + 0.3,
                 "low": px - 2.5, "close": px + 0.2})
    return _build_bars(rows)


def test_detect_bullish_hammer_at_end_of_downtrend():
    bars = _downtrend_then_hammer()
    flags = detect_patterns_for_ticker(
        ticker="TEST", bars=bars, scan_date=date(2026, 3, 13))
    pattern_ids = {f.pattern_id for f in flags}
    assert "BULLISH_HAMMER" in pattern_ids


def test_no_pattern_on_quiet_bar():
    rows = [{"date": (pd.Timestamp("2026-01-01") + pd.Timedelta(days=i)).strftime("%Y-%m-%d"),
             "open": 100.0, "high": 100.5,
             "low": 99.5, "close": 100.0} for i in range(70)]
    bars = _build_bars(rows)
    flags = detect_patterns_for_ticker(
        ticker="TEST", bars=bars, scan_date=date(2026, 3, 11))
    assert flags == []


def test_engulfing_split_by_sign():
    """Bearish engulfing: long red candle engulfing previous green."""
    rows = []
    px = 100.0
    for i in range(68):
        d = (pd.Timestamp("2026-01-01") + pd.Timedelta(days=i)).strftime("%Y-%m-%d")
        rows.append({"date": d, "open": px, "high": px + 0.3, "low": px - 0.3, "close": px})
    # day 69: small green
    d69 = (pd.Timestamp("2026-01-01") + pd.Timedelta(days=68)).strftime("%Y-%m-%d")
    rows.append({"date": d69, "open": 100.0, "high": 100.5, "low": 99.5, "close": 100.3})
    # day 70: bearish engulfing — opens above prev close, closes well below prev open
    d70 = (pd.Timestamp("2026-01-01") + pd.Timedelta(days=69)).strftime("%Y-%m-%d")
    rows.append({"date": d70, "open": 100.5, "high": 100.6, "low": 99.0, "close": 99.1})
    bars = _build_bars(rows)
    flags = detect_patterns_for_ticker("TEST", bars, date(2026, 3, 11))
    assert any(f.pattern_id == "BEARISH_ENGULFING" for f in flags)
    assert not any(f.pattern_id == "BULLISH_ENGULFING" for f in flags)


def test_insufficient_history_returns_empty():
    rows = [{"date": "2026-01-01", "open": 100.0, "high": 100.5, "low": 99.5, "close": 100.0}]
    bars = _build_bars(rows)
    flags = detect_patterns_for_ticker("TEST", bars, date(2026, 1, 1))
    assert flags == []


def test_pattern_flag_shape():
    bars = _downtrend_then_hammer()
    flags = detect_patterns_for_ticker("TEST", bars, date(2026, 3, 13))
    if flags:
        f = flags[0]
        assert isinstance(f, PatternFlag)
        assert f.ticker == "TEST"
        assert f.date == date(2026, 3, 13)
        assert f.direction in ("LONG", "SHORT")
