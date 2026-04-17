# Technical Fingerprint Engine — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a per-stock technical fingerprinting system that backtests 15 pattern types across 5 years of daily data for 213 F&O stocks, producing fingerprint cards and daily scanner alerts.

**Architecture:** EODHD fetches 5yr OHLCV → pure-math indicator library computes BB/MACD/RSI/ATR/EMA/candles → pattern detector finds events → backtester measures forward returns → fingerprint card assembles per-stock profile → daily scanner checks live prices against proven patterns.

**Tech Stack:** Python 3.13, pandas, numpy, requests. EODHD API (key in pipeline/.env). pytest for testing.

**Spec:** `docs/superpowers/specs/2026-04-17-technical-fingerprint-engine-design.md`

**Important context:**
- Working directory: `C:/Users/Claude_Anka/askanka.com`
- Tests run with: `cd C:/Users/Claude_Anka/askanka.com && PYTHONPATH=pipeline python -m pytest ...`
- EODHD client exists at `pipeline/eodhd_client.py` with `EODHD_API_KEY` from `pipeline/.env`
- F&O stock list: `opus/config/fno_stocks.json` key `"symbols"` (213 symbols)
- Existing TA: `pipeline/technical_scanner.py` — only RSI+SMA on 24 stocks. We build separately, don't modify it.
- pandas and numpy are already installed

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `pipeline/ta_data_fetcher.py` | CREATE | Fetch 5yr OHLCV from EODHD, cache to CSV |
| `pipeline/ta_indicators.py` | CREATE | Pure indicator math: SMA, EMA, BB, MACD, RSI, ATR, candles |
| `pipeline/ta_pattern_detector.py` | CREATE | Detect 15 pattern event types from indicator output |
| `pipeline/ta_backtester.py` | CREATE | Measure 1/3/5/10d forward returns per event |
| `pipeline/ta_fingerprint.py` | CREATE | Assemble fingerprint cards + personality classification |
| `pipeline/ta_daily_scanner.py` | CREATE | Daily scanner: check live prices vs fingerprint cards |
| `pipeline/tests/test_ta_indicators.py` | CREATE | Indicator unit tests |
| `pipeline/tests/test_ta_pattern_detector.py` | CREATE | Pattern detection tests |
| `pipeline/tests/test_ta_backtester.py` | CREATE | Backtest engine tests |
| `pipeline/tests/test_ta_fingerprint.py` | CREATE | Fingerprint card tests |
| `pipeline/tests/test_ta_data_fetcher.py` | CREATE | Data fetcher tests |
| `pipeline/tests/test_ta_daily_scanner.py` | CREATE | Daily scanner tests |

---

### Task 1: Indicator Library — SMA, EMA, RSI

**Files:**
- Create: `pipeline/ta_indicators.py`
- Create: `pipeline/tests/test_ta_indicators.py`

- [ ] **Step 1: Write failing tests for SMA, EMA, RSI**

```python
# pipeline/tests/test_ta_indicators.py
"""Tests for technical analysis indicator library."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


def _make_df(closes: list[float], n: int = 0) -> pd.DataFrame:
    """Build minimal OHLCV DataFrame from close prices."""
    if not closes:
        closes = list(range(100, 100 + n))
    n = len(closes)
    return pd.DataFrame({
        "Date": pd.date_range("2025-01-01", periods=n, freq="B"),
        "Open": [c - 0.5 for c in closes],
        "High": [c + 1.0 for c in closes],
        "Low": [c - 1.0 for c in closes],
        "Close": closes,
        "Volume": [1000000] * n,
    })


def test_sma_basic():
    """SMA of 5 values with period=5 → last value is mean of all 5."""
    from ta_indicators import sma
    series = pd.Series([10.0, 20.0, 30.0, 40.0, 50.0])
    result = sma(series, period=5)
    assert result.iloc[-1] == 30.0
    assert pd.isna(result.iloc[0])  # not enough data for first values


def test_sma_constant_series():
    """SMA of constant series equals the constant."""
    from ta_indicators import sma
    series = pd.Series([42.0] * 20)
    result = sma(series, period=10)
    assert result.iloc[-1] == 42.0


def test_ema_responds_faster_than_sma():
    """EMA gives more weight to recent prices than SMA."""
    from ta_indicators import sma, ema
    prices = pd.Series([10.0] * 19 + [20.0])
    sma_val = sma(prices, period=10).iloc[-1]
    ema_val = ema(prices, period=10).iloc[-1]
    assert ema_val > sma_val  # EMA reacts faster to the jump


def test_rsi_constant_series_is_50():
    """RSI of constant prices (no gains, no losses) should be ~50 or NaN."""
    from ta_indicators import rsi
    df = _make_df([100.0] * 30)
    result = rsi(df, period=14)
    valid = result.dropna()
    if len(valid) > 0:
        assert abs(valid.iloc[-1] - 50.0) < 5.0


def test_rsi_all_gains_near_100():
    """Monotonically increasing prices → RSI near 100."""
    from ta_indicators import rsi
    df = _make_df([float(i) for i in range(100, 130)])
    result = rsi(df, period=14)
    assert result.iloc[-1] > 90.0


def test_rsi_all_losses_near_0():
    """Monotonically decreasing prices → RSI near 0."""
    from ta_indicators import rsi
    df = _make_df([float(i) for i in range(130, 100, -1)])
    result = rsi(df, period=14)
    assert result.iloc[-1] < 10.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd C:/Users/Claude_Anka/askanka.com && PYTHONPATH=pipeline python -m pytest pipeline/tests/test_ta_indicators.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'ta_indicators'`

- [ ] **Step 3: Implement SMA, EMA, RSI**

```python
# pipeline/ta_indicators.py
"""
Technical Analysis Indicator Library — pure math, no I/O.

All functions take pandas Series or DataFrame, return Series or DataFrame.
No side effects, no file reads, no API calls.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def sma(series: pd.Series, period: int) -> pd.Series:
    """Simple Moving Average."""
    return series.rolling(window=period, min_periods=period).mean()


def ema(series: pd.Series, period: int) -> pd.Series:
    """Exponential Moving Average."""
    return series.ewm(span=period, adjust=False, min_periods=period).mean()


def rsi(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Relative Strength Index using Wilder's smoothing."""
    close = df["Close"]
    delta = close.diff()
    gains = delta.clip(lower=0)
    losses = (-delta).clip(lower=0)

    avg_gain = gains.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    avg_loss = losses.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100.0 - (100.0 / (1.0 + rs))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd C:/Users/Claude_Anka/askanka.com && PYTHONPATH=pipeline python -m pytest pipeline/tests/test_ta_indicators.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
cd C:/Users/Claude_Anka/askanka.com
git add pipeline/ta_indicators.py pipeline/tests/test_ta_indicators.py
git commit -m "feat(ta): indicator library — SMA, EMA, RSI with Wilder's smoothing"
```

---

### Task 2: Indicator Library — Bollinger Bands, MACD, ATR

**Files:**
- Modify: `pipeline/ta_indicators.py`
- Modify: `pipeline/tests/test_ta_indicators.py`

- [ ] **Step 1: Write failing tests for Bollinger, MACD, ATR**

Append to `pipeline/tests/test_ta_indicators.py`:

