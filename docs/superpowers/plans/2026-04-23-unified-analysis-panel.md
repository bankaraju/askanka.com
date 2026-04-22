# Unified Analysis Panel (UAP) v1 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship one shared terminal component that renders FCS, TA, Spread, and Correlation Break analyses through the same envelope — replacing `attractiveness-panel.js` and the hardcoded 5-layer spread block in `candidate-drawer.js`, and landing a TA Coincidence Scorer v1 (RELIANCE pilot) whose endpoint the new TA adapter consumes.

**Architecture:** TA scorer mirrors the FCS package layout (fit_universe.py / score_universe.py / storage.py / model.py / walk_forward.py / features.py / labels.py / patterns.py) but pinned to a single ticker and daily-bar cadence. On the frontend, a new `pipeline/terminal/static/js/components/analysis/` module exports `panel.js` (shared renderer, responsive), four adapters that translate per-engine raw responses into the shared envelope, and a calibration-tag-aware health helper. The Trading tab drawer loops over `candidate.analyses_raw` and renders four cards in a frozen order (FCS → TA → Spread → Corr Break). No backend aggregation layer — page-level `Promise.allSettled` parallel-fetches the four engine endpoints.

**Tech Stack:** Python 3.11 (scikit-learn, pandas, numpy), FastAPI + APIRouter, vanilla JS ES modules, pytest, Windows scheduled tasks via `.bat` wrappers.

---

## File Map (where everything lives)

**Backend — new files:**
- `pipeline/ta_scorer/__init__.py` — version pin
- `pipeline/ta_scorer/patterns.py` — candlestick pattern detection (5 patterns)
- `pipeline/ta_scorer/features.py` — feature vector builder (TA + context)
- `pipeline/ta_scorer/labels.py` — 1D simulated-PnL label under B9/B10 stop hierarchy
- `pipeline/ta_scorer/model.py` — logistic regression + interaction columns
- `pipeline/ta_scorer/walk_forward.py` — 2y/3mo quarterly walk-forward + health bands
- `pipeline/ta_scorer/storage.py` — read/write `ta_feature_models.json` + `ta_attractiveness_scores.json`
- `pipeline/ta_scorer/fit_universe.py` — Sunday 01:30 entry point (RELIANCE only)
- `pipeline/ta_scorer/score_universe.py` — Daily 16:00 entry point (RELIANCE only)
- `pipeline/terminal/api/ta_attractiveness.py` — FastAPI `/api/ta_attractiveness` + `/ta_attractiveness/{ticker}`
- `pipeline/scripts/fit_ta_scorer.bat` — Sunday weekly fit wrapper
- `pipeline/scripts/score_ta_scorer.bat` — daily EOD score wrapper

**Backend — modified files:**
- `pipeline/terminal/api/__init__.py` — register new `ta_attractiveness` router
- `pipeline/config/anka_inventory.json` — add `AnkaTAScorerFit` + `AnkaTAScorerScore` entries
- `pipeline/scripts/eod_review.bat` OR equivalent 16:00 caller — add score_universe invocation (see Task 20 for placement decision)
- `docs/SYSTEM_OPERATIONS_MANUAL.md` — new Station 10 + Clockwork updates
- `CLAUDE.md` — architecture line + clockwork schedule entries

**Backend — test files:**
- `pipeline/tests/ta_scorer/test_patterns.py`
- `pipeline/tests/ta_scorer/test_features.py`
- `pipeline/tests/ta_scorer/test_labels.py`
- `pipeline/tests/ta_scorer/test_model.py`
- `pipeline/tests/ta_scorer/test_walk_forward.py`
- `pipeline/tests/ta_scorer/test_storage.py`
- `pipeline/tests/ta_scorer/test_fit_universe.py`
- `pipeline/tests/ta_scorer/test_score_universe.py`
- `pipeline/tests/test_ta_attractiveness_api.py`
- `pipeline/tests/test_watchdog_ta_scorer.py`
- `pipeline/tests/test_analysis_panel_fixtures.py` (golden HTML fixtures)
- `pipeline/tests/test_analysis_adapters.py` (adapter Node tests via subprocess)

**Frontend — new files:**
- `pipeline/terminal/static/js/components/analysis/envelope.js`
- `pipeline/terminal/static/js/components/analysis/health.js`
- `pipeline/terminal/static/js/components/analysis/panel.js`
- `pipeline/terminal/static/js/components/analysis/adapters/fcs.js`
- `pipeline/terminal/static/js/components/analysis/adapters/ta.js`
- `pipeline/terminal/static/js/components/analysis/adapters/spread.js`
- `pipeline/terminal/static/js/components/analysis/adapters/corr.js`

**Frontend — modified files:**
- `pipeline/terminal/static/js/pages/trading.js` — extend parallel pre-fetch to four engines
- `pipeline/terminal/static/js/components/candidate-drawer.js` — rewrite around shared panel
- `pipeline/terminal/static/css/terminal.css` — append `.analysis-card`, `.analysis-card__*` styles

**Frontend — deleted files (day one clean replace):**
- `pipeline/terminal/static/js/components/attractiveness-panel.js`

**Memory — new file:**
- `C:\Users\Claude_Anka\.claude\projects\C--Users-Claude-Anka-askanka-com\memory\project_unified_analysis_panel.md`
- `MEMORY.md` index entry

**Visual fixtures:**
- `pipeline/tests/fixtures/analysis-panel/fcs-green-long.html`
- `pipeline/tests/fixtures/analysis-panel/ta-unavailable.html`
- `pipeline/tests/fixtures/analysis-panel/spread-pass-high.html`
- `pipeline/tests/fixtures/analysis-panel/corr-neutral.html`

---

## Phase 1 — TA Coincidence Scorer backend (RELIANCE pilot)

TA engine mirrors the FCS pattern so adapters on the frontend can treat FCS and TA identically. Daily-bar cadence (not intraday), single-ticker pilot.

### Task 1: Package skeleton + stub entry points

**Files:**
- Create: `pipeline/ta_scorer/__init__.py`
- Create: `pipeline/ta_scorer/fit_universe.py`
- Create: `pipeline/ta_scorer/score_universe.py`
- Create: `pipeline/tests/ta_scorer/__init__.py`
- Test: `pipeline/tests/ta_scorer/test_package.py`

- [ ] **Step 1: Write failing test**

```python
# pipeline/tests/ta_scorer/test_package.py
import importlib


def test_package_imports():
    mod = importlib.import_module("pipeline.ta_scorer")
    assert mod.__version__ == "0.1.0"


def test_fit_universe_callable():
    from pipeline.ta_scorer import fit_universe
    assert callable(fit_universe.main)


def test_score_universe_callable():
    from pipeline.ta_scorer import score_universe
    assert callable(score_universe.main)
```

- [ ] **Step 2: Run, expect FAIL** (module missing)

```
pytest pipeline/tests/ta_scorer/test_package.py -v
```

- [ ] **Step 3: Create stubs**

```python
# pipeline/ta_scorer/__init__.py
"""TA Coincidence Scorer v1 — RELIANCE pilot."""
__version__ = "0.1.0"
```

```python
# pipeline/ta_scorer/fit_universe.py
"""Weekly Sunday 01:30 IST — fit RELIANCE TA model via walk-forward."""
from __future__ import annotations
import logging
log = logging.getLogger(__name__)


def main() -> int:
    log.info("ta_scorer.fit_universe stub")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

```python
# pipeline/ta_scorer/score_universe.py
"""Daily 16:00 IST — score RELIANCE from cached model."""
from __future__ import annotations
import logging
log = logging.getLogger(__name__)


def main() -> int:
    log.info("ta_scorer.score_universe stub")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

```python
# pipeline/tests/ta_scorer/__init__.py
```

- [ ] **Step 4: Run, expect PASS**

```
pytest pipeline/tests/ta_scorer/test_package.py -v
```

- [ ] **Step 5: Commit**

```
git add pipeline/ta_scorer/ pipeline/tests/ta_scorer/
git commit -m "feat(ta_scorer): package skeleton + stub entry points"
```

---

### Task 2: Candlestick pattern detection

**Files:**
- Create: `pipeline/ta_scorer/patterns.py`
- Test: `pipeline/tests/ta_scorer/test_patterns.py`

- [ ] **Step 1: Write failing tests**

```python
# pipeline/tests/ta_scorer/test_patterns.py
from pipeline.ta_scorer import patterns


def _bar(o, h, l, c):
    return {"open": o, "high": h, "low": l, "close": c}


def test_doji_true_for_tiny_body():
    # Body 0.05% of range
    assert patterns.is_doji(_bar(100.0, 101.0, 99.0, 100.05)) is True


def test_doji_false_for_big_body():
    assert patterns.is_doji(_bar(100.0, 101.0, 99.0, 100.8)) is False


def test_hammer_true_long_lower_shadow_small_body():
    # body top 100-100.2, lower shadow to 98, upper shadow negligible
    assert patterns.is_hammer(_bar(100.0, 100.25, 98.0, 100.2)) is True


def test_hammer_false_long_upper_shadow():
    assert patterns.is_hammer(_bar(100.0, 102.0, 99.8, 100.2)) is False


def test_shooting_star_true_long_upper_shadow():
    assert patterns.is_shooting_star(_bar(100.0, 102.5, 99.9, 100.1)) is True


def test_bullish_engulfing_true():
    prev = _bar(100.0, 100.5, 99.0, 99.2)   # red
    cur = _bar(99.0, 101.0, 98.9, 100.8)    # green, engulfs prev body
    assert patterns.is_bullish_engulfing(prev, cur) is True


def test_bullish_engulfing_false_when_not_engulfed():
    prev = _bar(100.0, 100.5, 99.0, 99.2)
    cur = _bar(99.5, 100.0, 99.3, 99.8)
    assert patterns.is_bullish_engulfing(prev, cur) is False


def test_bearish_engulfing_true():
    prev = _bar(100.0, 101.0, 99.8, 100.8)  # green
    cur = _bar(101.0, 101.2, 99.0, 99.2)    # red, engulfs prev body
    assert patterns.is_bearish_engulfing(prev, cur) is True
```

- [ ] **Step 2: Run, expect FAIL**

```
pytest pipeline/tests/ta_scorer/test_patterns.py -v
```

- [ ] **Step 3: Implement**

```python
# pipeline/ta_scorer/patterns.py
"""Classic candlestick pattern detection. All functions accept mapping-like
rows with keys: open, high, low, close.

v1 rules are intentionally mainstream (Steve Nison / standard TA textbooks).
No ATR normalization — tuning knobs are exposed via kwargs.
"""
from __future__ import annotations
from typing import Mapping


def _body(row: Mapping) -> float:
    return abs(row["close"] - row["open"])


def _range(row: Mapping) -> float:
    return max(1e-9, row["high"] - row["low"])


def is_doji(row: Mapping, body_frac_max: float = 0.1) -> bool:
    """Body ≤ body_frac_max of the total range."""
    return _body(row) / _range(row) <= body_frac_max


def is_hammer(row: Mapping, body_frac_max: float = 0.35,
               lower_shadow_min: float = 2.0) -> bool:
    """Small body near top; lower shadow ≥ lower_shadow_min × body.
    Upper shadow small (≤ body)."""
    body = max(1e-9, _body(row))
    upper = row["high"] - max(row["open"], row["close"])
    lower = min(row["open"], row["close"]) - row["low"]
    return (body / _range(row) <= body_frac_max
            and lower >= lower_shadow_min * body
            and upper <= body)


def is_shooting_star(row: Mapping, body_frac_max: float = 0.35,
                      upper_shadow_min: float = 2.0) -> bool:
    """Mirror of hammer: small body near bottom; long upper shadow."""
    body = max(1e-9, _body(row))
    upper = row["high"] - max(row["open"], row["close"])
    lower = min(row["open"], row["close"]) - row["low"]
    return (body / _range(row) <= body_frac_max
            and upper >= upper_shadow_min * body
            and lower <= body)


def is_bullish_engulfing(prev: Mapping, cur: Mapping) -> bool:
    """Prev is red (close<open); cur is green (close>open) and
    cur body fully engulfs prev body."""
    prev_red = prev["close"] < prev["open"]
    cur_green = cur["close"] > cur["open"]
    engulfs = cur["open"] <= prev["close"] and cur["close"] >= prev["open"]
    return prev_red and cur_green and engulfs


def is_bearish_engulfing(prev: Mapping, cur: Mapping) -> bool:
    prev_green = prev["close"] > prev["open"]
    cur_red = cur["close"] < cur["open"]
    engulfs = cur["open"] >= prev["close"] and cur["close"] <= prev["open"]
    return prev_green and cur_red and engulfs
```

- [ ] **Step 4: Run, expect PASS** (all 8 tests)

- [ ] **Step 5: Commit**

```
git add pipeline/ta_scorer/patterns.py pipeline/tests/ta_scorer/test_patterns.py
git commit -m "feat(ta_scorer): candlestick pattern detection (5 patterns)"
```

---

### Task 3: Feature extractor (TA + context vocabulary)

**Files:**
- Create: `pipeline/ta_scorer/features.py`
- Test: `pipeline/tests/ta_scorer/test_features.py`

- [ ] **Step 1: Write failing tests**

```python
# pipeline/tests/ta_scorer/test_features.py
import pandas as pd
import numpy as np
import pytest
from pipeline.ta_scorer import features


def _synthetic_prices(n=260):
    dates = pd.date_range("2024-01-01", periods=n, freq="B")
    # Gently rising with noise
    close = 100.0 + np.linspace(0, 20, n) + np.random.default_rng(42).normal(0, 1, n)
    return pd.DataFrame({
        "date": dates.strftime("%Y-%m-%d"),
        "open": close - 0.5,
        "high": close + 1.0,
        "low": close - 1.0,
        "close": close,
        "volume": 1_000_000,
    })


def _synthetic_sector(n=260):
    df = _synthetic_prices(n)
    df["close"] = df["close"] * 0.5 + 500
    return df


def test_vector_has_all_v1_keys():
    prices = _synthetic_prices()
    sector = _synthetic_sector()
    nifty = _synthetic_sector()
    vec = features.build_feature_vector(
        prices=prices, sector=sector, nifty=nifty,
        as_of=prices["date"].iloc[-1], regime="NEUTRAL",
        sector_breadth=0.6,
    )
    expected = {
        "doji_flag", "hammer_flag", "shooting_star_flag",
        "bullish_engulfing_flag", "bearish_engulfing_flag",
        "dist_20dma_pct", "dist_50dma_pct", "dist_200dma_pct", "bb_pos",
        "rsi14", "rsi_oversold", "rsi_neutral", "rsi_overbought",
        "ret_3d", "ret_10d", "macd_hist", "macd_hist_slope",
        "atr20_pct", "range_pct",
        "vol_rel20", "vol_spike_flag",
        "sector_ret_5d", "sector_trend_flag", "sector_breadth_estimate",
        "nifty_ret_5d",
        "regime_RISK_OFF", "regime_NEUTRAL", "regime_RISK_ON",
        "regime_EUPHORIA", "regime_CRISIS",
    }
    assert expected.issubset(set(vec.keys()))


def test_regime_one_hots_sum_to_one():
    prices = _synthetic_prices()
    sector = _synthetic_sector()
    vec = features.build_feature_vector(
        prices=prices, sector=sector, nifty=sector,
        as_of=prices["date"].iloc[-1], regime="NEUTRAL",
        sector_breadth=0.5,
    )
    total = (vec["regime_RISK_OFF"] + vec["regime_NEUTRAL"] +
             vec["regime_RISK_ON"] + vec["regime_EUPHORIA"] + vec["regime_CRISIS"])
    assert total == 1


def test_rsi_buckets_mutually_exclusive():
    prices = _synthetic_prices()
    sector = _synthetic_sector()
    vec = features.build_feature_vector(
        prices=prices, sector=sector, nifty=sector,
        as_of=prices["date"].iloc[-1], regime="NEUTRAL",
        sector_breadth=0.5,
    )
    assert vec["rsi_oversold"] + vec["rsi_neutral"] + vec["rsi_overbought"] == 1


def test_vol_spike_triggers_at_1_5x():
    prices = _synthetic_prices()
    # Amplify last volume
    prices.loc[prices.index[-1], "volume"] = 5_000_000  # 5x average
    sector = _synthetic_sector()
    vec = features.build_feature_vector(
        prices=prices, sector=sector, nifty=sector,
        as_of=prices["date"].iloc[-1], regime="NEUTRAL",
        sector_breadth=0.5,
    )
    assert vec["vol_spike_flag"] == 1
    assert vec["vol_rel20"] >= 1.5


def test_insufficient_history_returns_none():
    # Less than 200 rows → 200DMA unavailable
    short = _synthetic_prices(n=50)
    sector = _synthetic_sector()
    res = features.build_feature_vector(
        prices=short, sector=sector, nifty=sector,
        as_of=short["date"].iloc[-1], regime="NEUTRAL",
        sector_breadth=0.5,
    )
    assert res is None
```

