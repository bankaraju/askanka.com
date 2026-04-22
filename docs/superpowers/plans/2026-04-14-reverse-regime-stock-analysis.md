# Reverse Regime-Stock Analysis — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a research analysis that maps which of 66 F&O stocks historically moved in each ETF regime, separating gap from drift, to find tradeable patterns that persist beyond opening gaps.

**Architecture:** Reuse ETF composite signal reconstruction from `regime_to_trades.py`. Load 66 local CSVs for stock prices. Compute gap/drift/persistence for every stock × regime × holding period. Output ranked JSON + console report.

**Tech Stack:** Python, pandas, numpy. No new dependencies. All data is local.

**Spec:** `docs/superpowers/specs/2026-04-14-reverse-regime-stock-analysis-design.md`

---

### Task 1: Regime Label Reconstruction Module

**Files:**
- Create: `C:/Users/Claude_Anka/Documents/askanka.com/pipeline/autoresearch/reverse_regime_analysis.py`
- Read: `C:/Users/Claude_Anka/Documents/askanka.com/pipeline/autoresearch/etf_optimal_weights.json`
- Read: `C:/Users/Claude_Anka/Documents/askanka.com/pipeline/autoresearch/regime_to_trades.py` (reference for load_data pattern)

- [ ] **Step 1: Write the failing test — regime label reconstruction**

Create test file:

```python
# C:/Users/Claude_Anka/Documents/askanka.com/pipeline/autoresearch/tests/test_reverse_regime.py

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

def test_reconstruct_regime_labels():
    from reverse_regime_analysis import reconstruct_regime_labels
    zones, composite = reconstruct_regime_labels()
    
    # Must return a pandas Series of zone labels
    assert len(zones) > 600, f"Expected 600+ days, got {len(zones)}"
    
    # All labels must be valid zones
    valid_zones = {"RISK-OFF", "CAUTION", "NEUTRAL", "RISK-ON", "EUPHORIA"}
    assert set(zones.unique()).issubset(valid_zones), f"Invalid zones: {set(zones.unique()) - valid_zones}"
    
    # NEUTRAL should be most common (120 episodes, 5d avg)
    assert zones.value_counts()["NEUTRAL"] > zones.value_counts().sum() * 0.3, "NEUTRAL should be >30% of days"
    
    # Composite signal should be a numeric Series
    assert composite.dtype in ("float64", "float32"), f"Composite must be float, got {composite.dtype}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd C:/Users/Claude_Anka/Documents/askanka.com/pipeline/autoresearch && C:/Python313/python.exe -m pytest tests/test_reverse_regime.py::test_reconstruct_regime_labels -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'reverse_regime_analysis'`

- [ ] **Step 3: Write the regime reconstruction function**