```python
def test_bollinger_bands_shape():
    """Bollinger returns DataFrame with upper, middle, lower, bandwidth, pct_b."""
    from ta_indicators import bollinger
    df = _make_df([float(100 + i % 5) for i in range(50)])
    result = bollinger(df, period=20, std=2)
    assert "upper" in result.columns
    assert "middle" in result.columns
    assert "lower" in result.columns
    assert "bandwidth" in result.columns
    assert "pct_b" in result.columns
    assert result["upper"].iloc[-1] > result["middle"].iloc[-1] > result["lower"].iloc[-1]


def test_bollinger_constant_series_narrow_bands():
    """Constant prices → bandwidth near zero."""
    from ta_indicators import bollinger
    df = _make_df([100.0] * 30)
    result = bollinger(df, period=20, std=2)
    assert result["bandwidth"].iloc[-1] < 0.01


def test_macd_shape():
    """MACD returns DataFrame with macd_line, signal_line, histogram."""
    from ta_indicators import macd
    df = _make_df([float(100 + i * 0.5) for i in range(50)])
    result = macd(df, fast=12, slow=26, signal=9)
    assert "macd_line" in result.columns
    assert "signal_line" in result.columns
    assert "histogram" in result.columns


def test_macd_trending_up_positive():
    """Strongly trending up → MACD line positive."""
    from ta_indicators import macd
    df = _make_df([float(100 + i * 2) for i in range(50)])
    result = macd(df, fast=12, slow=26, signal=9)
    assert result["macd_line"].iloc[-1] > 0


def test_atr_constant_range():
    """Constant high-low range → ATR equals that range."""
    from ta_indicators import atr
    n = 30
    df = pd.DataFrame({
        "Date": pd.date_range("2025-01-01", periods=n, freq="B"),
        "Open": [100.0] * n,
        "High": [105.0] * n,
        "Low": [95.0] * n,
        "Close": [100.0] * n,
        "Volume": [1000000] * n,
    })
    result = atr(df, period=14)
    assert abs(result.iloc[-1] - 10.0) < 0.5


def test_volume_spike_detects_2x():
    """Volume at 3x average → detected as spike."""
    from ta_indicators import volume_spike
    volumes = [1000000] * 25 + [3000000]
    df = pd.DataFrame({
        "Date": pd.date_range("2025-01-01", periods=26, freq="B"),
        "Open": [100.0] * 26, "High": [101.0] * 26,
        "Low": [99.0] * 26, "Close": [100.0] * 26,
        "Volume": volumes,
    })
    result = volume_spike(df, lookback=20, threshold=2.0)
    assert result.iloc[-1] == True
    assert result.iloc[-2] == False
```

- [ ] **Step 2: Run tests to verify new tests fail**

Run: `cd C:/Users/Claude_Anka/askanka.com && PYTHONPATH=pipeline python -m pytest pipeline/tests/test_ta_indicators.py -v`
Expected: 6 old pass, 6 new FAIL

- [ ] **Step 3: Implement Bollinger, MACD, ATR, volume_spike**

Append to `pipeline/ta_indicators.py`:

```python
def bollinger(df: pd.DataFrame, period: int = 20, std: int = 2) -> pd.DataFrame:
    """Bollinger Bands: upper, middle, lower, bandwidth, pct_b."""
    close = df["Close"]
    middle = sma(close, period)
    rolling_std = close.rolling(window=period, min_periods=period).std()
    upper = middle + std * rolling_std
    lower = middle - std * rolling_std
    bandwidth = (upper - lower) / middle
    pct_b = (close - lower) / (upper - lower)
    return pd.DataFrame({
        "upper": upper, "middle": middle, "lower": lower,
        "bandwidth": bandwidth, "pct_b": pct_b,
    }, index=df.index)


def macd(df: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    """MACD: macd_line, signal_line, histogram."""
    close = df["Close"]
    fast_ema = ema(close, fast)
    slow_ema = ema(close, slow)
    macd_line = fast_ema - slow_ema
    signal_line = macd_line.ewm(span=signal, adjust=False, min_periods=signal).mean()
    histogram = macd_line - signal_line
    return pd.DataFrame({
        "macd_line": macd_line, "signal_line": signal_line, "histogram": histogram,
    }, index=df.index)


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Average True Range."""
    high, low, close = df["High"], df["Low"], df["Close"]
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()


def volume_spike(df: pd.DataFrame, lookback: int = 20, threshold: float = 2.0) -> pd.Series:
    """Detect volume spikes: volume > threshold × lookback-period average."""
    vol = df["Volume"].astype(float)
    avg_vol = vol.rolling(window=lookback, min_periods=lookback).mean().shift(1)
    return vol > (threshold * avg_vol)
```

- [ ] **Step 4: Run tests to verify all pass**

Run: `cd C:/Users/Claude_Anka/askanka.com && PYTHONPATH=pipeline python -m pytest pipeline/tests/test_ta_indicators.py -v`
Expected: 12 passed

- [ ] **Step 5: Commit**

```bash
cd C:/Users/Claude_Anka/askanka.com
git add pipeline/ta_indicators.py pipeline/tests/test_ta_indicators.py
git commit -m "feat(ta): Bollinger Bands, MACD, ATR, volume spike detection"
```

---

### Task 3: Indicator Library — Candlestick Patterns

**Files:**
- Modify: `pipeline/ta_indicators.py`
- Modify: `pipeline/tests/test_ta_indicators.py`

- [ ] **Step 1: Write failing tests for candlestick detection**

Append to `pipeline/tests/test_ta_indicators.py`:

```python
def test_detect_doji():
    """Doji: open ≈ close, non-zero range."""
    from ta_indicators import detect_candles
    df = pd.DataFrame({
        "Date": pd.date_range("2025-01-01", periods=5, freq="B"),
        "Open":  [100.0, 100.0, 100.0, 100.0, 100.1],
        "High":  [101.0, 102.0, 103.0, 104.0, 105.0],
        "Low":   [99.0,  98.0,  97.0,  96.0,  95.0],
        "Close": [100.0, 100.0, 100.0, 100.0, 100.0],
        "Volume": [1e6] * 5,
    })
    result = detect_candles(df)
    assert result["doji"].iloc[-1] == True


def test_detect_bullish_engulfing():
    """Green candle fully engulfs prior red candle."""
    from ta_indicators import detect_candles
    df = pd.DataFrame({
        "Date": pd.date_range("2025-01-01", periods=5, freq="B"),
        "Open":  [105, 104, 103, 102, 98],
        "High":  [106, 105, 104, 103, 104],
        "Low":   [104, 103, 102, 97,  97],
        "Close": [104, 103, 102, 98,  103],
        "Volume": [1e6] * 5,
    })
    result = detect_candles(df)
    assert result["engulfing_bull"].iloc[-1] == True


def test_detect_hammer():
    """Lower shadow ≥ 2× body, small upper shadow."""
    from ta_indicators import detect_candles
    df = pd.DataFrame({
        "Date": pd.date_range("2025-01-01", periods=5, freq="B"),
        "Open":  [105, 104, 103, 102, 100.5],
        "High":  [106, 105, 104, 103, 101.0],
        "Low":   [104, 103, 102, 101, 97.0],
        "Close": [104, 103, 102, 101, 100.0],
        "Volume": [1e6] * 5,
    })
    result = detect_candles(df)
    assert result["hammer"].iloc[-1] == True


def test_no_false_doji_on_big_body():
    """Large body candle should NOT be a doji."""
    from ta_indicators import detect_candles
    df = pd.DataFrame({
        "Date": pd.date_range("2025-01-01", periods=3, freq="B"),
        "Open":  [100, 100, 95],
        "High":  [101, 101, 106],
        "Low":   [99,  99,  94],
        "Close": [100, 100, 105],
        "Volume": [1e6] * 3,
    })
    result = detect_candles(df)
    assert result["doji"].iloc[-1] == False
```

- [ ] **Step 2: Run tests to verify new tests fail**

Run: `cd C:/Users/Claude_Anka/askanka.com && PYTHONPATH=pipeline python -m pytest pipeline/tests/test_ta_indicators.py -v`
Expected: 12 old pass, 4 new FAIL

- [ ] **Step 3: Implement detect_candles**

Append to `pipeline/ta_indicators.py`:

```python
def detect_candles(df: pd.DataFrame) -> pd.DataFrame:
    """Detect candlestick patterns: doji, hammer, shooting_star, engulfing_bull, engulfing_bear."""
    o, h, l, c = df["Open"].astype(float), df["High"].astype(float), df["Low"].astype(float), df["Close"].astype(float)
    body = (c - o).abs()
    full_range = h - l
    upper_shadow = h - pd.concat([o, c], axis=1).max(axis=1)
    lower_shadow = pd.concat([o, c], axis=1).min(axis=1) - l

    # Doji: tiny body relative to range
    doji = (full_range > 0) & (body / full_range < 0.1)

    # Hammer: lower shadow ≥ 2× body, upper shadow ≤ 0.3× body
    hammer = (lower_shadow >= 2 * body) & (upper_shadow <= 0.3 * body.clip(lower=0.01)) & (full_range > 0)

    # Shooting star: upper shadow ≥ 2× body, lower shadow ≤ 0.3× body
    shooting_star = (upper_shadow >= 2 * body) & (lower_shadow <= 0.3 * body.clip(lower=0.01)) & (full_range > 0)

    # Bullish engulfing: today green engulfs yesterday's red body
    prev_o, prev_c = o.shift(1), c.shift(1)
    today_green = c > o
    prev_red = prev_c < prev_o
    engulfing_bull = today_green & prev_red & (o <= prev_c) & (c >= prev_o)

    # Bearish engulfing: today red engulfs yesterday's green body
    today_red = c < o
    prev_green = prev_c > prev_o
    engulfing_bear = today_red & prev_green & (o >= prev_c) & (c <= prev_o)

    return pd.DataFrame({
        "doji": doji, "hammer": hammer, "shooting_star": shooting_star,
        "engulfing_bull": engulfing_bull, "engulfing_bear": engulfing_bear,
    }, index=df.index)
```

- [ ] **Step 4: Run tests to verify all pass**

Run: `cd C:/Users/Claude_Anka/askanka.com && PYTHONPATH=pipeline python -m pytest pipeline/tests/test_ta_indicators.py -v`
Expected: 16 passed

- [ ] **Step 5: Commit**

```bash
cd C:/Users/Claude_Anka/askanka.com
git add pipeline/ta_indicators.py pipeline/tests/test_ta_indicators.py
git commit -m "feat(ta): candlestick pattern detection — doji, hammer, engulfing"
```

---

### Task 4: Data Fetcher — 5yr EODHD OHLCV

**Files:**
- Create: `pipeline/ta_data_fetcher.py`
- Create: `pipeline/tests/test_ta_data_fetcher.py`

- [ ] **Step 1: Write failing tests**

```python
# pipeline/tests/test_ta_data_fetcher.py
"""Tests for TA data fetcher — EODHD 5yr OHLCV."""
from __future__ import annotations

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock


SAMPLE_EODHD_RESPONSE = [
    {"date": "2025-01-02", "open": 100, "high": 105, "low": 98, "close": 103, "adjusted_close": 103, "volume": 1500000},
    {"date": "2025-01-03", "open": 103, "high": 107, "low": 101, "close": 106, "adjusted_close": 106, "volume": 1200000},
]


def test_fetch_single_stock(tmp_path: Path):
    """Fetches OHLCV and writes CSV."""
    from ta_data_fetcher import fetch_stock_history

    with patch("ta_data_fetcher.requests") as mock_req:
        mock_resp = MagicMock()
        mock_resp.json.return_value = SAMPLE_EODHD_RESPONSE
        mock_resp.status_code = 200
        mock_req.get.return_value = mock_resp

        path = fetch_stock_history("HAL", cache_dir=tmp_path)

    assert path.exists()
    lines = path.read_text().strip().split("\n")
    assert len(lines) == 3  # header + 2 rows
    assert "Date,Open,High,Low,Close,Volume" in lines[0]


def test_fetch_uses_cache(tmp_path: Path):
    """Existing CSV is not re-fetched."""
    from ta_data_fetcher import fetch_stock_history

    csv = tmp_path / "HAL.csv"
    csv.write_text("Date,Open,High,Low,Close,Volume\n2025-01-02,100,105,98,103,1500000\n")

    with patch("ta_data_fetcher.requests") as mock_req:
        path = fetch_stock_history("HAL", cache_dir=tmp_path, force=False)
        mock_req.get.assert_not_called()

    assert path == csv


def test_fetch_no_key_returns_none(tmp_path: Path):
    """No EODHD key → returns None."""
    from ta_data_fetcher import fetch_stock_history

    with patch("ta_data_fetcher._api_key", return_value=None):
        result = fetch_stock_history("HAL", cache_dir=tmp_path)

    assert result is None


def test_fetch_batch(tmp_path: Path):
    """Batch fetches multiple stocks."""
    from ta_data_fetcher import fetch_batch

    with patch("ta_data_fetcher.fetch_stock_history") as mock_fetch:
        mock_fetch.return_value = tmp_path / "HAL.csv"
        result = fetch_batch(["HAL", "TCS"], cache_dir=tmp_path, delay=0)

    assert len(result) == 2
    assert mock_fetch.call_count == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd C:/Users/Claude_Anka/askanka.com && PYTHONPATH=pipeline python -m pytest pipeline/tests/test_ta_data_fetcher.py -v`
Expected: FAIL

- [ ] **Step 3: Implement data fetcher**

```python
# pipeline/ta_data_fetcher.py
"""
TA Data Fetcher — 5 years of daily OHLCV from EODHD for F&O stocks.

Bootstrap: fetch_batch(symbols) for all 213 stocks (~45 seconds).
Daily: fetch_stock_history(symbol, force=False) appends new days.
"""
from __future__ import annotations

import os
import csv
import time
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

log = logging.getLogger("anka.ta_data")

EODHD_BASE = "https://eodhd.com/api"
DEFAULT_CACHE = Path(__file__).parent / "data" / "ta_historical"
YEARS_BACK = 5


def _api_key() -> Optional[str]:
    key = os.getenv("EODHD_API_KEY", "").strip()
    return key if key and key != "YOUR_KEY_HERE" else None


def fetch_stock_history(
    symbol: str,
    cache_dir: Path = DEFAULT_CACHE,
    force: bool = False,
) -> Optional[Path]:
    """Fetch 5yr daily OHLCV for one stock. Returns path to CSV or None."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    csv_path = cache_dir / f"{symbol}.csv"

    if csv_path.exists() and not force:
        return csv_path

    key = _api_key()
    if not key:
        log.debug("EODHD_API_KEY not set — skipping %s", symbol)
        return None

    try:
        to_date = datetime.now().strftime("%Y-%m-%d")
        from_date = (datetime.now() - timedelta(days=YEARS_BACK * 365)).strftime("%Y-%m-%d")

        resp = requests.get(
            f"{EODHD_BASE}/eod/{symbol}.NSE",
            params={"api_token": key, "fmt": "json", "from": from_date, "to": to_date},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()

        if not isinstance(data, list) or not data:
            log.warning("EODHD returned empty for %s", symbol)
            return None

        with open(csv_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["Date", "Open", "High", "Low", "Close", "Volume"])
            for row in data:
                if "close" in row and row["close"]:
                    writer.writerow([
                        row["date"],
                        row.get("open", 0),
                        row.get("high", 0),
                        row.get("low", 0),
                        row["close"],
                        row.get("volume", 0),
                    ])

        log.info("  %s: %d days fetched", symbol, len(data))
        return csv_path

    except Exception as exc:
        log.warning("EODHD fetch failed for %s: %s", symbol, exc)
        return None


def fetch_batch(
    symbols: list[str],
    cache_dir: Path = DEFAULT_CACHE,
    delay: float = 0.2,
    force: bool = False,
) -> dict[str, Optional[Path]]:
    """Fetch history for all symbols. Returns {symbol: path_or_none}."""
    results = {}
    for i, sym in enumerate(symbols):
        results[sym] = fetch_stock_history(sym, cache_dir=cache_dir, force=force)
        if delay > 0 and i < len(symbols) - 1:
            time.sleep(delay)
        if (i + 1) % 50 == 0:
            log.info("  Progress: %d/%d", i + 1, len(symbols))
    return results
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd C:/Users/Claude_Anka/askanka.com && PYTHONPATH=pipeline python -m pytest pipeline/tests/test_ta_data_fetcher.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
cd C:/Users/Claude_Anka/askanka.com
git add pipeline/ta_data_fetcher.py pipeline/tests/test_ta_data_fetcher.py
git commit -m "feat(ta): EODHD 5yr OHLCV data fetcher with caching"
```

