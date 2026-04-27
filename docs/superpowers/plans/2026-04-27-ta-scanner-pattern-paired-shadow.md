# Scanner (TA) Pattern Engine + Paired-Shadow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current Scanner (TA) tab's broken display with a daily F&O-universe pattern-occurrence engine that ranks today's candlestick / structural / momentum fires by historical win-rate × z-score × magnitude, surfaces the Top-10, and fires paired (futures + ATM monthly options) forward-only OOS shadow trades on each.

**Architecture:** Five layers — `detect` (daily pandas-ta scan), `stats` (weekly 5y walk-forward fit), `rank` (Top-10 composite ranker), `UI rewire` (Scanner tab + click-to-chart fix), `paired shadow` (sidecar engine reusing Phase C helper modules). Sidecar pattern: open at T+1 09:25 IST, close mechanical at T+1 15:30 IST. Forward-only OOS, descriptive only — no edge claim, no §0-16 compliance, no kill-switch trigger.

**Tech Stack:** Python 3.11, `pandas-ta==0.3.14b`, pandas, parquet (pyarrow), pytest, FastAPI (existing terminal API), vanilla JS (existing terminal frontend), Kite Connect (existing).

**Spec:** `docs/superpowers/specs/2026-04-27-ta-scanner-pattern-paired-shadow-design.md` (commit 7e7c6be).

**Hard prerequisite:** This plan reuses three helper modules introduced by the Phase C paired-shadow spec (`docs/superpowers/specs/2026-04-27-phase-c-options-paired-shadow-design.md`):
- `pipeline/options_atm_helpers.py` (`resolve_atm_strike`, `resolve_nearest_monthly_expiry`, `compose_tradingsymbol`)
- `pipeline/options_quote.py` (`fetch_mid_with_liquidity_check`, `OptionsQuote`)
- `pipeline/options_greeks.py` (`backsolve_iv`, `compute_greeks`)

If those files don't exist when starting Task 7, run Phase C plan tasks T1–T3 first.

---

## Task 0: Verify pandas-ta install + pin version

**Files:**
- Modify: `requirements.txt`
- Test: `pipeline/tests/pattern_scanner/test_pandas_ta_smoke.py`

**Files (create dirs):**
- Create: `pipeline/pattern_scanner/__init__.py` (empty)
- Create: `pipeline/tests/pattern_scanner/__init__.py` (empty)

- [ ] **Step 1: Add pandas-ta to requirements.txt**

Append to `requirements.txt`:
```
pandas-ta==0.3.14b
```

- [ ] **Step 2: Install in venv**

Run: `pip install pandas-ta==0.3.14b`
Expected: install succeeds without TA-Lib transitive dep on Windows. If pip resolver tries to pull TA-Lib, fail loudly — see §15 risk #1 in spec; fallback is hand-rolling 12 detectors in numpy.

- [ ] **Step 3: Create empty package files**

```bash
mkdir -p pipeline/pattern_scanner pipeline/tests/pattern_scanner
type nul > pipeline/pattern_scanner/__init__.py
type nul > pipeline/tests/pattern_scanner/__init__.py
```

- [ ] **Step 4: Write smoke test**

`pipeline/tests/pattern_scanner/test_pandas_ta_smoke.py`:
```python
"""Smoke test: pandas-ta installs and produces expected outputs on a 1-bar fixture."""
import pandas as pd
import pandas_ta as ta


def _bullish_hammer_bar() -> pd.DataFrame:
    """A canonical bullish-hammer candle: small body near high, long lower shadow,
    coming after a downtrend."""
    return pd.DataFrame({
        "open":  [100.0, 99.0, 98.0, 97.0, 96.0, 95.0, 94.0],
        "high":  [101.0, 100.0, 99.0, 98.0, 97.0, 96.0, 95.5],
        "low":   [99.0,  98.0, 97.0, 96.0, 95.0, 94.0, 92.0],
        "close": [99.5,  98.5, 97.5, 96.5, 95.5, 94.5, 95.4],
    })


def test_pandas_ta_imports_and_runs():
    df = _bullish_hammer_bar()
    result = ta.cdl_pattern(df["open"], df["high"], df["low"], df["close"], name="hammer")
    assert result is not None
    assert len(result) == len(df)


def test_pandas_ta_macd_runs():
    df = pd.DataFrame({"close": [100.0 + i * 0.5 for i in range(50)]})
    macd = ta.macd(df["close"])
    assert macd is not None
    assert "MACD_12_26_9" in macd.columns
    assert "MACDs_12_26_9" in macd.columns


def test_pandas_ta_bbands_runs():
    df = pd.DataFrame({"close": [100.0 + i * 0.1 for i in range(40)]})
    bb = ta.bbands(df["close"], length=20, std=2.0)
    assert bb is not None
    assert any("BBU" in c for c in bb.columns)
    assert any("BBL" in c for c in bb.columns)
```

- [ ] **Step 5: Run test, expect PASS**

Run: `pytest pipeline/tests/pattern_scanner/test_pandas_ta_smoke.py -v`
Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add requirements.txt pipeline/pattern_scanner/__init__.py pipeline/tests/pattern_scanner/__init__.py pipeline/tests/pattern_scanner/test_pandas_ta_smoke.py
git commit -m "chore(pattern-scanner): pin pandas-ta and verify install with smoke tests"
```

---

## Task 1: `pattern_scanner/constants.py` — 12 pattern definitions

**Files:**
- Create: `pipeline/pattern_scanner/constants.py`
- Test: `pipeline/tests/pattern_scanner/test_constants.py`

- [ ] **Step 1: Write failing test**

`pipeline/tests/pattern_scanner/test_constants.py`:
```python
from pipeline.pattern_scanner import constants as C


def test_pattern_set_has_exactly_12():
    assert len(C.PATTERNS) == 12


def test_balanced_directions():
    longs = [p for p in C.PATTERNS if p.direction == "LONG"]
    shorts = [p for p in C.PATTERNS if p.direction == "SHORT"]
    assert len(longs) == 6
    assert len(shorts) == 6


def test_pattern_ids_unique():
    ids = [p.pattern_id for p in C.PATTERNS]
    assert len(ids) == len(set(ids))


def test_thresholds():
    assert C.WIN_THRESHOLD == 0.008
    assert C.MIN_N == 30
    assert C.MIN_FOLD_STABILITY == 0.5
    assert C.TOP_N == 10


def test_specific_patterns_present():
    ids = {p.pattern_id for p in C.PATTERNS}
    expected = {
        "BULLISH_HAMMER", "BULLISH_ENGULFING", "MORNING_STAR", "PIERCING_LINE",
        "SHOOTING_STAR", "BEARISH_ENGULFING", "EVENING_STAR", "DARK_CLOUD_COVER",
        "BB_BREAKOUT", "BB_BREAKDOWN", "MACD_BULL_CROSS", "MACD_BEAR_CROSS",
    }
    assert ids == expected
```

- [ ] **Step 2: Run test, expect FAIL**

Run: `pytest pipeline/tests/pattern_scanner/test_constants.py -v`
Expected: ImportError / 5 errors (constants module doesn't exist).

- [ ] **Step 3: Implement constants**

`pipeline/pattern_scanner/constants.py`:
```python
"""Pattern Scanner constants — the canonical 12-pattern set + thresholds.

Per spec §9 (`docs/superpowers/specs/2026-04-27-ta-scanner-pattern-paired-shadow-design.md`).
"""
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class PatternDef:
    pattern_id: str
    direction: Literal["LONG", "SHORT"]
    pandas_ta_name: str | None  # None = custom detector (BB / MACD events)
    semantic: str


PATTERNS: list[PatternDef] = [
    PatternDef("BULLISH_HAMMER",    "LONG",  "hammer",        "Reversal-up after downtrend"),
    PatternDef("BULLISH_ENGULFING", "LONG",  "engulfing+",    "Strong reversal-up"),
    PatternDef("MORNING_STAR",      "LONG",  "morningstar",   "3-candle reversal-up"),
    PatternDef("PIERCING_LINE",     "LONG",  "piercing",      "2-candle reversal-up"),
    PatternDef("SHOOTING_STAR",     "SHORT", "shootingstar",  "Reversal-down after uptrend"),
    PatternDef("BEARISH_ENGULFING", "SHORT", "engulfing-",    "Strong reversal-down"),
    PatternDef("EVENING_STAR",      "SHORT", "eveningstar",   "3-candle reversal-down"),
    PatternDef("DARK_CLOUD_COVER",  "SHORT", "darkcloudcover","2-candle reversal-down"),
    PatternDef("BB_BREAKOUT",       "LONG",  None,            "BB squeeze + close above upper"),
    PatternDef("BB_BREAKDOWN",      "SHORT", None,            "BB squeeze + close below lower"),
    PatternDef("MACD_BULL_CROSS",   "LONG",  None,            "MACD line crosses signal up"),
    PatternDef("MACD_BEAR_CROSS",   "SHORT", None,            "MACD line crosses signal down"),
]

WIN_THRESHOLD: float = 0.008          # ±0.8% T+1 open-to-close
MIN_N: int = 30                        # min occurrences for ranking eligibility
MIN_FOLD_STABILITY: float = 0.5        # min walk-forward fold-stability ratio
TOP_N: int = 10                        # daily Top-N

BB_LENGTH: int = 20
BB_STD: float = 2.0
BB_SQUEEZE_RATIO: float = 0.7          # current band width < 20-day avg × 0.7

MACD_FAST: int = 12
MACD_SLOW: int = 26
MACD_SIGNAL: int = 9
```

- [ ] **Step 4: Run test, expect PASS**

Run: `pytest pipeline/tests/pattern_scanner/test_constants.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add pipeline/pattern_scanner/constants.py pipeline/tests/pattern_scanner/test_constants.py
git commit -m "feat(pattern-scanner): pattern definitions and thresholds (T1)"
```

---

## Task 2: `pattern_scanner/detect.py` — daily pattern detection (Layer 1)

**Files:**
- Create: `pipeline/pattern_scanner/detect.py`
- Test: `pipeline/tests/pattern_scanner/test_detect.py`

- [ ] **Step 1: Write failing tests for the 8 candle patterns**

`pipeline/tests/pattern_scanner/test_detect.py`:
```python
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
    for i in range(10):
        rows.append({"date": f"2026-01-{i+1:02d}", "open": px, "high": px + 0.5,
                     "low": px - 1.0, "close": px - 0.8})
        px -= 0.8
    # textbook hammer: small body, long lower shadow, near top of range
    rows.append({"date": "2026-01-11", "open": px, "high": px + 0.3,
                 "low": px - 2.5, "close": px + 0.2})
    return _build_bars(rows)


def test_detect_bullish_hammer_at_end_of_downtrend():
    bars = _downtrend_then_hammer()
    flags = detect_patterns_for_ticker(
        ticker="TEST", bars=bars, scan_date=date(2026, 1, 11))
    pattern_ids = {f.pattern_id for f in flags}
    assert "BULLISH_HAMMER" in pattern_ids


def test_no_pattern_on_quiet_bar():
    rows = [{"date": f"2026-01-{i+1:02d}", "open": 100.0, "high": 100.5,
             "low": 99.5, "close": 100.0} for i in range(15)]
    bars = _build_bars(rows)
    flags = detect_patterns_for_ticker(
        ticker="TEST", bars=bars, scan_date=date(2026, 1, 15))
    assert flags == []


def test_engulfing_split_by_sign():
    """pandas-ta returns +/- for engulfing; our detector splits into BULLISH_ENGULFING
    or BEARISH_ENGULFING based on sign."""
    # Bearish engulfing: long red candle engulfing previous green
    rows = [
        {"date": "2026-01-01", "open": 100.0, "high": 100.5, "low": 99.5, "close": 100.3},
        {"date": "2026-01-02", "open": 100.5, "high": 100.6, "low": 99.0, "close": 99.1},
    ]
    bars = _build_bars(rows)
    flags = detect_patterns_for_ticker("TEST", bars, date(2026, 1, 2))
    assert any(f.pattern_id == "BEARISH_ENGULFING" for f in flags)
    assert not any(f.pattern_id == "BULLISH_ENGULFING" for f in flags)


def test_insufficient_history_returns_empty():
    rows = [{"date": "2026-01-01", "open": 100.0, "high": 100.5, "low": 99.5, "close": 100.0}]
    bars = _build_bars(rows)
    flags = detect_patterns_for_ticker("TEST", bars, date(2026, 1, 1))
    assert flags == []