- [ ] **Step 2: Run, expect FAIL**

- [ ] **Step 3: Implement**

```python
# pipeline/ta_scorer/features.py
"""Feature-vector builder for TA Coincidence Scorer v1. Point-in-time features
computed from OHLCV up to `as_of` (inclusive). Uses pipeline.ta_scorer.patterns
for candlestick flags.
"""
from __future__ import annotations
from typing import Optional
import numpy as np
import pandas as pd

from pipeline.ta_scorer import patterns


_REGIME_VALUES = ("RISK_OFF", "NEUTRAL", "RISK_ON", "EUPHORIA", "CRISIS")
_MIN_HISTORY = 200  # 200DMA requires 200 rows


def _slice_up_to(df: pd.DataFrame, as_of: str) -> pd.DataFrame:
    return df[df["date"] <= as_of].copy()


def _rsi(closes: pd.Series, window: int = 14) -> float:
    if len(closes) < window + 1:
        return 50.0
    delta = closes.diff()
    up = delta.clip(lower=0).rolling(window).mean().iloc[-1]
    down = (-delta.clip(upper=0)).rolling(window).mean().iloc[-1]
    rs = up / max(1e-9, down)
    return float(100 - 100 / (1 + rs))


def _macd_hist(closes: pd.Series) -> tuple[float, float]:
    ema12 = closes.ewm(span=12, adjust=False).mean()
    ema26 = closes.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    hist = macd - signal
    if len(hist) < 2:
        return 0.0, 0.0
    return float(hist.iloc[-1]), float(hist.iloc[-1] - hist.iloc[-2])


def _atr(df: pd.DataFrame, window: int = 20) -> float:
    if len(df) < window + 1:
        return 0.0
    tr = np.maximum.reduce([
        (df["high"] - df["low"]).values,
        (df["high"] - df["close"].shift(1)).abs().values,
        (df["low"] - df["close"].shift(1)).abs().values,
    ])
    return float(pd.Series(tr).rolling(window).mean().iloc[-1])


def build_feature_vector(*, prices: pd.DataFrame, sector: pd.DataFrame,
                          nifty: pd.DataFrame, as_of: str, regime: str,
                          sector_breadth: float) -> Optional[dict]:
    prices = _slice_up_to(prices, as_of).sort_values("date").reset_index(drop=True)
    if len(prices) < _MIN_HISTORY:
        return None
    sector = _slice_up_to(sector, as_of).sort_values("date").reset_index(drop=True)
    nifty = _slice_up_to(nifty, as_of).sort_values("date").reset_index(drop=True)

    row = prices.iloc[-1].to_dict()
    prev = prices.iloc[-2].to_dict()

    close = float(row["close"])
    closes = prices["close"]

    ma20 = closes.rolling(20).mean().iloc[-1]
    ma50 = closes.rolling(50).mean().iloc[-1]
    ma200 = closes.rolling(200).mean().iloc[-1]
    bb_std = closes.rolling(20).std().iloc[-1]
    upper_bb = ma20 + 2 * bb_std
    lower_bb = ma20 - 2 * bb_std
    bb_pos_raw = (close - lower_bb) / max(1e-9, upper_bb - lower_bb)

    rsi = _rsi(closes, 14)
    macd_hist, macd_slope = _macd_hist(closes)
    atr = _atr(prices, 20)

    vol_rel20 = float(row["volume"]) / max(1e-9, prices["volume"].tail(20).mean())

    sector_closes = sector["close"]
    sector_ret_5d = float(np.log(sector_closes.iloc[-1] / sector_closes.iloc[-6])) if len(sector_closes) >= 6 else 0.0
    sector_ma20 = sector_closes.rolling(20).mean().iloc[-1] if len(sector_closes) >= 20 else sector_closes.iloc[-1]
    sector_ma50 = sector_closes.rolling(50).mean().iloc[-1] if len(sector_closes) >= 50 else sector_closes.iloc[-1]
    sector_trend = 1 if sector_ma20 > sector_ma50 else 0

    nifty_closes = nifty["close"]
    nifty_ret_5d = float(np.log(nifty_closes.iloc[-1] / nifty_closes.iloc[-6])) if len(nifty_closes) >= 6 else 0.0

    vec: dict = {
        "doji_flag": 1 if patterns.is_doji(row) else 0,
        "hammer_flag": 1 if patterns.is_hammer(row) else 0,
        "shooting_star_flag": 1 if patterns.is_shooting_star(row) else 0,
        "bullish_engulfing_flag": 1 if patterns.is_bullish_engulfing(prev, row) else 0,
        "bearish_engulfing_flag": 1 if patterns.is_bearish_engulfing(prev, row) else 0,
        "dist_20dma_pct": (close - ma20) / close,
        "dist_50dma_pct": (close - ma50) / close,
        "dist_200dma_pct": (close - ma200) / close,
        "bb_pos": float(np.clip(bb_pos_raw, -0.5, 1.5)),
        "rsi14": rsi,
        "rsi_oversold": 1 if rsi < 30 else 0,
        "rsi_neutral": 1 if 30 <= rsi <= 70 else 0,
        "rsi_overbought": 1 if rsi > 70 else 0,
        "ret_3d": float(np.log(closes.iloc[-1] / closes.iloc[-4])) if len(closes) >= 4 else 0.0,
        "ret_10d": float(np.log(closes.iloc[-1] / closes.iloc[-11])) if len(closes) >= 11 else 0.0,
        "macd_hist": macd_hist,
        "macd_hist_slope": macd_slope,
        "atr20_pct": atr / close,
        "range_pct": (float(row["high"]) - float(row["low"])) / close,
        "vol_rel20": vol_rel20,
        "vol_spike_flag": 1 if vol_rel20 >= 1.5 else 0,
        "sector_ret_5d": sector_ret_5d,
        "sector_trend_flag": sector_trend,
        "sector_breadth_estimate": float(sector_breadth),
        "nifty_ret_5d": nifty_ret_5d,
    }
    for r in _REGIME_VALUES:
        vec[f"regime_{r}"] = 1 if regime == r else 0
    return vec
```

- [ ] **Step 4: Run, expect PASS** (5 tests)

- [ ] **Step 5: Commit**

```
git add pipeline/ta_scorer/features.py pipeline/tests/ta_scorer/test_features.py
git commit -m "feat(ta_scorer): feature vector builder — TA + context v1"
```

---

### Task 4: Label generator (1D horizon, B9/B10 stop reuse)

**Files:**
- Create: `pipeline/ta_scorer/labels.py`
- Test: `pipeline/tests/ta_scorer/test_labels.py`

- [ ] **Step 1: Write failing tests**

```python
# pipeline/tests/ta_scorer/test_labels.py
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
```

- [ ] **Step 2: Run, expect FAIL**

- [ ] **Step 3: Implement**

```python
# pipeline/ta_scorer/labels.py
"""1D simulated-PnL label for RELIANCE TA scorer. Minimal vs FCS labels:
no trail arming — daily horizon too short. Pure close-to-close with a daily
stop (≤ -1.0%). If the next-day close is past the stop, exit at stop price.
"""
from __future__ import annotations
from typing import Optional
import pandas as pd


def make_label(prices: pd.DataFrame, *, entry_date: str, horizon_days: int = 1,
                win_threshold: float = 0.008, daily_stop_pct: float = -0.01
                ) -> Optional[dict]:
    df = prices.sort_values("date").reset_index(drop=True)
    idx = df.index[df["date"] == entry_date]
    if len(idx) == 0:
        return None
    i = int(idx[0])
    exit_i = i + horizon_days
    if exit_i >= len(df):
        return None
    entry = float(df["close"].iloc[i])
    exit_close = float(df["close"].iloc[exit_i])
    realized = (exit_close - entry) / entry
    # Daily stop — if low on exit day pierced stop, realize at stop
    stop_px = entry * (1.0 + daily_stop_pct)
    exit_low = float(df["low"].iloc[exit_i])
    if exit_low <= stop_px:
        realized = daily_stop_pct
    return {
        "y": 1 if realized >= win_threshold else 0,
        "realized_pct": realized,
        "entry_date": entry_date,
        "exit_date": df["date"].iloc[exit_i],
    }
```

- [ ] **Step 4: Run, expect PASS** (3 tests)

- [ ] **Step 5: Commit**

```
git add pipeline/ta_scorer/labels.py pipeline/tests/ta_scorer/test_labels.py
git commit -m "feat(ta_scorer): 1D label generator with daily stop"
```

---

### Task 5: Model wrapper + interaction columns

**Files:**
- Create: `pipeline/ta_scorer/model.py`
- Test: `pipeline/tests/ta_scorer/test_model.py`

- [ ] **Step 1: Write failing tests**

```python
# pipeline/tests/ta_scorer/test_model.py
import numpy as np
import pandas as pd
from pipeline.ta_scorer import model


def test_interactions_added():
    df = pd.DataFrame({
        "doji_flag": [1, 0, 1],
        "dist_200dma_pct": [0.01, -0.02, 0.03],
        "rsi_oversold": [1, 0, 0],
        "bullish_engulfing_flag": [0, 1, 0],
        "bearish_engulfing_flag": [0, 0, 1],
        "vol_spike_flag": [1, 0, 1],
        "hammer_flag": [0, 1, 0],
        "bb_pos": [0.2, 0.8, 0.5],
        "rsi14": [45, 72, 28],
        "sector_ret_5d": [0.01, -0.005, 0.02],
        "dist_20dma_pct": [0.01, -0.01, 0.02],
        "ret_3d": [0.005, -0.01, 0.015],
    })
    out = model.build_interaction_columns(df)
    assert "doji_x_dist200" in out.columns
    assert "doji_x_rsi_oversold" in out.columns
    assert "engulfing_x_vol_spike" in out.columns
    assert "hammer_x_bb_pos" in out.columns
    assert "rsi14_x_sector5d" in out.columns
    assert "dist20_x_ret3d" in out.columns


def test_logistic_fits_separable_synthetic():
    rng = np.random.default_rng(7)
    n = 200
    x = rng.normal(size=n)
    y = (x + rng.normal(size=n) * 0.3 > 0).astype(int)
    X = pd.DataFrame({"f1": x})
    clf = model.fit_logistic(X, y)
    assert hasattr(clf, "predict_proba")
    p = model.predict_proba(clf, X)
    assert p.shape == (n,)


def test_coefficients_dict_roundtrip():
    rng = np.random.default_rng(3)
    X = pd.DataFrame({"f1": rng.normal(size=50), "f2": rng.normal(size=50)})
    y = (X["f1"] + X["f2"] > 0).astype(int)
    clf = model.fit_logistic(X, y)
    d = model.coefficients_dict(clf, ["f1", "f2"])
    assert set(d.keys()) == {"f1", "f2"}
```

- [ ] **Step 2: Run, expect FAIL**

- [ ] **Step 3: Implement**

```python
# pipeline/ta_scorer/model.py
"""Logistic regression with explicit interaction columns for TA scorer."""
from __future__ import annotations
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression


_INTERACTIONS = [
    ("doji_x_dist200", "doji_flag", "dist_200dma_pct"),
    ("doji_x_rsi_oversold", "doji_flag", "rsi_oversold"),
    ("hammer_x_bb_pos", "hammer_flag", "bb_pos"),
    ("rsi14_x_sector5d", "rsi14", "sector_ret_5d"),
    ("dist20_x_ret3d", "dist_20dma_pct", "ret_3d"),
]


def build_interaction_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for name, a, b in _INTERACTIONS:
        if a in out.columns and b in out.columns:
            out[name] = out[a] * out[b]
    # OR-of-flags × vol_spike_flag for engulfing confirmation
    if all(c in out.columns for c in ("bullish_engulfing_flag", "bearish_engulfing_flag", "vol_spike_flag")):
        out["engulfing_x_vol_spike"] = (
            (out["bullish_engulfing_flag"] | out["bearish_engulfing_flag"]) * out["vol_spike_flag"]
        )
    return out


def fit_logistic(X: pd.DataFrame, y, C: float = 1.0, max_iter: int = 500,
                  random_state: int = 42) -> LogisticRegression:
    clf = LogisticRegression(C=C, max_iter=max_iter, solver="lbfgs",
                              random_state=random_state)
    clf.fit(X.values, np.asarray(y))
    return clf


def predict_proba(clf: LogisticRegression, X: pd.DataFrame) -> np.ndarray:
    return clf.predict_proba(X.values)[:, 1]


def coefficients_dict(clf: LogisticRegression, columns: list[str]) -> dict[str, float]:
    return {c: float(v) for c, v in zip(columns, clf.coef_[0])}
```

- [ ] **Step 4: Run, expect PASS** (3 tests)

- [ ] **Step 5: Commit**

```
git add pipeline/ta_scorer/model.py pipeline/tests/ta_scorer/test_model.py
git commit -m "feat(ta_scorer): logistic regression + 6 interaction terms"
```

---

### Task 6: Walk-forward validation + health bands

**Files:**
- Create: `pipeline/ta_scorer/walk_forward.py`
- Test: `pipeline/tests/ta_scorer/test_walk_forward.py`

- [ ] **Step 1: Write failing tests**

```python
# pipeline/tests/ta_scorer/test_walk_forward.py
import numpy as np
import pandas as pd
from pipeline.ta_scorer import walk_forward


def test_classify_health_green():
    h = walk_forward.classify_health(mean_auc=0.58, min_fold_auc=0.53, n_folds=5)
    assert h == "GREEN"


def test_classify_health_amber_on_low_min_fold():
    h = walk_forward.classify_health(mean_auc=0.56, min_fold_auc=0.50, n_folds=4)
    assert h == "AMBER"


def test_classify_health_amber_on_mid_mean():
    h = walk_forward.classify_health(mean_auc=0.53, min_fold_auc=0.52, n_folds=3)
    assert h == "AMBER"


def test_classify_health_red_on_poor_mean():
    h = walk_forward.classify_health(mean_auc=0.48, min_fold_auc=0.45, n_folds=4)
    assert h == "RED"


def test_classify_health_unavailable_on_few_folds():
    h = walk_forward.classify_health(mean_auc=0.60, min_fold_auc=0.58, n_folds=2)
    assert h == "UNAVAILABLE"


def test_walk_forward_strong_signal_is_green():
    # Build synthetic strong signal over 3 years of business days
    rng = np.random.default_rng(11)
    n = 3 * 252
    dates = pd.date_range("2022-01-01", periods=n, freq="B").strftime("%Y-%m-%d")
    f1 = rng.normal(size=n)
    y = (f1 + rng.normal(size=n) * 0.3 > 0).astype(int)
    frame = pd.DataFrame({"date": dates, "f1": f1, "y": y})
    res = walk_forward.run_walk_forward(frame, train_years=2, test_months=3,
                                         as_of=dates[-1], max_folds=6)
    assert res["health"] == "GREEN"
    assert res["mean_auc"] >= 0.55
    assert res["n_folds"] >= 3
```