---

### Task 5: Pattern Event Detector

**Files:**
- Create: `pipeline/ta_pattern_detector.py`
- Create: `pipeline/tests/test_ta_pattern_detector.py`

- [ ] **Step 1: Write failing tests**

```python
# pipeline/tests/test_ta_pattern_detector.py
"""Tests for pattern event detector."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


def _trending_up_df(n: int = 60) -> pd.DataFrame:
    """Strong uptrend: close goes from 100 to 200."""
    closes = [100.0 + (i * 100.0 / n) for i in range(n)]
    return pd.DataFrame({
        "Date": pd.date_range("2025-01-01", periods=n, freq="B"),
        "Open": [c - 0.5 for c in closes],
        "High": [c + 2.0 for c in closes],
        "Low": [c - 2.0 for c in closes],
        "Close": closes,
        "Volume": [1000000] * n,
    })


def _with_dma200_crossover(n: int = 250) -> pd.DataFrame:
    """Price below 200 EMA for most of series, then crosses above at end."""
    closes = [100.0 - (i * 0.1) for i in range(230)]  # slow decline
    closes += [closes[-1] + (i * 1.5) for i in range(1, n - 230 + 1)]  # sharp recovery
    closes = closes[:n]
    return pd.DataFrame({
        "Date": pd.date_range("2024-01-01", periods=n, freq="B"),
        "Open": [c - 0.3 for c in closes],
        "High": [c + 1.0 for c in closes],
        "Low": [c - 1.0 for c in closes],
        "Close": closes,
        "Volume": [1000000] * n,
    })


def test_detect_events_returns_list():
    """detect_all_events returns a list of event dicts."""
    from ta_pattern_detector import detect_all_events
    df = _trending_up_df(60)
    events = detect_all_events(df)
    assert isinstance(events, list)
    if events:
        assert "date" in events[0]
        assert "pattern" in events[0]
        assert "direction" in events[0]


def test_rsi_overbought_detected_in_strong_uptrend():
    """Strong uptrend should trigger RSI_OVERBOUGHT_REV when RSI > 70 then drops."""
    from ta_pattern_detector import detect_all_events
    # Build: strong uptrend then pullback
    closes = [100.0 + i * 3.0 for i in range(30)] + [190.0 - i * 2.0 for i in range(10)]
    df = pd.DataFrame({
        "Date": pd.date_range("2025-01-01", periods=40, freq="B"),
        "Open": [c - 0.5 for c in closes],
        "High": [c + 1.0 for c in closes],
        "Low": [c - 1.0 for c in closes],
        "Close": closes,
        "Volume": [1000000] * 40,
    })
    events = detect_all_events(df)
    patterns = {e["pattern"] for e in events}
    assert "RSI_OVERBOUGHT_REV" in patterns or "MACD_CROSS_DN" in patterns


def test_dma200_crossover_detected():
    """Price crossing above 200 EMA triggers DMA200_CROSS_UP."""
    from ta_pattern_detector import detect_all_events
    df = _with_dma200_crossover(250)
    events = detect_all_events(df)
    patterns = {e["pattern"] for e in events}
    assert "DMA200_CROSS_UP" in patterns


def test_events_have_required_fields():
    """Every event has date, pattern, direction, price_at_event."""
    from ta_pattern_detector import detect_all_events
    df = _with_dma200_crossover(250)
    events = detect_all_events(df)
    for e in events:
        assert "date" in e
        assert "pattern" in e
        assert "direction" in e
        assert "price_at_event" in e
        assert e["direction"] in ("LONG", "SHORT", "NEUTRAL")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd C:/Users/Claude_Anka/askanka.com && PYTHONPATH=pipeline python -m pytest pipeline/tests/test_ta_pattern_detector.py -v`
Expected: FAIL

- [ ] **Step 3: Implement pattern detector**

```python
# pipeline/ta_pattern_detector.py
"""
Pattern Event Detector — scans indicator output for 15 actionable pattern types.

Takes an OHLCV DataFrame, computes all indicators, returns a list of event dicts.
"""
from __future__ import annotations

import pandas as pd
import numpy as np
from ta_indicators import sma, ema, bollinger, macd, rsi, atr, volume_spike, detect_candles

PATTERN_DIRECTION = {
    "BB_SQUEEZE": "LONG", "BB_BREAKOUT_UP": "LONG", "BB_BREAKOUT_DN": "SHORT",
    "DMA200_CROSS_UP": "LONG", "DMA200_CROSS_DN": "SHORT",
    "MACD_CROSS_UP": "LONG", "MACD_CROSS_DN": "SHORT",
    "RSI_OVERSOLD_BOUNCE": "LONG", "RSI_OVERBOUGHT_REV": "SHORT",
    "VOL_BREAKOUT": "LONG",
    "ATR_COMPRESSION": "NEUTRAL",
    "CANDLE_HAMMER": "LONG", "CANDLE_ENGULF_BULL": "LONG",
    "CANDLE_ENGULF_BEAR": "SHORT", "CANDLE_DOJI": "NEUTRAL",
}


def _crosses_above(series: pd.Series, level: pd.Series) -> pd.Series:
    """True on the day series crosses above level (was below yesterday, above today)."""
    return (series > level) & (series.shift(1) <= level.shift(1))


def _crosses_below(series: pd.Series, level: pd.Series) -> pd.Series:
    """True on the day series crosses below level."""
    return (series < level) & (series.shift(1) >= level.shift(1))


def detect_all_events(df: pd.DataFrame) -> list[dict]:
    """Detect all 15 pattern types in an OHLCV DataFrame.

    Returns list of {"date", "pattern", "direction", "price_at_event"}.
    """
    if len(df) < 50:
        return []

    close = df["Close"].astype(float)
    dates = df["Date"]
    events: list[dict] = []

    def _add(mask: pd.Series, pattern: str):
        for idx in mask[mask].index:
            events.append({
                "date": str(dates.iloc[idx] if isinstance(dates.iloc[idx], str) else dates.iloc[idx].strftime("%Y-%m-%d")) if idx < len(dates) else "",
                "pattern": pattern,
                "direction": PATTERN_DIRECTION[pattern],
                "price_at_event": float(close.iloc[idx]) if idx < len(close) else 0.0,
            })

    # Bollinger Bands
    bb = bollinger(df)
    vol = volume_spike(df)
    bb_bw = bb["bandwidth"]
    bb_bw_min20 = bb_bw.rolling(20, min_periods=20).min()
    squeeze = (bb_bw <= bb_bw_min20.shift(1)) & (bb_bw > bb_bw.shift(1))
    _add(squeeze, "BB_SQUEEZE")
    _add((close > bb["upper"]) & vol, "BB_BREAKOUT_UP")
    _add((close < bb["lower"]) & vol, "BB_BREAKOUT_DN")

    # 200 EMA crossover
    ema200 = ema(close, 200)
    _add(_crosses_above(close, ema200), "DMA200_CROSS_UP")
    _add(_crosses_below(close, ema200), "DMA200_CROSS_DN")

    # MACD
    m = macd(df)
    _add(_crosses_above(m["macd_line"], m["signal_line"]), "MACD_CROSS_UP")
    _add(_crosses_below(m["macd_line"], m["signal_line"]), "MACD_CROSS_DN")

    # RSI
    r = rsi(df)
    _add(_crosses_above(r, pd.Series(30.0, index=r.index)), "RSI_OVERSOLD_BOUNCE")
    _add(_crosses_below(r, pd.Series(70.0, index=r.index)), "RSI_OVERBOUGHT_REV")

    # Volume breakout
    high_20 = close.rolling(20, min_periods=20).max().shift(1)
    _add(vol & (close > high_20), "VOL_BREAKOUT")

    # ATR compression
    a = atr(df)
    a_sma50 = sma(a, 50)
    _add(a < 0.5 * a_sma50, "ATR_COMPRESSION")

    # Candlesticks
    candles = detect_candles(df)
    sma20 = sma(close, 20)
    sma50 = sma(close, 50)
    near_ma = ((close - sma20).abs() / close < 0.02) | ((close - sma50).abs() / close < 0.02)
    _add(candles["hammer"] & near_ma, "CANDLE_HAMMER")

    # Engulfing after 3+ consecutive candles in opposite direction
    prev_red_3 = (close.shift(1) < df["Open"].astype(float).shift(1)) & \
                 (close.shift(2) < df["Open"].astype(float).shift(2)) & \
                 (close.shift(3) < df["Open"].astype(float).shift(3))
    prev_green_3 = (close.shift(1) > df["Open"].astype(float).shift(1)) & \
                   (close.shift(2) > df["Open"].astype(float).shift(2)) & \
                   (close.shift(3) > df["Open"].astype(float).shift(3))
    _add(candles["engulfing_bull"] & prev_red_3, "CANDLE_ENGULF_BULL")
    _add(candles["engulfing_bear"] & prev_green_3, "CANDLE_ENGULF_BEAR")

    # Doji near 20-day high or low
    high_20d = close.rolling(20, min_periods=20).max()
    low_20d = close.rolling(20, min_periods=20).min()
    near_extreme = ((close - high_20d).abs() / close < 0.01) | ((close - low_20d).abs() / close < 0.01)
    _add(candles["doji"] & near_extreme, "CANDLE_DOJI")

    return sorted(events, key=lambda e: e["date"])
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd C:/Users/Claude_Anka/askanka.com && PYTHONPATH=pipeline python -m pytest pipeline/tests/test_ta_pattern_detector.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
cd C:/Users/Claude_Anka/askanka.com
git add pipeline/ta_pattern_detector.py pipeline/tests/test_ta_pattern_detector.py
git commit -m "feat(ta): pattern event detector — 15 pattern types from indicator output"
```