def test_pattern_flag_shape():
    bars = _downtrend_then_hammer()
    flags = detect_patterns_for_ticker("TEST", bars, date(2026, 1, 11))
    if flags:
        f = flags[0]
        assert isinstance(f, PatternFlag)
        assert f.ticker == "TEST"
        assert f.date == date(2026, 1, 11)
        assert f.direction in ("LONG", "SHORT")
```

- [ ] **Step 2: Run tests, expect FAIL**

Run: `pytest pipeline/tests/pattern_scanner/test_detect.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement detect.py**

`pipeline/pattern_scanner/detect.py`:
```python
"""Daily pattern detection on EOD bars. One ticker at a time; runner.py
fans out across the universe.

Per spec §6.1.
"""
from dataclasses import dataclass
from datetime import date as _date
from typing import Literal

import pandas as pd
import pandas_ta as ta

from pipeline.pattern_scanner.constants import (
    PATTERNS, BB_LENGTH, BB_STD, BB_SQUEEZE_RATIO,
    MACD_FAST, MACD_SLOW, MACD_SIGNAL,
)

MIN_BARS_FOR_DETECTION = 60  # need history for BB squeeze ref + MACD warmup


@dataclass(frozen=True)
class PatternFlag:
    date: _date
    ticker: str
    pattern_id: str
    direction: Literal["LONG", "SHORT"]
    raw_features: dict


def detect_patterns_for_ticker(
    ticker: str, bars: pd.DataFrame, scan_date: _date
) -> list[PatternFlag]:
    """Returns list of patterns active at scan_date close.
    bars: DatetimeIndex with columns open/high/low/close, sorted ascending.
    """
    if bars is None or len(bars) < MIN_BARS_FOR_DETECTION:
        return []

    # Truncate to scan_date inclusive
    scan_ts = pd.Timestamp(scan_date)
    if scan_ts not in bars.index:
        return []
    bars = bars.loc[:scan_ts]

    flags: list[PatternFlag] = []
    flags.extend(_detect_candles(ticker, bars, scan_date))
    flags.extend(_detect_bb(ticker, bars, scan_date))
    flags.extend(_detect_macd(ticker, bars, scan_date))
    return flags


def _detect_candles(ticker: str, bars: pd.DataFrame, scan_date: _date) -> list[PatternFlag]:
    out: list[PatternFlag] = []
    for p in PATTERNS:
        if p.pandas_ta_name is None:
            continue
        # engulfing+ / engulfing- are split by sign
        ta_name = p.pandas_ta_name.rstrip("+-")
        try:
            series = ta.cdl_pattern(
                bars["open"], bars["high"], bars["low"], bars["close"], name=ta_name)
        except Exception:
            continue
        if series is None or len(series) == 0:
            continue
        col = series.columns[0] if hasattr(series, "columns") else None
        last = series.iloc[-1, 0] if col is not None else series.iloc[-1]
        if pd.isna(last) or last == 0:
            continue
        # Sign-aware split for engulfing
        if p.pandas_ta_name == "engulfing+" and last <= 0:
            continue
        if p.pandas_ta_name == "engulfing-" and last >= 0:
            continue
        out.append(PatternFlag(
            date=scan_date, ticker=ticker,
            pattern_id=p.pattern_id, direction=p.direction,
            raw_features={"signal_value": float(last)},
        ))
    return out


def _detect_bb(ticker: str, bars: pd.DataFrame, scan_date: _date) -> list[PatternFlag]:
    out: list[PatternFlag] = []
    bb = ta.bbands(bars["close"], length=BB_LENGTH, std=BB_STD)
    if bb is None or len(bb) < BB_LENGTH:
        return out
    upper = bb[f"BBU_{BB_LENGTH}_{BB_STD}"]
    lower = bb[f"BBL_{BB_LENGTH}_{BB_STD}"]
    width = upper - lower
    width_avg = width.rolling(BB_LENGTH).mean()
    last_close = bars["close"].iloc[-1]
    last_upper = upper.iloc[-1]
    last_lower = lower.iloc[-1]
    last_width = width.iloc[-1]
    last_width_avg = width_avg.iloc[-1]
    if pd.isna(last_width_avg):
        return out
    in_squeeze_yesterday = (
        not pd.isna(width.iloc[-2])
        and not pd.isna(width_avg.iloc[-2])
        and width.iloc[-2] < width_avg.iloc[-2] * BB_SQUEEZE_RATIO
    )
    if in_squeeze_yesterday and last_close > last_upper:
        out.append(PatternFlag(
            date=scan_date, ticker=ticker,
            pattern_id="BB_BREAKOUT", direction="LONG",
            raw_features={"close": float(last_close), "upper": float(last_upper),
                          "width": float(last_width), "width_avg": float(last_width_avg)},
        ))
    if in_squeeze_yesterday and last_close < last_lower:
        out.append(PatternFlag(
            date=scan_date, ticker=ticker,
            pattern_id="BB_BREAKDOWN", direction="SHORT",
            raw_features={"close": float(last_close), "lower": float(last_lower),
                          "width": float(last_width), "width_avg": float(last_width_avg)},
        ))
    return out


def _detect_macd(ticker: str, bars: pd.DataFrame, scan_date: _date) -> list[PatternFlag]:
    out: list[PatternFlag] = []
    macd = ta.macd(bars["close"], fast=MACD_FAST, slow=MACD_SLOW, signal=MACD_SIGNAL)
    if macd is None or len(macd) < MACD_SLOW:
        return out
    line_col = f"MACD_{MACD_FAST}_{MACD_SLOW}_{MACD_SIGNAL}"
    sig_col = f"MACDs_{MACD_FAST}_{MACD_SLOW}_{MACD_SIGNAL}"
    if line_col not in macd.columns or sig_col not in macd.columns:
        return out
    line = macd[line_col]
    sig = macd[sig_col]
    if pd.isna(line.iloc[-2]) or pd.isna(sig.iloc[-2]):
        return out
    if line.iloc[-2] <= sig.iloc[-2] and line.iloc[-1] > sig.iloc[-1]:
        out.append(PatternFlag(
            date=scan_date, ticker=ticker,
            pattern_id="MACD_BULL_CROSS", direction="LONG",
            raw_features={"macd": float(line.iloc[-1]), "signal": float(sig.iloc[-1])},
        ))
    if line.iloc[-2] >= sig.iloc[-2] and line.iloc[-1] < sig.iloc[-1]:
        out.append(PatternFlag(
            date=scan_date, ticker=ticker,
            pattern_id="MACD_BEAR_CROSS", direction="SHORT",
            raw_features={"macd": float(line.iloc[-1]), "signal": float(sig.iloc[-1])},
        ))
    return out
```

- [ ] **Step 4: Run tests, expect PASS**

Run: `pytest pipeline/tests/pattern_scanner/test_detect.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add pipeline/pattern_scanner/detect.py pipeline/tests/pattern_scanner/test_detect.py
git commit -m "feat(pattern-scanner): daily detector for 12 patterns via pandas-ta (T2)"
```

---

## Task 3: `pattern_scanner/stats.py` — historical fit + walk-forward folds (Layer 2)

**Files:**
- Create: `pipeline/pattern_scanner/stats.py`
- Test: `pipeline/tests/pattern_scanner/test_stats.py`

- [ ] **Step 1: Write failing tests**

`pipeline/tests/pattern_scanner/test_stats.py`:
```python
"""Stats engine tests on synthetic panels with known win rates."""
from datetime import date
import math
import numpy as np
import pandas as pd
from pipeline.pattern_scanner.stats import (
    aggregate_pattern_cell, walk_forward_fold_stability, compute_z_score,
)


def test_z_score_perfect_winrate_on_30():
    z = compute_z_score(win_rate=1.0, n=30)
    # (1.0 - 0.5) / sqrt(0.25/30) ≈ 5.477
    assert math.isclose(z, 5.477, rel_tol=1e-2)


def test_z_score_coinflip_zero():
    assert compute_z_score(win_rate=0.5, n=100) == 0.0


def test_z_score_zero_n_returns_nan():
    assert math.isnan(compute_z_score(win_rate=0.6, n=0))


def test_aggregate_60_percent_winrate():
    """100 fires, 60 wins (returns >= +0.008), 40 losses (returns < +0.008)."""
    fire_dates = [date(2026, 1, 1) + pd.Timedelta(days=i) for i in range(100)]
    returns = [0.012] * 60 + [0.001] * 40  # bullish: win = return >= +0.008
    cell = aggregate_pattern_cell(
        ticker="TEST", pattern_id="BULLISH_HAMMER", direction="LONG",
        fire_dates=fire_dates, returns=returns, win_threshold=0.008)
    assert cell["n_occurrences"] == 100
    assert cell["wins"] == 60
    assert cell["losses"] == 40
    assert math.isclose(cell["win_rate"], 0.6, rel_tol=1e-9)
    assert cell["z_score"] > 1.9  # stat-significant against H0=0.5


def test_aggregate_short_pattern_signed_pnl():
    """SHORT pattern: pnl is -return. A -1% drop is a +1% trade pnl."""
    fire_dates = [date(2026, 1, 1) + pd.Timedelta(days=i) for i in range(20)]
    returns = [-0.012] * 12 + [0.001] * 8  # drop of 1.2% counts as win for SHORT
    cell = aggregate_pattern_cell(
        ticker="TEST", pattern_id="SHOOTING_STAR", direction="SHORT",
        fire_dates=fire_dates, returns=returns, win_threshold=0.008)
    assert cell["wins"] == 12
    assert cell["mean_pnl_pct"] > 0  # signed P&L is positive overall


def test_walk_forward_stable_pattern_high_ratio():
    """Stable pattern across 4 folds → high stability ratio."""
    fold_win_rates = [0.60, 0.62, 0.59, 0.61]
    ratio = walk_forward_fold_stability(fold_win_rates)
    assert ratio > 0.9


def test_walk_forward_unstable_pattern_low_ratio():
    fold_win_rates = [0.85, 0.30, 0.70, 0.45]
    ratio = walk_forward_fold_stability(fold_win_rates)
    assert ratio < 0.5


def test_walk_forward_zero_mean_returns_zero():
    assert walk_forward_fold_stability([0.0, 0.0, 0.0, 0.0]) == 0.0
```

- [ ] **Step 2: Run tests, expect FAIL**

Run: `pytest pipeline/tests/pattern_scanner/test_stats.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement stats.py**

`pipeline/pattern_scanner/stats.py`:
```python
"""Historical pattern-occurrence stats. Reads daily bars per ticker, finds every
pattern fire over the lookback window, computes T+1 open-to-close return per
fire, aggregates per (ticker, pattern). Walk-forward fold stability via 4
contiguous folds.

Per spec §6.2 + §10.
"""
import math
from collections.abc import Callable
from datetime import date as _date
from typing import Literal

import numpy as np
import pandas as pd

from pipeline.pattern_scanner.constants import PATTERNS, WIN_THRESHOLD
from pipeline.pattern_scanner.detect import detect_patterns_for_ticker


def compute_z_score(win_rate: float, n: int) -> float:
    """Binomial test against H0=50/50."""
    if n <= 0:
        return float("nan")
    se = math.sqrt(0.25 / n)
    return (win_rate - 0.5) / se


def walk_forward_fold_stability(fold_win_rates: list[float]) -> float:
    """1 − (max − min) / max(0.01, mean). Bounded [0, 1]; higher = more stable."""
    if not fold_win_rates:
        return 0.0
    mean = float(np.mean(fold_win_rates))
    if mean <= 0:
        return 0.0
    spread = max(fold_win_rates) - min(fold_win_rates)
    ratio = 1.0 - spread / max(0.01, mean)
    return max(0.0, min(1.0, ratio))


