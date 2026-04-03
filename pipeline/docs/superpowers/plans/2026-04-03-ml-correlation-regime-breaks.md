# ML Correlation Regime Break Detection — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an ML-driven fragility scoring system that detects when spread correlations are about to break down, integrated into the live Anka Research pipeline.

**Architecture:** Extends existing spread_statistics.py and macro_stress.py. New module `correlation_regime.py` computes rolling correlations, detects change-points, engineers features, and trains XGBoost to produce a per-spread fragility score (0-100). Score feeds into signal_tracker.py for dynamic stop adjustment and website_exporter.py for dashboard display.

**Tech Stack:** Python 3.13, numpy, pandas, scipy (1.17.1), scikit-learn (1.8.0), xgboost (3.2.0) — all in pipeline/lib/. Data from india_historical/ CSVs (988 rows × 66 tickers).

---

## File Structure

| File | Responsibility | Status |
|------|---------------|--------|
| `correlation_regime.py` | Core ML module: rolling correlations, change-point detection, feature engineering, model training, fragility scoring | CREATE |
| `run_fragility.py` | CLI runner: train model, score current state, export results | CREATE |
| `tests/test_correlation_regime.py` | Unit tests for all computation functions | CREATE |
| `data/correlation_history.json` | Cached rolling correlation + break labels | OUTPUT |
| `data/fragility_scores.json` | Current fragility scores per spread pair | OUTPUT |
| `data/fragility_model.json` | Trained model feature importances + metadata | OUTPUT |
| `signal_tracker.py` | MODIFY: read fragility score to adjust stop widths | MODIFY (lines 474-487) |
| `website_exporter.py` | MODIFY: export fragility scores to website JSON | MODIFY |
| `config.py` | MODIFY: add CORRELATION_PAIRS and ML config constants | MODIFY |

---

### Task 1: Define Correlation Pairs and Config

**Files:**
- Modify: `C:\Users\Claude_Anka\Documents\askanka.com\pipeline\config.py`

- [ ] **Step 1: Add correlation pair definitions and ML config to config.py**

Add after the `CORRELATION_THRESHOLDS` line (~line 389):

```python
# === ML CORRELATION REGIME CONFIG ===
# Pairs to track for rolling correlation and regime break detection
CORRELATION_PAIRS = [
    # Index vs sector
    {"name": "Nifty_vs_BankNifty",  "a": "HDFCBANK",  "b": "ICICIBANK", "a_label": "Nifty proxy", "b_label": "Bank proxy"},
    {"name": "Defence_vs_IT",       "a": "HAL",        "b": "TCS",       "a_label": "Defence",     "b_label": "IT"},
    {"name": "Defence_vs_Auto",     "a": "HAL",        "b": "TATAMOTORS","a_label": "Defence",     "b_label": "Auto"},
    {"name": "Upstream_vs_Downstream","a": "ONGC",      "b": "BPCL",     "a_label": "Upstream",    "b_label": "Downstream"},
    {"name": "Metals_vs_IT",        "a": "HINDALCO",   "b": "INFY",     "a_label": "Metals",      "b_label": "IT"},
    {"name": "FMCG_vs_Cyclicals",   "a": "HUL",        "b": "TATAMOTORS","a_label": "FMCG",       "b_label": "Cyclicals"},
    {"name": "Pharma_vs_Banks",     "a": "SUNPHARMA",  "b": "HDFCBANK", "a_label": "Pharma",      "b_label": "Banks"},
    {"name": "PSU_vs_Private",      "a": "SBI",        "b": "HDFCBANK", "a_label": "PSU Bank",    "b_label": "Pvt Bank"},
    {"name": "Coal_vs_OMC",         "a": "COALINDIA",  "b": "BPCL",     "a_label": "Coal",        "b_label": "OMC"},
    {"name": "Finance_vs_Energy",   "a": "BAJFINANCE", "b": "ONGC",     "a_label": "NBFC",        "b_label": "Energy"},
]

# Rolling windows for correlation computation
CORR_WINDOW_SHORT = 21   # ~1 month trading days
CORR_WINDOW_LONG = 63    # ~3 months trading days

# Change-point detection
CORR_BREAK_ZSCORE = 2.0        # Z-score threshold for break detection
CORR_BREAK_MIN_SHIFT = 0.3     # minimum absolute correlation change to flag

# Fragility model
FRAGILITY_FORWARD_WINDOW = 5   # predict break in next N trading days
FRAGILITY_RETRAIN_DAYS = 30    # retrain model every N days
```

- [ ] **Step 2: Commit**

```bash
cd C:\Users\Claude_Anka\Documents\askanka.com\pipeline
git add config.py
git commit -m "feat(config): add correlation pair definitions and ML regime config"
```

---

### Task 2: Rolling Correlation Computation

**Files:**
- Create: `C:\Users\Claude_Anka\Documents\askanka.com\pipeline\correlation_regime.py`
- Create: `C:\Users\Claude_Anka\Documents\askanka.com\pipeline\tests\test_correlation_regime.py`

- [ ] **Step 1: Write failing test for rolling correlation**

Create `tests/test_correlation_regime.py`:

