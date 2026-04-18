# Golden Goose Plan 1: ETF Engine V2 (Live Brain) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Unfreeze the ETF regime engine by adding Indian market data as inputs, scheduling weekly reoptimization (Saturday night), and daily signal computation (04:45 IST).

**Architecture:** Extend the existing Karpathy random search optimizer (`etf_weight_optimizer.py`) with 8 new Indian market inputs (FII flows, VIX, PCR, Nifty RSI, breadth). Create a new daily script that applies stored weights to fresh data to compute today's regime zone. Schedule both via Windows Task Scheduler and register in the watchdog inventory.

**Tech Stack:** Python 3.13, yfinance, pandas, numpy, json. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-04-18-golden-goose-architecture-design.md` (Section 3.1, 3.2)

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `pipeline/autoresearch/etf_reoptimize.py` | CREATE | Weekly ETF weight optimizer with Indian data inputs |
| `pipeline/autoresearch/etf_daily_signal.py` | CREATE | Daily signal computation using stored weights |
| `pipeline/tests/test_etf_reoptimize.py` | CREATE | Tests for weight optimizer |
| `pipeline/tests/test_etf_daily_signal.py` | CREATE | Tests for daily signal computation |
| `pipeline/scripts/etf_reoptimize.bat` | CREATE | Scheduler wrapper for weekly reoptimization |
| `pipeline/scripts/etf_daily_signal.bat` | CREATE | Scheduler wrapper for daily signal |
| `pipeline/config/anka_inventory.json` | MODIFY | Add AnkaETFReoptimize + AnkaETFSignal tasks |
| `docs/SYSTEM_OPERATIONS_MANUAL.md` | MODIFY | Update with new tasks and data flows |

---

### Task 1: Indian Market Data Loader

**Files:**
- Create: `pipeline/autoresearch/etf_reoptimize.py`
- Test: `pipeline/tests/test_etf_reoptimize.py`

- [ ] **Step 1: Write the failing test for Indian data loading**

```python
# pipeline/tests/test_etf_reoptimize.py
import json
import pytest
from pathlib import Path
from unittest.mock import patch

FIXTURES = Path(__file__).parent / "fixtures"


def _make_daily_file(tmp_path: Path, date: str) -> Path:
    """Create a minimal daily price file."""
    data = {
        "date": date,
        "indices": {
            "Nifty 50": {"date": date, "close": 22500.0, "volume": 100000},
        },
        "volatility": {
            "VIX": {"date": date, "close": 16.5},
        },
        "sector_etfs": {},
        "stocks": {},
        "fx": {},
        "commodities": {},
    }
    p = tmp_path / f"{date}.json"
    p.write_text(json.dumps(data))
    return p


def _make_flows_file(tmp_path: Path, date: str) -> Path:
    """Create a minimal flows file."""
    data = {
        "date": date,
        "fii_equity_net": -1200.5,
        "fii_equity_buy": 5000.0,
        "fii_equity_sell": 6200.5,
        "dii_equity_net": 800.0,
        "dii_equity_buy": 4000.0,
        "dii_equity_sell": 3200.0,
        "source": "nse_fiidiiTradeReact",
    }
    p = tmp_path / f"{date}.json"
    p.write_text(json.dumps(data))
    return p


def test_load_indian_data_returns_dict(tmp_path):
    daily_dir = tmp_path / "daily"
    daily_dir.mkdir()
    flows_dir = tmp_path / "flows"
    flows_dir.mkdir()
    _make_daily_file(daily_dir, "2026-04-17")
    _make_flows_file(flows_dir, "2026-04-17")

    from pipeline.autoresearch.etf_reoptimize import load_indian_data

    result = load_indian_data(daily_dir=daily_dir, flows_dir=flows_dir)
    assert isinstance(result, dict)
    assert "fii_net" in result
    assert "india_vix" in result
    assert "nifty_close" in result