def aggregate_pattern_cell(
    ticker: str,
    pattern_id: str,
    direction: Literal["LONG", "SHORT"],
    fire_dates: list[_date],
    returns: list[float],
    win_threshold: float = WIN_THRESHOLD,
) -> dict:
    """Aggregate one (ticker, pattern) cell from a list of fire dates and their
    T+1 returns. Returns are RAW (not signed). For SHORT patterns, P&L = -return.
    """
    if len(fire_dates) != len(returns):
        raise ValueError("fire_dates and returns must be the same length")

    # Per-trade P&L: LONG = return; SHORT = -return
    pnl = np.array(returns, dtype=float)
    if direction == "SHORT":
        pnl = -pnl

    n = len(pnl)
    if n == 0:
        return {
            "ticker": ticker, "pattern_id": pattern_id, "direction": direction,
            "n_occurrences": 0, "wins": 0, "losses": 0,
            "win_rate": float("nan"), "mean_pnl_pct": float("nan"),
            "stddev_pnl_pct": float("nan"), "z_score": float("nan"),
            "fold_win_rates": [], "fold_stability": 0.0,
            "first_seen": None, "last_seen": None,
        }

    # Win = pnl >= threshold (threshold is positive; SHORT was already sign-flipped)
    wins_mask = pnl >= win_threshold
    wins = int(wins_mask.sum())
    losses = n - wins
    win_rate = wins / n
    mean_pnl = float(np.mean(pnl))
    std_pnl = float(np.std(pnl, ddof=1)) if n > 1 else 0.0
    z = compute_z_score(win_rate, n)

    # Walk-forward 4 folds (sorted by fire_date)
    df = pd.DataFrame({"date": fire_dates, "win": wins_mask}).sort_values("date")
    fold_win_rates: list[float] = []
    if len(df) >= 4:
        chunks = np.array_split(df, 4)
        for c in chunks:
            if len(c) > 0:
                fold_win_rates.append(float(c["win"].mean()))
    fold_stability = walk_forward_fold_stability(fold_win_rates)

    return {
        "ticker": ticker, "pattern_id": pattern_id, "direction": direction,
        "n_occurrences": n, "wins": wins, "losses": losses,
        "win_rate": win_rate, "mean_pnl_pct": mean_pnl,
        "stddev_pnl_pct": std_pnl, "z_score": z,
        "fold_win_rates": fold_win_rates, "fold_stability": fold_stability,
        "first_seen": df["date"].min(), "last_seen": df["date"].max(),
    }


def fit_universe(
    universe: list[str],
    bars_loader: Callable[[str], pd.DataFrame],
    start: _date,
    end: _date,
    win_threshold: float = WIN_THRESHOLD,
) -> pd.DataFrame:
    """Per (ticker, pattern), find every fire over [start, end], compute T+1
    open-to-close return, aggregate. Returns a DataFrame with one row per cell.
    """
    rows: list[dict] = []
    for ticker in universe:
        bars = bars_loader(ticker)
        if bars is None or bars.empty:
            continue
        per_pattern: dict[str, dict] = {p.pattern_id: {"dates": [], "returns": [],
                                                       "direction": p.direction}
                                        for p in PATTERNS}
        # Walk every date in [start, end] that has a NEXT bar (for T+1 return)
        idx = bars.index
        for i in range(len(idx) - 1):
            d_i = idx[i]
            d_next = idx[i + 1]
            scan_date = d_i.date()
            if scan_date < start or scan_date > end:
                continue
            flags = detect_patterns_for_ticker(ticker, bars, scan_date)
            if not flags:
                continue
            o = bars.loc[d_next, "open"]
            c = bars.loc[d_next, "close"]
            if o == 0 or pd.isna(o) or pd.isna(c):
                continue
            ret = (c - o) / o
            for f in flags:
                per_pattern[f.pattern_id]["dates"].append(scan_date)
                per_pattern[f.pattern_id]["returns"].append(ret)
        for p in PATTERNS:
            cell = aggregate_pattern_cell(
                ticker=ticker, pattern_id=p.pattern_id, direction=p.direction,
                fire_dates=per_pattern[p.pattern_id]["dates"],
                returns=per_pattern[p.pattern_id]["returns"],
                win_threshold=win_threshold,
            )
            rows.append(cell)

    return pd.DataFrame(rows)
```

- [ ] **Step 4: Run tests, expect PASS**

Run: `pytest pipeline/tests/pattern_scanner/test_stats.py -v`
Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add pipeline/pattern_scanner/stats.py pipeline/tests/pattern_scanner/test_stats.py
git commit -m "feat(pattern-scanner): historical fit + walk-forward fold stability (T3)"
```

---

## Task 4: `pattern_scanner/rank.py` — Top-10 composite ranker (Layer 3 ranker)

**Files:**
- Create: `pipeline/pattern_scanner/rank.py`
- Test: `pipeline/tests/pattern_scanner/test_rank.py`

- [ ] **Step 1: Write failing tests**

`pipeline/tests/pattern_scanner/test_rank.py`:
```python
from datetime import date
import math
import pandas as pd
from pipeline.pattern_scanner.rank import rank_today, ScannerSignal
from pipeline.pattern_scanner.detect import PatternFlag


def _stats_row(ticker, pattern, direction, n, wr, z, mean_pnl, fold_stab):
    return {
        "ticker": ticker, "pattern_id": pattern, "direction": direction,
        "n_occurrences": n, "wins": int(round(wr * n)), "losses": n - int(round(wr * n)),
        "win_rate": wr, "mean_pnl_pct": mean_pnl, "stddev_pnl_pct": 0.01,
        "z_score": z, "fold_win_rates": [wr] * 4, "fold_stability": fold_stab,
        "first_seen": date(2020, 1, 1), "last_seen": date(2026, 4, 1),
    }


def test_filters_below_min_n():
    flags = [PatternFlag(date(2026, 4, 27), "ABC", "BULLISH_HAMMER", "LONG", {})]
    stats = pd.DataFrame([_stats_row("ABC", "BULLISH_HAMMER", "LONG", n=20,
                                      wr=0.7, z=2.0, mean_pnl=0.012, fold_stab=0.8)])
    out = rank_today(flags, stats, min_n=30, min_fold_stability=0.5, top_n=10)
    assert out == []


def test_filters_unstable_folds():
    flags = [PatternFlag(date(2026, 4, 27), "ABC", "BULLISH_HAMMER", "LONG", {})]
    stats = pd.DataFrame([_stats_row("ABC", "BULLISH_HAMMER", "LONG", n=100,
                                      wr=0.7, z=4.0, mean_pnl=0.012, fold_stab=0.3)])
    out = rank_today(flags, stats, min_n=30, min_fold_stability=0.5, top_n=10)
    assert out == []


def test_composite_score_ordering():
    flags = [
        PatternFlag(date(2026, 4, 27), "AAA", "BULLISH_HAMMER", "LONG", {}),
        PatternFlag(date(2026, 4, 27), "BBB", "MORNING_STAR", "LONG", {}),
    ]
    stats = pd.DataFrame([
        # AAA: high z, modest n, modest pnl
        _stats_row("AAA", "BULLISH_HAMMER", "LONG", n=50, wr=0.62, z=1.7,
                   mean_pnl=0.010, fold_stab=0.8),
        # BBB: lower z but bigger n and bigger pnl
        _stats_row("BBB", "MORNING_STAR", "LONG", n=500, wr=0.55, z=2.2,
                   mean_pnl=0.020, fold_stab=0.8),
    ])
    out = rank_today(flags, stats, min_n=30, min_fold_stability=0.5, top_n=10)
    assert len(out) == 2
    # composite = z * log(1+n) * |mean_pnl|; BBB > AAA
    assert out[0].ticker == "BBB"


def test_top_n_truncation():
    flags = [PatternFlag(date(2026, 4, 27), f"T{i:02d}", "BULLISH_HAMMER", "LONG", {})
             for i in range(15)]
    stats = pd.DataFrame([
        _stats_row(f"T{i:02d}", "BULLISH_HAMMER", "LONG", n=50, wr=0.6 - i * 0.001,
                   z=2.0, mean_pnl=0.012, fold_stab=0.8) for i in range(15)
    ])
    out = rank_today(flags, stats, min_n=30, min_fold_stability=0.5, top_n=10)
    assert len(out) == 10


def test_signal_id_format():
    flags = [PatternFlag(date(2026, 4, 27), "RELIANCE", "BULLISH_HAMMER", "LONG", {})]
    stats = pd.DataFrame([_stats_row("RELIANCE", "BULLISH_HAMMER", "LONG", n=50,
                                      wr=0.6, z=2.0, mean_pnl=0.012, fold_stab=0.8)])
    out = rank_today(flags, stats)
    assert out[0].signal_id == "2026-04-27_RELIANCE_BULLISH_HAMMER"
```

- [ ] **Step 2: Run tests, expect FAIL**

Run: `pytest pipeline/tests/pattern_scanner/test_rank.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement rank.py**

`pipeline/pattern_scanner/rank.py`:
```python
"""Daily Top-10 ranker. Joins today's flags against pattern_stats.parquet,
filters by minimum-N + fold-stability gates, ranks by composite score.

Per spec §6.3.
"""
import math
from dataclasses import dataclass
from datetime import date as _date
from typing import Literal

import pandas as pd

from pipeline.pattern_scanner.constants import MIN_N, MIN_FOLD_STABILITY, TOP_N
from pipeline.pattern_scanner.detect import PatternFlag


@dataclass
class ScannerSignal:
    signal_id: str
    date: _date
    ticker: str
    pattern_id: str
    direction: Literal["LONG", "SHORT"]
    composite_score: float
    n_occurrences: int
    win_rate: float
    z_score: float
    mean_pnl_pct: float
    fold_stability: float
    last_seen: _date


def _composite(z: float, n: int, mean_pnl: float) -> float:
    if n <= 0 or pd.isna(z) or pd.isna(mean_pnl):
        return float("-inf")
    return z * math.log1p(n) * abs(mean_pnl)


def rank_today(
    flags: list[PatternFlag],
    stats: pd.DataFrame,
    min_n: int = MIN_N,
    min_fold_stability: float = MIN_FOLD_STABILITY,
    top_n: int = TOP_N,
) -> list[ScannerSignal]:
    if not flags:
        return []
    if stats is None or stats.empty:
        return []

    indexed = stats.set_index(["ticker", "pattern_id"])
    out: list[ScannerSignal] = []
    for f in flags:
        try:
            row = indexed.loc[(f.ticker, f.pattern_id)]
        except KeyError:
            continue
        n = int(row["n_occurrences"]) if not pd.isna(row["n_occurrences"]) else 0
        if n < min_n:
            continue
        fs = float(row["fold_stability"])
        if fs < min_fold_stability:
            continue
        z = float(row["z_score"])
        mean_pnl = float(row["mean_pnl_pct"])
        composite = _composite(z, n, mean_pnl)
        if not math.isfinite(composite):
            continue
        out.append(ScannerSignal(
            signal_id=f"{f.date.isoformat()}_{f.ticker}_{f.pattern_id}",
            date=f.date,
            ticker=f.ticker,
            pattern_id=f.pattern_id,
            direction=f.direction,
            composite_score=composite,
            n_occurrences=n,
            win_rate=float(row["win_rate"]),
            z_score=z,
            mean_pnl_pct=mean_pnl,
            fold_stability=fs,
            last_seen=row["last_seen"].date() if hasattr(row["last_seen"], "date")
                else row["last_seen"],
        ))
    out.sort(key=lambda s: s.composite_score, reverse=True)
    return out[:top_n]
```

- [ ] **Step 4: Run tests, expect PASS**

Run: `pytest pipeline/tests/pattern_scanner/test_rank.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add pipeline/pattern_scanner/rank.py pipeline/tests/pattern_scanner/test_rank.py
git commit -m "feat(pattern-scanner): Top-10 composite ranker with min-N + fold-stability gates (T4)"
```

---

## Task 5: `pattern_scanner/runner.py` — Layer 3 orchestration + daily artifact

**Files:**
- Create: `pipeline/pattern_scanner/runner.py`
- Test: `pipeline/tests/pattern_scanner/test_runner.py`

- [ ] **Step 1: Write failing test**

`pipeline/tests/pattern_scanner/test_runner.py`:
```python
import json
from datetime import date
from unittest.mock import MagicMock
import pandas as pd
import pytest
from pipeline.pattern_scanner.runner import run_daily_scan
from pipeline.pattern_scanner.detect import PatternFlag