---

### Task 6: Backtest Engine

**Files:**
- Create: `pipeline/ta_backtester.py`
- Create: `pipeline/tests/test_ta_backtester.py`

- [ ] **Step 1: Write failing tests**

```python
# pipeline/tests/test_ta_backtester.py
"""Tests for TA backtest engine — forward returns after pattern events."""
from __future__ import annotations

import pandas as pd
import pytest


def _make_prices(n: int = 30, start: float = 100.0, step: float = 1.0) -> pd.DataFrame:
    closes = [start + i * step for i in range(n)]
    return pd.DataFrame({
        "Date": pd.date_range("2025-01-01", periods=n, freq="B"),
        "Close": closes,
    })


SAMPLE_EVENTS = [
    {"date": "2025-01-06", "pattern": "BB_SQUEEZE", "direction": "LONG", "price_at_event": 105.0},
    {"date": "2025-01-13", "pattern": "BB_SQUEEZE", "direction": "LONG", "price_at_event": 112.0},
    {"date": "2025-01-20", "pattern": "RSI_OVERBOUGHT_REV", "direction": "SHORT", "price_at_event": 119.0},
]


def test_backtest_returns_stats_per_pattern():
    """Backtest produces stats dict keyed by pattern."""
    from ta_backtester import backtest_events
    df = _make_prices(30, 100.0, 1.0)
    stats = backtest_events(SAMPLE_EVENTS, df)
    assert "BB_SQUEEZE" in stats
    assert stats["BB_SQUEEZE"]["occurrences"] == 2
    assert "win_rate_5d" in stats["BB_SQUEEZE"]
    assert "avg_return_5d" in stats["BB_SQUEEZE"]


def test_backtest_long_wins_on_uptrend():
    """LONG events in uptrend → positive returns, high win rate."""
    from ta_backtester import backtest_events
    df = _make_prices(30, 100.0, 1.0)  # monotonic up
    events = [{"date": "2025-01-06", "pattern": "TEST_LONG", "direction": "LONG", "price_at_event": 105.0}]
    stats = backtest_events(events, df)
    assert stats["TEST_LONG"]["win_rate_5d"] == 1.0
    assert stats["TEST_LONG"]["avg_return_5d"] > 0


def test_backtest_short_wins_on_downtrend():
    """SHORT events in downtrend → positive win rate."""
    from ta_backtester import backtest_events
    df = _make_prices(30, 130.0, -1.0)  # monotonic down
    events = [{"date": "2025-01-06", "pattern": "TEST_SHORT", "direction": "SHORT", "price_at_event": 125.0}]
    stats = backtest_events(events, df)
    assert stats["TEST_SHORT"]["win_rate_5d"] == 1.0


def test_backtest_skips_events_near_end():
    """Events too close to end of data (not enough forward days) are excluded."""
    from ta_backtester import backtest_events
    df = _make_prices(15, 100.0, 1.0)
    events = [{"date": "2025-01-20", "pattern": "LATE", "direction": "LONG", "price_at_event": 114.0}]
    stats = backtest_events(events, df)
    # Event is too late for 10d forward return
    assert stats.get("LATE", {}).get("occurrences", 0) <= 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd C:/Users/Claude_Anka/askanka.com && PYTHONPATH=pipeline python -m pytest pipeline/tests/test_ta_backtester.py -v`
Expected: FAIL

- [ ] **Step 3: Implement backtest engine**

```python
# pipeline/ta_backtester.py
"""
TA Backtest Engine — measure forward returns after pattern events.

Takes a list of events + OHLCV DataFrame, returns per-pattern statistics
with win rates and average returns at 1/3/5/10 day horizons.
"""
from __future__ import annotations

import pandas as pd
import numpy as np
from collections import defaultdict


HORIZONS = [1, 3, 5, 10]


def backtest_events(events: list[dict], df: pd.DataFrame) -> dict[str, dict]:
    """Compute forward return statistics for each pattern type.

    Returns: {pattern: {occurrences, win_rate_Nd, avg_return_Nd, ...}}
    """
    if not events or df.empty:
        return {}

    close = df.set_index("Date")["Close"].astype(float)
    if not isinstance(close.index, pd.DatetimeIndex):
        close.index = pd.to_datetime(close.index)

    pattern_returns: dict[str, list[dict]] = defaultdict(list)

    for event in events:
        event_date = pd.Timestamp(event["date"])
        if event_date not in close.index:
            idx = close.index.searchsorted(event_date)
            if idx >= len(close.index):
                continue
            event_date = close.index[idx]

        pos = close.index.get_loc(event_date)
        if isinstance(pos, slice):
            pos = pos.start

        entry_price = close.iloc[pos]
        fwd = {}
        for h in HORIZONS:
            if pos + h < len(close):
                exit_price = close.iloc[pos + h]
                ret = (exit_price - entry_price) / entry_price * 100.0
                fwd[h] = ret

        if fwd:
            pattern_returns[event["pattern"]].append({
                "direction": event["direction"],
                "returns": fwd,
            })

    results = {}
    for pattern, trades in pattern_returns.items():
        n = len(trades)
        direction = trades[0]["direction"]
        stats: dict = {"occurrences": n, "direction": direction}

        for h in HORIZONS:
            rets = [t["returns"][h] for t in trades if h in t["returns"]]
            if not rets:
                continue
            if direction == "SHORT":
                rets = [-r for r in rets]
            wins = sum(1 for r in rets if r > 0)
            stats[f"win_rate_{h}d"] = round(wins / len(rets), 2)
            stats[f"avg_return_{h}d"] = round(np.mean(rets), 2)
            stats[f"max_return_{h}d"] = round(max(rets), 2)
            stats[f"min_return_{h}d"] = round(min(rets), 2)

        dates = []
        for event in events:
            if event["pattern"] == pattern:
                dates.append(event["date"])
        stats["last_occurrence"] = max(dates) if dates else ""
        stats["dates"] = sorted(dates)

        results[pattern] = stats

    return results
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd C:/Users/Claude_Anka/askanka.com && PYTHONPATH=pipeline python -m pytest pipeline/tests/test_ta_backtester.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
cd C:/Users/Claude_Anka/askanka.com
git add pipeline/ta_backtester.py pipeline/tests/test_ta_backtester.py
git commit -m "feat(ta): backtest engine — forward returns at 1/3/5/10d horizons"
```