```python
# C:/Users/Claude_Anka/Documents/askanka.com/pipeline/autoresearch/reverse_regime_analysis.py
"""
Reverse Regime-Stock Analysis (Phase A)
Given a regime, which stocks historically moved, how much was gap vs drift,
and does the effect persist long enough to trade after the opening gap?
"""

import json
import sys
import numpy as np
import pandas as pd
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from eodhd_client import fetch_eod_series

CALM_CENTER = 0.0953
CALM_BAND = 3.8974

ETFS = {
    "ITA.US": "defence", "XLE.US": "energy", "XLF.US": "financials",
    "XLK.US": "tech", "XLV.US": "healthcare", "XLP.US": "staples",
    "XLI.US": "industrials", "EEM.US": "em", "EWZ.US": "brazil",
    "INDA.US": "india_etf", "FXI.US": "china", "EWJ.US": "japan",
    "EFA.US": "developed", "USO.US": "oil", "UNG.US": "natgas",
    "SLV.US": "silver", "DBA.US": "agriculture", "HYG.US": "high_yield",
    "LQD.US": "ig_bond", "TLT.US": "treasury", "IEF.US": "mid_treasury",
    "UUP.US": "dollar", "FXE.US": "euro", "FXY.US": "yen",
    "SPY.US": "sp500", "GLD.US": "gold", "VIX.INDX": "vix",
    "KBE.US": "kbw_bank", "KRE.US": "regional_bank",
    "JETS.US": "airlines", "ARKK.US": "innovation",
    "NSEI.INDX": "nifty",
}


def reconstruct_regime_labels():
    """Rebuild daily regime zones from ETF composite signal.
    Returns (zones: pd.Series[str], composite: pd.Series[float]).
    """
    weights = json.loads(
        Path(__file__).parent.joinpath("etf_optimal_weights.json").read_text()
    )["optimal_weights"]

    all_data = {}
    for sym, name in ETFS.items():
        try:
            data = fetch_eod_series(sym, days=1095)
            if data and len(data) > 200:
                df = pd.DataFrame(data)
                df["date"] = pd.to_datetime(df["date"])
                df = df.set_index("date").sort_index()
                col = "adjusted_close" if "adjusted_close" in df.columns else "close"
                all_data[name] = df[col].astype(float)
        except Exception:
            pass

    combined = pd.DataFrame(all_data).dropna()
    feature_cols = [c for c in combined.columns if c != "nifty"]

    daily_returns = pd.DataFrame(
        {c: combined[c].pct_change() * 100 for c in feature_cols}
    ).dropna()

    composite = pd.Series(0.0, index=daily_returns.index)
    for col in feature_cols:
        if col in weights:
            composite += daily_returns[col] * weights[col]

    zones = pd.Series("NEUTRAL", index=composite.index)
    zones[composite < CALM_CENTER - 2 * CALM_BAND] = "RISK-OFF"
    zones[(composite >= CALM_CENTER - 2 * CALM_BAND) & (composite < CALM_CENTER - CALM_BAND)] = "CAUTION"
    zones[(composite >= CALM_CENTER + CALM_BAND) & (composite < CALM_CENTER + 2 * CALM_BAND)] = "RISK-ON"
    zones[composite >= CALM_CENTER + 2 * CALM_BAND] = "EUPHORIA"

    return zones, composite
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd C:/Users/Claude_Anka/Documents/askanka.com/pipeline/autoresearch && C:/Python313/python.exe -m pytest tests/test_reverse_regime.py::test_reconstruct_regime_labels -v`

Expected: PASS (takes ~30-60s to fetch ETF data from EODHD)

- [ ] **Step 5: Commit**

```bash
cd C:/Users/Claude_Anka/Documents/askanka.com/pipeline
git add autoresearch/reverse_regime_analysis.py autoresearch/tests/test_reverse_regime.py
git commit -m "feat: regime label reconstruction for reverse analysis"
```

---

### Task 2: Stock Price Loader + Gap/Drift Calculator

**Files:**
- Modify: `C:/Users/Claude_Anka/Documents/askanka.com/pipeline/autoresearch/reverse_regime_analysis.py`
- Modify: `C:/Users/Claude_Anka/Documents/askanka.com/pipeline/autoresearch/tests/test_reverse_regime.py`

- [ ] **Step 1: Write the failing test — load stock prices**

Append to test file:

```python
def test_load_stock_prices():
    from reverse_regime_analysis import load_stock_prices
    prices = load_stock_prices()
    
    # Must load from india_historical CSVs
    assert len(prices) >= 60, f"Expected 60+ stocks, got {len(prices)}"
    
    # Each stock should have Open and Close columns
    for sym, df in list(prices.items())[:3]:
        assert "Open" in df.columns, f"{sym} missing Open"
        assert "Close" in df.columns, f"{sym} missing Close"
        assert len(df) > 500, f"{sym} has only {len(df)} rows, expected 500+"


def test_compute_gap_drift():
    from reverse_regime_analysis import load_stock_prices, reconstruct_regime_labels, compute_gap_drift
    
    prices = load_stock_prices()
    zones, _ = reconstruct_regime_labels()
    
    # Test with HAL
    result = compute_gap_drift("HAL", prices["HAL"], zones)
    
    # Must have results for at least some regimes
    assert len(result) > 0, "No regime results for HAL"
    
    # Each regime result must have gap, drift, persistence fields
    for regime, data in result.items():
        assert "gap_mean" in data, f"Missing gap_mean for {regime}"
        assert "drift_1d_mean" in data, f"Missing drift_1d_mean for {regime}"
        assert "drift_5d_mean" in data, f"Missing drift_5d_mean for {regime}"
        assert "persistence" in data, f"Missing persistence for {regime}"
        assert "tradeable" in data, f"Missing tradeable for {regime}"
        assert "episodes" in data, f"Missing episodes for {regime}"
        assert "hit_rate" in data, f"Missing hit_rate for {regime}"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd C:/Users/Claude_Anka/Documents/askanka.com/pipeline/autoresearch && C:/Python313/python.exe -m pytest tests/test_reverse_regime.py -v -k "load_stock or gap_drift"`

Expected: FAIL with `ImportError: cannot import name 'load_stock_prices'`

- [ ] **Step 3: Implement load_stock_prices and compute_gap_drift**

Add to `reverse_regime_analysis.py`:

```python
HIST_DIR = Path(__file__).parent.parent / "data" / "india_historical"


def load_stock_prices():
    """Load all indian_historical CSVs. Returns dict[symbol, DataFrame]."""
    prices = {}
    for csv_path in sorted(HIST_DIR.glob("*.csv")):
        sym = csv_path.stem
        df = pd.read_csv(csv_path, parse_dates=["Date"], index_col="Date").sort_index()
        if len(df) > 200:
            prices[sym] = df
    return prices


def compute_gap_drift(symbol, stock_df, zones):
    """For a single stock, compute gap/drift/persistence per regime.
    
    gap = (open_T / close_T-1) - 1
    drift_Nd = (close_T+N-1 / open_T) - 1
    tradeable = |drift_5d| > |gap|
    persistence = sign(drift_5d) == sign(gap)
    """
    # Align stock dates to regime dates
    common_dates = stock_df.index.intersection(zones.index)
    if len(common_dates) < 100:
        return {}

    # Find regime transition dates (where zone changes from previous day)
    zone_aligned = zones.reindex(common_dates).dropna()
    transitions = zone_aligned[zone_aligned != zone_aligned.shift(1)]

    results = {}
    for regime in ["RISK-OFF", "CAUTION", "NEUTRAL", "RISK-ON", "EUPHORIA"]:
        regime_dates = transitions[transitions == regime].index
        if len(regime_dates) < 3:
            continue

        gaps, drifts_1d, drifts_3d, drifts_5d = [], [], [], []

        for t_date in regime_dates:
            try:
                t_idx = stock_df.index.get_loc(t_date)
            except KeyError:
                # t_date not in stock data, find nearest
                nearest = stock_df.index.get_indexer([t_date], method="nearest")[0]
                if nearest < 0 or nearest >= len(stock_df) - 5:
                    continue
                t_idx = nearest

            if t_idx < 1 or t_idx + 5 > len(stock_df):
                continue

            prev_close = stock_df.iloc[t_idx - 1]["Close"]
            t_open = stock_df.iloc[t_idx]["Open"]
            t_close = stock_df.iloc[t_idx]["Close"]

            # Gap: previous close → today's open
            gap = (t_open / prev_close - 1) * 100
            gaps.append(gap)

            # Drift: today's open → close after N days
            drift_1d = (t_close / t_open - 1) * 100
            drifts_1d.append(drift_1d)

            if t_idx + 2 < len(stock_df):
                close_3d = stock_df.iloc[t_idx + 2]["Close"]
                drifts_3d.append((close_3d / t_open - 1) * 100)

            if t_idx + 4 < len(stock_df):
                close_5d = stock_df.iloc[t_idx + 4]["Close"]
                drifts_5d.append((close_5d / t_open - 1) * 100)

        if not gaps or not drifts_5d:
            continue

        gap_mean = np.mean(gaps)
        drift_5d_mean = np.mean(drifts_5d)

        # Persistence: how often does 5d drift go in same direction as gap?
        persist_count = sum(
            1 for g, d in zip(gaps[:len(drifts_5d)], drifts_5d)
            if np.sign(g) == np.sign(d) and g != 0
        )
        non_zero_gaps = sum(1 for g in gaps[:len(drifts_5d)] if g != 0)
        persistence = (persist_count / non_zero_gaps * 100) if non_zero_gaps > 0 else 0

        # Hit rate: % of episodes where drift_5d was positive (for longs) — use absolute direction
        # For regime analysis, hit rate = consistency of direction
        dominant_dir = np.sign(drift_5d_mean)
        if dominant_dir == 0:
            hit_rate = 50.0
        else:
            hit_rate = sum(1 for d in drifts_5d if np.sign(d) == dominant_dir) / len(drifts_5d) * 100

        results[regime] = {
            "episodes": len(gaps),
            "gap_mean": round(gap_mean, 3),
            "drift_1d_mean": round(np.mean(drifts_1d), 3),
            "drift_3d_mean": round(np.mean(drifts_3d), 3) if drifts_3d else None,
            "drift_5d_mean": round(drift_5d_mean, 3),
            "persistence": round(persistence, 1),
            "hit_rate": round(hit_rate, 1),
            "tradeable": abs(drift_5d_mean) > abs(gap_mean),
            "gap_std": round(np.std(gaps), 3),
            "drift_5d_std": round(np.std(drifts_5d), 3),
        }

    return results
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd C:/Users/Claude_Anka/Documents/askanka.com/pipeline/autoresearch && C:/Python313/python.exe -m pytest tests/test_reverse_regime.py -v`