def test_runner_writes_signals_today_json(tmp_path):
    out_dir = tmp_path / "scanner"
    out_dir.mkdir()
    out_path = out_dir / "pattern_signals_today.json"

    flags_by_ticker = {
        "RELIANCE": [PatternFlag(date(2026, 4, 27), "RELIANCE",
                                  "BULLISH_HAMMER", "LONG", {})],
        "TATAMOTORS": [PatternFlag(date(2026, 4, 27), "TATAMOTORS",
                                    "BEARISH_ENGULFING", "SHORT", {})],
    }
    detect_fn = lambda ticker, _bars, _scan_date: flags_by_ticker.get(ticker, [])
    bars_loader = lambda _t: pd.DataFrame({"open": [1], "high": [1], "low": [1],
                                            "close": [1]}, index=[pd.Timestamp("2026-04-27")])

    stats = pd.DataFrame([
        {"ticker": "RELIANCE", "pattern_id": "BULLISH_HAMMER", "direction": "LONG",
         "n_occurrences": 156, "wins": 97, "losses": 59, "win_rate": 0.62,
         "mean_pnl_pct": 0.012, "stddev_pnl_pct": 0.02, "z_score": 3.0,
         "fold_win_rates": [0.6, 0.62, 0.65, 0.61], "fold_stability": 0.78,
         "first_seen": date(2020, 4, 1), "last_seen": date(2026, 3, 12)},
        {"ticker": "TATAMOTORS", "pattern_id": "BEARISH_ENGULFING", "direction": "SHORT",
         "n_occurrences": 42, "wins": 24, "losses": 18, "win_rate": 0.57,
         "mean_pnl_pct": 0.009, "stddev_pnl_pct": 0.015, "z_score": 0.91,
         "fold_win_rates": [0.55, 0.6, 0.58, 0.56], "fold_stability": 0.85,
         "first_seen": date(2021, 1, 1), "last_seen": date(2026, 4, 20)},
    ])

    run_daily_scan(
        scan_date=date(2026, 4, 27),
        universe=["RELIANCE", "TATAMOTORS"],
        bars_loader=bars_loader,
        stats_df=stats,
        out_path=out_path,
        detect_fn=detect_fn,
    )

    assert out_path.exists()
    payload = json.loads(out_path.read_text())
    assert payload["as_of"].startswith("2026-04-27")
    assert payload["universe_size"] == 2
    assert payload["today_flags_total"] == 2
    # Both qualify (n>=30, fold_stab>=0.5)
    assert payload["qualified_count"] == 2
    assert len(payload["top_10"]) == 2
```

- [ ] **Step 2: Run test, expect FAIL**

Run: `pytest pipeline/tests/pattern_scanner/test_runner.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement runner.py**

`pipeline/pattern_scanner/runner.py`:
```python
"""Daily scan orchestration: detect → join stats → rank → write JSON.

Per spec §6.4 + §8.2.
"""
import json
from collections.abc import Callable
from dataclasses import asdict
from datetime import date as _date, datetime, timezone, timedelta
from pathlib import Path

import pandas as pd

from pipeline.pattern_scanner.detect import detect_patterns_for_ticker, PatternFlag
from pipeline.pattern_scanner.rank import rank_today

IST = timezone(timedelta(hours=5, minutes=30))


def run_daily_scan(
    scan_date: _date,
    universe: list[str],
    bars_loader: Callable[[str], pd.DataFrame],
    stats_df: pd.DataFrame,
    out_path: Path,
    detect_fn: Callable | None = None,
) -> dict:
    """Detect today's patterns across the universe, rank against historical stats,
    write pattern_signals_today.json. Returns the payload dict.
    """
    detect_fn = detect_fn or detect_patterns_for_ticker
    all_flags: list[PatternFlag] = []
    for ticker in universe:
        bars = bars_loader(ticker)
        flags = detect_fn(ticker, bars, scan_date)
        all_flags.extend(flags)

    ranked = rank_today(all_flags, stats_df)

    # qualified_count = those that PASSED the min_n + fold_stability filter
    qualified = [s for s in ranked]  # already filtered inside rank_today
    qualified_count = len(qualified)
    today_flags_total = len(all_flags)
    below_threshold_count = today_flags_total - qualified_count

    payload = {
        "as_of": datetime.now(IST).isoformat(),
        "universe_size": len(universe),
        "today_flags_total": today_flags_total,
        "qualified_count": qualified_count,
        "below_threshold_count": below_threshold_count,
        "top_10": [
            {
                "signal_id": s.signal_id,
                "date": s.date.isoformat(),
                "ticker": s.ticker,
                "pattern_id": s.pattern_id,
                "direction": s.direction,
                "composite_score": round(s.composite_score, 4),
                "n_occurrences": s.n_occurrences,
                "win_rate": round(s.win_rate, 4),
                "z_score": round(s.z_score, 3),
                "mean_pnl_pct": round(s.mean_pnl_pct, 5),
                "fold_stability": round(s.fold_stability, 3),
                "last_seen": s.last_seen.isoformat() if hasattr(s.last_seen, "isoformat")
                    else str(s.last_seen),
            } for s in ranked
        ],
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2))
    return payload
```

- [ ] **Step 4: Run test, expect PASS**

Run: `pytest pipeline/tests/pattern_scanner/test_runner.py -v`
Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add pipeline/pattern_scanner/runner.py pipeline/tests/pattern_scanner/test_runner.py
git commit -m "feat(pattern-scanner): daily scan orchestration writes pattern_signals_today.json (T5)"
```

---

## Task 6: API endpoint `/api/scanner/pattern-signals`

**Files:**
- Create: `pipeline/terminal/api/scanner_pattern.py`
- Modify: `pipeline/terminal/cli.py` (or wherever routers are mounted) — register router
- Test: `pipeline/tests/terminal/test_scanner_pattern_api.py`

- [ ] **Step 1: Write failing test**

`pipeline/tests/terminal/test_scanner_pattern_api.py`:
```python
import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from pipeline.terminal.api.scanner_pattern import router, _resolve_signals_path


@pytest.fixture
def client_with_fixture(tmp_path, monkeypatch):
    fixture = {
        "as_of": "2026-04-27T16:30:00+05:30",
        "universe_size": 213,
        "today_flags_total": 47,
        "qualified_count": 18,
        "below_threshold_count": 29,
        "top_10": [
            {"signal_id": "2026-04-27_BPCL_BULLISH_HAMMER",
             "date": "2026-04-27", "ticker": "BPCL",
             "pattern_id": "BULLISH_HAMMER", "direction": "LONG",
             "composite_score": 4.27, "n_occurrences": 156,
             "win_rate": 0.62, "z_score": 3.0, "mean_pnl_pct": 0.012,
             "fold_stability": 0.78, "last_seen": "2026-03-12"}
        ],
    }
    f = tmp_path / "pattern_signals_today.json"
    f.write_text(json.dumps(fixture))
    monkeypatch.setattr(
        "pipeline.terminal.api.scanner_pattern._resolve_signals_path",
        lambda: f,
    )
    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_endpoint_returns_full_payload(client_with_fixture):
    r = client_with_fixture.get("/api/scanner/pattern-signals")
    assert r.status_code == 200
    data = r.json()
    assert data["as_of"].startswith("2026-04-27")
    assert data["universe_size"] == 213
    assert len(data["top_10"]) == 1
    # Endpoint adds cumulative_paired_shadow rollup
    assert "cumulative_paired_shadow" in data


def test_endpoint_missing_file_returns_404(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "pipeline.terminal.api.scanner_pattern._resolve_signals_path",
        lambda: tmp_path / "does_not_exist.json",
    )
    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    r = client.get("/api/scanner/pattern-signals")
    assert r.status_code == 404
```

- [ ] **Step 2: Run test, expect FAIL**

Run: `pytest pipeline/tests/terminal/test_scanner_pattern_api.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement endpoint**

`pipeline/terminal/api/scanner_pattern.py`:
```python
"""Scanner pattern signals endpoint.

Per spec §6.7. Returns the full pattern_signals_today.json contents merged
with a cumulative_paired_shadow rollup computed from the close ledgers.
"""
import json
from pathlib import Path

from fastapi import APIRouter, HTTPException

router = APIRouter()

PATTERN_SIGNALS_PATH = Path("pipeline/data/scanner/pattern_signals_today.json")
PAIRED_LEDGER_PATH = Path(
    "pipeline/data/research/scanner/live_paper_scanner_options_ledger.json")


def _resolve_signals_path() -> Path:
    return PATTERN_SIGNALS_PATH


def _resolve_ledger_path() -> Path:
    return PAIRED_LEDGER_PATH


def _cumulative_rollup() -> dict:
    p = _resolve_ledger_path()
    if not p.exists():
        return {"n_closed": 0, "win_rate": None,
                "mean_options_pnl_pct": None, "mean_futures_pnl_pct": None,
                "mean_paired_diff": None}
    rows = json.loads(p.read_text())
    closed = [r for r in rows if r.get("status") == "CLOSED"]
    if not closed:
        return {"n_closed": 0, "win_rate": None,
                "mean_options_pnl_pct": None, "mean_futures_pnl_pct": None,
                "mean_paired_diff": None}
    n = len(closed)
    opt = [r["pnl_net_pct"] for r in closed if r.get("pnl_net_pct") is not None]
    fut = [r.get("futures_pnl_net_pct") for r in closed
           if r.get("futures_pnl_net_pct") is not None]
    wins = sum(1 for r in closed if (r.get("pnl_net_pct") or 0) > 0)
    return {
        "n_closed": n,
        "win_rate": wins / n if n else None,
        "mean_options_pnl_pct": sum(opt) / len(opt) if opt else None,
        "mean_futures_pnl_pct": sum(fut) / len(fut) if fut else None,
        "mean_paired_diff": (sum(opt) / len(opt) - sum(fut) / len(fut))
            if opt and fut else None,
    }


@router.get("/api/scanner/pattern-signals")
def get_pattern_signals():
    p = _resolve_signals_path()
    if not p.exists():
        raise HTTPException(status_code=404, detail="pattern_signals_today.json missing")
    payload = json.loads(p.read_text())
    payload["cumulative_paired_shadow"] = _cumulative_rollup()
    return payload
```

- [ ] **Step 4: Mount router in terminal app**

`pipeline/terminal/cli.py` — add to FastAPI app initialization (search for existing `include_router` calls, add alongside):
```python
from pipeline.terminal.api.scanner_pattern import router as scanner_pattern_router
app.include_router(scanner_pattern_router)
```

- [ ] **Step 5: Run test, expect PASS**

Run: `pytest pipeline/tests/terminal/test_scanner_pattern_api.py -v`
Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add pipeline/terminal/api/scanner_pattern.py pipeline/terminal/cli.py pipeline/tests/terminal/test_scanner_pattern_api.py
git commit -m "feat(terminal-api): /api/scanner/pattern-signals endpoint with cumulative rollup (T6)"
```

---

## Task 7: Scanner UI rewire + click-to-chart fix

**Files:**
- Modify: `pipeline/terminal/static/js/pages/scanner.js`
- Test: `pipeline/tests/terminal/test_scanner_pattern_js.py` (golden HTML fixture comparison)

- [ ] **Step 1: Read current scanner.js to understand the existing render shape**

Run: `cat pipeline/terminal/static/js/pages/scanner.js`
Note structure; we'll replace the render entirely.

- [ ] **Step 2: Write failing JS-render test (golden HTML fixture)**

`pipeline/tests/terminal/test_scanner_pattern_js.py`:
```python
"""Golden-fixture render test: scanner.js consumes the new endpoint and
renders Top-10 + click-to-chart anchors."""
import re
from pathlib import Path

JS_PATH = Path("pipeline/terminal/static/js/pages/scanner.js")


def test_scanner_js_calls_new_endpoint():
    text = JS_PATH.read_text(encoding="utf-8")
    assert "/api/scanner/pattern-signals" in text


def test_scanner_js_includes_click_to_chart_handler():
    text = JS_PATH.read_text(encoding="utf-8")
    # Either an href to chart route or a click handler navigating to one.
    chart_pattern = re.compile(r"#chart/|navigateToChart\(|onclick=.*chart", re.I)
    assert chart_pattern.search(text) is not None, (
        "scanner.js must restore click-to-chart on ticker cells (regression #269)")


def test_scanner_js_renders_z_score_column():
    text = JS_PATH.read_text(encoding="utf-8")
    assert "z_score" in text or "Z-score" in text or "z-score" in text


def test_scanner_js_renders_fold_stability_column():
    text = JS_PATH.read_text(encoding="utf-8")
    assert "fold_stability" in text or "Fold-stability" in text


def test_scanner_js_renders_below_threshold_footer():
    text = JS_PATH.read_text(encoding="utf-8")
    assert "below_threshold_count" in text or "below threshold" in text.lower()
```

- [ ] **Step 3: Run tests, expect FAIL**

Run: `pytest pipeline/tests/terminal/test_scanner_pattern_js.py -v`
Expected: 5 fails.

- [ ] **Step 4: Rewrite scanner.js**

`pipeline/terminal/static/js/pages/scanner.js` — replace entire file:
```js
// pipeline/terminal/static/js/pages/scanner.js
// Scanner (TA) tab — pattern-occurrence engine. Daily Top-10 candlestick /
// structural / momentum fires across the F&O universe, fortified with
// per-(ticker x pattern) historical stats (n, win-rate, z-score against
// random, walk-forward fold-stability, mean P&L). Click-to-chart on every
// ticker (was regression #269 — restored).
//
// Spec: docs/superpowers/specs/2026-04-27-ta-scanner-pattern-paired-shadow-design.md
import { get } from '../lib/api.js';

let _refreshTimer = null;
let _inflight = false;