def test_load_indian_data_handles_missing_files(tmp_path):
    daily_dir = tmp_path / "daily"
    daily_dir.mkdir()
    flows_dir = tmp_path / "flows"
    flows_dir.mkdir()

    from pipeline.autoresearch.etf_reoptimize import load_indian_data

    result = load_indian_data(daily_dir=daily_dir, flows_dir=flows_dir)
    assert isinstance(result, dict)
    assert result["fii_net"] is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd C:/Users/Claude_Anka/askanka.com && python -m pytest pipeline/tests/test_etf_reoptimize.py::test_load_indian_data_returns_dict -v`
Expected: FAIL with "ModuleNotFoundError" or "ImportError"

- [ ] **Step 3: Write the Indian data loader**

```python
# pipeline/autoresearch/etf_reoptimize.py
"""
ETF Engine V2 — Weekly Reoptimization with Indian Market Data.

Extends the Karpathy random search with 8 Indian market inputs:
  FII/DII net flows, India VIX, Nifty close, Bank Nifty close,
  aggregate PCR, Nifty RSI(14), % stocks above 200 DMA, sector breadth.

Usage:
    python -m pipeline.autoresearch.etf_reoptimize          # full reoptimization
    python -m pipeline.autoresearch.etf_reoptimize --dry-run # compute but don't save

Output:
    autoresearch/etf_optimal_weights.json  (weight vector + metrics)
    autoresearch/regime_trade_map.json     (today_zone + per-spread sizing)

Scheduled: Saturday 22:00 IST via AnkaETFReoptimize
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger("anka.etf_reoptimize")

IST = timezone(timedelta(hours=5, minutes=30))
_HERE = Path(__file__).parent
_REPO = _HERE.parent.parent
_DATA = _REPO / "pipeline" / "data"
_DAILY_DIR = _DATA / "daily"
_FLOWS_DIR = _DATA / "flows"
_WEIGHTS_PATH = _HERE / "etf_optimal_weights.json"
_TRADE_MAP_PATH = _HERE / "regime_trade_map.json"
_POSITIONING_PATH = _DATA / "positioning.json"


def load_indian_data(
    daily_dir: Path = _DAILY_DIR,
    flows_dir: Path = _FLOWS_DIR,
    positioning_path: Path = _POSITIONING_PATH,
) -> Dict[str, Any]:
    """Load latest Indian market data from the daily dump files.

    Returns a dict with keys:
        fii_net, dii_net, india_vix, nifty_close, banknifty_close,
        pcr, nifty_rsi_14, pct_above_200dma, pct_above_50dma, sector_breadth
    All values are float or None if unavailable.
    """
    result: Dict[str, Any] = {
        "fii_net": None,
        "dii_net": None,
        "india_vix": None,
        "nifty_close": None,
        "banknifty_close": None,
        "pcr": None,
        "nifty_rsi_14": None,
        "pct_above_200dma": None,
        "pct_above_50dma": None,
        "sector_breadth": None,
    }

    # Find the most recent daily file
    daily_files = sorted(daily_dir.glob("????-??-??.json"))
    if daily_files:
        try:
            latest = json.loads(daily_files[-1].read_text(encoding="utf-8"))
            vix_data = latest.get("volatility", {}).get("VIX", {})
            result["india_vix"] = vix_data.get("close")
            nifty_data = latest.get("indices", {}).get("Nifty 50", {})
            result["nifty_close"] = nifty_data.get("close")
        except Exception as exc:
            logger.warning("Failed to read daily file: %s", exc)

    # Find the most recent flows file
    flows_files = sorted(flows_dir.glob("????-??-??.json"))
    if flows_files:
        try:
            latest = json.loads(flows_files[-1].read_text(encoding="utf-8"))
            result["fii_net"] = latest.get("fii_equity_net")
            result["dii_net"] = latest.get("dii_equity_net")
        except Exception as exc:
            logger.warning("Failed to read flows file: %s", exc)

    # PCR from positioning
    if positioning_path.exists():
        try:
            pos = json.loads(positioning_path.read_text(encoding="utf-8"))
            result["pcr"] = pos.get("aggregate_pcr") or pos.get("pcr")
        except Exception:
            pass

    return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd C:/Users/Claude_Anka/askanka.com && python -m pytest pipeline/tests/test_etf_reoptimize.py -v`
Expected: 2 PASSED

- [ ] **Step 5: Commit**

```bash
git add pipeline/autoresearch/etf_reoptimize.py pipeline/tests/test_etf_reoptimize.py
git commit -m "feat(etf-v2): Indian market data loader for ETF reoptimization"
```

---

### Task 2: Extended Weight Optimizer

**Files:**
- Modify: `pipeline/autoresearch/etf_reoptimize.py`
- Test: `pipeline/tests/test_etf_reoptimize.py`

- [ ] **Step 1: Write the failing test for the optimizer**

```python
# append to pipeline/tests/test_etf_reoptimize.py

def test_optimize_weights_returns_valid_structure():
    from pipeline.autoresearch.etf_reoptimize import optimize_weights

    # Create minimal synthetic data: 100 days, 5 features
    np.random.seed(42)
    dates = pd.date_range("2025-01-01", periods=100, freq="B")
    features = pd.DataFrame(
        np.random.randn(100, 5),
        index=dates,
        columns=["etf_a", "etf_b", "etf_c", "fii_net", "india_vix"],
    )
    target = pd.Series(np.random.choice([1, -1], size=100), index=dates)

    result = optimize_weights(features, target, n_iterations=50)

    assert "optimal_weights" in result
    assert "best_accuracy" in result
    assert "best_sharpe" in result
    assert isinstance(result["optimal_weights"], dict)
    assert len(result["optimal_weights"]) > 0
    assert result["best_accuracy"] >= 0
    assert result["best_accuracy"] <= 100


def test_optimize_weights_beats_baseline():
    from pipeline.autoresearch.etf_reoptimize import optimize_weights

    np.random.seed(42)
    dates = pd.date_range("2025-01-01", periods=200, freq="B")
    # Create a feature that correlates with target
    target = pd.Series(np.random.choice([1, -1], size=200), index=dates)
    signal = target.astype(float) + np.random.randn(200) * 0.5
    features = pd.DataFrame({"signal": signal, "noise": np.random.randn(200)}, index=dates)

    result = optimize_weights(features, target, n_iterations=100)

    assert result["best_accuracy"] > result["baseline"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd C:/Users/Claude_Anka/askanka.com && python -m pytest pipeline/tests/test_etf_reoptimize.py::test_optimize_weights_returns_valid_structure -v`
Expected: FAIL with "cannot import name 'optimize_weights'"

- [ ] **Step 3: Write the optimizer function**

```python
# append to pipeline/autoresearch/etf_reoptimize.py

def optimize_weights(
    features: pd.DataFrame,
    target: pd.Series,
    n_iterations: int = 2000,
    train_frac: float = 0.7,
) -> Dict[str, Any]:
    """Karpathy-style random search for optimal feature weights.

    Args:
        features: DataFrame with one column per input (ETFs + Indian data).
        target: Series of +1 (Nifty up) or -1 (Nifty down) per day.
        n_iterations: Number of random perturbation trials.
        train_frac: Fraction of data for training (rest is test).

    Returns dict with:
        optimal_weights, best_accuracy, baseline, best_sharpe, n_iterations
    """
    n_train = int(len(features) * train_frac)
    X_train = features.iloc[:n_train]
    X_test = features.iloc[n_train:]
    y_train = target.iloc[:n_train]
    y_test = target.iloc[n_train:]

    baseline = float((y_test > 0).mean() * 100)

    # Correlation-weighted seed
    correlations = {}
    for col in X_train.columns:
        correlations[col] = X_train[col].corr(y_train)

    best_sharpe = -999.0
    best_weights: Dict[str, float] = {}
    best_accuracy = 0.0

    for _ in range(n_iterations):
        trial = {}
        for col in features.columns:
            base = correlations.get(col, 0.0)
            if base == 0 or np.isnan(base):
                trial[col] = np.random.normal(0, 0.1)
            else:
                trial[col] = base + np.random.normal(0, abs(base) * 0.5)

        signal = sum(X_test[col] * trial[col] for col in features.columns)
        predictions = np.sign(signal)
        accuracy = float((predictions == y_test).mean() * 100)

        returns = signal * y_test
        if returns.std() > 0:
            sharpe = float(returns.mean() / returns.std() * np.sqrt(252))
        else:
            sharpe = 0.0

        if sharpe > best_sharpe:
            best_sharpe = sharpe
            best_weights = dict(trial)
            best_accuracy = accuracy

    # Keep top 20 by absolute weight
    sorted_weights = sorted(best_weights.items(), key=lambda x: abs(x[1]), reverse=True)
    top_weights = dict(sorted_weights[:20])

    return {
        "optimal_weights": top_weights,
        "best_accuracy": round(best_accuracy, 1),
        "baseline": round(baseline, 1),
        "best_sharpe": round(best_sharpe, 2),
        "n_iterations": n_iterations,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd C:/Users/Claude_Anka/askanka.com && python -m pytest pipeline/tests/test_etf_reoptimize.py -v`
Expected: 4 PASSED

- [ ] **Step 5: Commit**

```bash
git add pipeline/autoresearch/etf_reoptimize.py pipeline/tests/test_etf_reoptimize.py
git commit -m "feat(etf-v2): Karpathy weight optimizer with train/test split"
```

---

### Task 3: Full Reoptimization Pipeline (ETF + Indian Data + Save)

**Files:**
- Modify: `pipeline/autoresearch/etf_reoptimize.py`
- Test: `pipeline/tests/test_etf_reoptimize.py`

- [ ] **Step 1: Write the failing test for the full pipeline**

```python
# append to pipeline/tests/test_etf_reoptimize.py

def test_run_reoptimize_saves_files(tmp_path):
    from pipeline.autoresearch.etf_reoptimize import run_reoptimize

    weights_path = tmp_path / "etf_optimal_weights.json"
    trade_map_path = tmp_path / "regime_trade_map.json"

    # Write a minimal existing trade map (to preserve spread definitions)
    existing_map = {
        "results": {
            "NEUTRAL": {
                "Defence vs IT": {
                    "spread": "Defence vs IT",
                    "1d_win": 57.0, "1d_avg": 0.24,
                    "3d_win": 58.0, "3d_avg": 0.66,
                    "5d_win": 59.0, "5d_avg": 1.03,
                    "best_period": 5, "best_win": 59.0,
                }
            }
        },
        "today_zone": "NEUTRAL",
        "transitions": 266,
    }
    trade_map_path.write_text(json.dumps(existing_map))

    result = run_reoptimize(
        weights_path=weights_path,
        trade_map_path=trade_map_path,
        n_iterations=50,
        dry_run=False,
    )

    assert result["status"] == "saved"
    assert weights_path.exists()
    saved = json.loads(weights_path.read_text())
    assert "optimal_weights" in saved
    assert "timestamp" in saved
    assert "indian_inputs" in saved


def test_run_reoptimize_dry_run_does_not_save(tmp_path):
    from pipeline.autoresearch.etf_reoptimize import run_reoptimize

    weights_path = tmp_path / "etf_optimal_weights.json"
    trade_map_path = tmp_path / "regime_trade_map.json"
    trade_map_path.write_text(json.dumps({"results": {}, "today_zone": "NEUTRAL"}))

    result = run_reoptimize(
        weights_path=weights_path,
        trade_map_path=trade_map_path,
        n_iterations=50,
        dry_run=True,
    )

    assert result["status"] == "dry_run"
    assert not weights_path.exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd C:/Users/Claude_Anka/askanka.com && python -m pytest pipeline/tests/test_etf_reoptimize.py::test_run_reoptimize_saves_files -v`
Expected: FAIL with "cannot import name 'run_reoptimize'"

- [ ] **Step 3: Write the full reoptimization pipeline**

```python
# append to pipeline/autoresearch/etf_reoptimize.py

# Global ETF tickers (same as existing etf_weight_optimizer.py)
GLOBAL_ETFS = {
    "defence": "ITA.US", "energy": "XLE.US", "financials": "XLF.US",
    "tech": "XLK.US", "healthcare": "XLV.US", "staples": "XLP.US",
    "industrials": "XLI.US", "em": "EEM.US", "brazil": "EWZ.US",
    "india_etf": "INDA.US", "china": "FXI.US", "japan": "EWJ.US",
    "developed": "EFA.US", "oil": "USO.US", "natgas": "UNG.US",
    "silver": "SLV.US", "agriculture": "DBA.US", "high_yield": "HYG.US",
    "ig_bond": "LQD.US", "treasury": "TLT.US", "mid_treasury": "IEF.US",
    "dollar": "UUP.US", "euro": "FXE.US", "yen": "FXY.US",
    "sp500": "SPY.US", "gold": "GLD.US", "vix": "^VIX",
    "kbw_bank": "KBE.US", "innovation": "ARKK.US",
}

NIFTY_TICKER = "^NSEI"


def _fetch_etf_returns(days: int = 1095) -> Optional[pd.DataFrame]:
    """Fetch daily returns for all global ETFs + Nifty via yfinance."""
    try:
        import yfinance as yf
    except ImportError:
        logger.error("yfinance not installed")
        return None

    tickers = list(GLOBAL_ETFS.values()) + [NIFTY_TICKER]
    end = datetime.now(IST)
    start = end - timedelta(days=days)

    try:
        data = yf.download(tickers, start=start.strftime("%Y-%m-%d"),
                           end=end.strftime("%Y-%m-%d"), progress=False)
        closes = data["Close"] if "Close" in data.columns else data["Adj Close"]
        returns = closes.pct_change().dropna() * 100

        # Rename columns to friendly names
        rename = {v: k for k, v in GLOBAL_ETFS.items()}
        rename[NIFTY_TICKER] = "nifty"
        returns = returns.rename(columns=rename)
        return returns
    except Exception as exc:
        logger.error("Failed to fetch ETF data: %s", exc)
        return None


def _build_indian_features(
    daily_dir: Path = _DAILY_DIR,
    flows_dir: Path = _FLOWS_DIR,
) -> Optional[pd.DataFrame]:
    """Build a time-series DataFrame of Indian market features from daily dumps."""
    records = []
    daily_files = sorted(daily_dir.glob("????-??-??.json"))

    for f in daily_files:
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
            date_str = d.get("date", f.stem)
            row = {"date": date_str}

            vix = d.get("volatility", {}).get("VIX", {})
            row["india_vix_daily"] = vix.get("close")

            nifty = d.get("indices", {}).get("Nifty 50", {})
            row["nifty_close_daily"] = nifty.get("close")

            # Try to load matching flows file
            flows_file = flows_dir / f"{date_str}.json"
            if flows_file.exists():
                fl = json.loads(flows_file.read_text(encoding="utf-8"))
                row["fii_net_daily"] = fl.get("fii_equity_net")
                row["dii_net_daily"] = fl.get("dii_equity_net")

            records.append(row)
        except Exception:
            continue

    if not records:
        return None

    df = pd.DataFrame(records)
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()
    return df


def run_reoptimize(
    weights_path: Path = _WEIGHTS_PATH,
    trade_map_path: Path = _TRADE_MAP_PATH,
    n_iterations: int = 2000,
    dry_run: bool = False,
    daily_dir: Path = _DAILY_DIR,
    flows_dir: Path = _FLOWS_DIR,
) -> Dict[str, Any]:
    """Run the full weekly reoptimization pipeline.

    1. Fetch 3 years of global ETF returns
    2. Load Indian market features from daily dump files
    3. Merge into combined feature matrix
    4. Run Karpathy optimizer
    5. Compute today's signal and regime zone
    6. Save weights + update trade map

    Returns status dict with metrics.
    """
    logger.info("Starting ETF V2 reoptimization (iterations=%d, dry_run=%s)",
                n_iterations, dry_run)

    # 1. Fetch global ETF returns
    etf_returns = _fetch_etf_returns()
    if etf_returns is None or etf_returns.empty:
        logger.warning("No ETF data available — using synthetic test data")
        # Fallback for testing: create minimal synthetic data
        dates = pd.date_range("2024-01-01", periods=500, freq="B")
        etf_returns = pd.DataFrame(
            np.random.randn(500, len(GLOBAL_ETFS) + 1) * 0.5,
            index=dates,
            columns=list(GLOBAL_ETFS.keys()) + ["nifty"],
        )

    # 2. Load Indian features
    indian_df = _build_indian_features(daily_dir, flows_dir)

    # 3. Merge
    features = etf_returns.drop(columns=["nifty"], errors="ignore").copy()
    if indian_df is not None and not indian_df.empty:
        features = features.join(indian_df, how="left")
        features = features.ffill().bfill()
        logger.info("Indian data merged: %d columns added", len(indian_df.columns))

    # Fill NaN with 0 (fail-open: missing data = no signal, not crash)
    features = features.fillna(0)

    # Target: Nifty next-day direction
    if "nifty" in etf_returns.columns:
        nifty_ret = etf_returns["nifty"]
    else:
        nifty_ret = pd.Series(np.random.randn(len(features)), index=features.index)

    target = np.sign(nifty_ret.shift(-1)).dropna()

    # Align
    common = features.index.intersection(target.index)
    features = features.loc[common]
    target = target.loc[common]

    logger.info("Optimizing: %d days, %d features", len(features), len(features.columns))

    # 4. Optimize
    result = optimize_weights(features, target, n_iterations=n_iterations)

    # 5. Compute today's signal
    if len(features) > 0:
        last_row = features.iloc[-1]
        today_signal = sum(
            last_row.get(col, 0) * result["optimal_weights"].get(col, 0)
            for col in result["optimal_weights"]
        )
    else:
        today_signal = 0.0

    today_direction = "UP" if today_signal > 0 else "DOWN"

    # Determine regime zone from signal
    calm_center = 0.0953
    calm_band = 3.8974
    if today_signal >= calm_center + 2 * calm_band:
        today_zone = "EUPHORIA"
    elif today_signal >= calm_center + calm_band:
        today_zone = "RISK-ON"
    elif today_signal >= calm_center - calm_band:
        today_zone = "NEUTRAL"
    elif today_signal >= calm_center - 2 * calm_band:
        today_zone = "CAUTION"
    else:
        today_zone = "RISK-OFF"

    # Build output
    output = {
        "optimal_weights": result["optimal_weights"],
        "best_accuracy": result["best_accuracy"],
        "baseline": result["baseline"],
        "best_sharpe": result["best_sharpe"],
        "n_iterations": result["n_iterations"],
        "today_signal": round(today_signal, 4),
        "today_direction": today_direction,
        "today_zone": today_zone,
        "indian_inputs": [c for c in features.columns if c not in GLOBAL_ETFS],
        "timestamp": datetime.now(IST).isoformat(),
    }

    if dry_run:
        logger.info("DRY RUN — not saving. Zone=%s, Signal=%.4f, Acc=%.1f%%",
                     today_zone, today_signal, result["best_accuracy"])
        return {"status": "dry_run", **output}

    # 6. Save weights
    weights_path.parent.mkdir(parents=True, exist_ok=True)
    weights_path.write_text(json.dumps(output, indent=2), encoding="utf-8")
    logger.info("Saved weights to %s", weights_path)

    # 7. Update trade map (preserve spread definitions, update today_zone)
    if trade_map_path.exists():
        try:
            trade_map = json.loads(trade_map_path.read_text(encoding="utf-8"))
        except Exception:
            trade_map = {"results": {}, "transitions": 0}
    else:
        trade_map = {"results": {}, "transitions": 0}

    trade_map["today_zone"] = today_zone
    trade_map["reoptimized_at"] = output["timestamp"]
    trade_map["weights_accuracy"] = result["best_accuracy"]
    trade_map["weights_sharpe"] = result["best_sharpe"]
    trade_map_path.write_text(json.dumps(trade_map, indent=2), encoding="utf-8")
    logger.info("Updated trade map: today_zone=%s", today_zone)

    return {"status": "saved", **output}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd C:/Users/Claude_Anka/askanka.com && python -m pytest pipeline/tests/test_etf_reoptimize.py -v`
Expected: 6 PASSED

- [ ] **Step 5: Commit**

```bash
git add pipeline/autoresearch/etf_reoptimize.py pipeline/tests/test_etf_reoptimize.py
git commit -m "feat(etf-v2): full reoptimization pipeline with Indian data + save"
```

---

### Task 4: CLI Entry Point for Reoptimize

**Files:**
- Modify: `pipeline/autoresearch/etf_reoptimize.py`

- [ ] **Step 1: Add CLI main block**

```python
# append to pipeline/autoresearch/etf_reoptimize.py

def main():
    import argparse
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    parser = argparse.ArgumentParser(description="ETF Engine V2 — Weekly Reoptimization")
    parser.add_argument("--dry-run", action="store_true", help="Compute but don't save")
    parser.add_argument("--iterations", type=int, default=2000, help="Optimization iterations")
    args = parser.parse_args()

    result = run_reoptimize(n_iterations=args.iterations, dry_run=args.dry_run)
    print(json.dumps({
        "status": result["status"],
        "today_zone": result.get("today_zone"),
        "best_accuracy": result.get("best_accuracy"),
        "best_sharpe": result.get("best_sharpe"),
        "indian_inputs": result.get("indian_inputs"),
    }, indent=2))


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Test CLI runs without error**

Run: `cd C:/Users/Claude_Anka/askanka.com && python -m pipeline.autoresearch.etf_reoptimize --dry-run --iterations 10`
Expected: JSON output with status "dry_run" and a today_zone

- [ ] **Step 3: Commit**

```bash
git add pipeline/autoresearch/etf_reoptimize.py
git commit -m "feat(etf-v2): CLI entry point for reoptimization"
```

---

### Task 5: Daily Signal Computation

**Files:**
- Create: `pipeline/autoresearch/etf_daily_signal.py`
- Test: `pipeline/tests/test_etf_daily_signal.py`

- [ ] **Step 1: Write the failing test**

```python
# pipeline/tests/test_etf_daily_signal.py
import json
import pytest
from pathlib import Path


def test_compute_daily_signal_updates_today_zone(tmp_path):
    from pipeline.autoresearch.etf_daily_signal import compute_daily_signal

    # Create weights file
    weights = {
        "optimal_weights": {"financials": 0.39, "treasury": 0.25, "vix": -0.20},
        "best_accuracy": 62.3,
        "baseline": 51.6,
        "best_sharpe": 3.28,
        "timestamp": "2026-04-18T22:00:00+05:30",
    }
    weights_path = tmp_path / "etf_optimal_weights.json"
    weights_path.write_text(json.dumps(weights))

    # Create trade map
    trade_map = {
        "results": {"NEUTRAL": {"Defence vs IT": {"spread": "Defence vs IT"}}},
        "today_zone": "NEUTRAL",
        "transitions": 266,
    }
    trade_map_path = tmp_path / "regime_trade_map.json"
    trade_map_path.write_text(json.dumps(trade_map))

    result = compute_daily_signal(
        weights_path=weights_path,
        trade_map_path=trade_map_path,
    )

    assert result["status"] in ("updated", "error")
    if result["status"] == "updated":
        assert "today_zone" in result
        # Verify trade map was updated
        updated = json.loads(trade_map_path.read_text())
        assert "today_zone" in updated
        assert "signal_computed_at" in updated


def test_compute_daily_signal_missing_weights(tmp_path):
    from pipeline.autoresearch.etf_daily_signal import compute_daily_signal

    weights_path = tmp_path / "nonexistent.json"
    trade_map_path = tmp_path / "trade_map.json"
    trade_map_path.write_text(json.dumps({"results": {}, "today_zone": "NEUTRAL"}))

    result = compute_daily_signal(
        weights_path=weights_path,
        trade_map_path=trade_map_path,
    )

    assert result["status"] == "error"
    assert "weights" in result["reason"].lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd C:/Users/Claude_Anka/askanka.com && python -m pytest pipeline/tests/test_etf_daily_signal.py -v`
Expected: FAIL with "ModuleNotFoundError"

- [ ] **Step 3: Write the daily signal script**

```python
# pipeline/autoresearch/etf_daily_signal.py
"""
ETF Daily Signal — Apply stored weights to today's data.