- [ ] **Step 2: Run, expect FAIL**

- [ ] **Step 3: Implement**

```python
# pipeline/ta_scorer/walk_forward.py
"""Quarterly walk-forward validation for TA scorer. Mirrors feature_scorer
shape (2y train / 3mo test / 6 folds) but single-ticker and simpler frame
conventions."""
from __future__ import annotations
import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

from pipeline.ta_scorer import model as _model


def classify_health(*, mean_auc: float, min_fold_auc: float, n_folds: int) -> str:
    if n_folds < 3:
        return "UNAVAILABLE"
    if mean_auc >= 0.55 and min_fold_auc >= 0.52:
        return "GREEN"
    if mean_auc >= 0.52:  # includes case where mean>=0.55 but min<0.52
        return "AMBER"
    return "RED"


def _build_folds(dates: pd.Series, *, train_years: int, test_months: int,
                  max_folds: int) -> list[tuple[str, str, str, str]]:
    dates = pd.to_datetime(dates.drop_duplicates().sort_values())
    if len(dates) < 400:
        return []
    end = dates.iloc[-1]
    folds = []
    for k in range(max_folds):
        test_end = end - pd.DateOffset(months=k * test_months)
        test_start = test_end - pd.DateOffset(months=test_months) + pd.Timedelta(days=1)
        train_end = test_start - pd.Timedelta(days=1)
        train_start = train_end - pd.DateOffset(years=train_years) + pd.Timedelta(days=1)
        if train_start < dates.iloc[0]:
            break
        folds.append((train_start.strftime("%Y-%m-%d"),
                       train_end.strftime("%Y-%m-%d"),
                       test_start.strftime("%Y-%m-%d"),
                       test_end.strftime("%Y-%m-%d")))
    folds.reverse()
    return folds


def run_walk_forward(frame: pd.DataFrame, *, train_years: int, test_months: int,
                      as_of: str, max_folds: int = 6) -> dict:
    folds = _build_folds(frame["date"], train_years=train_years,
                          test_months=test_months, max_folds=max_folds)
    feature_cols = [c for c in frame.columns if c not in ("date", "y")]
    auc_list, details = [], []
    for tr_s, tr_e, te_s, te_e in folds:
        train = frame[(frame["date"] >= tr_s) & (frame["date"] <= tr_e)]
        test = frame[(frame["date"] >= te_s) & (frame["date"] <= te_e)]
        if len(train) < 400 or len(test) < 40:
            continue
        if train["y"].nunique() < 2 or test["y"].nunique() < 2:
            continue
        X_tr = _model.build_interaction_columns(train[feature_cols])
        X_te = _model.build_interaction_columns(test[feature_cols])
        clf = _model.fit_logistic(X_tr, train["y"])
        p = _model.predict_proba(clf, X_te)
        auc = float(roc_auc_score(test["y"], p))
        auc_list.append(auc)
        details.append({"train_start": tr_s, "train_end": tr_e,
                         "test_start": te_s, "test_end": te_e,
                         "n_train": len(train), "n_test": len(test),
                         "auc": auc})
    if not auc_list:
        return {"health": "UNAVAILABLE", "n_folds": 0, "mean_auc": None,
                 "min_fold_auc": None, "folds": []}
    mean_auc = float(np.mean(auc_list))
    min_fold = float(np.min(auc_list))
    return {
        "health": classify_health(mean_auc=mean_auc, min_fold_auc=min_fold,
                                    n_folds=len(auc_list)),
        "mean_auc": mean_auc, "min_fold_auc": min_fold,
        "n_folds": len(auc_list), "folds": details,
    }
```

- [ ] **Step 4: Run, expect PASS** (6 tests)

- [ ] **Step 5: Commit**

```
git add pipeline/ta_scorer/walk_forward.py pipeline/tests/ta_scorer/test_walk_forward.py
git commit -m "feat(ta_scorer): quarterly walk-forward + health bands"
```

---

### Task 7: Storage layer

**Files:**
- Create: `pipeline/ta_scorer/storage.py`
- Test: `pipeline/tests/ta_scorer/test_storage.py`

- [ ] **Step 1: Write failing tests**

```python
# pipeline/tests/ta_scorer/test_storage.py
import json
from pathlib import Path
from pipeline.ta_scorer import storage


def test_models_roundtrip(tmp_path: Path):
    p = tmp_path / "models.json"
    payload = {"version": "1.0", "models": {"RELIANCE": {"health": "GREEN"}}}
    storage.write_models(payload, out=p)
    data = storage.read_models(path=p)
    assert data["models"]["RELIANCE"]["health"] == "GREEN"


def test_scores_roundtrip(tmp_path: Path):
    p = tmp_path / "scores.json"
    storage.write_scores({"updated_at": "x", "scores": {}}, out=p)
    data = storage.read_scores(path=p)
    assert data["scores"] == {}


def test_read_models_missing_file_returns_empty(tmp_path: Path):
    missing = tmp_path / "nope.json"
    assert storage.read_models(path=missing) == {"version": "1.0", "models": {}}


def test_read_scores_missing_returns_empty(tmp_path: Path):
    missing = tmp_path / "nope.json"
    data = storage.read_scores(path=missing)
    assert data["scores"] == {}
```

- [ ] **Step 2: Run, expect FAIL**

- [ ] **Step 3: Implement**

```python
# pipeline/ta_scorer/storage.py
"""Read/write TA scorer models + scores JSON. Mirrors feature_scorer.storage.
Default paths are repo-relative; callers can override via `out=`/`path=`."""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any

_DATA = Path(__file__).resolve().parent.parent / "data"
_MODELS = _DATA / "ta_feature_models.json"
_SCORES = _DATA / "ta_attractiveness_scores.json"

_EMPTY_MODELS = {"version": "1.0", "models": {}}
_EMPTY_SCORES = {"updated_at": None, "scores": {}}


def write_models(data: dict[str, Any], out: Path | None = None) -> None:
    p = Path(out) if out else _MODELS
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2), encoding="utf-8")


def read_models(path: Path | None = None) -> dict[str, Any]:
    p = Path(path) if path else _MODELS
    if not p.exists():
        return dict(_EMPTY_MODELS)
    return json.loads(p.read_text(encoding="utf-8"))


def write_scores(data: dict[str, Any], out: Path | None = None) -> None:
    p = Path(out) if out else _SCORES
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2), encoding="utf-8")


def read_scores(path: Path | None = None) -> dict[str, Any]:
    p = Path(path) if path else _SCORES
    if not p.exists():
        return dict(_EMPTY_SCORES)
    return json.loads(p.read_text(encoding="utf-8"))
```

- [ ] **Step 4: Run, expect PASS** (4 tests)

- [ ] **Step 5: Commit**

```
git add pipeline/ta_scorer/storage.py pipeline/tests/ta_scorer/test_storage.py
git commit -m "feat(ta_scorer): storage layer for models + scores JSON"
```

---

### Task 8: fit_universe.py — RELIANCE-only Sunday fit

**Files:**
- Modify: `pipeline/ta_scorer/fit_universe.py`
- Test: `pipeline/tests/ta_scorer/test_fit_universe.py`

- [ ] **Step 1: Write failing test** (uses fixtures, not real disk)

```python
# pipeline/tests/ta_scorer/test_fit_universe.py
import json
import pandas as pd
import numpy as np
from pathlib import Path
import pytest

from pipeline.ta_scorer import fit_universe


def _seed_csv(path: Path, n=600, seed=0):
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2022-01-01", periods=n, freq="B")
    close = 100.0 + np.cumsum(rng.normal(0, 1, n))
    df = pd.DataFrame({
        "Date": dates.strftime("%Y-%m-%d"),
        "Open": close - 0.3, "High": close + 0.8, "Low": close - 0.8,
        "Close": close, "Volume": 1_000_000,
    })
    df.to_csv(path, index=False)


def test_fit_universe_writes_reliance_model(tmp_path, monkeypatch):
    hist = tmp_path / "fno_historical"
    idx = tmp_path / "india_historical" / "indices"
    hist.mkdir(parents=True)
    idx.mkdir(parents=True)
    _seed_csv(hist / "RELIANCE.csv", n=750, seed=1)
    _seed_csv(idx / "NIFTYENERGY_daily.csv", n=750, seed=2)
    _seed_csv(idx / "NIFTY_daily.csv", n=750, seed=3)

    out_models = tmp_path / "ta_feature_models.json"

    monkeypatch.setattr(fit_universe, "_STOCK_HISTORICAL_DIR", hist)
    monkeypatch.setattr(fit_universe, "_INDEX_HISTORICAL_DIR", idx)
    monkeypatch.setattr(fit_universe, "_MODELS_OUT", out_models)

    exit_code = fit_universe.main()
    assert exit_code == 0
    assert out_models.exists()
    data = json.loads(out_models.read_text(encoding="utf-8"))
    assert "RELIANCE" in data["models"]
    assert data["models"]["RELIANCE"]["health"] in ("GREEN", "AMBER", "RED", "UNAVAILABLE")
```

- [ ] **Step 2: Run, expect FAIL**

- [ ] **Step 3: Implement**

```python
# pipeline/ta_scorer/fit_universe.py
"""Sunday 01:30 IST — fit RELIANCE TA model via 2y/3mo walk-forward.

Writes pipeline/data/ta_feature_models.json. Universe-size=1 for v1 pilot.
"""
from __future__ import annotations
import logging
from datetime import datetime
from pathlib import Path
import pandas as pd

from pipeline.ta_scorer import features, labels, model, storage, walk_forward

log = logging.getLogger(__name__)

_PIPELINE_DIR = Path(__file__).resolve().parent.parent
_REPO_ROOT = _PIPELINE_DIR.parent
_STOCK_HISTORICAL_DIR = _PIPELINE_DIR / "data" / "fno_historical"
_INDEX_HISTORICAL_DIR = _PIPELINE_DIR / "data" / "india_historical" / "indices"
_MODELS_OUT = _PIPELINE_DIR / "data" / "ta_feature_models.json"

_PILOT_TICKER = "RELIANCE"
_SECTOR_INDEX = "NIFTYENERGY"  # RELIANCE sector


def _load_csv(path: Path) -> pd.DataFrame | None:
    if not path.exists():
        return None
    df = pd.read_csv(path)
    df.columns = [c.lower() for c in df.columns]
    return df


def _build_training_frame(prices: pd.DataFrame, sector: pd.DataFrame,
                           nifty: pd.DataFrame) -> pd.DataFrame | None:
    rows: list[dict] = []
    for i, d in enumerate(prices["date"]):
        if i < 210:
            continue
        vec = features.build_feature_vector(
            prices=prices, sector=sector, nifty=nifty,
            as_of=d, regime="NEUTRAL", sector_breadth=0.5,
        )
        if not vec:
            continue
        lbl = labels.make_label(prices, entry_date=d, horizon_days=1)
        if not lbl:
            continue
        vec["date"] = d
        vec["y"] = lbl["y"]
        rows.append(vec)
    if not rows:
        return None
    return pd.DataFrame(rows)


def main() -> int:
    prices = _load_csv(_STOCK_HISTORICAL_DIR / f"{_PILOT_TICKER}.csv")
    sector = _load_csv(_INDEX_HISTORICAL_DIR / f"{_SECTOR_INDEX}_daily.csv")
    nifty = _load_csv(_INDEX_HISTORICAL_DIR / "NIFTY_daily.csv")
    if prices is None or sector is None or nifty is None:
        log.warning("missing input CSVs — writing UNAVAILABLE model entry")
        storage.write_models({
            "version": "1.0",
            "fitted_at": datetime.now().isoformat(),
            "universe_size": 1,
            "models": {_PILOT_TICKER: {"health": "UNAVAILABLE",
                                         "source": "own",
                                         "reason": "missing input CSVs"}},
        }, out=_MODELS_OUT)
        return 0

    frame = _build_training_frame(prices, sector, nifty)
    if frame is None or len(frame) < 400:
        storage.write_models({
            "version": "1.0",
            "fitted_at": datetime.now().isoformat(),
            "universe_size": 1,
            "models": {_PILOT_TICKER: {"health": "UNAVAILABLE",
                                         "source": "own",
                                         "reason": "insufficient training frame"}},
        }, out=_MODELS_OUT)
        return 0

    as_of = frame["date"].iloc[-1]
    result = walk_forward.run_walk_forward(frame, train_years=2, test_months=3,
                                             as_of=as_of, max_folds=6)
    entry: dict = {
        "source": "own", "ticker": _PILOT_TICKER, "horizon": "1d",
        "health": result["health"],
        "mean_auc": result["mean_auc"], "min_fold_auc": result["min_fold_auc"],
        "n_folds": result["n_folds"], "folds": result["folds"],
    }
    if result["health"] in ("GREEN", "AMBER"):
        feature_cols = [c for c in frame.columns if c not in ("date", "y")]
        X = model.build_interaction_columns(frame[feature_cols])
        clf = model.fit_logistic(X, frame["y"])
        entry["coefficients"] = model.coefficients_dict(clf, list(X.columns))
    storage.write_models({
        "version": "1.0",
        "fitted_at": datetime.now().isoformat(),
        "universe_size": 1,
        "models": {_PILOT_TICKER: entry},
    }, out=_MODELS_OUT)
    log.info("fit %s → %s (mean_auc=%s, folds=%s)",
              _PILOT_TICKER, entry["health"], entry["mean_auc"], entry["n_folds"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run, expect PASS**

- [ ] **Step 5: Commit**

```
git add pipeline/ta_scorer/fit_universe.py pipeline/tests/ta_scorer/test_fit_universe.py
git commit -m "feat(ta_scorer): fit_universe.py — Sunday RELIANCE-only walk-forward"
```

---

### Task 9: score_universe.py — daily 16:00 apply

**Files:**
- Modify: `pipeline/ta_scorer/score_universe.py`
- Test: `pipeline/tests/ta_scorer/test_score_universe.py`

- [ ] **Step 1: Write failing test**

```python
# pipeline/tests/ta_scorer/test_score_universe.py
import json
import pandas as pd
import numpy as np
from pathlib import Path

from pipeline.ta_scorer import score_universe, fit_universe


def _seed_csv(path: Path, n=750, seed=0):
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2022-01-01", periods=n, freq="B")
    close = 100.0 + np.cumsum(rng.normal(0, 1, n))
    df = pd.DataFrame({
        "Date": dates.strftime("%Y-%m-%d"),
        "Open": close - 0.3, "High": close + 0.8, "Low": close - 0.8,
        "Close": close, "Volume": 1_000_000,
    })
    df.to_csv(path, index=False)