```python
"""Tests for correlation_regime module."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))

import numpy as np
import pandas as pd
import pytest


def _make_price_series(n=100, seed=42):
    """Generate two correlated price series for testing."""
    rng = np.random.RandomState(seed)
    # First half: positively correlated
    base = rng.randn(n).cumsum() + 100
    noise_a = rng.randn(n) * 0.5
    noise_b = rng.randn(n) * 0.5
    prices_a = base + noise_a
    prices_b = base * 0.8 + noise_b + 50  # correlated with a
    dates = pd.bdate_range("2023-01-01", periods=n)
    return pd.Series(prices_a, index=dates), pd.Series(prices_b, index=dates)


def test_compute_rolling_correlation():
    from correlation_regime import compute_rolling_correlation
    a, b = _make_price_series(100)
    result = compute_rolling_correlation(a, b, window=21)
    assert isinstance(result, pd.Series)
    assert len(result) == 100
    # First 20 values should be NaN (not enough data for window=21)
    assert result.iloc[:20].isna().all()
    # After that, correlations should be between -1 and 1
    valid = result.dropna()
    assert (valid >= -1.0).all() and (valid <= 1.0).all()
    assert len(valid) >= 70  # at least 70 valid values


def test_detect_change_points():
    from correlation_regime import compute_rolling_correlation, detect_change_points
    a, b = _make_price_series(200)
    corr = compute_rolling_correlation(a, b, window=21)
    breaks = detect_change_points(corr, zscore_threshold=2.0, min_shift=0.3)
    assert isinstance(breaks, list)
    # Each break should be a dict with date, old_corr, new_corr, zscore
    for bp in breaks:
        assert "date" in bp
        assert "old_corr" in bp
        assert "new_corr" in bp
        assert "zscore" in bp
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd C:\Users\Claude_Anka\Documents\askanka.com\pipeline
python -m pytest tests/test_correlation_regime.py -v
```
Expected: FAIL with `ModuleNotFoundError: No module named 'correlation_regime'`

- [ ] **Step 3: Implement rolling correlation and change-point detection**

Create `correlation_regime.py`:

```python
"""
Anka Research Pipeline — Correlation Regime Break Detection
ML-driven framework for detecting when spread correlations are about to break down.

Stages:
  1. Rolling correlation computation across key asset pairs
  2. Change-point detection using Z-score on correlation shifts
  3. Feature engineering from volatility, flows, breadth, macro
  4. XGBoost model: "will correlation break in next 5 days?"
  5. Fragility score (0-100) per spread pair
"""

import json
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

_lib = str(Path(__file__).parent / "lib")
if _lib not in sys.path:
    sys.path.insert(0, _lib)

import numpy as np
import pandas as pd

log = logging.getLogger("anka.corr_regime")

IST = timezone(timedelta(hours=5, minutes=30))
DATA_DIR = Path(__file__).parent / "data"
HIST_DIR = DATA_DIR / "india_historical"
CORR_HISTORY_FILE = DATA_DIR / "correlation_history.json"
FRAGILITY_FILE = DATA_DIR / "fragility_scores.json"
MODEL_META_FILE = DATA_DIR / "fragility_model.json"


# ──────────────────────────────────────────────────────────
# Stage 1: Rolling Correlation
# ──────────────────────────────────────────────────────────

def load_price_series(ticker: str) -> pd.Series:
    """Load closing prices for a ticker from india_historical/ CSV.

    Returns a pd.Series indexed by date with daily close prices.
    """
    csv_path = HIST_DIR / f"{ticker}.csv"
    if not csv_path.exists():
        log.warning("No historical CSV for %s", ticker)
        return pd.Series(dtype=float)
    df = pd.read_csv(csv_path, parse_dates=["Date"])
    df = df.sort_values("Date").drop_duplicates(subset="Date")
    return pd.Series(df["Close"].values, index=df["Date"], name=ticker, dtype=float)


def compute_rolling_correlation(
    prices_a: pd.Series,
    prices_b: pd.Series,
    window: int = 21,
) -> pd.Series:
    """Compute rolling Pearson correlation of daily returns.

    Args:
        prices_a: daily close prices for asset A
        prices_b: daily close prices for asset B
        window: rolling window in trading days (21 = ~1 month)

    Returns:
        pd.Series of rolling correlations, NaN for initial window.
    """
    # Align on common dates
    combined = pd.DataFrame({"a": prices_a, "b": prices_b}).dropna()
    if len(combined) < window + 5:
        return pd.Series(dtype=float)

    ret_a = combined["a"].pct_change()
    ret_b = combined["b"].pct_change()

    rolling_corr = ret_a.rolling(window=window).corr(ret_b)

    # Reindex to original prices_a index, filling gaps with NaN
    return rolling_corr.reindex(prices_a.index)


def detect_change_points(
    rolling_corr: pd.Series,
    zscore_threshold: float = 2.0,
    min_shift: float = 0.3,
) -> list[dict]:
    """Detect points where rolling correlation shifts significantly.

    Uses Z-score of day-over-day correlation change relative to
    the rolling standard deviation of correlation changes.

    Args:
        rolling_corr: output of compute_rolling_correlation
        zscore_threshold: Z-score above which a change is flagged
        min_shift: minimum absolute correlation change to flag

    Returns:
        List of break dicts: {date, old_corr, new_corr, zscore, shift}
    """
    clean = rolling_corr.dropna()
    if len(clean) < 30:
        return []

    changes = clean.diff()
    rolling_std = changes.rolling(window=63, min_periods=21).std()

    breaks = []
    for i in range(1, len(changes)):
        if pd.isna(changes.iloc[i]) or pd.isna(rolling_std.iloc[i]):
            continue
        if rolling_std.iloc[i] == 0:
            continue

        z = abs(changes.iloc[i]) / rolling_std.iloc[i]
        shift = abs(changes.iloc[i])

        if z >= zscore_threshold and shift >= min_shift:
            date = clean.index[i]
            breaks.append({
                "date": date.strftime("%Y-%m-%d") if hasattr(date, "strftime") else str(date),
                "old_corr": round(float(clean.iloc[i - 1]), 4),
                "new_corr": round(float(clean.iloc[i]), 4),
                "zscore": round(float(z), 2),
                "shift": round(float(changes.iloc[i]), 4),
            })

    return breaks


def label_regimes(
    rolling_corr: pd.Series,
    breaks: list[dict],
    forward_window: int = 5,
) -> pd.Series:
    """Label each date as STABLE (0), PRE_BREAK (1), or BREAK (2).

    PRE_BREAK = within forward_window days BEFORE a break.
    BREAK = the break date itself.
    STABLE = everything else.

    This creates the target variable for supervised learning.
    """
    labels = pd.Series(0, index=rolling_corr.dropna().index, dtype=int)

    break_dates = []
    for bp in breaks:
        try:
            dt = pd.Timestamp(bp["date"])
            break_dates.append(dt)
        except Exception:
            continue

    for bd in break_dates:
        # Label break date
        if bd in labels.index:
            labels.loc[bd] = 2

        # Label pre-break window
        for i in range(1, forward_window + 1):
            pre = bd - pd.tseries.offsets.BDay(i)
            if pre in labels.index:
                labels.loc[pre] = 1

    return labels
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd C:\Users\Claude_Anka\Documents\askanka.com\pipeline
python -m pytest tests/test_correlation_regime.py -v
```
Expected: 2 tests PASS