Expected: 3 tests PASS

- [ ] **Step 5: Commit**

```bash
cd C:/Users/Claude_Anka/Documents/askanka.com/pipeline
git add autoresearch/reverse_regime_analysis.py autoresearch/tests/test_reverse_regime.py
git commit -m "feat: stock price loader + gap/drift/persistence calculator"
```

---

### Task 3: Sector Basket Aggregation

**Files:**
- Modify: `C:/Users/Claude_Anka/Documents/askanka.com/pipeline/autoresearch/reverse_regime_analysis.py`
- Modify: `C:/Users/Claude_Anka/Documents/askanka.com/pipeline/autoresearch/tests/test_reverse_regime.py`

- [ ] **Step 1: Write the failing test — sector baskets**

Append to test file:

```python
def test_sector_baskets():
    from reverse_regime_analysis import SECTOR_BASKETS, build_sector_basket_prices, load_stock_prices
    
    # Must have sub-sector classification
    assert "Defence" in SECTOR_BASKETS
    assert "OMCs_Downstream" in SECTOR_BASKETS
    assert "Upstream_Energy" in SECTOR_BASKETS
    # Refiners and OMCs must NOT be grouped with upstream
    assert "ONGC" not in SECTOR_BASKETS.get("OMCs_Downstream", [])
    
    prices = load_stock_prices()
    baskets = build_sector_basket_prices(prices)
    
    assert len(baskets) >= 10, f"Expected 10+ sector baskets, got {len(baskets)}"
    for name, df in list(baskets.items())[:3]:
        assert "Open" in df.columns, f"Basket {name} missing Open"
        assert "Close" in df.columns, f"Basket {name} missing Close"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd C:/Users/Claude_Anka/Documents/askanka.com/pipeline/autoresearch && C:/Python313/python.exe -m pytest tests/test_reverse_regime.py::test_sector_baskets -v`