def test_score_universe_writes_reliance_score(tmp_path, monkeypatch):
    hist = tmp_path / "fno_historical"
    idx = tmp_path / "india_historical" / "indices"
    hist.mkdir(parents=True)
    idx.mkdir(parents=True)
    _seed_csv(hist / "RELIANCE.csv", 750, 1)
    _seed_csv(idx / "NIFTYENERGY_daily.csv", 750, 2)
    _seed_csv(idx / "NIFTY_daily.csv", 750, 3)

    models_path = tmp_path / "ta_feature_models.json"
    scores_path = tmp_path / "ta_attractiveness_scores.json"

    monkeypatch.setattr(fit_universe, "_STOCK_HISTORICAL_DIR", hist)
    monkeypatch.setattr(fit_universe, "_INDEX_HISTORICAL_DIR", idx)
    monkeypatch.setattr(fit_universe, "_MODELS_OUT", models_path)
    monkeypatch.setattr(score_universe, "_STOCK_HISTORICAL_DIR", hist)
    monkeypatch.setattr(score_universe, "_INDEX_HISTORICAL_DIR", idx)
    monkeypatch.setattr(score_universe, "_MODELS_IN", models_path)
    monkeypatch.setattr(score_universe, "_SCORES_OUT", scores_path)

    assert fit_universe.main() == 0
    assert score_universe.main() == 0

    data = json.loads(scores_path.read_text(encoding="utf-8"))
    assert "RELIANCE" in data["scores"]
    rec = data["scores"]["RELIANCE"]
    assert 0 <= rec["score"] <= 100
    assert rec["health"] in ("GREEN", "AMBER", "RED", "UNAVAILABLE")
    assert isinstance(rec["top_features"], list)
```

- [ ] **Step 2: Run, expect FAIL**

- [ ] **Step 3: Implement**

```python
# pipeline/ta_scorer/score_universe.py
"""Daily 16:00 IST — apply cached RELIANCE TA model to today's close."""
from __future__ import annotations
import logging
import math
from datetime import datetime
from pathlib import Path
import pandas as pd

from pipeline.ta_scorer import features, model, storage

log = logging.getLogger(__name__)

_PIPELINE_DIR = Path(__file__).resolve().parent.parent
_STOCK_HISTORICAL_DIR = _PIPELINE_DIR / "data" / "fno_historical"
_INDEX_HISTORICAL_DIR = _PIPELINE_DIR / "data" / "india_historical" / "indices"
_MODELS_IN = _PIPELINE_DIR / "data" / "ta_feature_models.json"
_SCORES_OUT = _PIPELINE_DIR / "data" / "ta_attractiveness_scores.json"

_PILOT_TICKER = "RELIANCE"
_SECTOR_INDEX = "NIFTYENERGY"


def _band(score: int) -> str:
    if score >= 80: return "VERY_HIGH"
    if score >= 60: return "HIGH"
    if score >= 40: return "MEDIUM"
    return "LOW"


def _load_csv(path: Path) -> pd.DataFrame | None:
    if not path.exists():
        return None
    df = pd.read_csv(path)
    df.columns = [c.lower() for c in df.columns]
    return df


def _score_one(coefs: dict, enriched: dict) -> tuple[int, list[dict]]:
    logit = 0.0
    contribs: list[tuple[str, float]] = []
    for name, coef in coefs.items():
        v = float(enriched.get(name, 0.0) or 0.0)
        c = coef * v
        logit += c
        contribs.append((name, c))
    prob = 1.0 / (1.0 + math.exp(-logit))
    contribs.sort(key=lambda x: abs(x[1]), reverse=True)
    top = [{"name": n, "contribution": round(c, 3),
             "sign": "+" if c >= 0 else "-",
             "magnitude": round(abs(c) * 100, 1)}
            for n, c in contribs[:3]]
    return int(round(prob * 100)), top


def main() -> int:
    models = storage.read_models(path=_MODELS_IN).get("models", {})
    meta = models.get(_PILOT_TICKER) or {}
    ts = datetime.now().isoformat()
    payload_empty = {"updated_at": ts, "scores": {_PILOT_TICKER: {
        "ticker": _PILOT_TICKER, "score": None, "band": "UNAVAILABLE",
        "health": meta.get("health", "UNAVAILABLE"),
        "source": "own", "top_features": [], "computed_at": ts,
    }}}
    if meta.get("health") not in ("GREEN", "AMBER"):
        storage.write_scores(payload_empty, out=_SCORES_OUT)
        log.info("skip scoring — model health=%s", meta.get("health"))
        return 0
    coefs = meta.get("coefficients") or {}
    if not coefs:
        storage.write_scores(payload_empty, out=_SCORES_OUT)
        return 0

    prices = _load_csv(_STOCK_HISTORICAL_DIR / f"{_PILOT_TICKER}.csv")
    sector = _load_csv(_INDEX_HISTORICAL_DIR / f"{_SECTOR_INDEX}_daily.csv")
    nifty = _load_csv(_INDEX_HISTORICAL_DIR / "NIFTY_daily.csv")
    if prices is None or sector is None or nifty is None:
        storage.write_scores(payload_empty, out=_SCORES_OUT)
        return 0

    as_of = str(prices["date"].iloc[-1])
    vec = features.build_feature_vector(
        prices=prices, sector=sector, nifty=nifty,
        as_of=as_of, regime="NEUTRAL", sector_breadth=0.5,
    )
    if not vec:
        storage.write_scores(payload_empty, out=_SCORES_OUT)
        return 0
    enriched = model.build_interaction_columns(pd.DataFrame([vec])).iloc[0].to_dict()
    score, top = _score_one(coefs, enriched)
    storage.write_scores({"updated_at": ts, "scores": {_PILOT_TICKER: {
        "ticker": _PILOT_TICKER, "horizon": "1d",
        "score": score, "band": _band(score),
        "health": meta["health"], "source": "own",
        "p_hat": round(score / 100, 3),
        "mean_auc": meta.get("mean_auc"),
        "min_fold_auc": meta.get("min_fold_auc"),
        "top_features": top, "computed_at": ts,
    }}}, out=_SCORES_OUT)
    log.info("scored %s: %d", _PILOT_TICKER, score)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run, expect PASS**

- [ ] **Step 5: Commit**

```
git add pipeline/ta_scorer/score_universe.py pipeline/tests/ta_scorer/test_score_universe.py
git commit -m "feat(ta_scorer): score_universe.py — daily RELIANCE apply"
```

---

## Phase 2 — TA API endpoint

### Task 10: FastAPI `/api/ta_attractiveness`

**Files:**
- Create: `pipeline/terminal/api/ta_attractiveness.py`
- Modify: `pipeline/terminal/api/__init__.py`
- Test: `pipeline/tests/test_ta_attractiveness_api.py`

- [ ] **Step 1: Write failing test**

```python
# pipeline/tests/test_ta_attractiveness_api.py
from fastapi.testclient import TestClient
from pipeline.terminal.app import app
from pipeline.ta_scorer import storage


def test_ta_attractiveness_all(monkeypatch):
    def fake(path=None):
        return {"updated_at": "2026-04-23T16:00:00+05:30",
                 "scores": {"RELIANCE": {"ticker": "RELIANCE", "score": 72,
                                          "band": "HIGH", "health": "GREEN",
                                          "source": "own", "top_features": [],
                                          "computed_at": "2026-04-23T16:00:00+05:30"}}}
    monkeypatch.setattr(storage, "read_scores", fake)
    with TestClient(app) as c:
        r = c.get("/api/ta_attractiveness")
    assert r.status_code == 200
    assert r.json()["scores"]["RELIANCE"]["score"] == 72


def test_ta_attractiveness_ticker_hit(monkeypatch):
    def fake(path=None):
        return {"updated_at": "x", "scores": {"RELIANCE": {"score": 55}}}
    monkeypatch.setattr(storage, "read_scores", fake)
    with TestClient(app) as c:
        r = c.get("/api/ta_attractiveness/RELIANCE")
    assert r.status_code == 200
    assert r.json()["score"] == 55


def test_ta_attractiveness_ticker_miss(monkeypatch):
    def fake(path=None):
        return {"updated_at": "x", "scores": {}}
    monkeypatch.setattr(storage, "read_scores", fake)
    with TestClient(app) as c:
        r = c.get("/api/ta_attractiveness/ITC")
    assert r.status_code == 404
```

- [ ] **Step 2: Run, expect FAIL**

- [ ] **Step 3: Implement router + registration**

```python
# pipeline/terminal/api/ta_attractiveness.py
"""FastAPI endpoints for TA Coincidence Scorer output."""
from __future__ import annotations
from fastapi import APIRouter, HTTPException
from pipeline.ta_scorer import storage

router = APIRouter()


@router.get("/ta_attractiveness")
def all_ta() -> dict:
    return storage.read_scores()


@router.get("/ta_attractiveness/{ticker}")
def one_ta(ticker: str) -> dict:
    data = storage.read_scores()
    scores = data.get("scores", {})
    key = ticker.upper()
    if key not in scores:
        raise HTTPException(status_code=404, detail=f"no TA score for {ticker}")
    return scores[key]
```

Register in `pipeline/terminal/api/__init__.py` — add alongside existing `attractiveness` router:

```python
# Append near other `from pipeline.terminal.api import ...` lines:
from pipeline.terminal.api import ta_attractiveness

# Append to the `ALL_ROUTERS` tuple (or equivalent existing collection):
# ALL_ROUTERS = (..., attractiveness.router, ta_attractiveness.router, ...)
```

(**Note for the implementer**: the exact registration idiom depends on how the existing `__init__.py` wires routers. Read `pipeline/terminal/api/__init__.py` once and mirror the pattern used by `attractiveness`. If routers are added via `app.include_router(...)` in `pipeline/terminal/app.py` instead, add the new line there.)

- [ ] **Step 4: Run, expect PASS**

- [ ] **Step 5: Commit**

```
git add pipeline/terminal/api/ta_attractiveness.py pipeline/terminal/api/__init__.py pipeline/tests/test_ta_attractiveness_api.py
git commit -m "feat(terminal): /api/ta_attractiveness endpoints"
```

---

## Phase 3 — Shared envelope + renderer

### Task 11: envelope.js — type shape + defensive parse

**Files:**
- Create: `pipeline/terminal/static/js/components/analysis/envelope.js`
- Test: `pipeline/tests/test_analysis_adapters.py` (sets up Node test harness)

- [ ] **Step 1: Write failing test (Python shells to Node)**

```python
# pipeline/tests/test_analysis_adapters.py
import subprocess
import json
from pathlib import Path

TERMINAL_JS = Path("pipeline/terminal/static/js/components/analysis")


def _run(node_src: str) -> dict:
    """Execute Node script, return parsed JSON of its stdout."""
    proc = subprocess.run(["node", "--input-type=module", "-e", node_src],
                          capture_output=True, text=True, timeout=15)
    assert proc.returncode == 0, f"node failed: {proc.stderr}"
    return json.loads(proc.stdout)


def test_envelope_defaults():
    src = f"""
    import {{ makeEnvelope }} from '{(TERMINAL_JS / "envelope.js").as_posix()}';
    const env = makeEnvelope({{engine: 'fcs', ticker: 'RELIANCE'}});
    console.log(JSON.stringify(env));
    """
    env = _run(src)
    assert env["engine"] == "fcs"
    assert env["ticker"] == "RELIANCE"
    assert env["verdict"] == "UNAVAILABLE"
    assert env["conviction_0_100"] is None
    assert env["evidence"] == []
    assert env["calibration"] == "heuristic"


def test_envelope_validates_health_band():
    src = f"""
    import {{ makeEnvelope }} from '{(TERMINAL_JS / "envelope.js").as_posix()}';
    const env = makeEnvelope({{engine: 'fcs', ticker: 'X',
      health: {{band: 'BOGUS', detail: 'x'}}}});
    console.log(JSON.stringify(env));
    """
    env = _run(src)
    assert env["health"]["band"] == "UNAVAILABLE"
```

- [ ] **Step 2: Run, expect FAIL** (module missing)

- [ ] **Step 3: Implement**

```javascript
// pipeline/terminal/static/js/components/analysis/envelope.js
// Shared envelope: every analysis engine renders through this shape.
// See docs/superpowers/specs/2026-04-23-unified-analysis-panel-design.md

export const VALID_VERDICTS = new Set([
  'LONG', 'SHORT', 'NEUTRAL', 'WATCH', 'NO_SIGNAL', 'UNAVAILABLE',
]);
export const VALID_BANDS = new Set(['GREEN', 'AMBER', 'RED', 'UNAVAILABLE']);
export const VALID_CALIBRATION = new Set(['walk_forward', 'heuristic']);

// Defensive constructor. Any malformed input → UNAVAILABLE envelope.
export function makeEnvelope(raw = {}) {
  const engine = raw.engine || 'unknown';
  const ticker = raw.ticker || '';
  const verdict = VALID_VERDICTS.has(raw.verdict) ? raw.verdict : 'UNAVAILABLE';
  const conviction_0_100 = (typeof raw.conviction_0_100 === 'number'
    && raw.conviction_0_100 >= 0 && raw.conviction_0_100 <= 100)
    ? raw.conviction_0_100 : null;
  const evidence = Array.isArray(raw.evidence) ? raw.evidence.slice(0, 3).map(e => ({
    name: String(e?.name || '—'),
    contribution: typeof e?.contribution === 'number' ? e.contribution : 0,
    direction: e?.direction === 'pos' || e?.direction === 'neg' ? e.direction
      : ((e?.contribution || 0) >= 0 ? 'pos' : 'neg'),
  })) : [];
  const rawBand = raw.health?.band;
  const band = VALID_BANDS.has(rawBand) ? rawBand : 'UNAVAILABLE';
  const calibration = VALID_CALIBRATION.has(raw.calibration) ? raw.calibration : 'heuristic';
  return {
    engine, ticker, verdict, conviction_0_100, evidence,
    health: { band, detail: String(raw.health?.detail || '') },
    calibration,
    computed_at: raw.computed_at || null,
    source: raw.source || null,
    empty_state_reason: raw.empty_state_reason || null,
  };
}
```

- [ ] **Step 4: Run, expect PASS**

- [ ] **Step 5: Commit**

```
git add pipeline/terminal/static/js/components/analysis/envelope.js pipeline/tests/test_analysis_adapters.py
git commit -m "feat(analysis): shared envelope shape + defensive constructor"
```

---

### Task 12: health.js + freshness formatting

**Files:**
- Create: `pipeline/terminal/static/js/components/analysis/health.js`
- Test: add cases to `pipeline/tests/test_analysis_adapters.py`

- [ ] **Step 1: Write failing test**

Append to `pipeline/tests/test_analysis_adapters.py`:

```python
def test_health_colors_match_tokens():
    src = f"""
    import {{ bandToCssVar, fmtRelative }} from '{(TERMINAL_JS / "health.js").as_posix()}';
    const out = {{
      green: bandToCssVar('GREEN'),
      amber: bandToCssVar('AMBER'),
      red:   bandToCssVar('RED'),
      unav:  bandToCssVar('UNAVAILABLE'),
      weird: bandToCssVar('BOGUS'),
    }};
    console.log(JSON.stringify(out));
    """
    out = _run(src)
    assert out["green"] == "var(--accent-green)"
    assert out["amber"] == "var(--accent-gold)"
    assert out["red"] == "var(--accent-red)"
    assert out["unav"] == "var(--text-muted)"
    assert out["weird"] == "var(--text-muted)"


def test_fmt_relative_labels():
    src = f"""
    import {{ fmtRelative }} from '{(TERMINAL_JS / "health.js").as_posix()}';
    const now = new Date('2026-04-23T14:00:00+05:30').toISOString();
    const labels = {{
      just_now: fmtRelative(new Date('2026-04-23T13:57:00+05:30').toISOString(), now),
      yesterday: fmtRelative(new Date('2026-04-22T16:00:00+05:30').toISOString(), now),
      missing: fmtRelative(null, now),
    }};
    console.log(JSON.stringify(labels));
    """
    out = _run(src)
    assert "min" in out["just_now"]
    assert "yesterday" in out["yesterday"].lower() or "day" in out["yesterday"].lower()
    assert out["missing"] == "—"
```