---

### Task 7: Fingerprint Card Generator

**Files:**
- Create: `pipeline/ta_fingerprint.py`
- Create: `pipeline/tests/test_ta_fingerprint.py`

- [ ] **Step 1: Write failing tests**

```python
# pipeline/tests/test_ta_fingerprint.py
"""Tests for fingerprint card generator."""
from __future__ import annotations

import json
import pytest
from pathlib import Path


SAMPLE_BACKTEST = {
    "BB_SQUEEZE": {
        "occurrences": 18, "direction": "LONG",
        "win_rate_5d": 0.72, "avg_return_5d": 2.8, "avg_return_10d": 4.1,
        "min_return_5d": -3.1, "last_occurrence": "2026-03-12",
    },
    "DMA200_CROSS_UP": {
        "occurrences": 4, "direction": "LONG",
        "win_rate_5d": 0.50, "avg_return_5d": 1.2, "avg_return_10d": 1.8,
        "min_return_5d": -2.0, "last_occurrence": "2025-11-03",
    },
    "RSI_OVERSOLD_BOUNCE": {
        "occurrences": 12, "direction": "LONG",
        "win_rate_5d": 0.58, "avg_return_5d": 1.5, "avg_return_10d": 2.2,
        "min_return_5d": -1.8, "last_occurrence": "2026-02-10",
    },
    "MACD_CROSS_UP": {
        "occurrences": 3, "direction": "LONG",
        "win_rate_5d": 0.33, "avg_return_5d": -0.5, "avg_return_10d": 0.1,
        "min_return_5d": -4.0, "last_occurrence": "2025-06-01",
    },
}


def test_generate_fingerprint_filters_significant():
    """Only patterns with ≥5 occurrences AND ≥50% win rate are included."""
    from ta_fingerprint import generate_fingerprint
    card = generate_fingerprint("HAL", SAMPLE_BACKTEST, data_points=1247)
    patterns = {p["pattern"] for p in card["fingerprint"]}
    assert "BB_SQUEEZE" in patterns      # 18 occ, 72% → STRONG
    assert "RSI_OVERSOLD_BOUNCE" in patterns  # 12 occ, 58% → MODERATE
    assert "DMA200_CROSS_UP" not in patterns  # 4 occ → below threshold
    assert "MACD_CROSS_UP" not in patterns    # 3 occ, 33% → below threshold


def test_significance_levels():
    """STRONG ≥10 occ + ≥60%; MODERATE ≥5 occ + ≥55%."""
    from ta_fingerprint import generate_fingerprint
    card = generate_fingerprint("HAL", SAMPLE_BACKTEST, data_points=1247)
    by_pattern = {p["pattern"]: p for p in card["fingerprint"]}
    assert by_pattern["BB_SQUEEZE"]["significance"] == "STRONG"
    assert by_pattern["RSI_OVERSOLD_BOUNCE"]["significance"] == "MODERATE"


def test_personality_classification():
    """Best pattern is BB_SQUEEZE → personality = momentum_breakout."""
    from ta_fingerprint import generate_fingerprint
    card = generate_fingerprint("HAL", SAMPLE_BACKTEST, data_points=1247)
    assert card["personality"] == "momentum_breakout"
    assert card["best_pattern"] == "BB_SQUEEZE"


def test_empty_backtest_returns_agnostic():
    """No significant patterns → personality = pattern_agnostic."""
    from ta_fingerprint import generate_fingerprint
    card = generate_fingerprint("UNKNOWN", {}, data_points=1247)
    assert card["personality"] == "pattern_agnostic"
    assert card["significant_patterns"] == 0


def test_fingerprint_writes_json(tmp_path: Path):
    """save_fingerprint writes to correct path."""
    from ta_fingerprint import generate_fingerprint, save_fingerprint
    card = generate_fingerprint("HAL", SAMPLE_BACKTEST, data_points=1247)
    save_fingerprint(card, output_dir=tmp_path)
    path = tmp_path / "HAL.json"
    assert path.exists()
    loaded = json.loads(path.read_text())
    assert loaded["symbol"] == "HAL"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd C:/Users/Claude_Anka/askanka.com && PYTHONPATH=pipeline python -m pytest pipeline/tests/test_ta_fingerprint.py -v`
Expected: FAIL

- [ ] **Step 3: Implement fingerprint generator**

```python
# pipeline/ta_fingerprint.py
"""
Fingerprint Card Generator — per-stock technical profile from backtest results.

Filters statistically significant patterns, assigns personality classification,
writes JSON fingerprint cards.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

log = logging.getLogger("anka.ta_fingerprint")

IST = timezone(timedelta(hours=5, minutes=30))
DEFAULT_OUTPUT = Path(__file__).parent / "data" / "ta_fingerprints"

MOMENTUM_PATTERNS = {"BB_SQUEEZE", "VOL_BREAKOUT", "BB_BREAKOUT_UP"}
MEAN_REVERT_PATTERNS = {"RSI_OVERSOLD_BOUNCE", "RSI_OVERBOUGHT_REV"}
TREND_PATTERNS = {"DMA200_CROSS_UP", "MACD_CROSS_UP", "DMA200_CROSS_DN", "MACD_CROSS_DN"}
CANDLE_PATTERNS = {"CANDLE_HAMMER", "CANDLE_ENGULF_BULL", "CANDLE_ENGULF_BEAR", "CANDLE_DOJI"}


def _significance(occurrences: int, win_rate: float) -> str:
    if occurrences >= 10 and win_rate >= 0.60:
        return "STRONG"
    if occurrences >= 5 and win_rate >= 0.55:
        return "MODERATE"
    if occurrences >= 5 and win_rate >= 0.50:
        return "WEAK"
    return "INSIGNIFICANT"


def _classify_personality(significant: list[dict]) -> str:
    if not significant:
        return "pattern_agnostic"
    best = significant[0]["pattern"]
    if best in MOMENTUM_PATTERNS:
        return "momentum_breakout"
    if best in MEAN_REVERT_PATTERNS:
        return "mean_reverter"
    if best in TREND_PATTERNS:
        return "trend_follower"
    if best == "VOL_BREAKOUT":
        return "volume_driven"
    if best in CANDLE_PATTERNS:
        return "candlestick_responsive"
    return "mixed"


def generate_fingerprint(symbol: str, backtest_stats: dict, data_points: int = 0) -> dict:
    """Generate a fingerprint card from backtest statistics.

    Args:
        symbol: NSE stock symbol
        backtest_stats: {pattern: {occurrences, win_rate_5d, avg_return_5d, ...}}
        data_points: number of OHLCV rows used

    Returns: fingerprint card dict
    """
    significant: list[dict] = []

    for pattern, stats in backtest_stats.items():
        occ = stats.get("occurrences", 0)
        wr = stats.get("win_rate_5d", 0)
        sig = _significance(occ, wr)
        if sig == "INSIGNIFICANT":
            continue
        significant.append({
            "pattern": pattern,
            "direction": stats.get("direction", "LONG"),
            "significance": sig,
            "occurrences": occ,
            "win_rate_5d": wr,
            "avg_return_5d": stats.get("avg_return_5d", 0),
            "avg_return_10d": stats.get("avg_return_10d", 0),
            "avg_drawdown": stats.get("min_return_5d", 0),
            "last_occurrence": stats.get("last_occurrence", ""),
        })

    significant.sort(key=lambda x: (-["INSIGNIFICANT", "WEAK", "MODERATE", "STRONG"].index(x["significance"]),
                                     -x["win_rate_5d"]))

    now = datetime.now(IST)
    return {
        "symbol": symbol,
        "generated": now.strftime("%Y-%m-%d"),
        "data_points": data_points,
        "total_patterns_tested": 15,
        "significant_patterns": len(significant),
        "fingerprint": significant,
        "best_pattern": significant[0]["pattern"] if significant else None,
        "best_win_rate": significant[0]["win_rate_5d"] if significant else 0,
        "personality": _classify_personality(significant),
    }


def save_fingerprint(card: dict, output_dir: Path = DEFAULT_OUTPUT) -> Path:
    """Write fingerprint card to JSON file."""
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{card['symbol']}.json"
    path.write_text(json.dumps(card, indent=2, ensure_ascii=False), encoding="utf-8")
    return path
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd C:/Users/Claude_Anka/askanka.com && PYTHONPATH=pipeline python -m pytest pipeline/tests/test_ta_fingerprint.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
cd C:/Users/Claude_Anka/askanka.com
git add pipeline/ta_fingerprint.py pipeline/tests/test_ta_fingerprint.py
git commit -m "feat(ta): fingerprint card generator with personality classification"
```