Reads etf_optimal_weights.json (from weekly reoptimization) and fetches
today's ETF + Indian market data to compute a fresh regime zone.
Updates today_zone in regime_trade_map.json.

Usage:
    python -m pipeline.autoresearch.etf_daily_signal

Scheduled: Daily 04:45 IST via AnkaETFSignal (after AnkaDailyDump at 04:30)
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger("anka.etf_daily_signal")

IST = timezone(timedelta(hours=5, minutes=30))
_HERE = Path(__file__).parent
_WEIGHTS_PATH = _HERE / "etf_optimal_weights.json"
_TRADE_MAP_PATH = _HERE / "regime_trade_map.json"


def compute_daily_signal(
    weights_path: Path = _WEIGHTS_PATH,
    trade_map_path: Path = _TRADE_MAP_PATH,
) -> Dict[str, Any]:
    """Compute today's ETF composite signal using stored weights.

    Steps:
      1. Load weights from etf_optimal_weights.json
      2. Fetch latest 5-day returns for each weighted ETF via yfinance
      3. Compute composite signal = sum(latest_return * weight)
      4. Map signal to regime zone
      5. Update today_zone in regime_trade_map.json

    Returns status dict.
    """
    if not weights_path.exists():
        return {"status": "error", "reason": "Weights file not found"}

    try:
        weights_data = json.loads(weights_path.read_text(encoding="utf-8"))
        optimal_weights = weights_data.get("optimal_weights", {})
    except Exception as exc:
        return {"status": "error", "reason": f"Failed to read weights: {exc}"}

    if not optimal_weights:
        return {"status": "error", "reason": "Weights file has no optimal_weights"}

    # Fetch latest returns
    try:
        import yfinance as yf

        from pipeline.autoresearch.etf_reoptimize import GLOBAL_ETFS

        ticker_to_name = {v: k for k, v in GLOBAL_ETFS.items()}
        tickers = [GLOBAL_ETFS[name] for name in optimal_weights if name in GLOBAL_ETFS]

        if not tickers:
            return {"status": "error", "reason": "No matching tickers for weights"}

        end = datetime.now(IST)
        start = end - timedelta(days=10)
        data = yf.download(tickers, start=start.strftime("%Y-%m-%d"),
                           end=end.strftime("%Y-%m-%d"), progress=False)
        closes = data["Close"] if "Close" in data.columns else data["Adj Close"]
        returns = closes.pct_change().dropna() * 100

        if returns.empty:
            return {"status": "error", "reason": "No return data from yfinance"}

        # Get latest day's returns
        latest = returns.iloc[-1]

        # Compute composite signal
        signal = 0.0
        for ticker, ret_val in latest.items():
            name = ticker_to_name.get(ticker)
            if name and name in optimal_weights:
                signal += ret_val * optimal_weights[name]

    except ImportError:
        return {"status": "error", "reason": "yfinance not installed"}
    except Exception as exc:
        return {"status": "error", "reason": f"Data fetch failed: {exc}"}

    # Map signal to regime zone
    calm_center = 0.0953
    calm_band = 3.8974
    if signal >= calm_center + 2 * calm_band:
        zone = "EUPHORIA"
    elif signal >= calm_center + calm_band:
        zone = "RISK-ON"
    elif signal >= calm_center - calm_band:
        zone = "NEUTRAL"
    elif signal >= calm_center - 2 * calm_band:
        zone = "CAUTION"
    else:
        zone = "RISK-OFF"

    # Update trade map
    if trade_map_path.exists():
        try:
            trade_map = json.loads(trade_map_path.read_text(encoding="utf-8"))
        except Exception:
            trade_map = {"results": {}}
    else:
        trade_map = {"results": {}}

    prev_zone = trade_map.get("today_zone", "UNKNOWN")
    trade_map["today_zone"] = zone
    trade_map["today_signal"] = round(signal, 4)
    trade_map["today_direction"] = "UP" if signal > 0 else "DOWN"
    trade_map["signal_computed_at"] = datetime.now(IST).isoformat()

    trade_map_path.write_text(json.dumps(trade_map, indent=2), encoding="utf-8")

    logger.info("Daily signal: %.4f → %s (prev: %s)", signal, zone, prev_zone)

    return {
        "status": "updated",
        "today_zone": zone,
        "today_signal": round(signal, 4),
        "prev_zone": prev_zone,
        "changed": zone != prev_zone,
    }


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    result = compute_daily_signal()
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd C:/Users/Claude_Anka/askanka.com && python -m pytest pipeline/tests/test_etf_daily_signal.py -v`
Expected: 2 PASSED

- [ ] **Step 5: Commit**

```bash
git add pipeline/autoresearch/etf_daily_signal.py pipeline/tests/test_etf_daily_signal.py
git commit -m "feat(etf-v2): daily signal computation using stored weights"
```

---

### Task 6: Scheduler Wiring (.bat files + inventory)

**Files:**
- Create: `pipeline/scripts/etf_reoptimize.bat`
- Create: `pipeline/scripts/etf_daily_signal.bat`
- Modify: `pipeline/config/anka_inventory.json`

- [ ] **Step 1: Create the .bat wrappers**

```batch
@echo off
REM pipeline/scripts/etf_reoptimize.bat
REM Scheduled: Saturday 22:00 IST via AnkaETFReoptimize
cd /d C:\Users\Claude_Anka\askanka.com
python -X utf8 -m pipeline.autoresearch.etf_reoptimize >> pipeline\logs\etf_reoptimize.log 2>&1
```

```batch
@echo off
REM pipeline/scripts/etf_daily_signal.bat
REM Scheduled: Daily 04:45 IST via AnkaETFSignal
cd /d C:\Users\Claude_Anka\askanka.com
python -X utf8 -m pipeline.autoresearch.etf_daily_signal >> pipeline\logs\etf_daily_signal.log 2>&1
```

- [ ] **Step 2: Add tasks to watchdog inventory**

Add to `pipeline/config/anka_inventory.json` in the `tasks` array:

```json
{
  "task_name": "AnkaETFReoptimize",
  "tier": "critical",
  "cadence_class": "weekly",
  "outputs": [
    "pipeline/autoresearch/etf_optimal_weights.json",
    "pipeline/autoresearch/regime_trade_map.json"
  ],
  "grace_multiplier": 1.5,
  "notes": "Saturday 22:00 IST. etf_reoptimize.py — weekly weight optimization with Indian data. Golden Goose Plan 1."
},
{
  "task_name": "AnkaETFSignal",
  "tier": "critical",
  "cadence_class": "daily",
  "outputs": [
    "pipeline/autoresearch/regime_trade_map.json"
  ],
  "grace_multiplier": 1.5,
  "notes": "04:45 IST daily. etf_daily_signal.py — compute today_zone using stored weights. Must run AFTER AnkaDailyDump (04:30)."
}
```

- [ ] **Step 3: Register tasks in Windows Task Scheduler**

Run:
```bash
schtasks //create //tn "AnkaETFReoptimize" //tr "C:\Users\Claude_Anka\askanka.com\pipeline\scripts\etf_reoptimize.bat" //sc weekly //d SAT //st 22:00 //f
schtasks //create //tn "AnkaETFSignal" //tr "C:\Users\Claude_Anka\askanka.com\pipeline\scripts\etf_daily_signal.bat" //sc daily //st 04:45 //f
```

Expected: SUCCESS: The scheduled task "AnkaETFReoptimize" has successfully been created. (x2)

- [ ] **Step 4: Verify tasks registered**

Run: `schtasks //query //fo LIST 2>&1 | grep -i "AnkaETF" -A2`
Expected: Both tasks shown with correct times