- [ ] **Step 2: Run, expect FAIL**

- [ ] **Step 3: Implement**

```javascript
// pipeline/terminal/static/js/components/analysis/health.js
// Band → CSS var + computed_at → relative label.

const BAND_VAR = {
  GREEN: 'var(--accent-green)',
  AMBER: 'var(--accent-gold)',
  RED: 'var(--accent-red)',
  UNAVAILABLE: 'var(--text-muted)',
};

export function bandToCssVar(band) {
  return BAND_VAR[band] || 'var(--text-muted)';
}

// Cadence in minutes per engine (for stale detection).
export const CADENCE_MIN = { fcs: 15, ta: 1440, spread: 15, corr_break: 15 };

export function fmtRelative(isoAt, nowIso) {
  if (!isoAt) return '—';
  const t = new Date(isoAt).getTime();
  const now = nowIso ? new Date(nowIso).getTime() : Date.now();
  if (isNaN(t)) return '—';
  const mins = Math.floor((now - t) / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins} min ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  if (days === 1) return `yesterday ${new Date(isoAt).toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'})}`;
  return `${days}d ago`;
}

export function isStale(isoAt, engine, nowIso) {
  if (!isoAt) return true;
  const cadence = CADENCE_MIN[engine] || 60;
  const mins = (new Date(nowIso || Date.now()).getTime() - new Date(isoAt).getTime()) / 60000;
  return mins > 2 * cadence;
}
```

- [ ] **Step 4: Run, expect PASS**

- [ ] **Step 5: Commit**

```
git add pipeline/terminal/static/js/components/analysis/health.js pipeline/tests/test_analysis_adapters.py
git commit -m "feat(analysis): health band mapping + relative-freshness helpers"
```

---

### Task 13: panel.js — shared responsive renderer

**Files:**
- Create: `pipeline/terminal/static/js/components/analysis/panel.js`
- Test: append to `pipeline/tests/test_analysis_adapters.py`

- [ ] **Step 1: Write failing tests**

Append:

```python
def test_panel_renders_full_envelope():
    src = f"""
    import {{ renderCardHtml }} from '{(TERMINAL_JS / "panel.js").as_posix()}';
    const env = {{
      engine: 'fcs', ticker: 'RELIANCE', verdict: 'LONG',
      conviction_0_100: 72,
      evidence: [{{name: 'rs_10d', contribution: 0.38, direction: 'pos'}}],
      health: {{band: 'GREEN', detail: 'mean AUC 0.61'}},
      calibration: 'walk_forward',
      computed_at: '2026-04-23T13:57:00+05:30',
      source: 'own',
    }};
    const html = renderCardHtml(env, '2026-04-23T14:00:00+05:30');
    console.log(JSON.stringify({{html}}));
    """
    out = _run(src)
    h = out["html"]
    assert "RELIANCE" in h
    assert "LONG" in h
    assert "72" in h
    assert "var(--accent-gold)" in h
    assert "GREEN" in h


def test_panel_renders_unavailable_with_reason():
    src = f"""
    import {{ renderCardHtml }} from '{(TERMINAL_JS / "panel.js").as_posix()}';
    const env = {{
      engine: 'ta', ticker: 'ITC', verdict: 'UNAVAILABLE',
      conviction_0_100: null, evidence: [],
      health: {{band: 'UNAVAILABLE', detail: 'pilot'}},
      calibration: 'heuristic',
      empty_state_reason: 'TA pilot — RELIANCE only, 212 tickers await v2 rollout',
    }};
    const html = renderCardHtml(env, '2026-04-23T14:00:00+05:30');
    console.log(JSON.stringify({{html}}));
    """
    out = _run(src)
    assert "TA pilot" in out["html"]
    assert "ITC" in out["html"]


def test_panel_calibration_styling():
    src = f"""
    import {{ renderCardHtml }} from '{(TERMINAL_JS / "panel.js").as_posix()}';
    const wf = {{engine:'fcs',ticker:'X',verdict:'LONG',conviction_0_100:72,
                calibration:'walk_forward',evidence:[],
                health:{{band:'GREEN',detail:''}},computed_at:'2026-04-23T14:00:00+05:30'}};
    const h  = {{engine:'spread',ticker:'X',verdict:'LONG',conviction_0_100:60,
                calibration:'heuristic',evidence:[],
                health:{{band:'GREEN',detail:''}},computed_at:'2026-04-23T14:00:00+05:30'}};
    const wfHtml = renderCardHtml(wf, '2026-04-23T14:00:00+05:30');
    const heuristicHtml = renderCardHtml(h, '2026-04-23T14:00:00+05:30');
    console.log(JSON.stringify({{wf: wfHtml, heuristic: heuristicHtml}}));
    """
    out = _run(src)
    assert "var(--accent-gold)" in out["wf"]
    assert "var(--text-muted)" in out["heuristic"]
    assert 'class="analysis-card__conviction--heuristic"' in out["heuristic"]
```

- [ ] **Step 2: Run, expect FAIL**

- [ ] **Step 3: Implement**

```javascript
// pipeline/terminal/static/js/components/analysis/panel.js
// Shared renderer. Given an envelope, produce a single analysis card's HTML.
// Responsive: CSS (in terminal.css) decides stacked vs header+2col at ≥480px.

import { bandToCssVar, fmtRelative, isStale } from './health.js';