Expected: FAIL with `ImportError: cannot import name 'SECTOR_BASKETS'`

- [ ] **Step 3: Implement sector baskets**

Add to `reverse_regime_analysis.py`:

```python
SECTOR_BASKETS = {
    "Defence": ["HAL", "BEL", "BDL"],
    "IT_Services": ["TCS", "INFY", "WIPRO", "HCLTECH", "TECHM", "LTIM", "PERSISTENT"],
    "Banks_Private": ["HDFCBANK", "ICICIBANK", "AXISBANK", "KOTAKBANK"],
    "Banks_PSU": ["SBI", "BANKBARODA", "FEDERALBNK"],
    "OMCs_Downstream": ["BPCL", "HPCL", "IOC"],
    "Upstream_Energy": ["ONGC", "OIL", "COALINDIA"],
    "Pharma": ["SUNPHARMA", "DRREDDY", "CIPLA", "DIVISLAB"],
    "Metals": ["TATASTEEL", "HINDALCO", "JSPL", "SAIL", "VEDL", "NMDC"],
    "Auto": ["MARUTI", "TATAMOTORS", "M&M", "BHARATFORG"],
    "FMCG": ["HUL", "ITC", "DABUR", "BRITANNIA"],
    "Real_Estate": ["DLF", "OBEROIRLTY", "GODREJPROP", "SOBHA"],
    "Infra_Power": ["NTPC", "POWERGRID", "TATAPOWER", "LT"],
    "Conglomerate": ["RELIANCE", "ADANIENT", "SIEMENS"],
    "Healthcare": ["APOLLOHOSP", "MAXHEALTH", "ASTERDM"],
    "Cement": ["ULTRACEMCO", "AMBUJACEM"],
}


def build_sector_basket_prices(prices):
    """Build equal-weight sector basket OHLCV from individual stock prices.
    Returns dict[basket_name, DataFrame with Open/Close columns].
    """
    baskets = {}
    for basket_name, symbols in SECTOR_BASKETS.items():
        available = [s for s in symbols if s in prices]
        if len(available) < 2:
            continue

        # Equal-weight: normalize each stock to 100 at start, then average
        opens, closes = [], []
        for sym in available:
            df = prices[sym]
            base = df["Close"].iloc[0]
            opens.append(df["Open"] / base * 100)
            closes.append(df["Close"] / base * 100)

        basket_open = pd.concat(opens, axis=1).mean(axis=1)
        basket_close = pd.concat(closes, axis=1).mean(axis=1)

        baskets[basket_name] = pd.DataFrame({
            "Open": basket_open,
            "Close": basket_close,
        }).dropna()

    return baskets
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd C:/Users/Claude_Anka/Documents/askanka.com/pipeline/autoresearch && C:/Python313/python.exe -m pytest tests/test_reverse_regime.py::test_sector_baskets -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd C:/Users/Claude_Anka/Documents/askanka.com/pipeline
git add autoresearch/reverse_regime_analysis.py autoresearch/tests/test_reverse_regime.py
git commit -m "feat: sub-sector basket aggregation for regime analysis"
```

---

### Task 4: Full Analysis Runner + JSON Output

**Files:**
- Modify: `C:/Users/Claude_Anka/Documents/askanka.com/pipeline/autoresearch/reverse_regime_analysis.py`
- Modify: `C:/Users/Claude_Anka/Documents/askanka.com/pipeline/autoresearch/tests/test_reverse_regime.py`

- [ ] **Step 1: Write the failing test — full analysis**

Append to test file:

```python
def test_run_full_analysis():
    from reverse_regime_analysis import run_reverse_regime_analysis
    
    results = run_reverse_regime_analysis()
    
    # Must have individual stocks and sector baskets
    assert "stocks" in results, "Missing 'stocks' key"
    assert "baskets" in results, "Missing 'baskets' key"
    assert "meta" in results, "Missing 'meta' key"
    
    # Must have analyzed 60+ stocks
    assert len(results["stocks"]) >= 50, f"Expected 50+ stocks, got {len(results['stocks'])}"
    
    # Must have analyzed 10+ baskets
    assert len(results["baskets"]) >= 10, f"Expected 10+ baskets, got {len(results['baskets'])}"
    
    # Meta must have regime episode counts
    assert "regime_episodes" in results["meta"]
    assert "NEUTRAL" in results["meta"]["regime_episodes"]


def test_tradeable_filter():
    from reverse_regime_analysis import run_reverse_regime_analysis, get_tradeable_signals
    
    results = run_reverse_regime_analysis()
    tradeable = get_tradeable_signals(results)
    
    # Each tradeable entry must have required fields
    for entry in tradeable:
        assert "symbol" in entry
        assert "regime" in entry
        assert "drift_5d_mean" in entry
        assert "hit_rate" in entry
        assert "persistence" in entry
        assert entry["hit_rate"] >= 55.0, f"{entry['symbol']} hit_rate {entry['hit_rate']} < 55%"
        assert entry["persistence"] >= 50.0, f"{entry['symbol']} persistence {entry['persistence']} < 50%"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd C:/Users/Claude_Anka/Documents/askanka.com/pipeline/autoresearch && C:/Python313/python.exe -m pytest tests/test_reverse_regime.py -v -k "full_analysis or tradeable"`

Expected: FAIL with `ImportError: cannot import name 'run_reverse_regime_analysis'`

- [ ] **Step 3: Implement the full analysis runner**

Add to `reverse_regime_analysis.py`:

```python
def run_reverse_regime_analysis():
    """Run complete reverse regime analysis on all stocks + sector baskets."""
    print("=" * 70)
    print("REVERSE REGIME ANALYSIS: Which stocks move in each regime?")
    print("=" * 70)

    # Step 1: Reconstruct regime labels
    print("\nReconstructing regime labels from ETF composite...")
    zones, composite = reconstruct_regime_labels()
    print(f"  {len(zones)} trading days, {len(zones[zones != zones.shift(1)])} transitions")

    regime_episodes = {}
    for regime in ["RISK-OFF", "CAUTION", "NEUTRAL", "RISK-ON", "EUPHORIA"]:
        transitions = zones[zones == regime][zones.shift(1) != regime]
        regime_episodes[regime] = len(transitions)
        print(f"  {regime}: {len(transitions)} episodes")

    # Step 2: Load stock prices
    print("\nLoading stock prices...")
    prices = load_stock_prices()
    print(f"  {len(prices)} stocks loaded")

    # Step 3: Analyze individual stocks
    print("\nAnalyzing individual stocks...")
    stock_results = {}
    for sym, df in sorted(prices.items()):
        result = compute_gap_drift(sym, df, zones)
        if result:
            stock_results[sym] = result

    print(f"  {len(stock_results)} stocks with regime data")

    # Step 4: Analyze sector baskets
    print("\nAnalyzing sector baskets...")
    baskets = build_sector_basket_prices(prices)
    basket_results = {}
    for basket_name, df in sorted(baskets.items()):
        result = compute_gap_drift(basket_name, df, zones)
        if result:
            basket_results[basket_name] = result

    print(f"  {len(basket_results)} baskets with regime data")

    results = {
        "stocks": stock_results,
        "baskets": basket_results,
        "meta": {
            "regime_episodes": regime_episodes,
            "total_days": len(zones),
            "stock_count": len(stock_results),
            "basket_count": len(basket_results),
            "date_range": f"{zones.index[0].date()} to {zones.index[-1].date()}",
        },
    }

    return results


def get_tradeable_signals(results, min_hit_rate=55.0, min_persistence=50.0):
    """Filter for tradeable stock-regime combinations.
    Tradeable = drift exceeds gap AND hit rate >= threshold AND persistence >= threshold.
    """
    tradeable = []

    for source_key in ["stocks", "baskets"]:
        for symbol, regimes in results[source_key].items():
            for regime, data in regimes.items():
                if (
                    data["tradeable"]
                    and data["hit_rate"] >= min_hit_rate
                    and data["persistence"] >= min_persistence
                    and data["episodes"] >= 5
                ):
                    tradeable.append({
                        "symbol": symbol,
                        "type": "stock" if source_key == "stocks" else "basket",
                        "regime": regime,
                        **data,
                    })

    tradeable.sort(key=lambda x: abs(x["drift_5d_mean"]), reverse=True)
    return tradeable
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd C:/Users/Claude_Anka/Documents/askanka.com/pipeline/autoresearch && C:/Python313/python.exe -m pytest tests/test_reverse_regime.py -v`