---

### Task 8: Daily Scanner

**Files:**
- Create: `pipeline/ta_daily_scanner.py`
- Create: `pipeline/tests/test_ta_daily_scanner.py`

- [ ] **Step 1: Write failing tests**

```python
# pipeline/tests/test_ta_daily_scanner.py
"""Tests for TA daily scanner — check live prices vs fingerprint cards."""
from __future__ import annotations

import json
import pytest
from pathlib import Path
from unittest.mock import patch
import pandas as pd


SAMPLE_FINGERPRINT = {
    "symbol": "HAL",
    "fingerprint": [
        {"pattern": "BB_SQUEEZE", "direction": "LONG", "significance": "STRONG",
         "occurrences": 18, "win_rate_5d": 0.72, "avg_return_5d": 2.8},
        {"pattern": "RSI_OVERSOLD_BOUNCE", "direction": "LONG", "significance": "MODERATE",
         "occurrences": 12, "win_rate_5d": 0.58, "avg_return_5d": 1.5},
    ],
}


@pytest.fixture
def setup_dirs(tmp_path: Path):
    fp_dir = tmp_path / "ta_fingerprints"
    fp_dir.mkdir()
    (fp_dir / "HAL.json").write_text(json.dumps(SAMPLE_FINGERPRINT))

    hist_dir = tmp_path / "ta_historical"
    hist_dir.mkdir()
    # Write 50 days of CSV
    rows = ["Date,Open,High,Low,Close,Volume"]
    for i in range(50):
        d = f"2025-{(i // 30) + 1:02d}-{(i % 28) + 1:02d}"
        rows.append(f"{d},{100+i},{102+i},{98+i},{101+i},1000000")
    (hist_dir / "HAL.csv").write_text("\n".join(rows))

    return {"fingerprints": fp_dir, "historical": hist_dir, "output": tmp_path}


def test_scan_returns_alerts(setup_dirs):
    """Scanner returns a list of alert dicts."""
    from ta_daily_scanner import scan_stock
    alerts = scan_stock("HAL",
                        fingerprint_dir=setup_dirs["fingerprints"],
                        historical_dir=setup_dirs["historical"])
    assert isinstance(alerts, list)
    for a in alerts:
        assert "symbol" in a
        assert "pattern" in a
        assert "status" in a
        assert a["status"] in ("TRIGGERED", "APPROACHING")


def test_scan_missing_fingerprint_returns_empty(setup_dirs):
    """Stock without fingerprint card → empty alerts."""
    from ta_daily_scanner import scan_stock
    alerts = scan_stock("NONEXISTENT",
                        fingerprint_dir=setup_dirs["fingerprints"],
                        historical_dir=setup_dirs["historical"])
    assert alerts == []


def test_scan_all_writes_output(setup_dirs):
    """scan_all writes ta_alerts.json."""
    from ta_daily_scanner import scan_all
    scan_all(symbols=["HAL"],
             fingerprint_dir=setup_dirs["fingerprints"],
             historical_dir=setup_dirs["historical"],
             output_path=setup_dirs["output"] / "ta_alerts.json")
    assert (setup_dirs["output"] / "ta_alerts.json").exists()
    data = json.loads((setup_dirs["output"] / "ta_alerts.json").read_text())
    assert "date" in data
    assert "alerts" in data
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd C:/Users/Claude_Anka/askanka.com && PYTHONPATH=pipeline python -m pytest pipeline/tests/test_ta_daily_scanner.py -v`
Expected: FAIL

- [ ] **Step 3: Implement daily scanner**