- [ ] **Step 5: Commit**

```bash
git add correlation_regime.py tests/test_correlation_regime.py
git commit -m "feat: rolling correlation + change-point detection (Stage 1)"
```

---

### Task 3: Compute Full Correlation History

**Files:**
- Modify: `C:\Users\Claude_Anka\Documents\askanka.com\pipeline\correlation_regime.py`

- [ ] **Step 1: Write failing test for full history computation**

Append to `tests/test_correlation_regime.py`:

```python
def test_compute_all_pair_correlations():
    from correlation_regime import compute_all_pair_correlations
    from config import CORRELATION_PAIRS
    # Just test it runs without error on real data
    result = compute_all_pair_correlations(CORRELATION_PAIRS[:2], windows=[21])
    assert isinstance(result, dict)
    assert len(result) > 0
    for pair_name, pair_data in result.items():
        assert "breaks" in pair_data
        assert "corr_21" in pair_data
        assert isinstance(pair_data["breaks"], list)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_correlation_regime.py::test_compute_all_pair_correlations -v
```

- [ ] **Step 3: Implement compute_all_pair_correlations**

Add to `correlation_regime.py`:

```python
def compute_all_pair_correlations(
    pairs: list[dict] | None = None,
    windows: list[int] | None = None,
) -> dict[str, dict]:
    """Compute rolling correlations and detect breaks for all configured pairs.

    Returns dict keyed by pair name:
    {
        "Defence_vs_IT": {
            "a": "HAL", "b": "TCS",
            "corr_21": [{"date": "...", "value": 0.75}, ...],
            "corr_63": [...],
            "breaks": [...],
            "current_corr_21": 0.65,
            "current_corr_63": 0.72,
            "labels": [{"date": "...", "label": 0}, ...],
        }
    }
    """
    if pairs is None:
        from config import CORRELATION_PAIRS
        pairs = CORRELATION_PAIRS
    if windows is None:
        from config import CORR_WINDOW_SHORT, CORR_WINDOW_LONG
        windows = [CORR_WINDOW_SHORT, CORR_WINDOW_LONG]

    from config import CORR_BREAK_ZSCORE, CORR_BREAK_MIN_SHIFT, FRAGILITY_FORWARD_WINDOW

    results = {}

    for pair in pairs:
        name = pair["name"]
        prices_a = load_price_series(pair["a"])
        prices_b = load_price_series(pair["b"])

        if prices_a.empty or prices_b.empty:
            log.warning("Skipping %s — missing price data", name)
            continue

        pair_data = {
            "a": pair["a"],
            "b": pair["b"],
            "a_label": pair.get("a_label", pair["a"]),
            "b_label": pair.get("b_label", pair["b"]),
        }

        all_breaks = []
        for w in windows:
            corr = compute_rolling_correlation(prices_a, prices_b, window=w)
            clean = corr.dropna()

            # Store time series (sampled weekly to keep JSON small)
            weekly = clean.resample("W").last().dropna()
            pair_data[f"corr_{w}"] = [
                {"date": d.strftime("%Y-%m-%d"), "value": round(float(v), 4)}
                for d, v in weekly.items()
            ]

            # Current value
            if not clean.empty:
                pair_data[f"current_corr_{w}"] = round(float(clean.iloc[-1]), 4)

            # Detect breaks
            breaks = detect_change_points(corr, CORR_BREAK_ZSCORE, CORR_BREAK_MIN_SHIFT)
            all_breaks.extend(breaks)

        # Deduplicate breaks by date
        seen_dates = set()
        unique_breaks = []
        for bp in sorted(all_breaks, key=lambda x: x["date"]):
            if bp["date"] not in seen_dates:
                seen_dates.add(bp["date"])
                unique_breaks.append(bp)

        pair_data["breaks"] = unique_breaks
        pair_data["n_breaks"] = len(unique_breaks)

        # Labels for supervised learning
        primary_corr = compute_rolling_correlation(prices_a, prices_b, window=windows[0])
        labels = label_regimes(primary_corr, unique_breaks, FRAGILITY_FORWARD_WINDOW)
        pair_data["label_counts"] = {
            "stable": int((labels == 0).sum()),
            "pre_break": int((labels == 1).sum()),
            "break": int((labels == 2).sum()),
        }

        results[name] = pair_data
        log.info("%s: %d breaks detected, corr_%d = %.3f",
                 name, len(unique_breaks), windows[0],
                 pair_data.get(f"current_corr_{windows[0]}", 0))

    return results


def save_correlation_history(results: dict) -> None:
    """Save correlation history to JSON."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    output = {
        "computed_at": datetime.now(IST).isoformat(),
        "pairs": results,
    }
    CORR_HISTORY_FILE.write_text(json.dumps(output, indent=2, default=str), encoding="utf-8")
    log.info("Saved correlation history: %d pairs", len(results))
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/test_correlation_regime.py -v
```