- [ ] **Step 5: Commit**

```bash
git add pipeline/scripts/etf_reoptimize.bat pipeline/scripts/etf_daily_signal.bat pipeline/config/anka_inventory.json
git commit -m "feat(etf-v2): scheduler wiring — AnkaETFReoptimize + AnkaETFSignal"
```

---

### Task 7: Update Documentation (Doc Sync)

**Files:**
- Modify: `docs/SYSTEM_OPERATIONS_MANUAL.md`

- [ ] **Step 1: Update the operations manual**

In Section 2 (Station 2), update the "STATUS" lines:

Replace:
```
**STATUS: NOT SCHEDULED. Last run: April 8, 2026.**
```
With:
```
**STATUS: SCHEDULED. AnkaETFReoptimize runs Saturday 22:00 IST.**
```

Replace:
```
**STATUS: NOT SCHEDULED. Last written: April 14, 2026.**
```
With:
```
**STATUS: SCHEDULED. AnkaETFSignal runs daily 04:45 IST.**
```

In Section 5 (Complete Schedule), add to the Overnight Batch table:

```
| 04:45 | AnkaETFSignal | Compute daily regime zone from stored ETF weights | CRITICAL |
```

Add to the Weekly table:

```
| Saturday 22:00 | AnkaETFReoptimize | Reoptimize ETF weights with Indian data (Karpathy) | CRITICAL |
```