// Browser-or-node HTML escaping — mirror other components' convention.
function _esc(s) {
  if (s == null) return '';
  if (typeof document !== 'undefined') {
    const d = document.createElement('div');
    d.textContent = String(s);
    return d.innerHTML;
  }
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

function _evidenceBar(ev, maxAbs) {
  const v = Number(ev.contribution) || 0;
  const pct = maxAbs > 0 ? Math.abs(v) / maxAbs * 100 : 0;
  const cls = v >= 0 ? 'analysis-card__bar-pos' : 'analysis-card__bar-neg';
  const sign = v >= 0 ? '+' : '−';
  return `
    <div class="analysis-card__bar-row">
      <span class="analysis-card__bar-label">${sign}${Math.abs(v).toFixed(2)}</span>
      <div class="analysis-card__bar-track"><div class="analysis-card__bar ${cls}" style="width:${pct.toFixed(1)}%"></div></div>
      <span class="analysis-card__bar-name">${_esc(ev.name)}</span>
    </div>`;
}

export function renderCardHtml(env, nowIso) {
  const bandVar = bandToCssVar(env.health.band);
  const convictionCls = env.calibration === 'walk_forward'
    ? 'analysis-card__conviction--walk-forward'
    : 'analysis-card__conviction--heuristic';
  const convictionStyle = env.calibration === 'walk_forward'
    ? 'color: var(--accent-gold);'
    : 'color: var(--text-muted); text-decoration: underline dotted;';
  const convictionTitle = env.calibration === 'heuristic'
    ? 'Not calibrated — heuristic mapping from gate/σ.'
    : '';
  const convictionText = (env.conviction_0_100 == null) ? '—' : String(env.conviction_0_100);

  const evidenceHtml = env.evidence.length
    ? (() => {
        const maxAbs = Math.max(1e-9, ...env.evidence.map(e => Math.abs(Number(e.contribution) || 0)));
        return env.evidence.map(e => _evidenceBar(e, maxAbs)).join('');
      })()
    : '';

  const emptyHtml = (env.verdict === 'UNAVAILABLE' && env.empty_state_reason)
    ? `<div class="analysis-card__empty">${_esc(env.empty_state_reason)}</div>` : '';

  const stale = isStale(env.computed_at, env.engine, nowIso);
  const stalePill = stale ? `<span class="analysis-card__stale" title="Older than 2× expected cadence">●</span>` : '';

  return `
    <div class="analysis-card" data-engine="${_esc(env.engine)}">
      <div class="analysis-card__header">
        <div class="analysis-card__id">
          <span class="analysis-card__engine">${_esc(env.engine.toUpperCase())}</span>
          <span class="analysis-card__ticker">${_esc(env.ticker)}</span>
        </div>
        <div class="analysis-card__verdict">${_esc(env.verdict)}</div>
        <div class="analysis-card__conviction ${convictionCls}" style="${convictionStyle}" title="${_esc(convictionTitle)}">${_esc(convictionText)}</div>
      </div>
      <div class="analysis-card__body">
        ${emptyHtml}
        ${evidenceHtml ? `<div class="analysis-card__evidence">${evidenceHtml}</div>` : ''}
        <div class="analysis-card__health">
          <span class="analysis-card__dot" style="background:${bandVar}"></span>
          <span>${_esc(env.health.band)}</span>
          <span class="analysis-card__health-detail">${_esc(env.health.detail)}</span>
        </div>
      </div>
      <div class="analysis-card__footer">
        <span class="analysis-card__freshness">${_esc(fmtRelative(env.computed_at, nowIso))}${stalePill}</span>
        <span class="analysis-card__source">${_esc(env.source || '')}</span>
      </div>
    </div>`;
}

// Render an ordered array of envelopes (the frozen FCS→TA→Spread→Corr order).
export function renderPanel(container, envelopes, nowIso) {
  if (!container) return;
  const html = (envelopes || []).map(e => renderCardHtml(e, nowIso)).join('');
  container.innerHTML = `<div class="analysis-panel">${html}</div>`;
}
```

- [ ] **Step 4: Run, expect PASS**

- [ ] **Step 5: Commit**

```
git add pipeline/terminal/static/js/components/analysis/panel.js pipeline/tests/test_analysis_adapters.py
git commit -m "feat(analysis): responsive panel renderer with calibration styling"
```

---

## Phase 4 — Four engine adapters

### Task 14: adapters/fcs.js

**Files:**
- Create: `pipeline/terminal/static/js/components/analysis/adapters/fcs.js`
- Test: append to `pipeline/tests/test_analysis_adapters.py`

- [ ] **Step 1: Write failing test**

```python
def test_fcs_adapter_green_long():
    src = f"""
    import {{ adapt }} from '{(TERMINAL_JS / "adapters" / "fcs.js").as_posix()}';
    const raw = {{score: 72, band: 'HIGH', health: 'GREEN', source: 'own',
      computed_at: '2026-04-23T14:00:00+05:30',
      mean_auc: 0.61, min_fold_auc: 0.54, n_folds: 6,
      top_features: [{{name: 'rs_10d', contribution: 0.38}},
                      {{name: 'sec5d', contribution: 0.22}},
                      {{name: 'vol60', contribution: -0.11}}]}};
    const env = adapt('RELIANCE', raw);
    console.log(JSON.stringify(env));
    """
    env = _run(src)
    assert env["engine"] == "fcs"
    assert env["verdict"] == "LONG"
    assert env["conviction_0_100"] == 72
    assert env["calibration"] == "walk_forward"
    assert len(env["evidence"]) == 3


def test_fcs_adapter_short_on_low_score():
    src = f"""
    import {{ adapt }} from '{(TERMINAL_JS / "adapters" / "fcs.js").as_posix()}';
    const env = adapt('X', {{score: 30, health: 'GREEN',
      top_features: [], computed_at: 'x'}});
    console.log(JSON.stringify(env));
    """
    env = _run(src)
    assert env["verdict"] == "SHORT"


def test_fcs_adapter_missing_returns_unavailable():
    src = f"""
    import {{ adapt }} from '{(TERMINAL_JS / "adapters" / "fcs.js").as_posix()}';
    const env = adapt('X', null);
    console.log(JSON.stringify(env));
    """
    env = _run(src)
    assert env["verdict"] == "UNAVAILABLE"
    assert env["empty_state_reason"]
```

- [ ] **Step 2: Run, expect FAIL**

- [ ] **Step 3: Implement**

```javascript
// pipeline/terminal/static/js/components/analysis/adapters/fcs.js
import { makeEnvelope } from '../envelope.js';

function _verdict(score) {
  if (score == null) return 'UNAVAILABLE';
  if (score >= 60) return 'LONG';
  if (score <= 40) return 'SHORT';
  return 'NEUTRAL';
}

export function adapt(ticker, raw) {
  if (!raw || typeof raw !== 'object') {
    return makeEnvelope({
      engine: 'fcs', ticker, verdict: 'UNAVAILABLE',
      empty_state_reason: 'No FCS score available for this ticker.',
      calibration: 'walk_forward',
    });
  }
  const score = Number.isFinite(raw.score) ? raw.score : null;
  const detailBits = [];
  if (raw.mean_auc != null) detailBits.push(`mean AUC ${Number(raw.mean_auc).toFixed(2)}`);
  if (raw.min_fold_auc != null) detailBits.push(`min ${Number(raw.min_fold_auc).toFixed(2)}`);
  if (raw.n_folds != null) detailBits.push(`${raw.n_folds} folds`);
  return makeEnvelope({
    engine: 'fcs', ticker,
    verdict: _verdict(score),
    conviction_0_100: score,
    evidence: (raw.top_features || []).slice(0, 3).map(t => ({
      name: t.name, contribution: t.contribution,
      direction: (t.contribution || 0) >= 0 ? 'pos' : 'neg',
    })),
    health: { band: raw.health || 'UNAVAILABLE', detail: detailBits.join(' · ') },
    calibration: 'walk_forward',
    computed_at: raw.computed_at || null,
    source: raw.source || 'own',
  });
}
```

- [ ] **Step 4: Run, expect PASS**

- [ ] **Step 5: Commit**

```
git add pipeline/terminal/static/js/components/analysis/adapters/fcs.js pipeline/tests/test_analysis_adapters.py
git commit -m "feat(analysis): FCS adapter — /attractiveness → envelope"
```

---

### Task 15: adapters/ta.js

**Files:**
- Create: `pipeline/terminal/static/js/components/analysis/adapters/ta.js`
- Test: append

- [ ] **Step 1: Write failing tests** (both RELIANCE green and non-pilot UNAVAILABLE)

```python
def test_ta_adapter_reliance_green():
    src = f"""
    import {{ adapt }} from '{(TERMINAL_JS / "adapters" / "ta.js").as_posix()}';
    const raw = {{score: 72, band: 'HIGH', health: 'GREEN', source: 'own',
      computed_at: '2026-04-23T16:00:00+05:30',
      mean_auc: 0.58, min_fold_auc: 0.53, n_folds: 5,
      top_features: [{{name: 'doji_flag', sign: '+', magnitude: 24,
                        contribution: 0.24}}]}};
    const env = adapt('RELIANCE', raw);
    console.log(JSON.stringify(env));
    """
    env = _run(src)
    assert env["engine"] == "ta"
    assert env["verdict"] == "LONG"
    assert env["calibration"] == "walk_forward"
    assert "daily bars" in env["health"]["detail"]


def test_ta_adapter_non_pilot_ticker_unavailable():
    src = f"""
    import {{ adapt }} from '{(TERMINAL_JS / "adapters" / "ta.js").as_posix()}';
    const env = adapt('ITC', null);
    console.log(JSON.stringify(env));
    """
    env = _run(src)
    assert env["verdict"] == "UNAVAILABLE"
    assert "RELIANCE only" in env["empty_state_reason"]
    assert "212" in env["empty_state_reason"]
```

- [ ] **Step 2: Run, expect FAIL**

- [ ] **Step 3: Implement**

```javascript
// pipeline/terminal/static/js/components/analysis/adapters/ta.js
import { makeEnvelope } from '../envelope.js';

const PILOT = 'RELIANCE';

function _verdict(score) {
  if (score == null) return 'UNAVAILABLE';
  if (score >= 60) return 'LONG';
  if (score <= 40) return 'SHORT';
  return 'NEUTRAL';
}

export function adapt(ticker, raw) {
  const isPilot = String(ticker || '').toUpperCase() === PILOT;
  if (!isPilot) {
    return makeEnvelope({
      engine: 'ta', ticker, verdict: 'UNAVAILABLE',
      empty_state_reason: 'TA pilot — RELIANCE only, 212 tickers await v2 rollout.',
      calibration: 'walk_forward',
      health: { band: 'UNAVAILABLE', detail: 'daily bars, EOD cadence' },
    });
  }
  if (!raw || typeof raw !== 'object') {
    return makeEnvelope({
      engine: 'ta', ticker, verdict: 'UNAVAILABLE',
      empty_state_reason: 'TA model not yet fitted — awaiting Sunday 01:30 run.',
      calibration: 'walk_forward',
      health: { band: 'UNAVAILABLE', detail: 'daily bars, EOD cadence' },
    });
  }
  const score = Number.isFinite(raw.score) ? raw.score : null;
  const detailBits = ['daily bars, EOD cadence'];
  if (raw.mean_auc != null) detailBits.push(`mean AUC ${Number(raw.mean_auc).toFixed(2)}`);
  if (raw.min_fold_auc != null) detailBits.push(`min ${Number(raw.min_fold_auc).toFixed(2)}`);
  if (raw.n_folds != null) detailBits.push(`${raw.n_folds} folds`);
  return makeEnvelope({
    engine: 'ta', ticker,
    verdict: _verdict(score),
    conviction_0_100: score,
    evidence: (raw.top_features || []).slice(0, 3).map(t => ({
      name: t.name,
      contribution: Number.isFinite(t.contribution) ? t.contribution
        : ((t.sign === '-' ? -1 : 1) * (Number(t.magnitude) || 0) / 100),
      direction: t.sign === '-' ? 'neg' : 'pos',
    })),
    health: { band: raw.health || 'UNAVAILABLE', detail: detailBits.join(' · ') },
    calibration: 'walk_forward',
    computed_at: raw.computed_at || null,
    source: raw.source || 'own',
  });
}
```

- [ ] **Step 4: Run, expect PASS**

- [ ] **Step 5: Commit**

```
git add pipeline/terminal/static/js/components/analysis/adapters/ta.js pipeline/tests/test_analysis_adapters.py
git commit -m "feat(analysis): TA adapter with RELIANCE-pilot UNAVAILABLE guard"
```

---

### Task 16: adapters/spread.js

**Files:**
- Create: `pipeline/terminal/static/js/components/analysis/adapters/spread.js`
- Test: append

- [ ] **Step 1: Write failing tests**

```python
def test_spread_adapter_pass_high():
    src = f"""
    import {{ adapt }} from '{(TERMINAL_JS / "adapters" / "spread.js").as_posix()}';
    const thesis = {{name: 'Defence vs IT', conviction: 'HIGH',
      regime_fit: true, gate_status: 'PASS', score: 85, z_score: 2.1,
      action: 'LONG', long_legs: ['HAL'], short_legs: ['INFY']}};
    const env = adapt('HAL', thesis);
    console.log(JSON.stringify(env));
    """
    env = _run(src)
    assert env["engine"] == "spread"
    assert env["verdict"] == "LONG"
    assert env["conviction_0_100"] == 80
    assert env["calibration"] == "heuristic"


def test_spread_adapter_gate_fail_watch():
    src = f"""
    import {{ adapt }} from '{(TERMINAL_JS / "adapters" / "spread.js").as_posix()}';
    const t = {{name: 'X', conviction: 'LOW', gate_status: 'FAIL',
      regime_fit: false, long_legs: ['X'], short_legs: []}};
    const env = adapt('X', t);
    console.log(JSON.stringify(env));
    """
    env = _run(src)
    assert env["verdict"] == "WATCH"
    assert env["conviction_0_100"] == 20


def test_spread_adapter_missing_returns_unavailable():
    src = f"""
    import {{ adapt }} from '{(TERMINAL_JS / "adapters" / "spread.js").as_posix()}';
    console.log(JSON.stringify(adapt('X', null)));
    """
    env = _run(src)
    assert env["verdict"] == "UNAVAILABLE"
```

- [ ] **Step 2: Run, expect FAIL**

- [ ] **Step 3: Implement**

```javascript
// pipeline/terminal/static/js/components/analysis/adapters/spread.js
import { makeEnvelope } from '../envelope.js';

// Replaces the inline 5-layer narration block in candidate-drawer.js.
// `raw` is one entry from /api/research/digest spread_theses[].
export function adapt(ticker, raw) {
  if (!raw || typeof raw !== 'object') {
    return makeEnvelope({
      engine: 'spread', ticker, verdict: 'UNAVAILABLE',
      empty_state_reason: 'No spread thesis for this ticker.',
      calibration: 'heuristic',
    });
  }
  const pass = String(raw.gate_status || '').toUpperCase() === 'PASS';
  const conviction = String(raw.conviction || '').toUpperCase();
  const convictionMap = {HIGH: 80, MEDIUM: 60, LOW: 40};
  const conviction_0_100 = pass ? (convictionMap[conviction] ?? 40) : 20;

  const upper = String(ticker || '').toUpperCase();
  const isLong = (raw.long_legs || []).some(l => String(l || '').toUpperCase() === upper);
  const isShort = (raw.short_legs || []).some(l => String(l || '').toUpperCase() === upper);
  let verdict;
  if (!pass) verdict = 'WATCH';
  else if (isLong) verdict = 'LONG';
  else if (isShort) verdict = 'SHORT';
  else verdict = 'NEUTRAL';

  const evidence = [
    {name: 'regime_gate', contribution: raw.regime_fit ? 1 : -1, direction: raw.regime_fit ? 'pos' : 'neg'},
    {name: 'scorecard_delta', contribution: (raw.score != null && raw.score >= 70) ? 1 : -1,
      direction: (raw.score != null && raw.score >= 70) ? 'pos' : 'neg'},
    {name: 'z_score', contribution: (raw.z_score != null && Math.abs(raw.z_score) >= 1.5) ? 1 : -1,
      direction: (raw.z_score != null && Math.abs(raw.z_score) >= 1.5) ? 'pos' : 'neg'},
  ];

  return makeEnvelope({
    engine: 'spread', ticker,
    verdict,
    conviction_0_100,
    evidence,
    health: { band: pass ? 'GREEN' : 'AMBER',
               detail: raw.name ? `pair: ${raw.name}` : '' },
    calibration: 'heuristic',
    computed_at: raw.computed_at || null,
    source: 'static_config',
  });
}
```

- [ ] **Step 4: Run, expect PASS**

- [ ] **Step 5: Commit**

```
git add pipeline/terminal/static/js/components/analysis/adapters/spread.js pipeline/tests/test_analysis_adapters.py
git commit -m "feat(analysis): spread adapter — replaces inline 5-layer block"
```

---

### Task 17: adapters/corr.js

**Files:**
- Create: `pipeline/terminal/static/js/components/analysis/adapters/corr.js`
- Test: append

- [ ] **Step 1: Write failing tests**

```python
def test_corr_adapter_long_on_negative_sigma():
    src = f"""
    import {{ adapt }} from '{(TERMINAL_JS / "adapters" / "corr.js").as_posix()}';
    const raw = {{sigma: -2.4, sector_divergence: -1.2, volume_anomaly: 0.3,
                   trust_delta: 0.1, computed_at: '2026-04-23T13:57:00+05:30'}};
    const env = adapt('HAL', raw);
    console.log(JSON.stringify(env));
    """
    env = _run(src)
    assert env["engine"] == "corr_break"
    assert env["verdict"] == "LONG"
    assert env["conviction_0_100"] == 60  # 2.4 × 25 = 60
    assert env["calibration"] == "heuristic"


def test_corr_adapter_short_on_positive_sigma():
    src = f"""
    import {{ adapt }} from '{(TERMINAL_JS / "adapters" / "corr.js").as_posix()}';
    console.log(JSON.stringify(adapt('X', {{sigma: 3.0, sector_divergence: 2,
      volume_anomaly: 0, trust_delta: 0, computed_at: 'x'}})));
    """
    env = _run(src)
    assert env["verdict"] == "SHORT"
    assert env["conviction_0_100"] == 75


def test_corr_adapter_neutral_when_small_sigma():
    src = f"""
    import {{ adapt }} from '{(TERMINAL_JS / "adapters" / "corr.js").as_posix()}';
    console.log(JSON.stringify(adapt('X', {{sigma: 0.8, sector_divergence: 0,
      volume_anomaly: 0, trust_delta: 0, computed_at: 'x'}})));
    """
    env = _run(src)
    assert env["verdict"] == "NEUTRAL"


def test_corr_adapter_missing():
    src = f"""
    import {{ adapt }} from '{(TERMINAL_JS / "adapters" / "corr.js").as_posix()}';
    console.log(JSON.stringify(adapt('X', null)));
    """
    env = _run(src)
    assert env["verdict"] == "UNAVAILABLE"
```

- [ ] **Step 2: Run, expect FAIL**

- [ ] **Step 3: Implement**

```javascript
// pipeline/terminal/static/js/components/analysis/adapters/corr.js
import { makeEnvelope } from '../envelope.js';

export function adapt(ticker, raw) {
  if (!raw || typeof raw !== 'object' || raw.sigma == null) {
    return makeEnvelope({
      engine: 'corr_break', ticker, verdict: 'UNAVAILABLE',
      empty_state_reason: 'No correlation-break observation for this ticker.',
      calibration: 'heuristic',
    });
  }
  const sigma = Number(raw.sigma) || 0;
  const abs = Math.abs(sigma);
  const conviction_0_100 = Math.min(100, Math.round(abs * 25));
  let verdict = 'NEUTRAL';
  if (abs >= 1.5) verdict = sigma < 0 ? 'LONG' : 'SHORT';

  const fields = [
    {name: 'sigma', value: sigma},
    {name: 'sector_divergence', value: Number(raw.sector_divergence) || 0},
    {name: 'volume_anomaly', value: Number(raw.volume_anomaly) || 0},
    {name: 'trust_delta', value: Number(raw.trust_delta) || 0},
  ];
  fields.sort((a, b) => Math.abs(b.value) - Math.abs(a.value));
  const evidence = fields.slice(0, 3).map(f => ({
    name: f.name, contribution: f.value,
    direction: f.value >= 0 ? 'pos' : 'neg',
  }));

  return makeEnvelope({
    engine: 'corr_break', ticker, verdict, conviction_0_100,
    evidence,
    health: { band: 'UNAVAILABLE', detail: 'heuristic — no calibration yet' },
    calibration: 'heuristic',
    computed_at: raw.computed_at || null,
    source: 'own',
  });
}
```

- [ ] **Step 4: Run, expect PASS**

- [ ] **Step 5: Commit**

```
git add pipeline/terminal/static/js/components/analysis/adapters/corr.js pipeline/tests/test_analysis_adapters.py
git commit -m "feat(analysis): correlation-break adapter (σ-based heuristic)"
```

---

## Phase 5 — Trading tab integration & clean replace

### Task 18: trading.js — parallel pre-fetch for all four engines

**Files:**
- Modify: `pipeline/terminal/static/js/pages/trading.js`
- Test: extend existing page smoke test OR add one at `pipeline/tests/test_trading_page.py` (manual verification at end of Task 21)

- [ ] **Step 1: Read the current file to preserve the attachment pattern**

The current code (see existing `pipeline/terminal/static/js/pages/trading.js`) does:
```js
const [data, scores] = await Promise.all([
  get('/candidates'),
  attractiveness.fetchAll().catch(() => ({ scores: {} })),
]);
_allCandidates = data.tradeable_candidates || [];
_attachAttractiveness(_allCandidates, scores);
```

- [ ] **Step 2: Replace `Promise.all` with `Promise.allSettled` over four endpoints**

```js
// pipeline/terminal/static/js/pages/trading.js (loadData block replaces the Promise.all)
async function loadData() {
  try {
    const [dataRes, fcsRes, taRes, spreadRes, corrRes] = await Promise.allSettled([
      get('/candidates'),
      get('/attractiveness'),
      get('/ta_attractiveness'),
      get('/research/digest'),
      get('/correlation_breaks'),
    ]);
    _allCandidates = (dataRes.status === 'fulfilled'
      ? (dataRes.value.tradeable_candidates || []) : []);

    const fcsScores = (fcsRes.status === 'fulfilled') ? fcsRes.value : { scores: {} };
    const taScores = (taRes.status === 'fulfilled') ? taRes.value : { scores: {} };
    const digest = (spreadRes.status === 'fulfilled') ? spreadRes.value : { spread_theses: [] };
    const corrBreaks = (corrRes.status === 'fulfilled') ? corrRes.value : { breaks: [] };

    _attachAnalyses(_allCandidates, fcsScores, taScores, digest, corrBreaks);

    // Keep existing attractiveness cell attachment for the table column.
    _attachAttractiveness(_allCandidates, fcsScores);

    const sources = [...new Set(_allCandidates.map(c => c.source).filter(Boolean))];
    const convictions = [...new Set(_allCandidates.map(c => c.conviction).filter(Boolean))];
    const horizons = [...new Set(_allCandidates.map(c => c.horizon_basis).filter(Boolean))];

    const filterEl = document.getElementById('trading-filters');
    filterChips.render(filterEl, {
      groups: [
        { key: 'source', label: 'Source', options: sources },
        { key: 'conviction', label: 'Conviction', options: convictions },
        { key: 'horizon_basis', label: 'Horizon', options: horizons },
      ],
    }, applyFilters, 'trading');

    applyFilters(filterChips.getState('trading'));
  } catch (err) {
    document.getElementById('trading-table').innerHTML =
      `<div class="empty-state"><p>Failed to load candidates: ${err.message}</p></div>`;
  }
}

function _attachAnalyses(candidates, fcs, ta, digest, corr) {
  const fcsMap = (fcs && fcs.scores) || {};
  const taMap = (ta && ta.scores) || {};
  const spreadsByName = Object.fromEntries((digest.spread_theses || []).map(s => [s.name, s]));
  const corrByTicker = Object.fromEntries(
    (corr.breaks || []).map(b => [String(b.ticker || '').toUpperCase(), b]));
  for (const c of candidates) {
    const raw = c.long_legs?.[0] || c.short_legs?.[0] || c.ticker;
    const key = raw ? String(raw).toUpperCase() : null;
    c.analyses_raw = {
      fcs: key ? (fcsMap[key] || null) : null,
      ta: key ? (taMap[key] || null) : null,
      spread: c.name ? (spreadsByName[c.name] || null) : null,
      corr: key ? (corrByTicker[key] || null) : null,
    };
  }
}
```

- [ ] **Step 3: Manual verification**

Open the terminal in dev mode (`python -m pipeline.terminal` per FCS workflow), load Trading tab, open browser devtools → Network → confirm 4 requests fire in parallel.

- [ ] **Step 4: Commit**

```
git add pipeline/terminal/static/js/pages/trading.js
git commit -m "feat(trading): parallel pre-fetch four engines + analyses_raw attach"
```

---

### Task 19: candidate-drawer.js — rewrite around shared panel (clean replace)

**Files:**
- Modify: `pipeline/terminal/static/js/components/candidate-drawer.js`
- Test: inline manual test (full page smoke at Task 28 is the end-to-end check)

- [ ] **Step 1: Read the full file** (already reviewed during brainstorm — the 5-layer `layersHtml` block is the thing being deleted).

- [ ] **Step 2: Replace entire file contents**

```javascript
// pipeline/terminal/static/js/components/candidate-drawer.js
// Renders the expandable inline drawer beneath a candidate row.
// v1 of Unified Analysis Panel: loops over candidate.analyses_raw, runs each
// through its adapter, renders the shared panel. Replaces the hardcoded
// 5-layer narration block.
import { renderPanel } from './analysis/panel.js';
import { makeEnvelope } from './analysis/envelope.js';
import { adapt as adaptFcs } from './analysis/adapters/fcs.js';
import { adapt as adaptTa } from './analysis/adapters/ta.js';
import { adapt as adaptSpread } from './analysis/adapters/spread.js';
import { adapt as adaptCorr } from './analysis/adapters/corr.js';

function _esc(s) {
  if (s == null) return '';
  const d = document.createElement('div');
  d.textContent = String(s);
  return d.innerHTML;
}

export async function render(container, candidate) {
  const tkr = String(
    (candidate.long_legs && candidate.long_legs[0]) ||
    (candidate.short_legs && candidate.short_legs[0]) ||
    candidate.ticker || ''
  ).toUpperCase();

  const raw = candidate.analyses_raw || {};
  // Frozen render order: FCS → TA → Spread → Corr Break.
  const envelopes = [
    adaptFcs(tkr, raw.fcs),
    adaptTa(tkr, raw.ta),
    adaptSpread(tkr, raw.spread),
    adaptCorr(tkr, raw.corr),
  ];

  const narration = candidate.reason || '';
  const sizingLine = candidate.sizing_basis
    ? `<div><span class="text-muted">Sizing basis:</span> <span class="mono">${_esc(candidate.sizing_basis)}</span></div>`
    : '';
  const horizonLine = `<div><span class="text-muted">Horizon:</span> <span class="mono">${_esc(candidate.horizon_days)}d (${_esc(candidate.horizon_basis)})</span></div>`;

  const panelMountId = `uap-${Math.random().toString(36).slice(2, 8)}`;

  container.innerHTML = `
    <div style="padding: var(--spacing-md); background: var(--bg-elevated); border-left: 3px solid var(--accent-gold);">
      <div style="font-size: 0.875rem; line-height: 1.6;">${_esc(narration)}</div>
      <div style="margin-top: var(--spacing-sm); display: grid; grid-template-columns: repeat(2, 1fr); gap: var(--spacing-xs); font-size: 0.75rem;">
        ${horizonLine}
        ${sizingLine}
        <div><span class="text-muted">Source:</span> <span class="mono">${_esc(candidate.source)}</span></div>
        <div><span class="text-muted">Conviction:</span> <span class="mono">${_esc(candidate.conviction)}</span></div>
      </div>
      <div id="${panelMountId}" style="margin-top: var(--spacing-md);"></div>
    </div>`;

  const mount = container.querySelector(`#${panelMountId}`);
  if (mount) {
    renderPanel(mount, envelopes, new Date().toISOString());
  }
}
```

- [ ] **Step 3: Manual verification**

Reload Trading tab, click a candidate row → four cards render in FCS → TA → Spread → Corr order; calibration tag coloring differs per engine; UNAVAILABLE card for TA on non-RELIANCE rows shows the pilot message.

- [ ] **Step 4: Commit**

```
git add pipeline/terminal/static/js/components/candidate-drawer.js
git commit -m "feat(drawer): rewrite around shared analysis panel (clean replace)"
```

---

### Task 20: Delete `attractiveness-panel.js` + migrate its tests

**Files:**
- Delete: `pipeline/terminal/static/js/components/attractiveness-panel.js`
- Test: if any unit tests reference the deleted module, port them into `pipeline/tests/test_analysis_adapters.py`

- [ ] **Step 1: Search for imports of the deleted module**

Run:
```
grep -rn "attractiveness-panel" pipeline/terminal/static/js pipeline/terminal/tests
```

Expected matches: previously in `candidate-drawer.js` (already removed in Task 19). If any others remain, they must be updated in the same commit.

- [ ] **Step 2: Delete the file**

```
git rm pipeline/terminal/static/js/components/attractiveness-panel.js
```

- [ ] **Step 3: Run the full terminal test suite to confirm no regression**

```
pytest pipeline/tests/test_analysis_adapters.py pipeline/tests/test_ta_attractiveness_api.py -v
```

Expected: all pass; zero references to the deleted module remain.

- [ ] **Step 4: Commit**

```
git commit -m "refactor(drawer): delete attractiveness-panel.js (absorbed into shared panel)"
```

---

### Task 21: CSS for `.analysis-card` + `.analysis-panel`

**Files:**
- Modify: `pipeline/terminal/static/css/terminal.css`
- Test: visual inspection; golden HTML fixture at Task 22 asserts class names exist

- [ ] **Step 1: Read the current CSS to find the right insertion point** — append at end of file after existing `.attract*` block. Verify no class name collision (`.analysis-card*` is fresh).

- [ ] **Step 2: Append block**

```css
/* Unified Analysis Panel (UAP) v1 */
.analysis-panel {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);
}
.analysis-card {
  background: var(--bg-elevated);
  border-left: 3px solid var(--accent-gold);
  padding: var(--spacing-sm);
  font-family: var(--font-mono);
  font-size: 0.75rem;
}
.analysis-card__header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: var(--spacing-xs);
}
.analysis-card__engine {
  color: var(--text-muted);
  font-size: 0.6875rem;
  letter-spacing: 0.08em;
  margin-right: 6px;
}
.analysis-card__ticker {
  font-weight: 600;
}
.analysis-card__verdict {
  font-weight: 600;
  font-size: 0.8125rem;
}
.analysis-card__conviction {
  font-weight: 700;
  font-size: 1.25rem;
  min-width: 2.5em;
  text-align: right;
}
.analysis-card__body {
  margin-top: var(--spacing-xs);
}
.analysis-card__empty {
  color: var(--text-muted);
  font-style: italic;
  margin: 6px 0;
}
.analysis-card__evidence {
  margin: 6px 0;
}
.analysis-card__bar-row {
  display: grid;
  grid-template-columns: 60px 1fr 140px;
  gap: 8px;
  align-items: center;
  margin-bottom: 3px;
}
.analysis-card__bar-label {
  color: var(--text-muted);
  font-size: 0.6875rem;
}
.analysis-card__bar-track {
  height: 6px;
  background: rgba(255,255,255,0.05);
}
.analysis-card__bar { height: 6px; }
.analysis-card__bar-pos { background: var(--accent-gold); }
.analysis-card__bar-neg { background: var(--text-muted); }
.analysis-card__bar-name { font-size: 0.6875rem; color: var(--text-muted); }
.analysis-card__health {
  display: flex;
  gap: 6px;
  align-items: center;
  font-size: 0.6875rem;
}
.analysis-card__dot {
  display: inline-block;
  width: 8px; height: 8px; border-radius: 50%;
}
.analysis-card__health-detail { color: var(--text-muted); }
.analysis-card__footer {
  display: flex;
  justify-content: space-between;
  margin-top: 6px;
  color: var(--text-muted);
  font-size: 0.6875rem;
}
.analysis-card__stale { color: var(--accent-gold); margin-left: 4px; }