- [ ] **Step 5: Run on real data to verify**

```bash
cd C:\Users\Claude_Anka\Documents\askanka.com\pipeline
python -c "
import sys; sys.path.insert(0, 'lib')
import logging; logging.basicConfig(level=logging.INFO, format='%(message)s')
from correlation_regime import compute_all_pair_correlations, save_correlation_history
results = compute_all_pair_correlations()
save_correlation_history(results)
for name, data in results.items():
    print(f'{name}: {data[\"n_breaks\"]} breaks, corr_21={data.get(\"current_corr_21\", \"?\")}, labels={data[\"label_counts\"]}')
"
```

- [ ] **Step 6: Commit**

```bash
git add correlation_regime.py tests/test_correlation_regime.py
git commit -m "feat: compute full correlation history for 10 pairs (Stage 1 complete)"
```

---

### Task 4: Feature Engineering

**Files:**
- Modify: `C:\Users\Claude_Anka\Documents\askanka.com\pipeline\correlation_regime.py`
- Modify: `C:\Users\Claude_Anka\Documents\askanka.com\pipeline\tests\test_correlation_regime.py`

- [ ] **Step 1: Write failing test for feature engineering**

Append to `tests/test_correlation_regime.py`:

```python
def test_engineer_features():
    from correlation_regime import engineer_features, load_price_series
    prices_a = load_price_series("HAL")
    prices_b = load_price_series("TCS")
    features = engineer_features(prices_a, prices_b)
    assert isinstance(features, pd.DataFrame)
    assert len(features) > 100
    # Check key feature columns exist
    expected_cols = [
        "ret_a_5d_vol", "ret_b_5d_vol", "ret_a_21d_vol", "ret_b_21d_vol",
        "corr_21", "corr_63", "corr_change_5d", "corr_change_21d",
        "dispersion_5d", "volume_shock_a", "volume_shock_b",
        "beta_instability",
    ]
    for col in expected_cols:
        assert col in features.columns, f"Missing feature: {col}"
    # No inf values
    assert not features.replace([np.inf, -np.inf], np.nan).isna().all(axis=1).any()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_correlation_regime.py::test_engineer_features -v
```

- [ ] **Step 3: Implement feature engineering**

Add to `correlation_regime.py`:

```python
# ──────────────────────────────────────────────────────────
# Stage 2: Feature Engineering
# ──────────────────────────────────────────────────────────

def _load_volume_series(ticker: str) -> pd.Series:
    """Load volume series from india_historical/ CSV."""
    csv_path = HIST_DIR / f"{ticker}.csv"
    if not csv_path.exists():
        return pd.Series(dtype=float)
    df = pd.read_csv(csv_path, parse_dates=["Date"])
    df = df.sort_values("Date").drop_duplicates(subset="Date")
    return pd.Series(df["Volume"].values, index=df["Date"], name=f"{ticker}_vol", dtype=float)


def engineer_features(
    prices_a: pd.Series,
    prices_b: pd.Series,
    vol_a: pd.Series | None = None,
    vol_b: pd.Series | None = None,
) -> pd.DataFrame:
    """Engineer ML features from two price series for regime break prediction.

    Features capture:
      - Realized volatility (5d, 21d) for both assets
      - Rolling correlation at two windows + rate of change
      - Cross-sectional dispersion (return spread volatility)
      - Volume shocks (today vs 20d avg)
      - Rolling beta instability
      - Return momentum and mean reversion signals

    Returns DataFrame indexed by date, one row per trading day.
    """
    combined = pd.DataFrame({"a": prices_a, "b": prices_b}).dropna()
    if len(combined) < 100:
        return pd.DataFrame()

    ret_a = combined["a"].pct_change()
    ret_b = combined["b"].pct_change()

    features = pd.DataFrame(index=combined.index)

    # ── Realized volatility ──
    features["ret_a_5d_vol"] = ret_a.rolling(5).std()
    features["ret_b_5d_vol"] = ret_b.rolling(5).std()
    features["ret_a_21d_vol"] = ret_a.rolling(21).std()
    features["ret_b_21d_vol"] = ret_b.rolling(21).std()

    # Volatility ratio (short-term spike relative to longer-term)
    features["vol_ratio_a"] = features["ret_a_5d_vol"] / features["ret_a_21d_vol"].replace(0, np.nan)
    features["vol_ratio_b"] = features["ret_b_5d_vol"] / features["ret_b_21d_vol"].replace(0, np.nan)

    # ── Rolling correlations ──
    features["corr_21"] = ret_a.rolling(21).corr(ret_b)
    features["corr_63"] = ret_a.rolling(63).corr(ret_b)

    # Correlation rate of change
    features["corr_change_5d"] = features["corr_21"].diff(5)
    features["corr_change_21d"] = features["corr_21"].diff(21)

    # Correlation level relative to 63d (is short-term diverging from long-term?)
    features["corr_divergence"] = features["corr_21"] - features["corr_63"]

    # ── Cross-sectional dispersion ──
    spread_ret = ret_a - ret_b
    features["dispersion_5d"] = spread_ret.rolling(5).std()
    features["dispersion_21d"] = spread_ret.rolling(21).std()
    features["dispersion_ratio"] = features["dispersion_5d"] / features["dispersion_21d"].replace(0, np.nan)

    # ── Volume shocks ──
    if vol_a is not None and not vol_a.empty:
        vol_a_aligned = vol_a.reindex(combined.index)
        features["volume_shock_a"] = vol_a_aligned / vol_a_aligned.rolling(20).mean().replace(0, np.nan)
    else:
        features["volume_shock_a"] = 1.0

    if vol_b is not None and not vol_b.empty:
        vol_b_aligned = vol_b.reindex(combined.index)
        features["volume_shock_b"] = vol_b_aligned / vol_b_aligned.rolling(20).mean().replace(0, np.nan)
    else:
        features["volume_shock_b"] = 1.0

    # ── Rolling beta instability ──
    # Beta = cov(a,b) / var(b), measure its stability
    cov_21 = ret_a.rolling(21).cov(ret_b)
    var_b_21 = ret_b.rolling(21).var()
    beta_21 = cov_21 / var_b_21.replace(0, np.nan)
    features["beta_21"] = beta_21
    features["beta_instability"] = beta_21.rolling(21).std()

    # ── Return momentum ──
    features["ret_a_5d"] = combined["a"].pct_change(5)
    features["ret_b_5d"] = combined["b"].pct_change(5)
    features["ret_a_21d"] = combined["a"].pct_change(21)
    features["ret_b_21d"] = combined["b"].pct_change(21)

    # Spread momentum (divergence in returns)
    features["spread_momentum_5d"] = features["ret_a_5d"] - features["ret_b_5d"]
    features["spread_momentum_21d"] = features["ret_a_21d"] - features["ret_b_21d"]

    # ── Clean up ──
    features = features.replace([np.inf, -np.inf], np.nan)

    return features
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/test_correlation_regime.py -v
```

- [ ] **Step 5: Commit**

```bash
git add correlation_regime.py tests/test_correlation_regime.py
git commit -m "feat: feature engineering — volatility, dispersion, beta instability (Stage 2)"
```

---

### Task 5: XGBoost Fragility Model

**Files:**
- Modify: `C:\Users\Claude_Anka\Documents\askanka.com\pipeline\correlation_regime.py`
- Modify: `C:\Users\Claude_Anka\Documents\askanka.com\pipeline\tests\test_correlation_regime.py`

- [ ] **Step 1: Write failing test for model training**

Append to `tests/test_correlation_regime.py`:

```python
def test_train_fragility_model():
    from correlation_regime import train_fragility_model
    result = train_fragility_model(min_pairs=2)
    assert isinstance(result, dict)
    assert "accuracy" in result
    assert "feature_importance" in result
    assert "n_samples" in result
    assert result["n_samples"] > 50
    assert len(result["feature_importance"]) > 5


def test_score_current_fragility():
    from correlation_regime import score_current_fragility
    scores = score_current_fragility()
    assert isinstance(scores, dict)
    # Each pair should have a score 0-100
    for pair_name, score_data in scores.items():
        assert 0 <= score_data["fragility_score"] <= 100
        assert "top_drivers" in score_data
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_correlation_regime.py::test_train_fragility_model -v
```

- [ ] **Step 3: Implement training and scoring**

Add to `correlation_regime.py`:

```python
# ──────────────────────────────────────────────────────────
# Stage 3: XGBoost Fragility Model
# ──────────────────────────────────────────────────────────

def _build_training_data(
    pairs: list[dict] | None = None,
) -> tuple[pd.DataFrame, pd.Series]:
    """Build X (features) and y (labels) from all pairs.

    Pools data across all pairs to create a single training set.
    Label: 1 if PRE_BREAK or BREAK, 0 if STABLE.
    """
    if pairs is None:
        from config import CORRELATION_PAIRS
        pairs = CORRELATION_PAIRS
    from config import CORR_WINDOW_SHORT, CORR_BREAK_ZSCORE, CORR_BREAK_MIN_SHIFT, FRAGILITY_FORWARD_WINDOW

    all_X = []
    all_y = []

    for pair in pairs:
        prices_a = load_price_series(pair["a"])
        prices_b = load_price_series(pair["b"])
        if prices_a.empty or prices_b.empty:
            continue

        vol_a = _load_volume_series(pair["a"])
        vol_b = _load_volume_series(pair["b"])

        features = engineer_features(prices_a, prices_b, vol_a, vol_b)
        if features.empty:
            continue

        corr = compute_rolling_correlation(prices_a, prices_b, window=CORR_WINDOW_SHORT)
        breaks = detect_change_points(corr, CORR_BREAK_ZSCORE, CORR_BREAK_MIN_SHIFT)
        labels = label_regimes(corr, breaks, FRAGILITY_FORWARD_WINDOW)

        # Align features and labels
        common_idx = features.index.intersection(labels.index)
        X = features.loc[common_idx]
        y = labels.loc[common_idx]

        # Binary: 1 = pre-break or break, 0 = stable
        y_binary = (y >= 1).astype(int)

        all_X.append(X)
        all_y.append(y_binary)

    if not all_X:
        return pd.DataFrame(), pd.Series(dtype=int)

    X_combined = pd.concat(all_X, axis=0)
    y_combined = pd.concat(all_y, axis=0)

    # Drop rows with NaN features
    mask = X_combined.notna().all(axis=1)
    return X_combined[mask], y_combined[mask]


def train_fragility_model(min_pairs: int = 5) -> dict:
    """Train XGBoost classifier for correlation break prediction.

    Uses walk-forward split: first 80% for training, last 20% for validation.
    Returns metadata dict with accuracy, feature importance, and model stats.
    """
    from sklearn.model_selection import TimeSeriesSplit
    from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score
    import xgboost as xgb

    X, y = _build_training_data()

    if len(X) < 100:
        log.warning("Insufficient training data: %d rows", len(X))
        return {"error": "insufficient_data", "n_samples": len(X)}

    # Walk-forward split
    split_idx = int(len(X) * 0.8)
    X_train, X_test = X.iloc[:split_idx], X.iloc[split_idx:]
    y_train, y_test = y.iloc[:split_idx], y.iloc[split_idx:]

    # Handle class imbalance
    n_stable = (y_train == 0).sum()
    n_break = (y_train == 1).sum()
    scale_pos_weight = n_stable / max(n_break, 1)

    model = xgb.XGBClassifier(
        n_estimators=200,
        max_depth=4,
        learning_rate=0.05,
        scale_pos_weight=scale_pos_weight,
        random_state=42,
        eval_metric="logloss",
        verbosity=0,
    )
    model.fit(X_train, y_train)

    # Evaluate
    y_pred = model.predict(X_test)
    y_prob = model.predict_proba(X_test)[:, 1]

    accuracy = accuracy_score(y_test, y_pred)
    precision = precision_score(y_test, y_pred, zero_division=0)
    recall = recall_score(y_test, y_pred, zero_division=0)
    f1 = f1_score(y_test, y_pred, zero_division=0)

    # Feature importance
    importance = dict(zip(X.columns, model.feature_importances_))
    sorted_imp = sorted(importance.items(), key=lambda x: -x[1])

    result = {
        "trained_at": datetime.now(IST).isoformat(),
        "n_samples": len(X),
        "n_train": len(X_train),
        "n_test": len(X_test),
        "class_balance": {
            "stable": int((y == 0).sum()),
            "pre_break_or_break": int((y == 1).sum()),
        },
        "accuracy": round(accuracy, 4),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1_score": round(f1, 4),
        "feature_importance": [
            {"feature": name, "importance": round(float(imp), 4)}
            for name, imp in sorted_imp
        ],
    }

    # Save model for scoring
    _TRAINED_MODEL_CACHE["model"] = model
    _TRAINED_MODEL_CACHE["features"] = list(X.columns)

    # Save metadata
    MODEL_META_FILE.write_text(json.dumps(result, indent=2), encoding="utf-8")
    log.info("Model trained: accuracy=%.3f precision=%.3f recall=%.3f f1=%.3f (n=%d)",
             accuracy, precision, recall, f1, len(X))

    return result


# In-memory cache for trained model (avoids re-training on every call)
_TRAINED_MODEL_CACHE: dict = {}


def score_current_fragility(
    pairs: list[dict] | None = None,
) -> dict[str, dict]:
    """Score current fragility for each pair using the trained model.

    Returns:
    {
        "Defence_vs_IT": {
            "fragility_score": 73,
            "probability": 0.73,
            "top_drivers": [{"feature": "corr_change_5d", "importance": 0.18}, ...],
            "current_corr_21": 0.65,
        }
    }
    """
    if "model" not in _TRAINED_MODEL_CACHE:
        log.info("No trained model in cache — training now")
        train_fragility_model()

    model = _TRAINED_MODEL_CACHE.get("model")
    feature_cols = _TRAINED_MODEL_CACHE.get("features", [])

    if model is None:
        return {}

    if pairs is None:
        from config import CORRELATION_PAIRS
        pairs = CORRELATION_PAIRS

    scores = {}
    for pair in pairs:
        name = pair["name"]
        prices_a = load_price_series(pair["a"])
        prices_b = load_price_series(pair["b"])
        if prices_a.empty or prices_b.empty:
            continue

        vol_a = _load_volume_series(pair["a"])
        vol_b = _load_volume_series(pair["b"])
        features = engineer_features(prices_a, prices_b, vol_a, vol_b)
        if features.empty:
            continue

        # Get latest row
        latest = features.iloc[-1:]

        # Align columns
        for col in feature_cols:
            if col not in latest.columns:
                latest[col] = 0
        latest = latest[feature_cols]

        if latest.isna().any(axis=1).iloc[0]:
            # Fill NaN with 0 for scoring
            latest = latest.fillna(0)

        try:
            prob = model.predict_proba(latest)[0, 1]
        except Exception as exc:
            log.warning("Scoring failed for %s: %s", name, exc)
            continue

        fragility_score = int(round(prob * 100))

        # Top drivers from model feature importance
        importance = dict(zip(feature_cols, model.feature_importances_))
        top_drivers = sorted(importance.items(), key=lambda x: -x[1])[:5]

        # Current correlation
        from config import CORR_WINDOW_SHORT
        corr = compute_rolling_correlation(prices_a, prices_b, window=CORR_WINDOW_SHORT)
        current_corr = float(corr.dropna().iloc[-1]) if not corr.dropna().empty else 0

        scores[name] = {
            "fragility_score": fragility_score,
            "probability": round(float(prob), 4),
            "top_drivers": [
                {"feature": f, "importance": round(float(imp), 4)}
                for f, imp in top_drivers
            ],
            "current_corr_21": round(current_corr, 4),
        }

    return scores


def save_fragility_scores(scores: dict) -> None:
    """Save fragility scores to JSON for website and pipeline consumption."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    output = {
        "scored_at": datetime.now(IST).isoformat(),
        "scores": scores,
    }
    FRAGILITY_FILE.write_text(json.dumps(output, indent=2, default=str), encoding="utf-8")
    log.info("Saved fragility scores: %d pairs", len(scores))
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/test_correlation_regime.py -v
```