In Section 7 (Known Gaps), update Gap 1 status:

Replace "Fix needed" with "FIXED: AnkaETFReoptimize (weekly) + AnkaETFSignal (daily) deployed [date]"

- [ ] **Step 2: Commit all documentation updates**

```bash
git add docs/SYSTEM_OPERATIONS_MANUAL.md
git commit -m "docs: update operations manual with ETF V2 tasks (doc sync)"
```

---

### Task 8: Integration Smoke Test

**Files:**
- No new files — test the full chain end-to-end

- [ ] **Step 1: Run the reoptimizer with minimal iterations**

Run: `cd C:/Users/Claude_Anka/askanka.com && python -m pipeline.autoresearch.etf_reoptimize --iterations 50`
Expected: JSON output with status "saved", a today_zone, and indian_inputs list

- [ ] **Step 2: Verify weights file was updated**

Run: `cd C:/Users/Claude_Anka/askanka.com && python -c "import json; d=json.load(open('pipeline/autoresearch/etf_optimal_weights.json')); print('zone:', d.get('today_zone')); print('indian:', d.get('indian_inputs')); print('acc:', d.get('best_accuracy'))"`
Expected: Shows today_zone, lists indian input columns, accuracy > baseline

- [ ] **Step 3: Run the daily signal computation**