```python
# pipeline/ta_daily_scanner.py
"""
TA Daily Scanner — check live prices against each stock's fingerprint card.

Runs at 15:35 IST as scheduled task. Checks if any of the 213 F&O stocks
is at or near a pattern trigger from its proven fingerprint.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pandas as pd
from ta_indicators import bollinger, macd, rsi, atr, ema, sma, volume_spike, detect_candles

log = logging.getLogger("anka.ta_scanner")

IST = timezone(timedelta(hours=5, minutes=30))
DEFAULT_FINGERPRINTS = Path(__file__).parent / "data" / "ta_fingerprints"
DEFAULT_HISTORICAL = Path(__file__).parent / "data" / "ta_historical"
DEFAULT_OUTPUT = Path(__file__).parent / "data" / "ta_alerts.json"


def _load_fingerprint(symbol: str, fingerprint_dir: Path) -> dict | None:
    path = fingerprint_dir / f"{symbol}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _load_ohlcv(symbol: str, historical_dir: Path) -> pd.DataFrame | None:
    path = historical_dir / f"{symbol}.csv"
    if not path.exists():
        return None
    df = pd.read_csv(path, parse_dates=["Date"])
    return df.sort_values("Date").reset_index(drop=True)


def _check_pattern_proximity(pattern: str, df: pd.DataFrame) -> dict | None:
    """Check if a pattern is TRIGGERED or APPROACHING on the latest bar."""
    if len(df) < 50:
        return None

    close = df["Close"].astype(float)
    last = close.iloc[-1]
    prev = close.iloc[-2] if len(close) > 1 else last

    if pattern == "BB_SQUEEZE":
        bb = bollinger(df)
        bw = bb["bandwidth"]
        bw_min20 = bw.rolling(20, min_periods=20).min()
        if pd.notna(bw.iloc[-1]) and pd.notna(bw_min20.iloc[-2]):
            if bw.iloc[-1] <= bw_min20.iloc[-2]:
                return {"status": "TRIGGERED", "detail": f"bandwidth={bw.iloc[-1]:.4f}"}
            ratio = bw.iloc[-1] / max(bw_min20.iloc[-2], 0.0001)
            if ratio < 1.1:
                return {"status": "APPROACHING", "proximity_pct": round((ratio - 1) * 100, 1)}

    elif pattern == "DMA200_CROSS_UP":
        e200 = ema(close, 200)
        if pd.notna(e200.iloc[-1]):
            if prev <= e200.iloc[-2] and last > e200.iloc[-1]:
                return {"status": "TRIGGERED", "detail": f"ema200={e200.iloc[-1]:.1f}"}
            dist = (last - e200.iloc[-1]) / e200.iloc[-1] * 100
            if -2.0 < dist < 0:
                return {"status": "APPROACHING", "proximity_pct": round(abs(dist), 1)}

    elif pattern == "RSI_OVERSOLD_BOUNCE":
        r = rsi(df)
        if pd.notna(r.iloc[-1]):
            if r.iloc[-2] < 30 and r.iloc[-1] >= 30:
                return {"status": "TRIGGERED", "detail": f"rsi={r.iloc[-1]:.1f}"}
            if 30 <= r.iloc[-1] <= 35:
                return {"status": "APPROACHING", "proximity_pct": round(r.iloc[-1] - 30, 1)}

    elif pattern == "MACD_CROSS_UP":
        m = macd(df)
        ml, sl = m["macd_line"], m["signal_line"]
        if pd.notna(ml.iloc[-1]) and pd.notna(sl.iloc[-1]):
            if ml.iloc[-2] <= sl.iloc[-2] and ml.iloc[-1] > sl.iloc[-1]:
                return {"status": "TRIGGERED", "detail": "macd crossed signal"}
            gap = (ml.iloc[-1] - sl.iloc[-1]) / max(abs(sl.iloc[-1]), 0.01)
            if -0.05 < gap < 0:
                return {"status": "APPROACHING", "proximity_pct": round(abs(gap) * 100, 1)}

    elif pattern == "VOL_BREAKOUT":
        vs = volume_spike(df)
        high_20 = close.rolling(20, min_periods=20).max().shift(1)
        if vs.iloc[-1] and last > high_20.iloc[-1]:
            return {"status": "TRIGGERED", "detail": f"vol_spike + new 20d high"}

    elif pattern == "ATR_COMPRESSION":
        a = atr(df)
        a_avg = sma(a, 50)
        if pd.notna(a.iloc[-1]) and pd.notna(a_avg.iloc[-1]):
            if a.iloc[-1] < 0.5 * a_avg.iloc[-1]:
                return {"status": "TRIGGERED", "detail": f"atr={a.iloc[-1]:.2f}"}

    return None


def scan_stock(
    symbol: str,
    fingerprint_dir: Path = DEFAULT_FINGERPRINTS,
    historical_dir: Path = DEFAULT_HISTORICAL,
) -> list[dict]:
    """Check one stock against its fingerprint card. Returns list of alerts."""
    fp = _load_fingerprint(symbol, fingerprint_dir)
    if not fp:
        return []

    df = _load_ohlcv(symbol, historical_dir)
    if df is None or df.empty:
        return []

    alerts = []
    for entry in fp.get("fingerprint", []):
        pattern = entry["pattern"]
        result = _check_pattern_proximity(pattern, df)
        if result:
            alerts.append({
                "symbol": symbol,
                "pattern": pattern,
                "status": result["status"],
                "proximity_pct": result.get("proximity_pct"),
                "detail": result.get("detail"),
                "historical_win_rate": entry.get("win_rate_5d", 0),
                "historical_avg_return": entry.get("avg_return_5d", 0),
                "occurrences": entry.get("occurrences", 0),
                "direction": entry.get("direction", "LONG"),
                "current_price": float(df["Close"].iloc[-1]),
            })

    return alerts


def scan_all(
    symbols: list[str] | None = None,
    fingerprint_dir: Path = DEFAULT_FINGERPRINTS,
    historical_dir: Path = DEFAULT_HISTORICAL,
    output_path: Path = DEFAULT_OUTPUT,
) -> dict:
    """Scan all stocks and write ta_alerts.json."""
    if symbols is None:
        symbols = [f.stem for f in fingerprint_dir.glob("*.json")]

    all_alerts = []
    for sym in symbols:
        alerts = scan_stock(sym, fingerprint_dir, historical_dir)
        all_alerts.extend(alerts)

    output = {
        "date": datetime.now(IST).strftime("%Y-%m-%d"),
        "scanned": len(symbols),
        "alerts": sorted(all_alerts, key=lambda a: (-a["historical_win_rate"], a["symbol"])),
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    log.info("TA scan: %d stocks, %d alerts", len(symbols), len(all_alerts))

    return output


if __name__ == "__main__":
    import sys, logging
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    scan_all()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd C:/Users/Claude_Anka/askanka.com && PYTHONPATH=pipeline python -m pytest pipeline/tests/test_ta_daily_scanner.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
cd C:/Users/Claude_Anka/askanka.com
git add pipeline/ta_daily_scanner.py pipeline/tests/test_ta_daily_scanner.py
git commit -m "feat(ta): daily scanner — checks live prices vs fingerprint cards"
```

---

### Task 9: Bootstrap — Fetch 5yr Data and Generate Fingerprints

This is the operational task — run the pipeline end-to-end.

- [ ] **Step 1: Fetch 5yr OHLCV for all 213 stocks**

```bash
cd C:/Users/Claude_Anka/askanka.com
PYTHONPATH=pipeline python -c "
import json, logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
from ta_data_fetcher import fetch_batch
symbols = json.load(open('opus/config/fno_stocks.json'))['symbols']
result = fetch_batch(symbols, delay=0.2)
fetched = sum(1 for v in result.values() if v is not None)
print(f'Fetched: {fetched}/213')
"
```

Expected: ≥ 200 of 213 fetched

- [ ] **Step 2: Generate fingerprint cards for all stocks**

```bash
cd C:/Users/Claude_Anka/askanka.com
PYTHONPATH=pipeline python -c "
import json, logging, pandas as pd
from pathlib import Path
logging.basicConfig(level=logging.INFO, format='%(message)s')
from ta_pattern_detector import detect_all_events
from ta_backtester import backtest_events
from ta_fingerprint import generate_fingerprint, save_fingerprint

hist_dir = Path('pipeline/data/ta_historical')
symbols = json.load(open('opus/config/fno_stocks.json'))['symbols']
strong = 0; moderate = 0; agnostic = 0

for i, sym in enumerate(symbols):
    csv_path = hist_dir / f'{sym}.csv'
    if not csv_path.exists():
        continue
    df = pd.read_csv(csv_path, parse_dates=['Date'])
    events = detect_all_events(df)
    stats = backtest_events(events, df)
    card = generate_fingerprint(sym, stats, data_points=len(df))
    save_fingerprint(card)

    sig = card['significant_patterns']
    if sig > 0:
        if card['fingerprint'][0]['significance'] == 'STRONG':
            strong += 1
        else:
            moderate += 1
    else:
        agnostic += 1

    if (i + 1) % 50 == 0:
        print(f'  Progress: {i+1}/{len(symbols)}')

print(f'Done: {strong} strong, {moderate} moderate, {agnostic} agnostic')
"
```

Expected: ≥ 150 stocks with at least one MODERATE+ pattern

- [ ] **Step 3: Run daily scanner**

```bash
cd C:/Users/Claude_Anka/askanka.com
PYTHONPATH=pipeline python ta_daily_scanner.py
cat pipeline/data/ta_alerts.json | python -m json.tool | head -30
```

Expected: alerts JSON with TRIGGERED and APPROACHING entries

- [ ] **Step 4: Commit generated data**

```bash
cd C:/Users/Claude_Anka/askanka.com
git add -f pipeline/data/ta_alerts.json
git commit -m "data(ta): first fingerprint scan — 213 stocks × 15 patterns × 5 years"
```