Expected: 5 tests PASS (this run takes ~60-90s due to EODHD fetches)

- [ ] **Step 5: Commit**

```bash
cd C:/Users/Claude_Anka/Documents/askanka.com/pipeline
git add autoresearch/reverse_regime_analysis.py autoresearch/tests/test_reverse_regime.py
git commit -m "feat: full reverse regime analysis runner with tradeable filter"
```

---

### Task 5: Console Report + JSON Save + main()

**Files:**
- Modify: `C:/Users/Claude_Anka/Documents/askanka.com/pipeline/autoresearch/reverse_regime_analysis.py`

- [ ] **Step 1: Write the failing test — report output**

Append to test file:

```python
import json
from pathlib import Path

def test_save_and_report(tmp_path):
    from reverse_regime_analysis import run_reverse_regime_analysis, print_report, save_results
    
    results = run_reverse_regime_analysis()
    
    # Test save
    out_path = tmp_path / "test_profile.json"
    save_results(results, out_path)
    assert out_path.exists()
    
    loaded = json.loads(out_path.read_text())
    assert "stocks" in loaded
    assert "baskets" in loaded
    assert "tradeable_signals" in loaded
    
    # Test report (just verify it doesn't crash)
    print_report(results)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd C:/Users/Claude_Anka/Documents/askanka.com/pipeline/autoresearch && C:/Python313/python.exe -m pytest tests/test_reverse_regime.py::test_save_and_report -v`

Expected: FAIL with `ImportError: cannot import name 'print_report'`

- [ ] **Step 3: Implement report and save functions**

Add to `reverse_regime_analysis.py`:

```python
def print_report(results):
    """Print ranked console report of regime-stock relationships."""
    tradeable = get_tradeable_signals(results)

    print(f"\n{'=' * 70}")
    print(f"TRADEABLE SIGNALS (drift > gap, hit rate >= 55%, persistence >= 50%)")
    print(f"{'=' * 70}")
    print(f"  Found: {len(tradeable)} tradeable stock-regime combinations\n")

    if not tradeable:
        print("  No tradeable signals found. The reverse analysis does not add value")
        print("  over the existing forward flow for this dataset.")
        return

    print(f"  {'Symbol':20s} {'Type':8s} {'Regime':12s} {'Gap':>8s} {'Drift5d':>8s} {'Hit%':>6s} {'Persist':>8s} {'Episodes':>8s}")
    print(f"  {'-' * 82}")

    for entry in tradeable[:30]:
        print(
            f"  {entry['symbol']:20s} "
            f"{entry['type']:8s} "
            f"{entry['regime']:12s} "
            f"{entry['gap_mean']:>+7.2f}% "
            f"{entry['drift_5d_mean']:>+7.2f}% "
            f"{entry['hit_rate']:>5.1f}% "
            f"{entry['persistence']:>7.1f}% "
            f"{entry['episodes']:>7d}"
        )

    # Spread opportunities: baskets that move in opposite directions in same regime
    print(f"\n{'=' * 70}")
    print(f"POTENTIAL SPREAD TRADES (baskets moving in opposite directions)")
    print(f"{'=' * 70}")

    basket_signals = [t for t in tradeable if t["type"] == "basket"]
    for regime in ["RISK-OFF", "CAUTION", "NEUTRAL", "RISK-ON", "EUPHORIA"]:
        regime_baskets = [b for b in basket_signals if b["regime"] == regime]
        longs = [b for b in regime_baskets if b["drift_5d_mean"] > 0]
        shorts = [b for b in regime_baskets if b["drift_5d_mean"] < 0]

        if longs and shorts:
            for l in longs:
                for s in shorts:
                    spread_drift = l["drift_5d_mean"] - s["drift_5d_mean"]
                    min_hit = min(l["hit_rate"], s["hit_rate"])
                    print(
                        f"  {regime:12s} LONG {l['symbol']:20s} ({l['drift_5d_mean']:+.2f}%) "
                        f"/ SHORT {s['symbol']:20s} ({s['drift_5d_mean']:+.2f}%) "
                        f"= {spread_drift:+.2f}% net, {min_hit:.0f}% min hit"
                    )

    # Gate check
    print(f"\n{'=' * 70}")
    gate_pass = len(tradeable) >= 5
    print(f"PHASE A GATE: {'PASS' if gate_pass else 'FAIL'} — {len(tradeable)} tradeable signals (need >= 5)")
    print(f"{'=' * 70}")


def save_results(results, path=None):
    """Save full results + tradeable signals to JSON."""
    if path is None:
        path = Path(__file__).parent / "reverse_regime_profile.json"

    tradeable = get_tradeable_signals(results)

    output = {
        "stocks": results["stocks"],
        "baskets": results["baskets"],
        "meta": results["meta"],
        "tradeable_signals": tradeable,
        "gate_pass": len(tradeable) >= 5,
    }

    Path(path).write_text(json.dumps(output, indent=2, default=str), encoding="utf-8")
    print(f"\nSaved to {path}")


if __name__ == "__main__":
    results = run_reverse_regime_analysis()
    print_report(results)
    save_results(results)
```

- [ ] **Step 4: Run all tests**

Run: `cd C:/Users/Claude_Anka/Documents/askanka.com/pipeline/autoresearch && C:/Python313/python.exe -m pytest tests/test_reverse_regime.py -v`

Expected: 6 tests PASS

- [ ] **Step 5: Run the full analysis end-to-end**

Run: `cd C:/Users/Claude_Anka/Documents/askanka.com/pipeline/autoresearch && PYTHONIOENCODING=utf-8 C:/Python313/python.exe reverse_regime_analysis.py`

Expected: Console report showing tradeable signals, spread opportunities, and Phase A gate result.

- [ ] **Step 6: Commit**

```bash
cd C:/Users/Claude_Anka/Documents/askanka.com/pipeline
git add autoresearch/reverse_regime_analysis.py autoresearch/tests/test_reverse_regime.py
git commit -m "feat: reverse regime analysis Phase A complete — report + JSON output"
```

---

### Task 6: Review Results + Gate Decision

This is a human-review task, not a code task.

- [ ] **Step 1: Read the output JSON**

Read: `C:/Users/Claude_Anka/Documents/askanka.com/pipeline/autoresearch/reverse_regime_profile.json`

- [ ] **Step 2: Evaluate the gate**

Check: Does `gate_pass` = true? Are there >= 5 tradeable stock-regime combinations with drift > gap, hit rate >= 55%, persistence >= 50%?

- [ ] **Step 3: Decision**

If PASS → proceed to Phase B (daily ranker automation). Plan will be written separately.
If FAIL → the reverse analysis doesn't add value. Document findings in memory and move on to other priorities.

- [ ] **Step 4: Save findings to memory**

Regardless of pass/fail, save a memory file with the key findings from this analysis.