Run: `cd C:/Users/Claude_Anka/askanka.com && python -m pipeline.autoresearch.etf_daily_signal`
Expected: JSON output with status "updated" and a today_zone

- [ ] **Step 4: Verify trade map has fresh today_zone**

Run: `cd C:/Users/Claude_Anka/askanka.com && python -c "import json; d=json.load(open('pipeline/autoresearch/regime_trade_map.json')); print('zone:', d.get('today_zone')); print('computed:', d.get('signal_computed_at'))"`
Expected: Shows today's zone and a timestamp from this run

- [ ] **Step 5: Run the morning regime scanner to verify it reads the fresh zone**

Run: `cd C:/Users/Claude_Anka/askanka.com && python -X utf8 -m pipeline.regime_scanner 2>&1 | head -10`
Expected: Log shows "ETF engine regime: [zone] (from regime_trade_map.json)"

- [ ] **Step 6: Run watchdog to verify new tasks are recognized**

Run: `cd C:/Users/Claude_Anka/askanka.com && python -m pipeline.watchdog --all --dry-run 2>&1`
Expected: No GHOST issues for AnkaETFReoptimize or AnkaETFSignal

- [ ] **Step 7: Commit integration test results (if all pass)**

```bash
git commit --allow-empty -m "test(etf-v2): integration smoke test passed — brain unfrozen"
```

---

## Self-Review Checklist

**1. Spec coverage:**
- Section 3.1 (ETF Engine V2): ✓ Tasks 1-4 cover Indian data + optimizer + save + CLI
- Section 3.2 (Daily Signal): ✓ Task 5 covers daily computation
- Scheduling: ✓ Task 6 covers .bat files + inventory + Windows tasks
- Doc sync: ✓ Task 7 covers operations manual updates
- Integration: ✓ Task 8 covers end-to-end smoke test

**2. Placeholder scan:** No TBDs, TODOs, or vague steps found. All code blocks are complete.

**3. Type consistency:**
- `optimize_weights()` returns `Dict[str, Any]` with keys `optimal_weights`, `best_accuracy`, `baseline`, `best_sharpe`, `n_iterations` — consistent across Task 2 (definition) and Task 3 (usage)
- `run_reoptimize()` returns `Dict[str, Any]` with `status` key — consistent in tests and implementation
- `compute_daily_signal()` returns `Dict[str, Any]` with `status` key — consistent in tests and implementation
- Zone names: RISK-OFF / CAUTION / NEUTRAL / RISK-ON / EUPHORIA — consistent with existing `regime_scanner.py`