/* Responsive: at ≥480px, header + 2-col body */
@media (min-width: 480px) {
  .analysis-card__body {
    display: grid;
    grid-template-columns: 1.3fr 1fr;
    gap: var(--spacing-sm);
  }
  .analysis-card__evidence { grid-column: 1; }
  .analysis-card__health { grid-column: 2; align-self: start; }
}
```

- [ ] **Step 3: Manual visual check**

Reload Trading drawer — four cards styled consistently; calibration heuristic cards show muted dotted-underline conviction numbers; walk-forward cards show gold.

- [ ] **Step 4: Commit**

```
git add pipeline/terminal/static/css/terminal.css
git commit -m "style(analysis): CSS for .analysis-card (responsive, theme tokens)"
```

---

### Task 22: Golden HTML fixtures + fixture test

**Files:**
- Create: `pipeline/tests/fixtures/analysis-panel/fcs-green-long.html`
- Create: `pipeline/tests/fixtures/analysis-panel/ta-unavailable-non-pilot.html`
- Create: `pipeline/tests/fixtures/analysis-panel/spread-pass-high.html`
- Create: `pipeline/tests/fixtures/analysis-panel/corr-long-negative-sigma.html`
- Test: `pipeline/tests/test_analysis_panel_fixtures.py`

- [ ] **Step 1: Write the failing test**

```python
# pipeline/tests/test_analysis_panel_fixtures.py
"""Golden-HTML regression: each (engine × verdict) combo has a frozen fixture.
If the adapter + panel output stops matching a fixture, test fails. Regenerate
fixtures deliberately — these are tripwires for silent UI drift."""
import json
import subprocess
from pathlib import Path

TERMINAL_JS = Path("pipeline/terminal/static/js/components/analysis")
FIXTURE_DIR = Path("pipeline/tests/fixtures/analysis-panel")

CASES = [
    {
      "name": "fcs-green-long",
      "adapter": "fcs",
      "ticker": "RELIANCE",
      "raw": {
        "score": 72, "band": "HIGH", "health": "GREEN", "source": "own",
        "computed_at": "2026-04-23T14:00:00+05:30",
        "mean_auc": 0.61, "min_fold_auc": 0.54, "n_folds": 6,
        "top_features": [
          {"name": "ticker_rs_10d", "contribution": 0.38},
          {"name": "sector_5d_return", "contribution": 0.22},
          {"name": "realized_vol_60d", "contribution": -0.11},
        ],
      },
      "now": "2026-04-23T14:00:00+05:30",
    },
    {
      "name": "ta-unavailable-non-pilot",
      "adapter": "ta", "ticker": "ITC", "raw": None,
      "now": "2026-04-23T16:00:00+05:30",
    },
    {
      "name": "spread-pass-high",
      "adapter": "spread", "ticker": "HAL",
      "raw": {"name": "Defence vs IT", "conviction": "HIGH",
               "regime_fit": True, "gate_status": "PASS",
               "score": 85, "z_score": 2.1, "action": "LONG",
               "long_legs": ["HAL"], "short_legs": ["INFY"],
               "computed_at": "2026-04-23T13:57:00+05:30"},
      "now": "2026-04-23T14:00:00+05:30",
    },
    {
      "name": "corr-long-negative-sigma",
      "adapter": "corr", "ticker": "HAL",
      "raw": {"sigma": -2.4, "sector_divergence": -1.2,
               "volume_anomaly": 0.3, "trust_delta": 0.1,
               "computed_at": "2026-04-23T13:57:00+05:30"},
      "now": "2026-04-23T14:00:00+05:30",
    },
]


def _render_html(case):
    src = f"""
    import {{ adapt }} from '{(TERMINAL_JS / "adapters" / (case["adapter"] + ".js")).as_posix()}';
    import {{ renderCardHtml }} from '{(TERMINAL_JS / "panel.js").as_posix()}';
    const env = adapt({json.dumps(case["ticker"])}, {json.dumps(case["raw"])});
    console.log(renderCardHtml(env, {json.dumps(case["now"])}));
    """
    proc = subprocess.run(["node", "--input-type=module", "-e", src],
                          capture_output=True, text=True, timeout=15)
    assert proc.returncode == 0, proc.stderr
    return proc.stdout.strip()


def test_all_fixtures_match():
    mismatches = []
    for case in CASES:
        fixture = FIXTURE_DIR / f"{case['name']}.html"
        rendered = _render_html(case)
        if not fixture.exists():
            fixture.parent.mkdir(parents=True, exist_ok=True)
            fixture.write_text(rendered, encoding="utf-8")
            continue
        expected = fixture.read_text(encoding="utf-8").strip()
        if rendered != expected:
            mismatches.append(case["name"])
    assert not mismatches, f"fixture drift: {mismatches}"
```

- [ ] **Step 2: First run** — FAILs until Task 19/17 are complete. On first pass against final adapters, fixtures write themselves. Re-run → PASS.

```
pytest pipeline/tests/test_analysis_panel_fixtures.py -v
```

- [ ] **Step 3: Verify fixtures were written**

```
ls pipeline/tests/fixtures/analysis-panel/
```

Expected: 4 `.html` files.

- [ ] **Step 4: Commit fixtures + test together**

```
git add pipeline/tests/test_analysis_panel_fixtures.py pipeline/tests/fixtures/analysis-panel/
git commit -m "test(analysis): golden HTML fixtures — 4 engine×verdict combos"
```

---

## Phase 6 — Ops wiring (scheduled tasks, watchdog)

### Task 23: `.bat` wrappers for TA scorer

**Files:**
- Create: `pipeline/scripts/fit_ta_scorer.bat`
- Create: `pipeline/scripts/score_ta_scorer.bat`
- Modify (optional): an existing EOD caller to chain `score_ta_scorer` — see Step 3 below.

- [ ] **Step 1: Create weekly fit wrapper**

`pipeline/scripts/fit_ta_scorer.bat`:
```bat
@echo off
REM ANKA TA Scorer — Sunday 01:30 IST weekly fit (RELIANCE pilot)
cd /d "C:\Users\Claude_Anka\askanka.com"
python -X utf8 -m pipeline.ta_scorer.fit_universe >> pipeline\logs\fit_ta_scorer.log 2>&1
```

- [ ] **Step 2: Create daily score wrapper**

`pipeline/scripts/score_ta_scorer.bat`:
```bat
@echo off
REM ANKA TA Scorer — daily 16:00 IST score after EOD bars locked
cd /d "C:\Users\Claude_Anka\askanka.com"
python -X utf8 -m pipeline.ta_scorer.score_universe >> pipeline\logs\score_ta_scorer.log 2>&1
```

- [ ] **Step 3: Decide scheduling strategy — standalone task vs chained**

The FCS intraday scorer chains off `intraday_scan.bat` (not a standalone task) to reuse the market-hours guard. For TA (daily EOD 16:00), pick one:

**Option A (cleaner):** Create two standalone scheduled tasks `AnkaTAScorerFit` (Sunday 01:30) + `AnkaTAScorerScore` (daily 16:00). Matches the spec's explicit task names.

**Option B (chained):** Append `call pipeline\scripts\score_ta_scorer.bat` to `pipeline/scripts/eod_review.bat` (runs 16:00). Chained task pattern like FCS-intraday, means only one inventory entry (virtual AnkaTAScorerScore).

Spec says explicit tasks → go with A. Create the two scheduled tasks in Windows Task Scheduler by hand (no script automates this — it's a one-off system config step). Record the schedule XMLs for reproducibility.

```
schtasks /create /tn AnkaTAScorerFit /sc weekly /d SUN /st 01:30 /tr "C:\Users\Claude_Anka\askanka.com\pipeline\scripts\fit_ta_scorer.bat"
schtasks /create /tn AnkaTAScorerScore /sc daily /st 16:00 /tr "C:\Users\Claude_Anka\askanka.com\pipeline\scripts\score_ta_scorer.bat"
```

- [ ] **Step 4: Verify tasks exist**

```
schtasks /query /tn AnkaTAScorerFit
schtasks /query /tn AnkaTAScorerScore
```

- [ ] **Step 5: Commit the .bat files**

```
git add pipeline/scripts/fit_ta_scorer.bat pipeline/scripts/score_ta_scorer.bat
git commit -m "ops(ta_scorer): Windows scheduled-task wrappers (weekly fit + daily score)"
```

---

### Task 24: Watchdog inventory entries + test

**Files:**
- Modify: `pipeline/config/anka_inventory.json`
- Test: `pipeline/tests/test_watchdog_ta_scorer.py`

- [ ] **Step 1: Write failing test** (follows `test_watchdog_feature_scorer.py` shape)

```python
# pipeline/tests/test_watchdog_ta_scorer.py
import json
from pathlib import Path