- [ ] **Step 5: Run on real data**

```bash
cd C:\Users\Claude_Anka\Documents\askanka.com\pipeline
python -c "
import sys; sys.path.insert(0, 'lib')
import logging; logging.basicConfig(level=logging.INFO, format='%(message)s')
from correlation_regime import train_fragility_model, score_current_fragility, save_fragility_scores

print('=== Training fragility model ===')
result = train_fragility_model()
print(f'Accuracy: {result[\"accuracy\"]:.1%}')
print(f'Precision: {result[\"precision\"]:.1%}')
print(f'Recall: {result[\"recall\"]:.1%}')
print(f'F1: {result[\"f1_score\"]:.1%}')
print(f'Samples: {result[\"n_samples\"]}')
print()
print('Top features:')
for f in result['feature_importance'][:8]:
    print(f'  {f[\"feature\"]:<25} {f[\"importance\"]:.3f}')

print()
print('=== Scoring current fragility ===')
scores = score_current_fragility()
save_fragility_scores(scores)
for name, s in sorted(scores.items(), key=lambda x: -x[1]['fragility_score']):
    print(f'  {name:<30} fragility={s[\"fragility_score\"]:3d}/100  corr_21={s[\"current_corr_21\"]:+.3f}')
"
```

- [ ] **Step 6: Commit**

```bash
git add correlation_regime.py tests/test_correlation_regime.py data/fragility_model.json
git commit -m "feat: XGBoost fragility model — train, score, save (Stage 3)"
```

---

### Task 6: CLI Runner

**Files:**
- Create: `C:\Users\Claude_Anka\Documents\askanka.com\pipeline\run_fragility.py`

- [ ] **Step 1: Create CLI runner**

```python
"""
Anka Research — Correlation Fragility Score Runner
Trains the XGBoost model and scores current fragility for all spread pairs.

Usage:
    python run_fragility.py              # train + score + save
    python run_fragility.py --score-only # score using cached model
    python run_fragility.py --history    # compute + save correlation history
"""

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent / "lib"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)


def main():
    parser = argparse.ArgumentParser(description="Anka Fragility Score Runner")
    parser.add_argument("--score-only", action="store_true", help="Score only (skip training)")
    parser.add_argument("--history", action="store_true", help="Compute correlation history only")
    args = parser.parse_args()

    from correlation_regime import (
        compute_all_pair_correlations,
        save_correlation_history,
        train_fragility_model,
        score_current_fragility,
        save_fragility_scores,
    )

    if args.history:
        print("\n=== Computing correlation history ===")
        results = compute_all_pair_correlations()
        save_correlation_history(results)
        for name, data in results.items():
            print(f"  {name}: {data['n_breaks']} breaks, corr_21={data.get('current_corr_21', '?')}")
        return

    if not args.score_only:
        print("\n=== Training fragility model ===")
        result = train_fragility_model()
        if "error" in result:
            print(f"Training failed: {result['error']}")
            return
        print(f"  Accuracy:  {result['accuracy']:.1%}")
        print(f"  Precision: {result['precision']:.1%}")
        print(f"  Recall:    {result['recall']:.1%}")
        print(f"  F1 Score:  {result['f1_score']:.1%}")
        print(f"  Samples:   {result['n_samples']}")
        print(f"\n  Top features:")
        for f in result["feature_importance"][:8]:
            print(f"    {f['feature']:<25} {f['importance']:.3f}")

    print("\n=== Scoring current fragility ===")
    scores = score_current_fragility()
    save_fragility_scores(scores)

    print(f"\n  {'Pair':<30} {'Fragility':>10} {'Corr_21':>10}")
    print("  " + "-" * 52)
    for name, s in sorted(scores.items(), key=lambda x: -x[1]["fragility_score"]):
        bar = "#" * (s["fragility_score"] // 5)
        print(f"  {name:<30} {s['fragility_score']:>6}/100  {s['current_corr_21']:>+8.3f}  {bar}")

    print(f"\n  Scores saved to data/fragility_scores.json")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run it**

```bash
cd C:\Users\Claude_Anka\Documents\askanka.com\pipeline
python run_fragility.py
```

- [ ] **Step 3: Commit**

```bash
git add run_fragility.py
git commit -m "feat: CLI runner for fragility model — train + score + save"
```

---

### Task 7: Integration — Dynamic Stop Widths

**Files:**
- Modify: `C:\Users\Claude_Anka\Documents\askanka.com\pipeline\signal_tracker.py` (lines 474-487)

- [ ] **Step 1: Wire fragility score into stop adjustment**

In `signal_tracker.py`, find the MACRO_STRESS stop widener block (lines ~477-487) and extend it:

Replace this block:
```python
    # Volatility-adjusted stops: widen by 1.5x during MACRO_STRESS to avoid
    # noise-triggered exits in high-volatility regimes
    try:
        from macro_stress import compute_msi
        _msi = compute_msi()
        if _msi.get("regime") == "MACRO_STRESS":
            daily_stop = daily_stop * 1.5
            two_day_stop = two_day_stop * 1.5
            log.debug("MACRO_STRESS active — stops widened 1.5x for %s", spread_name)
    except Exception:
        pass  # MSI unavailable — use unmodified stops