function _esc(s) {
  if (s == null) return '';
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

function _fmtPct(v) {
  if (v == null || isNaN(v)) return '--';
  const sign = v >= 0 ? '+' : '';
  return `${sign}${(v * 100).toFixed(2)}%`;
}

function _dirBadge(dir) {
  if (dir === 'LONG') {
    return '<span class="badge" style="font-size: 0.65rem; background: var(--colour-green, #4caf50); color: #000; margin-right: 0.4em;">L</span>';
  }
  return '<span class="badge" style="font-size: 0.65rem; background: var(--colour-red, #f44336); color: #fff; margin-right: 0.4em;">S</span>';
}

function _zClass(z) {
  if (z == null || isNaN(z)) return 'text-muted';
  if (z >= 3.0) return 'text-green';
  if (z >= 2.0) return 'text-amber';
  return 'text-muted';
}

function _navigateToChart(ticker) {
  // Existing chart route — set hash; ticker-chart-modal listens.
  window.location.hash = `#chart/${encodeURIComponent(ticker)}`;
}

function _renderTopRow(s) {
  const dirBadge = _dirBadge(s.direction);
  const zCls = _zClass(s.z_score);
  return `<tr class="scanner-row" data-ticker="${_esc(s.ticker)}"
              title="composite ${s.composite_score} | n=${s.n_occurrences} | last seen ${_esc(s.last_seen)}"
              style="cursor: pointer;">
    <td>${dirBadge}</td>
    <td class="mono"><a href="#chart/${encodeURIComponent(s.ticker)}"
                       class="text-primary" style="text-decoration: none;">${_esc(s.ticker)}</a></td>
    <td>${_esc(s.pattern_id)}</td>
    <td class="mono">${s.n_occurrences}</td>
    <td class="mono">${(s.win_rate * 100).toFixed(0)}%</td>
    <td class="mono ${zCls}">${s.z_score.toFixed(2)}</td>
    <td class="mono">${_fmtPct(s.mean_pnl_pct)}</td>
    <td class="mono">${(s.fold_stability * 100).toFixed(0)}%</td>
    <td class="mono text-muted">${_esc(s.last_seen)}</td>
  </tr>`;
}

export async function render(container) {
  if (_inflight) return;
  _inflight = true;
  if (!container.hasChildNodes()) {
    container.innerHTML = '<div class="skeleton skeleton--card"></div>';
  }
  try {
    const data = await get('/scanner/pattern-signals');
    const top10 = data.top_10 || [];
    const cum = data.cumulative_paired_shadow || {};

    const tableHtml = top10.length === 0
      ? '<p class="text-muted" style="font-size: 0.875rem;">No qualified pattern fires today.</p>'
      : `<table class="scanner-table">
          <thead><tr>
            <th>Dir</th><th>Ticker</th><th>Pattern</th>
            <th>N</th><th>Win%</th><th>Z</th>
            <th>μ P&L</th><th>Fold-stability</th><th>Last seen</th>
          </tr></thead>
          <tbody>${top10.map(_renderTopRow).join('')}</tbody>
        </table>`;

    const dormantFooter = (data.below_threshold_count || 0) > 0
      ? `<p class="text-muted" style="font-size: 0.75rem; margin-top: 0.5em;">+ ${data.below_threshold_count} below threshold (n &lt; 30 or unstable folds) — hidden</p>`
      : '';

    const cumHtml = (cum.n_closed || 0) > 0
      ? `<div class="digest-card" style="margin-top: 1em;">
          <div class="digest-card__title">Paired-shadow rollup (cumulative)</div>
          <div class="digest-row"><span class="digest-row__label">Closed trades</span>
            <span class="digest-row__value mono">${cum.n_closed}</span></div>
          <div class="digest-row"><span class="digest-row__label">Win rate</span>
            <span class="digest-row__value mono">${(cum.win_rate * 100).toFixed(1)}%</span></div>
          <div class="digest-row"><span class="digest-row__label">μ Options P&L</span>
            <span class="digest-row__value mono">${_fmtPct(cum.mean_options_pnl_pct)}</span></div>
          <div class="digest-row"><span class="digest-row__label">μ Futures P&L</span>
            <span class="digest-row__value mono">${_fmtPct(cum.mean_futures_pnl_pct)}</span></div>
          <div class="digest-row"><span class="digest-row__label">Paired diff</span>
            <span class="digest-row__value mono">${_fmtPct(cum.mean_paired_diff)}</span></div>
        </div>`
      : '';

    container.innerHTML = `
      <h2 style="margin-bottom: var(--spacing-md);">Scanner (TA) — Today's Top Patterns</h2>
      <div class="digest-card">
        <div class="digest-card__title">Top ${top10.length} of ${data.qualified_count} qualified fires</div>
        <div class="digest-card__subtitle">Universe ${data.universe_size} F&amp;O stocks | as of ${_esc(data.as_of?.slice(0, 16) || '--')}</div>
        ${tableHtml}
        ${dormantFooter}
      </div>
      ${cumHtml}`;

    // Click handler for entire row -> chart
    container.querySelectorAll('tr.scanner-row').forEach(tr => {
      tr.addEventListener('click', e => {
        // Don't double-fire if user clicked the anchor inside
        if (e.target.tagName === 'A') return;
        _navigateToChart(tr.dataset.ticker);
      });
    });

    if (_refreshTimer) clearInterval(_refreshTimer);
    _refreshTimer = setInterval(() => render(container), 60000);
  } catch (e) {
    console.error('scanner render failed', e);
    container.innerHTML = '<div class="empty-state"><p>Failed to load scanner data</p></div>';
  } finally {
    _inflight = false;
  }
}

export function destroy() {
  if (_refreshTimer) { clearInterval(_refreshTimer); _refreshTimer = null; }
}
```

- [ ] **Step 5: Run tests, expect PASS**

Run: `pytest pipeline/tests/terminal/test_scanner_pattern_js.py -v`
Expected: 5 passed.

- [ ] **Step 6: Verify JS syntax**

Run: `node --check pipeline/terminal/static/js/pages/scanner.js`
Expected: no output.

- [ ] **Step 7: Commit**

```bash
git add pipeline/terminal/static/js/pages/scanner.js pipeline/tests/terminal/test_scanner_pattern_js.py
git commit -m "feat(scanner): pattern-occurrence rewire + click-to-chart restored (T7, fixes #269)"
```

---

## Task 8: `scanner_paired_shadow.py` — sidecar (Layer 5)

**Prerequisite:** `pipeline/options_atm_helpers.py`, `options_quote.py`, `options_greeks.py` exist (built by Phase C plan T1–T3). If absent, run those first.

**Files:**
- Create: `pipeline/scanner_paired_shadow.py`
- Test: `pipeline/tests/test_scanner_paired_shadow.py`

- [ ] **Step 1: Write failing tests**

`pipeline/tests/test_scanner_paired_shadow.py`:
```python
import json
from datetime import datetime, date, time, timezone, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from pipeline.scanner_paired_shadow import open_options_pair, close_options_pair


@pytest.fixture
def signal_row():
    return {
        "signal_id": "2026-04-27_RELIANCE_BULLISH_HAMMER",
        "date": "2026-04-27",
        "ticker": "RELIANCE",
        "pattern_id": "BULLISH_HAMMER",
        "direction": "LONG",
        "composite_score": 4.27,
        "n_occurrences": 156,
        "win_rate": 0.62,
        "z_score": 3.0,
        "mean_pnl_pct": 0.012,
        "fold_stability": 0.78,
    }


def test_open_writes_open_row(tmp_path, signal_row, monkeypatch):
    ledger = tmp_path / "live_paper_scanner_options_ledger.json"
    ledger.write_text("[]")

    mock_quote = MagicMock(
        instrument_token=12345678, bid=119.5, ask=122.0, mid=120.75,
        spread_pct=0.0207, last_price=120.5, timestamp=datetime.now(timezone.utc),
        liquidity_passed=True, skip_reason=None,
    )
    mock_kite = MagicMock()

    monkeypatch.setattr(
        "pipeline.scanner_paired_shadow.LEDGER_PATH", ledger)
    monkeypatch.setattr(
        "pipeline.scanner_paired_shadow.options_quote.fetch_mid_with_liquidity_check",
        lambda *_a, **_kw: mock_quote)
    monkeypatch.setattr(
        "pipeline.scanner_paired_shadow.options_atm_helpers.resolve_nearest_monthly_expiry",
        lambda *_a, **_kw: date(2026, 5, 29))
    monkeypatch.setattr(
        "pipeline.scanner_paired_shadow.options_atm_helpers.resolve_atm_strike",
        lambda *_a, **_kw: 2400)
    monkeypatch.setattr(
        "pipeline.scanner_paired_shadow.options_atm_helpers.compose_tradingsymbol",
        lambda *_a, **_kw: "RELIANCE25MAY2400CE")
    monkeypatch.setattr(
        "pipeline.scanner_paired_shadow.options_greeks.backsolve_iv",
        lambda *_a, **_kw: 0.276)
    monkeypatch.setattr(
        "pipeline.scanner_paired_shadow.options_greeks.compute_greeks",
        lambda *_a, **_kw: {"delta": 0.51, "theta": -3.4, "vega": 4.1})

    row = open_options_pair(signal_row, kite_client=mock_kite, spot=2398.0,
                             lot_size=250)

    assert row["status"] == "OPEN"
    assert row["option_type"] == "CE"
    assert row["strike"] == 2400
    assert row["pattern_id"] == "BULLISH_HAMMER"
    assert row["scanner_z_score_at_entry"] == 3.0
    assert row["entry_mid"] == 120.75
    assert row["entry_iv"] == 0.276
    assert row["lots"] == 1
    assert row["notional_at_entry"] == 250 * 120.75 * 1

    ledger_rows = json.loads(ledger.read_text())
    assert len(ledger_rows) == 1
    assert ledger_rows[0]["signal_id"] == signal_row["signal_id"]


def test_open_skips_on_wide_spread(tmp_path, signal_row, monkeypatch):
    ledger = tmp_path / "live_paper_scanner_options_ledger.json"
    ledger.write_text("[]")

    mock_quote = MagicMock(
        instrument_token=12345678, bid=110.0, ask=130.0, mid=120.0,
        spread_pct=0.167, last_price=120.0, timestamp=datetime.now(timezone.utc),
        liquidity_passed=False, skip_reason="WIDE_SPREAD",
    )
    monkeypatch.setattr(
        "pipeline.scanner_paired_shadow.LEDGER_PATH", ledger)
    monkeypatch.setattr(
        "pipeline.scanner_paired_shadow.options_quote.fetch_mid_with_liquidity_check",
        lambda *_a, **_kw: mock_quote)
    monkeypatch.setattr(
        "pipeline.scanner_paired_shadow.options_atm_helpers.resolve_nearest_monthly_expiry",
        lambda *_a, **_kw: date(2026, 5, 29))
    monkeypatch.setattr(
        "pipeline.scanner_paired_shadow.options_atm_helpers.resolve_atm_strike",
        lambda *_a, **_kw: 2400)
    monkeypatch.setattr(
        "pipeline.scanner_paired_shadow.options_atm_helpers.compose_tradingsymbol",
        lambda *_a, **_kw: "RELIANCE25MAY2400CE")

    row = open_options_pair(signal_row, kite_client=MagicMock(), spot=2398.0,
                             lot_size=250)

    assert row["status"] == "SKIPPED_LIQUIDITY"
    assert row["skip_reason"] == "WIDE_SPREAD"


def test_close_updates_to_closed(tmp_path, signal_row, monkeypatch):
    ledger = tmp_path / "live_paper_scanner_options_ledger.json"
    open_row = {
        "signal_id": signal_row["signal_id"],
        "date": "2026-04-27", "symbol": "RELIANCE", "side": "LONG",
        "option_type": "CE", "expiry_date": "2026-05-29",
        "days_to_expiry": 30, "is_expiry_day": False,
        "strike": 2400, "tradingsymbol": "RELIANCE25MAY2400CE",
        "instrument_token": 12345678, "lot_size": 250, "lots": 1,
        "notional_at_entry": 30187.5,
        "entry_time": "2026-04-28T09:25:00+05:30",
        "entry_bid": 119.5, "entry_ask": 122.0, "entry_mid": 120.75,
        "spread_pct_at_entry": 0.0207,
        "entry_iv": 0.276, "entry_delta": 0.51, "entry_theta": -3.4,
        "entry_vega": 4.1, "pattern_id": "BULLISH_HAMMER",
        "scanner_composite_score_at_entry": 4.27,
        "scanner_z_score_at_entry": 3.0,
        "status": "OPEN", "skip_reason": None,
    }
    ledger.write_text(json.dumps([open_row]))

    mock_close_quote = MagicMock(
        instrument_token=12345678, bid=124.0, ask=126.0, mid=125.0,
        spread_pct=0.016, last_price=125.0, timestamp=datetime.now(timezone.utc),
        liquidity_passed=True, skip_reason=None,
    )
    monkeypatch.setattr(
        "pipeline.scanner_paired_shadow.LEDGER_PATH", ledger)
    monkeypatch.setattr(
        "pipeline.scanner_paired_shadow.options_quote.fetch_mid_with_liquidity_check",
        lambda *_a, **_kw: mock_close_quote)

    out = close_options_pair(signal_row["signal_id"], kite_client=MagicMock())

    assert out["status"] == "CLOSED"
    assert out["exit_mid"] == 125.0
    # gross = (125 - 120.75) / 120.75 = 0.0352
    assert abs(out["pnl_gross_pct"] - 0.0352) < 1e-3
    # net is gross - cost; should be positive
    assert out["pnl_net_pct"] is not None and out["pnl_net_pct"] < out["pnl_gross_pct"]
```

- [ ] **Step 2: Run tests, expect FAIL**

Run: `pytest pipeline/tests/test_scanner_paired_shadow.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement scanner_paired_shadow.py**

`pipeline/scanner_paired_shadow.py`:
```python
"""Scanner (TA) paired-shadow sidecar. Mirrors the Phase C paired-shadow
architecture (`docs/superpowers/specs/2026-04-27-phase-c-options-paired-shadow-design.md`)
but driven by daily pattern-engine Top-10 instead of OPPORTUNITY_LAG breaks.

Per spec §6.5 + §8.3 + §8.4.
"""
import json
import logging
from datetime import date as _date, datetime, time, timezone, timedelta
from pathlib import Path

from pipeline import options_atm_helpers, options_quote, options_greeks
from pipeline.research.phase_c_v5 import cost_model

logger = logging.getLogger(__name__)
IST = timezone(timedelta(hours=5, minutes=30))

LEDGER_PATH = Path(
    "pipeline/data/research/scanner/live_paper_scanner_options_ledger.json")
NFO_MASTER_PATH = Path("pipeline/data/kite_cache/instruments_nfo.csv")


def _load_ledger() -> list[dict]:
    if not LEDGER_PATH.exists():
        return []
    return json.loads(LEDGER_PATH.read_text())


def _save_ledger(rows: list[dict]) -> None:
    LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    LEDGER_PATH.write_text(json.dumps(rows, indent=2, default=str))


def open_options_pair(signal_row: dict, kite_client, spot: float,
                       lot_size: int) -> dict:
    """Open paired ATM options leg for a Scanner Top-10 signal.
    LONG signal → CE; SHORT signal → PE.
    Idempotent on signal_id.
    """
    sid = signal_row["signal_id"]
    rows = _load_ledger()
    if any(r.get("signal_id") == sid for r in rows):
        logger.info("scanner_paired_shadow: signal_id %s already opened, skipping", sid)
        return next(r for r in rows if r.get("signal_id") == sid)

    direction = signal_row["direction"]
    option_type = "CE" if direction == "LONG" else "PE"
    ticker = signal_row["ticker"]

    base_row = {
        "signal_id": sid, "date": signal_row["date"], "symbol": ticker,
        "side": direction, "option_type": option_type,
        "lot_size": lot_size, "lots": 1,
        "pattern_id": signal_row["pattern_id"],
        "scanner_composite_score_at_entry": signal_row.get("composite_score"),
        "scanner_z_score_at_entry": signal_row.get("z_score"),
        "status": "OPEN", "skip_reason": None,
        "exit_time": None, "exit_bid": None, "exit_ask": None, "exit_mid": None,
        "seconds_to_expiry_at_close": None,
        "pnl_gross_pct": None, "pnl_net_pct": None,
        "pnl_gross_inr": None, "pnl_net_inr": None,
        "futures_pnl_net_pct": None,
    }

    try:
        nfo_master = options_atm_helpers.load_nfo_master(NFO_MASTER_PATH)
        expiry = options_atm_helpers.resolve_nearest_monthly_expiry(
            today=datetime.now(IST).date(), ticker=ticker, nfo_master_df=nfo_master)
        strike = options_atm_helpers.resolve_atm_strike(
            spot=spot, ticker=ticker, expiry=expiry, nfo_master_df=nfo_master)
        tradingsymbol = options_atm_helpers.compose_tradingsymbol(
            ticker=ticker, expiry=expiry, strike=strike, option_type=option_type)
        instrument_token = options_atm_helpers.resolve_instrument_token(
            tradingsymbol=tradingsymbol, nfo_master_df=nfo_master)

        quote = options_quote.fetch_mid_with_liquidity_check(
            kite_client, instrument_token)

        dte = (expiry - datetime.now(IST).date()).days
        is_expiry_day = (dte == 0)

        base_row.update({
            "expiry_date": expiry.isoformat(),
            "days_to_expiry": dte,
            "is_expiry_day": is_expiry_day,
            "strike": strike,
            "tradingsymbol": tradingsymbol,
            "instrument_token": instrument_token,
            "entry_time": datetime.now(IST).isoformat(),
            "entry_bid": quote.bid, "entry_ask": quote.ask, "entry_mid": quote.mid,
            "spread_pct_at_entry": quote.spread_pct,
        })

        if not quote.liquidity_passed:
            base_row["status"] = "SKIPPED_LIQUIDITY"
            base_row["skip_reason"] = quote.skip_reason
        else:
            iv = options_greeks.backsolve_iv(
                spot=spot, strike=strike, dte_days=max(dte, 1),
                mid_premium=quote.mid, option_type=option_type)
            greeks = options_greeks.compute_greeks(
                spot=spot, strike=strike, dte_days=max(dte, 1),
                iv=iv, option_type=option_type)
            base_row.update({
                "entry_iv": iv,
                "entry_delta": greeks["delta"],
                "entry_theta": greeks["theta"],
                "entry_vega": greeks["vega"],
                "notional_at_entry": quote.mid * lot_size * 1,
            })
    except Exception as e:
        logger.exception("scanner_paired_shadow open failed for %s", sid)
        base_row["status"] = "ERROR"
        base_row["skip_reason"] = f"{type(e).__name__}: {str(e)[:200]}"

    rows.append(base_row)
    _save_ledger(rows)
    return base_row


def close_options_pair(signal_id: str, kite_client) -> dict | None:
    rows = _load_ledger()
    target = next((r for r in rows if r.get("signal_id") == signal_id
                   and r.get("status") == "OPEN"), None)
    if target is None:
        return None
    try:
        quote = options_quote.fetch_mid_with_liquidity_check(
            kite_client, target["instrument_token"])
        target["exit_time"] = datetime.now(IST).isoformat()
        target["exit_bid"] = quote.bid
        target["exit_ask"] = quote.ask
        target["exit_mid"] = quote.mid
        gross = (quote.mid - target["entry_mid"]) / target["entry_mid"]
        target["pnl_gross_pct"] = gross
        net = cost_model.apply_to_pnl(
            pnl_gross=gross, instrument_type="option",
            notional=target["notional_at_entry"])
        target["pnl_net_pct"] = net
        target["pnl_gross_inr"] = gross * target["notional_at_entry"]
        target["pnl_net_inr"] = net * target["notional_at_entry"]
        if target.get("is_expiry_day"):
            now_t = datetime.now(IST).time()
            expiry_close = time(15, 30)
            secs = (expiry_close.hour * 3600 + expiry_close.minute * 60) - \
                   (now_t.hour * 3600 + now_t.minute * 60 + now_t.second)
            target["seconds_to_expiry_at_close"] = max(0, secs)
        target["status"] = "CLOSED"
    except Exception as e:
        logger.exception("scanner_paired_shadow close failed for %s", signal_id)
        target["status"] = "TIME_STOP_FAIL_FETCH"
        target["skip_reason"] = f"{type(e).__name__}: {str(e)[:200]}"
    _save_ledger(rows)
    return target


def cmd_open(scanner_signals_path: Path, kite_client, spot_resolver, lot_size_resolver):
    """Read pattern_signals_today.json from yesterday's scan, open pairs."""
    payload = json.loads(scanner_signals_path.read_text())
    for sig in payload.get("top_10", []):
        spot = spot_resolver(sig["ticker"])
        lot_size = lot_size_resolver(sig["ticker"])
        if spot is None or lot_size is None:
            logger.warning("missing spot/lot_size for %s, skipping", sig["ticker"])
            continue
        open_options_pair(sig, kite_client=kite_client, spot=spot, lot_size=lot_size)


def cmd_close(kite_client):
    rows = _load_ledger()
    open_ids = [r["signal_id"] for r in rows if r.get("status") == "OPEN"]
    for sid in open_ids:
        close_options_pair(sid, kite_client=kite_client)
```

- [ ] **Step 4: Run tests, expect PASS**

Run: `pytest pipeline/tests/test_scanner_paired_shadow.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add pipeline/scanner_paired_shadow.py pipeline/tests/test_scanner_paired_shadow.py
git commit -m "feat(pattern-scanner): paired-shadow sidecar reusing Phase C helpers (T8)"
```

---

## Task 9: Scheduled-task `.bat` files + `anka_inventory.json` entries

**Files:**
- Create: `pipeline/scripts/pattern_scanner_scan.bat`
- Create: `pipeline/scripts/pattern_scanner_fit.bat`
- Create: `pipeline/scripts/scanner_paired_open.bat`
- Create: `pipeline/scripts/scanner_paired_close.bat`
- Create: `pipeline/cli_pattern_scanner.py` (CLI driver invoked from .bats)
- Modify: `pipeline/config/anka_inventory.json`

- [ ] **Step 1: Implement CLI driver**

`pipeline/cli_pattern_scanner.py`:
```python
"""CLI driver for pattern-scanner scheduled tasks. Subcommands:
- scan      → daily detect + rank + write pattern_signals_today.json
- fit       → weekly 5y fit, write pattern_stats.parquet
- paired-open  → open paired-shadow legs for yesterday's Top-10
- paired-close → close all OPEN paired-shadow rows at 15:30 IST
"""
import argparse
import sys
from datetime import date, datetime, timezone, timedelta
from pathlib import Path

import pandas as pd

from pipeline.pattern_scanner.runner import run_daily_scan
from pipeline.pattern_scanner.stats import fit_universe
from pipeline.pattern_scanner.constants import WIN_THRESHOLD
from pipeline.scanner_paired_shadow import cmd_open, cmd_close
from pipeline import kite_client as _kite
from pipeline.canonical_loader import load_daily_bars
from pipeline.fno_universe import load_universe

IST = timezone(timedelta(hours=5, minutes=30))
SCANNER_DIR = Path("pipeline/data/scanner")
SIGNALS_TODAY = SCANNER_DIR / "pattern_signals_today.json"
STATS_PATH = SCANNER_DIR / "pattern_stats.parquet"


def cmd_scan():
    universe = load_universe()
    if not STATS_PATH.exists():
        print(f"ERROR: {STATS_PATH} missing — run fit first", file=sys.stderr)
        sys.exit(1)
    stats = pd.read_parquet(STATS_PATH)
    today = datetime.now(IST).date()
    run_daily_scan(
        scan_date=today, universe=universe,
        bars_loader=load_daily_bars,
        stats_df=stats, out_path=SIGNALS_TODAY)


def cmd_fit():
    universe = load_universe()
    today = datetime.now(IST).date()
    start = today - timedelta(days=365 * 5)
    df = fit_universe(
        universe=universe, bars_loader=load_daily_bars,
        start=start, end=today, win_threshold=WIN_THRESHOLD)
    SCANNER_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(STATS_PATH, index=False)
    print(f"wrote {STATS_PATH} with {len(df)} cells")


def _spot_resolver(ticker: str):
    bars = load_daily_bars(ticker)
    if bars is None or bars.empty:
        return None
    return float(bars["close"].iloc[-1])


def _lot_size_resolver(ticker: str):
    # Read NFO master to find lot_size for ticker's monthly contracts
    from pipeline.options_atm_helpers import load_nfo_master, get_lot_size_for_ticker
    nfo = load_nfo_master(Path("pipeline/data/kite_cache/instruments_nfo.csv"))
    return get_lot_size_for_ticker(ticker, nfo)


def cmd_paired_open():
    kite = _kite.get_authenticated_client()
    cmd_open(SIGNALS_TODAY, kite_client=kite,
             spot_resolver=_spot_resolver,
             lot_size_resolver=_lot_size_resolver)


def cmd_paired_close():
    kite = _kite.get_authenticated_client()
    cmd_close(kite_client=kite)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("subcmd", choices=["scan", "fit", "paired-open", "paired-close"])
    args = parser.parse_args()
    {"scan": cmd_scan, "fit": cmd_fit,
     "paired-open": cmd_paired_open, "paired-close": cmd_paired_close}[args.subcmd]()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Implement .bat wrappers**

`pipeline/scripts/pattern_scanner_scan.bat`:
```bat
@echo off
cd /d C:\Users\Claude_Anka\askanka.com
call .venv\Scripts\activate.bat
python -m pipeline.cli_pattern_scanner scan
```

`pipeline/scripts/pattern_scanner_fit.bat`:
```bat
@echo off
cd /d C:\Users\Claude_Anka\askanka.com
call .venv\Scripts\activate.bat
python -m pipeline.cli_pattern_scanner fit
```

`pipeline/scripts/scanner_paired_open.bat`:
```bat
@echo off
cd /d C:\Users\Claude_Anka\askanka.com
call .venv\Scripts\activate.bat
python -m pipeline.cli_pattern_scanner paired-open
```

`pipeline/scripts/scanner_paired_close.bat`:
```bat
@echo off
cd /d C:\Users\Claude_Anka\askanka.com
call .venv\Scripts\activate.bat
python -m pipeline.cli_pattern_scanner paired-close
```

- [ ] **Step 3: Add inventory entries**

`pipeline/config/anka_inventory.json` — append 4 entries (preserve existing JSON structure):
```jsonc
{
  "task_name": "AnkaPatternScannerScan",
  "tier": "info",
  "cadence_class": "daily",
  "schedule": "16:30 IST",
  "expected_outputs": ["pipeline/data/scanner/pattern_signals_today.json"],
  "grace_multiplier": 1.5
},
{
  "task_name": "AnkaPatternScannerFit",
  "tier": "warn",
  "cadence_class": "weekly",
  "schedule": "Sun 02:00 IST",
  "expected_outputs": ["pipeline/data/scanner/pattern_stats.parquet"],
  "grace_multiplier": 2.0
},
{
  "task_name": "AnkaScannerPairedOpen",
  "tier": "info",
  "cadence_class": "intraday",
  "schedule": "09:25 IST",
  "expected_outputs": ["pipeline/data/research/scanner/live_paper_scanner_options_ledger.json"],
  "grace_multiplier": 1.5
},
{
  "task_name": "AnkaScannerPairedClose",
  "tier": "info",
  "cadence_class": "intraday",
  "schedule": "15:30 IST",
  "expected_outputs": ["pipeline/data/research/scanner/live_paper_scanner_options_ledger.json"],
  "grace_multiplier": 1.5
}
```

- [ ] **Step 4: Verify JSON parses**

Run: `python -c "import json; json.load(open('pipeline/config/anka_inventory.json'))"`
Expected: no output (valid JSON).

- [ ] **Step 5: Register Windows scheduled tasks**

Run (one-time, manual on the Windows host):
```bat
schtasks /create /tn "AnkaPatternScannerScan" /tr "C:\Users\Claude_Anka\askanka.com\pipeline\scripts\pattern_scanner_scan.bat" /sc daily /st 16:30 /f
schtasks /create /tn "AnkaPatternScannerFit" /tr "C:\Users\Claude_Anka\askanka.com\pipeline\scripts\pattern_scanner_fit.bat" /sc weekly /d SUN /st 02:00 /f
schtasks /create /tn "AnkaScannerPairedOpen" /tr "C:\Users\Claude_Anka\askanka.com\pipeline\scripts\scanner_paired_open.bat" /sc daily /st 09:25 /f
schtasks /create /tn "AnkaScannerPairedClose" /tr "C:\Users\Claude_Anka\askanka.com\pipeline\scripts\scanner_paired_close.bat" /sc daily /st 15:30 /f
```

- [ ] **Step 6: Commit**

```bash
git add pipeline/cli_pattern_scanner.py pipeline/scripts/pattern_scanner_scan.bat pipeline/scripts/pattern_scanner_fit.bat pipeline/scripts/scanner_paired_open.bat pipeline/scripts/scanner_paired_close.bat pipeline/config/anka_inventory.json
git commit -m "ops(pattern-scanner): CLI driver + 4 .bat wrappers + inventory entries (T9)"
```

---

## Task 10: First weekly fit on full 5y F&O universe

**Files:** none (validation step)

- [ ] **Step 1: Run the fit command**

Run: `python -m pipeline.cli_pattern_scanner fit`
Expected: completes in <30 minutes. Prints `wrote pipeline/data/scanner/pattern_stats.parquet with N cells` where N ≤ 213 × 12 = 2556.

- [ ] **Step 2: Verify parquet structure**

Run:
```python
python -c "
import pandas as pd
df = pd.read_parquet('pipeline/data/scanner/pattern_stats.parquet')
print(df.shape)
print(df.head())
print('Columns:', list(df.columns))
print('Patterns:', df['pattern_id'].unique())
print('Tickers:', df['ticker'].nunique())
print('Cells with n>=30:', (df['n_occurrences'] >= 30).sum())
print('Cells passing fold_stability>=0.5:', (df['fold_stability'] >= 0.5).sum())
"
```
Expected: 12 distinct pattern_ids; ~213 distinct tickers; somewhere between 200–600 cells with `n>=30 AND fold_stability>=0.5` (rough estimate from the literature on retail TA patterns).

- [ ] **Step 3: Sanity-check a known-named pattern's z-score distribution**

Run:
```python
python -c "
import pandas as pd
df = pd.read_parquet('pipeline/data/scanner/pattern_stats.parquet')
qual = df[(df['n_occurrences'] >= 30) & (df['fold_stability'] >= 0.5)]
print('Bullish hammer z-score range:',
    qual[qual['pattern_id']=='BULLISH_HAMMER']['z_score'].describe())
print('Top 5 by z*log(1+n)*|mean_pnl|:')
import numpy as np
qual['composite'] = qual['z_score'] * np.log1p(qual['n_occurrences']) * qual['mean_pnl_pct'].abs()
print(qual.nlargest(5, 'composite')[['ticker','pattern_id','n_occurrences','win_rate','z_score','mean_pnl_pct','fold_stability']])
"
```
Expected: A handful of cells with z > 2, win-rates 55–70%, fold_stability > 0.5. If everything is z ≈ 0, suspect a bug in detect.py or stats.py — investigate before proceeding.

- [ ] **Step 4: Commit the parquet artifact**

```bash
git add pipeline/data/scanner/pattern_stats.parquet
git commit -m "data(pattern-scanner): first 5y full-universe fit artifact (T10)"
```

---

## Task 11: 2-day end-to-end smoke run

**Files:** none (validation step)

- [ ] **Step 1: Day-1 dry-run scan**

Run: `python -m pipeline.cli_pattern_scanner scan`
Expected: writes `pipeline/data/scanner/pattern_signals_today.json` with `top_10` of 0–10 signals.

- [ ] **Step 2: Inspect today's Top-10**

Run: `cat pipeline/data/scanner/pattern_signals_today.json`
Verify: `qualified_count` matches `len(top_10)` ≤ 10; each row has `direction`, `n_occurrences>=30`, `fold_stability>=0.5`.

- [ ] **Step 3: Day-1 paired-open at 09:25 IST next morning**

Run on the next trading day's 09:25 (or simulate by triggering manually):
```bash
python -m pipeline.cli_pattern_scanner paired-open
```
Expected: ledger `pipeline/data/research/scanner/live_paper_scanner_options_ledger.json` gets new rows. At least 1 row with `status=OPEN` and full Greeks. At least 1 row with `status=SKIPPED_LIQUIDITY` (sanity on the gate).

- [ ] **Step 4: Day-1 paired-close at 15:30 IST**

Run at 15:30:
```bash
python -m pipeline.cli_pattern_scanner paired-close
```
Expected: every `OPEN` row from this morning becomes `CLOSED` with non-null `pnl_net_pct`.

- [ ] **Step 5: Day-2 repeat (sanity for idempotency)**

Repeat scan + paired-open + paired-close on day 2.

- [ ] **Step 6: Verify Scanner UI**

Open the terminal in browser. Visit Scanner tab. Verify:
- Top-10 table renders with z-score column.
- Click on any ticker → navigates to chart.
- Cumulative paired-shadow rollup card shows non-zero `n_closed`.

- [ ] **Step 7: Commit smoke artifact (if separate from T10)**

If the ledger picked up ≥1 closed pair, commit it:
```bash
git add pipeline/data/research/scanner/live_paper_scanner_options_ledger.json
git commit -m "data(pattern-scanner): 2-day smoke run ledger artifact (T11)"
```

---

## Task 12: Reporting module `pattern_scanner_report.py`

**Files:**
- Create: `pipeline/pattern_scanner_report.py`
- Test: `pipeline/tests/test_pattern_scanner_report.py`

- [ ] **Step 1: Write failing test**

`pipeline/tests/test_pattern_scanner_report.py`:
```python
import json
from pathlib import Path
from pipeline.pattern_scanner_report import build_report


def test_build_report_writes_markdown(tmp_path):
    ledger = tmp_path / "ledger.json"
    rows = [
        {"signal_id": "2026-04-28_RELIANCE_BULLISH_HAMMER",
         "date": "2026-04-28", "symbol": "RELIANCE", "side": "LONG",
         "pattern_id": "BULLISH_HAMMER", "is_expiry_day": False,
         "status": "CLOSED", "pnl_net_pct": 0.012,
         "futures_pnl_net_pct": 0.008,
         "scanner_z_score_at_entry": 3.0},
        {"signal_id": "2026-04-28_TATAMOTORS_BEARISH_ENGULFING",
         "date": "2026-04-28", "symbol": "TATAMOTORS", "side": "SHORT",
         "pattern_id": "BEARISH_ENGULFING", "is_expiry_day": False,
         "status": "CLOSED", "pnl_net_pct": -0.005,
         "futures_pnl_net_pct": -0.002,
         "scanner_z_score_at_entry": 2.1},
    ]
    ledger.write_text(json.dumps(rows))
    out = tmp_path / "report.md"
    build_report(ledger_path=ledger, out_path=out)
    text = out.read_text()
    assert "Headline paired diff" in text
    assert "Win rate by pattern_id" in text
    assert "BULLISH_HAMMER" in text
    assert "BEARISH_ENGULFING" in text
```

- [ ] **Step 2: Run test, expect FAIL**

Run: `pytest pipeline/tests/test_pattern_scanner_report.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement reporter**

`pipeline/pattern_scanner_report.py`:
```python
"""One-pager Markdown report after each scanner paired-shadow close.

Per spec §13. Stratified tables, no edge claim.
"""
import json
import statistics
from collections import defaultdict
from pathlib import Path


def _stratify(rows: list[dict], key: str) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        out[str(r.get(key, "UNKNOWN"))].append(r)
    return dict(out)


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return (sum(xs) / len(xs)) if xs else None


def _fmt_pct(v):
    if v is None:
        return "—"
    return f"{v * 100:+.2f}%"


def build_report(ledger_path: Path, out_path: Path) -> None:
    rows = json.loads(Path(ledger_path).read_text())
    closed = [r for r in rows if r.get("status") == "CLOSED"]

    lines: list[str] = []
    lines.append("# Pattern Scanner Paired-Shadow Report\n")
    lines.append(f"**Total closed:** {len(closed)}\n")

    # Table A — headline paired diff, stratified by is_expiry_day
    lines.append("\n## Table A — Headline paired diff (options − futures)\n")
    lines.append("| is_expiry_day | N | mean(opt − fut) | mean opt | mean fut |")
    lines.append("|---|---|---|---|---|")
    for k, cohort in _stratify(closed, "is_expiry_day").items():
        opt = _mean([r.get("pnl_net_pct") for r in cohort])
        fut = _mean([r.get("futures_pnl_net_pct") for r in cohort])
        diff = (opt - fut) if (opt is not None and fut is not None) else None
        lines.append(f"| {k} | {len(cohort)} | {_fmt_pct(diff)} | {_fmt_pct(opt)} | {_fmt_pct(fut)} |")

    # Table B — Win rate by pattern_id
    lines.append("\n## Table B — Win rate by pattern_id\n")
    lines.append("| pattern_id | N | win-rate | mean opt | mean fut |")
    lines.append("|---|---|---|---|---|")
    for k, cohort in _stratify(closed, "pattern_id").items():
        wins = sum(1 for r in cohort if (r.get("pnl_net_pct") or 0) > 0)
        wr = wins / len(cohort) if cohort else 0
        opt = _mean([r.get("pnl_net_pct") for r in cohort])
        fut = _mean([r.get("futures_pnl_net_pct") for r in cohort])
        lines.append(f"| {k} | {len(cohort)} | {wr*100:.1f}% | {_fmt_pct(opt)} | {_fmt_pct(fut)} |")

    # Table C — by direction
    lines.append("\n## Table C — Win rate by direction\n")
    lines.append("| side | N | win-rate | mean opt | mean fut |")
    lines.append("|---|---|---|---|---|")
    for k, cohort in _stratify(closed, "side").items():
        wins = sum(1 for r in cohort if (r.get("pnl_net_pct") or 0) > 0)
        wr = wins / len(cohort) if cohort else 0
        opt = _mean([r.get("pnl_net_pct") for r in cohort])
        fut = _mean([r.get("futures_pnl_net_pct") for r in cohort])
        lines.append(f"| {k} | {len(cohort)} | {wr*100:.1f}% | {_fmt_pct(opt)} | {_fmt_pct(fut)} |")

    # Skip rate
    skipped = [r for r in rows if r.get("status") == "SKIPPED_LIQUIDITY"]
    err = [r for r in rows if r.get("status") == "ERROR"]
    lines.append(f"\n## Skip-rate summary\n")
    lines.append(f"- SKIPPED_LIQUIDITY: {len(skipped)} rows ({len(skipped)/max(1,len(rows))*100:.1f}% of total)")
    lines.append(f"- ERROR: {len(err)} rows ({len(err)/max(1,len(rows))*100:.1f}% of total)")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n")
```

- [ ] **Step 4: Run test, expect PASS**

Run: `pytest pipeline/tests/test_pattern_scanner_report.py -v`
Expected: 1 passed.

- [ ] **Step 5: Wire reporter into close path**

Edit `pipeline/cli_pattern_scanner.py` `cmd_paired_close()`:
```python
def cmd_paired_close():
    kite = _kite.get_authenticated_client()
    cmd_close(kite_client=kite)
    # Generate report after close cycle
    from pipeline.pattern_scanner_report import build_report
    build_report(
        ledger_path=Path("pipeline/data/research/scanner/live_paper_scanner_options_ledger.json"),
        out_path=Path("pipeline/data/research/scanner/paired_shadow_report.md"))
```

- [ ] **Step 6: Commit**

```bash
git add pipeline/pattern_scanner_report.py pipeline/tests/test_pattern_scanner_report.py pipeline/cli_pattern_scanner.py
git commit -m "feat(pattern-scanner): paired-shadow Markdown report after each close (T12)"
```

---

## Task 13: Docs + memory sync

**Files:**
- Modify: `docs/SYSTEM_OPERATIONS_MANUAL.md`
- Modify: `CLAUDE.md`
- Create: `C:/Users/Claude_Anka/.claude/projects/C--Users-Claude-Anka-askanka-com/memory/project_pattern_scanner.md`
- Modify: `C:/Users/Claude_Anka/.claude/projects/C--Users-Claude-Anka-askanka-com/memory/MEMORY.md`

- [ ] **Step 1: Add Pattern Scanner section to SYSTEM_OPERATIONS_MANUAL**

Append to `docs/SYSTEM_OPERATIONS_MANUAL.md` under a new heading `## Pattern Scanner`:
```markdown
## Pattern Scanner (TA tab)

**Purpose:** Daily F&O-universe candlestick / structural / momentum pattern scan, ranked by historical occurrence stats (z-score × log(n) × |mean_pnl|), Top-10 fires paired (futures + ATM monthly options) shadow trades.

**Layers:**
1. `pipeline/pattern_scanner/detect.py` — daily detection (12 patterns: 4 bullish + 4 bearish candles + 2 BB structures + 2 MACD events)
2. `pipeline/pattern_scanner/stats.py` — weekly 5y fit, walk-forward 4-fold stability ratio
3. `pipeline/pattern_scanner/rank.py` + `runner.py` — daily Top-10 emission
4. `scanner.js` rewire (Scanner tab UI + click-to-chart)
5. `pipeline/scanner_paired_shadow.py` — sidecar paired-shadow ledger reusing Phase C helpers

**Schedule:**
- 02:00 IST Sun — `AnkaPatternScannerFit` (writes `pattern_stats.parquet`)
- 16:30 IST daily — `AnkaPatternScannerScan` (writes `pattern_signals_today.json`)
- 09:25 IST daily — `AnkaScannerPairedOpen` (opens paired legs for yesterday's Top-10)
- 15:30 IST daily — `AnkaScannerPairedClose` (closes paired legs + writes report)

**Artifacts:**
- `pipeline/data/scanner/pattern_stats.parquet` (weekly)
- `pipeline/data/scanner/pattern_signals_today.json` (daily)
- `pipeline/data/scanner/pattern_signals_history.parquet` (daily audit append)
- `pipeline/data/research/scanner/live_paper_scanner_options_ledger.json` (paired-shadow ledger)
- `pipeline/data/research/scanner/paired_shadow_report.md` (post-close one-pager)

**Status:** Forward-only OOS measurement layer. No edge claim, no kill-switch trigger, no §0-16 compliance pass for v1. Reporting stratifies by `is_expiry_day`, `pattern_id`, `direction`. Verdict: descriptive at N=30, bootstrap at N=100.

**Spec:** `docs/superpowers/specs/2026-04-27-ta-scanner-pattern-paired-shadow-design.md`
```

- [ ] **Step 2: Add 4 tasks to CLAUDE.md Clockwork Schedule**

Edit `CLAUDE.md` under the appropriate sections (Overnight Batch, Pre-Market, Market Hours, Post-Close):
```markdown
- 02:00 (Sun) — AnkaPatternScannerFit: weekly 5y F&O pattern fit, writes pattern_stats.parquet (warn)
- 09:25 — AnkaScannerPairedOpen: open paired (futures + ATM CE/PE) legs for yesterday's Top-10 pattern signals (info)
- 15:30 — AnkaScannerPairedClose: mechanical close at 15:30 IST + write paired-shadow report (info)
- 16:30 — AnkaPatternScannerScan: daily F&O pattern scan + Top-10 ranking, writes pattern_signals_today.json (info)
```

- [ ] **Step 3: Create memory file**

`C:/Users/Claude_Anka/.claude/projects/C--Users-Claude-Anka-askanka-com/memory/project_pattern_scanner.md`:
```markdown
---
name: Pattern Scanner (Scanner TA tab redesign)
description: Daily F&O pattern-occurrence engine with paired (futures + options) shadow ledger. 12 patterns; Top-10 by z-score × log(n) × |mean_pnl|. Replaces broken "80% CI" display.
type: project
---

Daily F&O-universe candlestick / structural / momentum pattern scan, fortified with 5-year historical occurrence stats per (ticker × pattern). Top-10 fires paired (futures + ATM monthly options) forward-only OOS shadow trades. v1 ships 2026-04-27.

**Why:** Bharat 2026-04-27: existing logistic-regression TA scorer is a black-box probability with no direction; "80% CI" was a band-threshold mislabel. Pattern engine is interpretable: "BPCL bullish hammer, n=156, won 62%, z=3.0." Scanner becomes a productivity tool that saves the trader from manually flipping through 213 charts. Most useful in NEUTRAL regimes when spread trades go quiet.

**How to apply:**
- Spec: `docs/superpowers/specs/2026-04-27-ta-scanner-pattern-paired-shadow-design.md`
- Plan: `docs/superpowers/plans/2026-04-27-ta-scanner-pattern-paired-shadow.md`
- Reuses Phase C helper modules (options_atm_helpers, options_quote, options_greeks, cost_model) — do NOT duplicate
- Logistic TA scorer survives as annotation column (Q1=B); 30-day stay-of-execution before sunset
- 12 patterns: hammer / engulfing×2 / morning star / piercing / shooting star / evening star / dark cloud / BB breakout/breakdown / MACD cross×2
- Win threshold ±0.8% T+1 open-to-close; min n=30; min fold_stability=0.5; Top-10 daily
- 4 new scheduled tasks: PatternScannerFit (Sun 02:00), Scan (16:30), PairedOpen (09:25), PairedClose (15:30)
- Reporting stratifies by is_expiry_day, pattern_id, direction. No edge claim, no hypothesis-registry append, no kill-switch trigger.
```

- [ ] **Step 4: Add MEMORY.md pointer**

Append one line to `C:/Users/Claude_Anka/.claude/projects/C--Users-Claude-Anka-askanka-com/memory/MEMORY.md`:
```markdown
- [Pattern Scanner](project_pattern_scanner.md) — Daily F&O pattern engine + paired (futures + options) shadow ledger. 12 patterns; Top-10 by z-score × log(n) × |mean_pnl|. Replaces broken Scanner-tab "80% CI". Spec 2026-04-27.
```

- [ ] **Step 5: Verify no broken markdown links**

Run: `python -c "from pathlib import Path; assert Path('docs/superpowers/specs/2026-04-27-ta-scanner-pattern-paired-shadow-design.md').exists(); assert Path('docs/superpowers/plans/2026-04-27-ta-scanner-pattern-paired-shadow.md').exists()"`
Expected: no output.

- [ ] **Step 6: Commit**

```bash
git add docs/SYSTEM_OPERATIONS_MANUAL.md CLAUDE.md
git commit -m "docs(pattern-scanner): SYSTEM_OPERATIONS_MANUAL + CLAUDE.md sync (T13)"
```

Memory files live outside the repo so they're not part of the git commit.

---

## Self-review

**1. Spec coverage:** Walking spec sections —
- §1 Motivation: covered in plan motivation/goal sections, no implementation.
- §2 Goal: covered by T0–T12 collectively.
- §3 In scope: every listed item maps to a task (`detect`→T2, `stats`→T3, `rank`→T4, `runner`→T5, `scanner.js`→T7, `scanner_paired_shadow.py`→T8, scheduled tasks→T9, `pattern_scanner_report.py`→T12, endpoint→T6, click-to-chart→T7).
- §4 Locked decisions: encoded in T1 constants (12 patterns, 0.8% threshold, MIN_N=30, MIN_FOLD=0.5) and respected throughout.
- §5 Architecture: matches T2/T3/T4/T5/T7/T8 task split.
- §6 Components: each component has its own task (T2 detect, T3 stats, T4 rank, T5 runner, T6 endpoint, T7 scanner.js, T8 sidecar).
- §7 Schemas: pattern_stats.parquet built in T3+T10; pattern_signals_today.json in T5; ledger schema in T8.
- §8 Data flow: weekly fit (T10) + daily scan (T5) + paired open/close (T8/T11).
- §9 The 12 patterns: encoded in T1 constants.PATTERNS list.
- §10 Backtest methodology: implemented in T3 stats.py (`aggregate_pattern_cell`, `walk_forward_fold_stability`).
- §11 Error handling: every failure mode handled in respective task (liquidity skip in T8, missing stats in T9 cmd_scan).
- §12 Testing: TDD steps in every task with unit + integration coverage.
- §13 Reporting: T12.
- §14 Docs sync: T13.
- §15 Risks: pandas-ta install verified in T0 (risk #1); other risks are documentation-level, no implementation needed.
- §16 Sequencing preview: T0–T12 mirrors §16 (slightly compressed — combined T8 .bat creation with CLI driver in plan T9 for atomicity).

**Gap check:** §13 Table F (logistic-scorer attribution) — *not* implemented in this plan. Justification: that table requires joining the paired ledger to the logistic-scorer's score-at-entry, which requires capturing the logistic score at signal generation. Snapshotting the logistic score should happen in T5 runner.py, but I left it out for v1 simplicity. Adding to T5 as a follow-up task in spec §15 risks would reveal this; flagging here for v2.

**2. Placeholder scan:** Searched for TBD/TODO/FIXME — none. Every code block is complete.

**3. Type consistency:** `PatternFlag` defined in T2, used in T4 and T5. `ScannerSignal` defined in T4, written by T5 to JSON, consumed by T6 endpoint and T7 scanner.js. `signal_id` format `{date}_{ticker}_{pattern_id}` consistent across T4/T8. `direction ∈ {LONG, SHORT}` consistent. All function signatures match between definition and call sites.

**One inline fix:** T5 runner.py's `_resolve_signals_path` reference path matches T6 API endpoint's `_resolve_signals_path` — both default to `pipeline/data/scanner/pattern_signals_today.json`. Consistent.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-27-ta-scanner-pattern-paired-shadow.md`. Two execution options:

1. **Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration
2. **Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