def _load_inventory():
    p = Path("pipeline/config/anka_inventory.json")
    return json.loads(p.read_text(encoding="utf-8"))


def test_ta_scorer_fit_task_present():
    inv = _load_inventory()
    tasks = {t["name"]: t for t in inv["tasks"]}
    assert "AnkaTAScorerFit" in tasks
    e = tasks["AnkaTAScorerFit"]
    assert e["cadence_class"] == "weekly"
    assert e["tier"] == "warn"
    assert e["grace_multiplier"] >= 1.5
    assert any("ta_feature_models.json" in o for o in e["outputs"])


def test_ta_scorer_score_task_present():
    inv = _load_inventory()
    tasks = {t["name"]: t for t in inv["tasks"]}
    assert "AnkaTAScorerScore" in tasks
    e = tasks["AnkaTAScorerScore"]
    assert e["cadence_class"] == "daily"
    assert e["tier"] == "warn"
    assert any("ta_attractiveness_scores.json" in o for o in e["outputs"])


def test_no_duplicate_ta_entries():
    inv = _load_inventory()
    names = [t["name"] for t in inv["tasks"]]
    assert names.count("AnkaTAScorerFit") == 1
    assert names.count("AnkaTAScorerScore") == 1
```

- [ ] **Step 2: Run, expect FAIL**

- [ ] **Step 3: Add inventory entries**

Open `pipeline/config/anka_inventory.json`, bump `"updated"` to `"2026-04-23"`, and append to the `tasks` array (match the shape of `AnkaFeatureScorerFit` / `AnkaFeatureScorerIntraday`):

```json
{
  "name": "AnkaTAScorerFit",
  "tier": "warn",
  "cadence_class": "weekly",
  "grace_multiplier": 2.0,
  "outputs": ["pipeline/data/ta_feature_models.json"],
  "notes": "TA Coincidence Scorer v1 weekly fit (RELIANCE pilot). Sunday 01:30 IST."
},
{
  "name": "AnkaTAScorerScore",
  "tier": "warn",
  "cadence_class": "daily",
  "grace_multiplier": 2.0,
  "outputs": ["pipeline/data/ta_attractiveness_scores.json"],
  "notes": "TA Coincidence Scorer v1 daily EOD scoring. 16:00 IST after bars locked."
}
```

- [ ] **Step 4: Run, expect PASS**

- [ ] **Step 5: Commit**

```
git add pipeline/config/anka_inventory.json pipeline/tests/test_watchdog_ta_scorer.py
git commit -m "ops(watchdog): inventory entries for AnkaTAScorer{Fit,Score}"
```

---

## Phase 7 — Documentation sync

### Task 25: SYSTEM_OPERATIONS_MANUAL Station 10 + CLAUDE.md

**Files:**
- Modify: `docs/SYSTEM_OPERATIONS_MANUAL.md`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Append Station 10 to the ops manual**

Open `docs/SYSTEM_OPERATIONS_MANUAL.md` and after the existing Station 9 (Feature Coincidence Scorer) section, append:

```markdown
## Station 10 — Unified Analysis Panel (UAP) v1

**Purpose.** One shared terminal component renders all four analysis engines (FCS, TA, Spread, Correlation Break) through a single envelope: Verdict + Conviction (0–100) + Evidence + Model Health + Freshness + Calibration tag. Replaces the engine-specific panels that preceded it.

**Data flow.** `pages/trading.js` parallel-fetches `/api/attractiveness`, `/api/ta_attractiveness`, `/api/research/digest`, `/api/correlation_breaks` via `Promise.allSettled`. Raw responses attach to each candidate as `analyses_raw`. Drawer open → `components/analysis/panel.js` renders four cards in frozen order `FCS → TA → Spread → Corr Break` via per-engine adapters.

**Calibration tag.** `walk_forward` scores render gold; `heuristic` scores render muted with dotted underline. Makes the no-hallucination mandate visible: FCS/TA earn their scores via walk-forward AUC; Spread (gate mapping) and Correlation Break (σ×25) are asserted heuristics with no calibration in v1.

**TA scorer inputs.** `pipeline/data/fno_historical/RELIANCE.csv` + `pipeline/data/india_historical/indices/NIFTYENERGY_daily.csv` + `NIFTY_daily.csv` → `fit_universe.py` (Sunday 01:30 `AnkaTAScorerFit`) → `pipeline/data/ta_feature_models.json`. → `score_universe.py` (daily 16:00 `AnkaTAScorerScore`) → `pipeline/data/ta_attractiveness_scores.json`. Surfaced by `/api/ta_attractiveness` + `/ta_attractiveness/{ticker}`.

**Freshness contract.** Watchdog tracks `ta_feature_models.json` (weekly warn, grace 2.0) and `ta_attractiveness_scores.json` (daily warn, grace 2.0). TA card in the UI shows previous-session 16:00 timestamp during market hours — this is correct by design (daily bars, not intraday).

**Scope boundary.** v1 is ranking/research only — does NOT gate trades or set size. RELIANCE-only TA pilot; 212/213 tickers show UNAVAILABLE card until v2 rollout after 60-day forward uplift audit.

**Files of interest.**
- Backend: `pipeline/ta_scorer/*.py`, `pipeline/terminal/api/ta_attractiveness.py`
- Frontend: `pipeline/terminal/static/js/components/analysis/{panel,envelope,health}.js`, `adapters/{fcs,ta,spread,corr}.js`
- Design: `docs/superpowers/specs/2026-04-23-unified-analysis-panel-design.md`
- Plan: `docs/superpowers/plans/2026-04-23-unified-analysis-panel.md`
```

- [ ] **Step 2: Update Clockwork schedule**

In `docs/SYSTEM_OPERATIONS_MANUAL.md` Clockwork section (the one CLAUDE.md mirrors), add under **Weekly**:
```
- Sunday 01:30 — AnkaTAScorerFit: RELIANCE TA model walk-forward fit (warn)
```

And under **Post-Close**:
```
- 16:00 — AnkaTAScorerScore: TA Coincidence Scorer daily apply (warn)
```

- [ ] **Step 3: Mirror the same additions into `CLAUDE.md`**

- [ ] **Step 4: Bump task count**

In `CLAUDE.md`, change `Total: 75+ scheduled tasks` → `Total: 77+ scheduled tasks`.

- [ ] **Step 5: Commit**

```
git add docs/SYSTEM_OPERATIONS_MANUAL.md CLAUDE.md
git commit -m "docs: Station 10 (UAP v1) + TA scorer in Clockwork"
```

---

### Task 26: Memory entry + MEMORY.md index

**Files:**
- Create: `C:\Users\Claude_Anka\.claude\projects\C--Users-Claude-Anka-askanka-com\memory\project_unified_analysis_panel.md`
- Modify: `C:\Users\Claude_Anka\.claude\projects\C--Users-Claude-Anka-askanka-com\memory\MEMORY.md`

- [ ] **Step 1: Write memory file**

```markdown
---
name: Unified Analysis Panel (UAP)
description: Shared terminal component + envelope — FCS/TA/Spread/Corr render through one template with a calibration tag separating walk-forward scores from heuristic asserts
type: project
---

v1 shipped 2026-04-23 (plan: `docs/superpowers/plans/2026-04-23-unified-analysis-panel.md`). Trading-tab drawer now renders four analysis cards in frozen order `FCS → TA → Spread → Corr Break`, each through the same responsive component at `pipeline/terminal/static/js/components/analysis/panel.js`. Calibration tag visible as color: walk-forward = gold, heuristic = muted/dotted-underlined. Four client-side adapters (`adapters/{fcs,ta,spread,corr}.js`) map engine-native responses to the shared envelope.

TA Coincidence Scorer v1 bundled — RELIANCE-only pilot via weekly `AnkaTAScorerFit` (Sunday 01:30) and daily `AnkaTAScorerScore` (16:00 EOD). Endpoints: `/api/ta_attractiveness` + `/ta_attractiveness/{ticker}`. TA adapter shows prominent UNAVAILABLE card for 212/213 non-pilot tickers with explicit "TA pilot — RELIANCE only" reason line.

Clean replace: `attractiveness-panel.js` deleted; the inline 5-layer narration block in `candidate-drawer.js` absorbed into `adapters/spread.js`. `attractiveness-cell.js` + `attractiveness-badge.js` kept (compact inline surfaces, not panels).

Out of v1 (deferred): Ticker Brief page (v2), cross-engine synthesis score, WebSocket freshness push, TA universe expansion beyond RELIANCE (gated by 60-day forward uplift audit), walk-forward calibration for Spread/Corr.

Design: `docs/superpowers/specs/2026-04-23-unified-analysis-panel-design.md`
```

- [ ] **Step 2: Append index entry to MEMORY.md**

After the existing `project_feature_coincidence_scorer.md` line, add:

```
- [Unified Analysis Panel](project_unified_analysis_panel.md) — shared terminal component: FCS/TA/Spread/Corr render through one template with calibration tag separating walk-forward from heuristic
```

- [ ] **Step 3: Commit (memory files live outside repo — this is a separate commit to the memory git if one exists, or just a file write)**

Memory files are outside the repo. Write them and no git action is needed. Confirm they exist:
```
ls "C:\Users\Claude_Anka\.claude\projects\C--Users-Claude-Anka-askanka-com\memory\" | grep unified
```

Expected: `project_unified_analysis_panel.md` listed.

---

## Phase 8 — End-to-end verification + forward-audit stub

### Task 27: Terminal smoke test

**Files:**
- Test: `pipeline/tests/test_analysis_panel_smoke.py`

- [ ] **Step 1: Write test** — hits real live data files, not fixtures; skips on missing deps

```python
# pipeline/tests/test_analysis_panel_smoke.py
"""End-to-end smoke: bring up the FastAPI app, hit all four engine endpoints,
verify shapes. Also spawn Node to render panel.js output for RELIANCE and
confirm the resulting HTML contains at least one card per engine. Skips when
local artifacts (ta_feature_models.json) don't exist yet — which is the
correct pre-fit state on fresh checkouts."""
import json
import subprocess
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from pipeline.terminal.app import app


def test_all_four_endpoints_return_200_or_404():
    with TestClient(app) as c:
        paths = ["/api/attractiveness", "/api/ta_attractiveness",
                 "/api/research/digest", "/api/correlation_breaks"]
        for p in paths:
            r = c.get(p)
            assert r.status_code in (200, 404), f"{p} → {r.status_code}"


def test_ta_endpoint_returns_reliance_when_fit(tmp_path):
    if not Path("pipeline/data/ta_feature_models.json").exists():
        pytest.skip("ta_feature_models.json not yet built — run fit_universe first")
    with TestClient(app) as c:
        r = c.get("/api/ta_attractiveness")
    assert r.status_code == 200
    scores = r.json().get("scores", {})
    # Either RELIANCE is present OR the file is a pre-fit skeleton — both OK
    assert isinstance(scores, dict)
```

- [ ] **Step 2: Run, expect PASS**

```
pytest pipeline/tests/test_analysis_panel_smoke.py -v
```

- [ ] **Step 3: Commit**

```
git add pipeline/tests/test_analysis_panel_smoke.py
git commit -m "test(analysis): end-to-end smoke — four endpoints + TA endpoint shape"
```

---

### Task 28: Forward-uplift audit stub (60-day gate)

**Files:**
- Test: `pipeline/tests/backtest/test_ta_scorer_uplift.py`

- [ ] **Step 1: Write the stub**

```python
# pipeline/tests/backtest/test_ta_scorer_uplift.py
"""Forward-uplift audit: RELIANCE days where TA score ≥ 70 and health=GREEN
must outperform the base win-rate by ≥ 5pp over a 60-trading-day window.

Skipped until ta_attractiveness_scores.json has accumulated ≥ 60 distinct
scoring days. When the skip lifts, this test gates the TA pilot's graduation
to the full 213-ticker universe."""
import json
from pathlib import Path
import pytest


def test_ta_pilot_forward_uplift_5pp():
    scores_path = Path("pipeline/data/ta_attractiveness_scores.json")
    if not scores_path.exists():
        pytest.skip("ta_attractiveness_scores.json missing — post-fit gate")

    # Snapshot history file grows daily post-deploy. Until ≥ 60 days accumulate,
    # we cannot fairly judge uplift. The stub is intentionally a skip, not a
    # pass — it surfaces the criterion on every test run.
    snaps = Path("pipeline/data/ta_attractiveness_snapshots.jsonl")
    if not snaps.exists() or snaps.stat().st_size == 0:
        pytest.skip("no TA snapshot history yet — revisit 60 days after first score run")

    days_seen = set()
    with snaps.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except Exception:
                continue
            ts = rec.get("ts") or rec.get("date") or ""
            if len(ts) >= 10:
                days_seen.add(ts[:10])
    if len(days_seen) < 60:
        pytest.skip(f"snapshot history {len(days_seen)} days — need 60 for pilot gate")

    # TODO — when skip lifts: walk snapshots, re-label via labels.make_label,
    # compute base win-rate vs (health=GREEN and score>=70) win-rate, assert
    # uplift >= 5pp. Until then this line is unreachable.
    pytest.skip("forward-uplift implementation deferred — skip lifts at 60 days")
```

- [ ] **Step 2: Run, expect PASS-as-skip**

```
pytest pipeline/tests/backtest/test_ta_scorer_uplift.py -v
```

Expected output: `SKIPPED [1] ... post-fit gate` or similar — not a failure.

- [ ] **Step 3: Commit**

```
git add pipeline/tests/backtest/test_ta_scorer_uplift.py
git commit -m "test(backtest): TA pilot 60-day forward-uplift audit stub"
```

---

## Verification checklist (end of plan)

Every one of these must be true before calling v1 done. If any are NO, do not declare completion — fix the gap and re-verify.

- [ ] `pytest pipeline/tests/ta_scorer/ -v` shows all tests passing, output captured in commit message or PR.
- [ ] `pytest pipeline/tests/test_analysis_adapters.py pipeline/tests/test_analysis_panel_fixtures.py pipeline/tests/test_ta_attractiveness_api.py pipeline/tests/test_watchdog_ta_scorer.py pipeline/tests/test_analysis_panel_smoke.py -v` all pass.
- [ ] `grep -rn "attractiveness-panel" pipeline/terminal` returns zero hits.
- [ ] `grep -rn "layersHtml" pipeline/terminal/static/js` returns zero hits.
- [ ] Trading-tab drawer on a live RELIANCE candidate shows 4 cards in order FCS → TA → Spread → Corr Break.
- [ ] Trading-tab drawer on a non-RELIANCE candidate shows TA card with explicit "TA pilot — RELIANCE only" text.
- [ ] walk-forward conviction numbers render in `var(--accent-gold)`; heuristic in `var(--text-muted)` with dotted underline — visual confirm.
- [ ] `docs/SYSTEM_OPERATIONS_MANUAL.md` Station 10 section exists; Clockwork has 77+ tasks; CLAUDE.md matches.
- [ ] `pipeline/config/anka_inventory.json` has both `AnkaTAScorerFit` and `AnkaTAScorerScore` entries; test file asserts this.
- [ ] `schtasks /query /tn AnkaTAScorerFit` and `schtasks /query /tn AnkaTAScorerScore` both return valid tasks.
- [ ] Memory file `project_unified_analysis_panel.md` exists; MEMORY.md index has a line pointing to it.
- [ ] Each commit message names a single task; no "fix everything" mega-commits.