```

With:
```python
    # Volatility-adjusted stops: widen based on MSI regime + fragility score
    stop_multiplier = 1.0

    # 1. MSI regime widening
    try:
        from macro_stress import compute_msi
        _msi = compute_msi()
        if _msi.get("regime") == "MACRO_STRESS":
            stop_multiplier = 1.5
            log.debug("MACRO_STRESS active — base multiplier 1.5x for %s", spread_name)
    except Exception:
        pass

    # 2. Fragility score widening (additive on top of MSI)
    try:
        import json as _json
        _frag_file = Path(__file__).parent / "data" / "fragility_scores.json"
        if _frag_file.exists():
            _frag_data = _json.loads(_frag_file.read_text(encoding="utf-8"))
            # Find fragility for any pair that contains this spread's tickers
            _spread_tickers = set(
                l["ticker"] for l in signal.get("long_legs", [])
            ) | set(
                s["ticker"] for s in signal.get("short_legs", [])
            )
            for _pair_name, _score in _frag_data.get("scores", {}).items():
                if _score.get("fragility_score", 0) >= 70:
                    # Check if this pair's tickers overlap with the spread
                    from config import CORRELATION_PAIRS
                    _pair_cfg = next((p for p in CORRELATION_PAIRS if p["name"] == _pair_name), None)
                    if _pair_cfg and (
                        _pair_cfg["a"] in _spread_tickers or _pair_cfg["b"] in _spread_tickers
                    ):
                        frag_mult = 1.0 + (_score["fragility_score"] - 50) / 100  # 70→1.2, 90→1.4
                        stop_multiplier = max(stop_multiplier, frag_mult)
                        log.debug("Fragility %d for %s — multiplier %.2f for %s",
                                  _score["fragility_score"], _pair_name, frag_mult, spread_name)
    except Exception as _exc:
        log.debug("Fragility score unavailable: %s", _exc)

    daily_stop = daily_stop * stop_multiplier
    two_day_stop = two_day_stop * stop_multiplier
```

- [ ] **Step 2: Run existing signal tracker to verify no regression**

```bash
cd C:\Users\Claude_Anka\Documents\askanka.com\pipeline
python -c "
import sys; sys.path.insert(0, 'lib')
from signal_tracker import load_open_signals
sigs = load_open_signals()
print(f'{len(sigs)} open signals loaded without error')
"
```

- [ ] **Step 3: Commit**

```bash
git add signal_tracker.py
git commit -m "feat: wire fragility score into dynamic stop widths"
```

---

### Task 8: Integration — Website Export

**Files:**
- Modify: `C:\Users\Claude_Anka\Documents\askanka.com\pipeline\website_exporter.py`

- [ ] **Step 1: Add fragility scores to live_status export**

In `website_exporter.py`, in the `export_live_status()` function, add after the `positions` list is built:

```python
    # Fragility scores
    fragility = {}
    frag_file = DATA_DIR / "fragility_scores.json"
    if frag_file.exists():
        try:
            frag_data = json.loads(frag_file.read_text(encoding="utf-8"))
            fragility = frag_data.get("scores", {})
        except Exception:
            pass
```

And add `"fragility": fragility` to the return dict.

- [ ] **Step 2: Commit**

```bash
git add website_exporter.py
git commit -m "feat: export fragility scores to website JSON"
```

---

## Execution Summary

| Task | What | Time est. |
|------|------|-----------|
| 1 | Config: correlation pairs + ML constants | 2 min |
| 2 | Rolling correlation + change-point detection | 10 min |
| 3 | Full correlation history computation | 8 min |
| 4 | Feature engineering (volatility, beta, dispersion) | 10 min |
| 5 | XGBoost fragility model (train + score) | 15 min |
| 6 | CLI runner | 3 min |
| 7 | Integration: dynamic stop widths | 5 min |
| 8 | Integration: website export | 3 min |

**Total: ~56 minutes of execution time**
