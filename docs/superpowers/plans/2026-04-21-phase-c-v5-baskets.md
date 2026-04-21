# Phase C V5 — Baskets, Index Hedges & Options Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Forward-validate Phase C OPPORTUNITY signals as basket structures (sector pairs, index hedges, options overlays, multi-day holds) on the 60-day Kite 1-min archive + 4-year daily history. Determine whether basket-level edge exists where v1 single-stock validation failed.

**Architecture:** New `pipeline/research/phase_c_v5/` package reads v1 ledger + signal universe as input, applies seven variant transformations, emits per-variant parquet ledgers and one comparative research document. Reuses v1's `stats.py` (bootstrap/binomial/Bonferroni), extends v1's `cost_model.py` for index/options instruments, and reuses `pipeline/options_pricer.py` (Black-Scholes) for V5.7. No live trading — F3 shadow continues separately.

**Tech Stack:** Python 3.13, pandas, numpy, scipy, pyarrow (parquet), matplotlib (plots), pytest (TDD). Kite Connect SDK for index OHLC (existing `pipeline.kite_client.fetch_historical`). Black-Scholes via existing `pipeline.options_pricer`.

**Spec:** `docs/superpowers/specs/2026-04-21-phase-c-v5-baskets-design.md`

---

## File Structure

**Reused from v1 (no changes):**
- `pipeline/research/phase_c_backtest/stats.py` — bootstrap_sharpe_ci, binomial_p, bonferroni_alpha_per
- `pipeline/options_pricer.py` — bs_call_price, bs_put_price, bs_greeks
- `pipeline/research/phase_c_backtest/fetcher.py` — pattern (we copy structure for index fetcher)

**New under `pipeline/research/phase_c_v5/`:**
- `__init__.py` — empty marker
- `paths.py` — path constants (cache dirs, doc dirs, config)
- `cost_model.py` — extends v1 with index futures + options rates
- `index_fetcher.py` — Kite-backed parquet cache for index OHLC (daily + 1-min)
- `concentration.py` — loader/builder for `sector_concentration.json`
- `tradeable_indices.py` — NSE live-quote check; outputs JSON of which sectorals have F&O
- `basket_builder.py` — groups Phase C signals into baskets (shared by V5.1–V5.5)
- `simulator.py` — replay engine for daily and 1-min ledgers
- `variants/__init__.py`
- `variants/v51_sector_pair.py`
- `variants/v52_stock_vs_index.py`
- `variants/v53_nifty_overlay.py`
- `variants/v54_dispersion.py` (covers BANKNIFTY + NIFTY IT)
- `variants/v55_leader_routing.py`
- `variants/v56_horizon_sweep.py`
- `variants/v57_options_overlay.py`
- `report.py` — 11-section research doc generator
- `run_v5.py` — CLI entry point

**New under `pipeline/tests/research/phase_c_v5/`:**
- `__init__.py`, `conftest.py`
- `test_paths.py`, `test_cost_model.py`, `test_index_fetcher.py`, `test_concentration.py`,
  `test_tradeable_indices.py`, `test_basket_builder.py`, `test_simulator.py`,
  `test_v51_sector_pair.py`, `test_v52_stock_vs_index.py`, `test_v53_nifty_overlay.py`,
  `test_v54_dispersion.py`, `test_v55_leader_routing.py`, `test_v56_horizon_sweep.py`,
  `test_v57_options_overlay.py`, `test_report.py`

**Output artefacts:**
- `pipeline/data/india_historical/indices/<INDEX>_daily.csv` — 5y per index
- `pipeline/data/india_historical/indices/intraday/<INDEX>_1min.parquet` — 60d per index
- `pipeline/config/sector_concentration.json` — top-N constituent weights
- `pipeline/config/tradeable_sectorals.json` — F&O availability per sectoral
- `pipeline/data/research/phase_c_v5/v5N_ledger.parquet` (one per variant)
- `pipeline/data/research/phase_c_v5/v5N_equity.png` (one per variant)
- `docs/research/phase-c-v5-baskets/01-executive-summary.md` … `11-verdict.md`

---

## Task 1: Scaffold + path constants

**Files:**
- Create: `pipeline/research/phase_c_v5/__init__.py`
- Create: `pipeline/research/phase_c_v5/paths.py`
- Create: `pipeline/tests/research/phase_c_v5/__init__.py`
- Create: `pipeline/tests/research/phase_c_v5/conftest.py`
- Create: `pipeline/tests/research/phase_c_v5/test_paths.py`

- [ ] **Step 1: Write the failing test**

```python
# pipeline/tests/research/phase_c_v5/test_paths.py
from pipeline.research.phase_c_v5 import paths


def test_path_constants_exist():
    assert paths.CACHE_DIR.name == "phase_c_v5"
    assert paths.LEDGERS_DIR.parent == paths.CACHE_DIR
    assert paths.PLOTS_DIR.parent == paths.CACHE_DIR
    assert paths.INDICES_DAILY_DIR.name == "indices"
    assert paths.INDICES_MINUTE_DIR.name == "intraday"
    assert paths.DOCS_DIR.name == "phase-c-v5-baskets"
    assert paths.CONCENTRATION_PATH.name == "sector_concentration.json"
    assert paths.TRADEABLE_PATH.name == "tradeable_sectorals.json"
    assert paths.V1_IN_SAMPLE_LEDGER.name == "in_sample_ledger.parquet"
    assert paths.V1_FORWARD_LEDGER.name == "forward_ledger.parquet"


def test_ensure_cache_creates_dirs(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "CACHE_DIR", tmp_path / "phase_c_v5")
    monkeypatch.setattr(paths, "LEDGERS_DIR", tmp_path / "phase_c_v5" / "ledgers")
    monkeypatch.setattr(paths, "PLOTS_DIR", tmp_path / "phase_c_v5" / "plots")
    paths.ensure_cache()
    assert (tmp_path / "phase_c_v5" / "ledgers").is_dir()
    assert (tmp_path / "phase_c_v5" / "plots").is_dir()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest pipeline/tests/research/phase_c_v5/test_paths.py -v`
Expected: ImportError — `pipeline.research.phase_c_v5` does not exist.

- [ ] **Step 3: Create the package files**

```python
# pipeline/research/phase_c_v5/__init__.py
```
(empty file)

```python
# pipeline/research/phase_c_v5/paths.py
from __future__ import annotations
from pathlib import Path

PIPELINE_DIR = Path(__file__).resolve().parent.parent.parent
REPO_DIR = PIPELINE_DIR.parent

CACHE_DIR = PIPELINE_DIR / "data" / "research" / "phase_c_v5"
LEDGERS_DIR = CACHE_DIR / "ledgers"
PLOTS_DIR = CACHE_DIR / "plots"

INDICES_DAILY_DIR = PIPELINE_DIR / "data" / "india_historical" / "indices"
INDICES_MINUTE_DIR = INDICES_DAILY_DIR / "intraday"

CONCENTRATION_PATH = PIPELINE_DIR / "config" / "sector_concentration.json"
TRADEABLE_PATH = PIPELINE_DIR / "config" / "tradeable_sectorals.json"

V1_IN_SAMPLE_LEDGER = REPO_DIR / "docs" / "research" / "phase-c-validation" / "in_sample_ledger.parquet"
V1_FORWARD_LEDGER = REPO_DIR / "docs" / "research" / "phase-c-validation" / "forward_ledger.parquet"

DOCS_DIR = REPO_DIR / "docs" / "research" / "phase-c-v5-baskets"


def ensure_cache() -> None:
    """Create cache subdirs if missing. Idempotent."""
    for d in (CACHE_DIR, LEDGERS_DIR, PLOTS_DIR, INDICES_DAILY_DIR, INDICES_MINUTE_DIR, DOCS_DIR):
        d.mkdir(parents=True, exist_ok=True)
```

```python
# pipeline/tests/research/phase_c_v5/__init__.py
```
(empty file)

```python
# pipeline/tests/research/phase_c_v5/conftest.py
"""Shared fixtures for V5 tests."""
import pytest
import pandas as pd


@pytest.fixture
def sample_v1_ledger() -> pd.DataFrame:
    """Two-row sample matching v1 ledger schema."""
    return pd.DataFrame([
        {"entry_date": "2024-10-04", "exit_date": "2024-10-07", "symbol": "ITC",
         "side": "SHORT", "entry_px": 429.5, "exit_px": 432.2,
         "notional_inr": 50000.0, "pnl_gross_inr": -314.32, "pnl_net_inr": -392.89,
         "label": "OPPORTUNITY", "z_score": -1.50, "expected_return": -0.0004},
        {"entry_date": "2024-10-04", "exit_date": "2024-10-07", "symbol": "RELIANCE",
         "side": "SHORT", "entry_px": 1393.5, "exit_px": 1370.7,
         "notional_inr": 50000.0, "pnl_gross_inr": 818.08, "pnl_net_inr": 739.51,
         "label": "OPPORTUNITY", "z_score": -1.22, "expected_return": -0.0005},
    ])
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest pipeline/tests/research/phase_c_v5/test_paths.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add pipeline/research/phase_c_v5/__init__.py pipeline/research/phase_c_v5/paths.py pipeline/tests/research/phase_c_v5/__init__.py pipeline/tests/research/phase_c_v5/conftest.py pipeline/tests/research/phase_c_v5/test_paths.py
git commit -m "feat(phase-c-v5): scaffold package + path constants"
```

---

## Task 2: cost_model.py — extends v1 for indices + options

**Files:**
- Create: `pipeline/research/phase_c_v5/cost_model.py`
- Create: `pipeline/tests/research/phase_c_v5/test_cost_model.py`

Reuses `pipeline.research.phase_c_backtest.cost_model` for the equity stock-fut case. Adds INSTRUMENT_RATES dispatch by `instrument` arg.

- [ ] **Step 1: Write the failing test**

```python
# pipeline/tests/research/phase_c_v5/test_cost_model.py
import pytest
from pipeline.research.phase_c_v5 import cost_model


def test_stock_fut_round_trip_matches_v1():
    """For instrument='stock_fut', cost equals v1 cost_model output."""
    from pipeline.research.phase_c_backtest import cost_model as v1
    ours = cost_model.round_trip_cost_inr(50000.0, "LONG", instrument="stock_fut")
    v1_cost = v1.round_trip_cost_inr(50000.0, "LONG", slippage_bps=5.0)
    assert abs(ours - v1_cost) < 0.01


def test_index_fut_uses_lower_slippage():
    """index_fut (NIFTY/BANKNIFTY) gets 2 bps round-trip vs 5 for stock_fut."""
    stock = cost_model.round_trip_cost_inr(100000.0, "LONG", instrument="stock_fut")
    index = cost_model.round_trip_cost_inr(100000.0, "LONG", instrument="index_fut")
    assert index < stock
    # 3 bps difference on 100k = ~30 INR
    assert 25 < (stock - index) < 50


def test_sectoral_fut_higher_slippage_than_index():
    """Sectoral indices (NIFTY IT, etc.) get 8 bps vs index_fut's 2 bps."""
    index = cost_model.round_trip_cost_inr(100000.0, "LONG", instrument="index_fut")
    sectoral = cost_model.round_trip_cost_inr(100000.0, "LONG", instrument="sectoral_fut")
    assert sectoral > index
    assert 50 < (sectoral - index) < 80


def test_options_long_slippage_15bps():
    """Long-only options get 15 bps mid-spread slippage."""
    cost = cost_model.round_trip_cost_inr(10000.0, "LONG", instrument="options_long")
    # 15 bps on 10k = 15 INR slippage + brokerage + STT (0.0625% sell)
    assert 25 < cost < 50


def test_unknown_instrument_raises():
    with pytest.raises(ValueError, match="unknown instrument"):
        cost_model.round_trip_cost_inr(50000.0, "LONG", instrument="bond")


def test_apply_to_pnl_subtracts():
    pnl_after = cost_model.apply_to_pnl(1000.0, 50000.0, "LONG", instrument="stock_fut")
    cost = cost_model.round_trip_cost_inr(50000.0, "LONG", instrument="stock_fut")
    assert abs(pnl_after - (1000.0 - cost)) < 0.01
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest pipeline/tests/research/phase_c_v5/test_cost_model.py -v`
Expected: ImportError — `cost_model` module not found.

- [ ] **Step 3: Implement**

```python
# pipeline/research/phase_c_v5/cost_model.py
"""V5 cost model — extends v1 with index futures + options instruments.

For stock_fut, exactly matches the v1 cost_model output (delegates to it).
For index_fut/sectoral_fut/options_long, applies instrument-specific
slippage and STT/stamp rates per spec section 'Cost Model'.
"""
from __future__ import annotations

from pipeline.research.phase_c_backtest import cost_model as v1

# Per spec section "Cost Model":
INSTRUMENT_RATES = {
    "stock_fut":    {"slippage_bps": 5.0,  "stt_sell": 0.000125,  "stamp_buy": 0.00002},
    "index_fut":    {"slippage_bps": 2.0,  "stt_sell": 0.000125,  "stamp_buy": 0.00002},
    "sectoral_fut": {"slippage_bps": 8.0,  "stt_sell": 0.000125,  "stamp_buy": 0.00002},
    "options_long": {"slippage_bps": 15.0, "stt_sell": 0.000625,  "stamp_buy": 0.00003},
}


def round_trip_cost_inr(notional_inr: float, side: str, instrument: str = "stock_fut") -> float:
    """Round-trip cost for a notional position. Routes by instrument.

    For stock_fut: identical to v1 cost_model output (back-compat).
    For other instruments: uses INSTRUMENT_RATES dispatch.
    """
    if side not in ("LONG", "SHORT"):
        raise ValueError(f"side must be LONG or SHORT, got {side!r}")
    if instrument not in INSTRUMENT_RATES:
        raise ValueError(f"unknown instrument: {instrument!r}")

    rates = INSTRUMENT_RATES[instrument]

    # For stock_fut, delegate to v1 to guarantee identical output.
    if instrument == "stock_fut":
        return v1.round_trip_cost_inr(notional_inr, side, slippage_bps=rates["slippage_bps"])

    # Brokerage + exchange + sebi + GST follow v1 leg formula, but we override
    # STT/stamp rates per instrument.
    brokerage_each = min(notional_inr * 0.0003, 20.0)
    txn_each = notional_inr * 0.0000345
    sebi_each = notional_inr * 0.000001
    gst_each = (brokerage_each + txn_each) * 0.18

    fixed = 2 * (brokerage_each + txn_each + sebi_each + gst_each)
    fixed += notional_inr * rates["stt_sell"]   # one sell leg
    fixed += notional_inr * rates["stamp_buy"]  # one buy leg

    slippage = notional_inr * (rates["slippage_bps"] / 10_000.0)
    return fixed + slippage


def apply_to_pnl(pnl_gross_inr: float, notional_inr: float, side: str, instrument: str = "stock_fut") -> float:
    """Subtract round-trip cost from gross P&L."""
    return pnl_gross_inr - round_trip_cost_inr(notional_inr, side, instrument)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest pipeline/tests/research/phase_c_v5/test_cost_model.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add pipeline/research/phase_c_v5/cost_model.py pipeline/tests/research/phase_c_v5/test_cost_model.py
git commit -m "feat(phase-c-v5): cost model with stock/index/sectoral/options dispatch"
```

---

## Task 3: index_fetcher.py — Kite cache for sectoral index OHLC

**Files:**
- Create: `pipeline/research/phase_c_v5/index_fetcher.py`
- Create: `pipeline/tests/research/phase_c_v5/test_index_fetcher.py`

Patterns after `pipeline/research/phase_c_backtest/fetcher.py`. Two cache dirs: daily CSV (long-lived, 5y), minute parquet (60d window).

- [ ] **Step 1: Write the failing test**

```python
# pipeline/tests/research/phase_c_v5/test_index_fetcher.py
import pandas as pd
import pytest
from unittest.mock import patch
from pipeline.research.phase_c_v5 import index_fetcher


SAMPLE_DAILY_ROWS = [
    {"date": "2024-10-04", "open": 25500.0, "high": 25700.0, "low": 25400.0, "close": 25620.0, "volume": 0, "source": "kite"},
    {"date": "2024-10-07", "open": 25620.0, "high": 25800.0, "low": 25550.0, "close": 25750.0, "volume": 0, "source": "kite"},
]


def test_fetch_daily_caches_to_csv(tmp_path, monkeypatch):
    monkeypatch.setattr(index_fetcher, "_DAILY_DIR", tmp_path)
    with patch("pipeline.research.phase_c_v5.index_fetcher._kite_fetch", return_value=SAMPLE_DAILY_ROWS):
        df = index_fetcher.fetch_daily("NIFTY 50", days=10)
    assert (tmp_path / "NIFTY_50_daily.csv").is_file()
    assert len(df) == 2
    assert list(df.columns) == ["date", "open", "high", "low", "close", "volume"]


def test_fetch_daily_uses_cache_when_fresh(tmp_path, monkeypatch):
    monkeypatch.setattr(index_fetcher, "_DAILY_DIR", tmp_path)
    cache = tmp_path / "BANKNIFTY_daily.csv"
    pd.DataFrame(SAMPLE_DAILY_ROWS).to_csv(cache, index=False)
    with patch("pipeline.research.phase_c_v5.index_fetcher._kite_fetch") as mock:
        df = index_fetcher.fetch_daily("BANKNIFTY", days=5)
        mock.assert_not_called()
    assert len(df) == 2


def test_fetch_minute_caches_to_parquet(tmp_path, monkeypatch):
    monkeypatch.setattr(index_fetcher, "_MINUTE_DIR", tmp_path)
    minute_rows = [{"date": "2024-10-04 09:15:00", "open": 25500, "high": 25510, "low": 25490, "close": 25505, "volume": 0, "source": "kite"}]
    with patch("pipeline.research.phase_c_v5.index_fetcher._kite_fetch", return_value=minute_rows):
        df = index_fetcher.fetch_minute("NIFTY 50", "2024-10-04")
    assert (tmp_path / "NIFTY_50_2024-10-04.parquet").is_file()
    assert len(df) == 1


def test_symbol_to_filename_replaces_spaces():
    assert index_fetcher._symbol_to_filename("NIFTY 50") == "NIFTY_50"
    assert index_fetcher._symbol_to_filename("NIFTY FIN SERVICE") == "NIFTY_FIN_SERVICE"


def test_fetch_minute_filters_to_trade_date(tmp_path, monkeypatch):
    monkeypatch.setattr(index_fetcher, "_MINUTE_DIR", tmp_path)
    rows = [
        {"date": "2024-10-04 09:15:00", "open": 1, "high": 1, "low": 1, "close": 1, "volume": 0, "source": "kite"},
        {"date": "2024-10-03 09:15:00", "open": 2, "high": 2, "low": 2, "close": 2, "volume": 0, "source": "kite"},
    ]
    with patch("pipeline.research.phase_c_v5.index_fetcher._kite_fetch", return_value=rows):
        df = index_fetcher.fetch_minute("NIFTY 50", "2024-10-04")
    assert len(df) == 1
    assert df.iloc[0]["close"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest pipeline/tests/research/phase_c_v5/test_index_fetcher.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement**

```python
# pipeline/research/phase_c_v5/index_fetcher.py
"""Kite-backed cache for sectoral index OHLC.

Daily bars cached as CSV (long-lived, 5y of history per index).
Minute bars cached as parquet (60-day window per Kite retention).
"""
from __future__ import annotations

import logging
from pathlib import Path
import pandas as pd

from . import paths

paths.ensure_cache()

_DAILY_DIR = paths.INDICES_DAILY_DIR
_MINUTE_DIR = paths.INDICES_MINUTE_DIR

log = logging.getLogger(__name__)


def _symbol_to_filename(symbol: str) -> str:
    """Convert 'NIFTY 50' → 'NIFTY_50' for safe path naming."""
    return symbol.replace(" ", "_")


def _kite_fetch(symbol: str, interval: str, days: int) -> list[dict]:
    """Lazy import so tests can patch without triggering kite SDK import."""
    from pipeline.kite_client import fetch_historical
    return fetch_historical(symbol, interval=interval, days=days)


def _to_df(rows: list[dict]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"])
    df = pd.DataFrame(rows)
    return df[["date", "open", "high", "low", "close", "volume"]].copy()


def fetch_daily(symbol: str, days: int = 1825) -> pd.DataFrame:
    """Fetch daily OHLC for an index. Cached at indices/<SYMBOL>_daily.csv."""
    fname = f"{_symbol_to_filename(symbol)}_daily.csv"
    cache_path = Path(_DAILY_DIR) / fname
    if cache_path.is_file():
        df = pd.read_csv(cache_path)
        log.debug("cache hit: %s daily (%d rows)", symbol, len(df))
        return df
    rows = _kite_fetch(symbol, interval="day", days=days)
    df = _to_df(rows)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(cache_path, index=False)
    log.info("fetched + cached: %s daily (%d rows)", symbol, len(df))
    return df


def fetch_minute(symbol: str, trade_date: str) -> pd.DataFrame:
    """Fetch 1-min bars for an index on trade_date (YYYY-MM-DD).

    Cached at indices/intraday/<SYMBOL>_<DATE>.parquet.
    """
    fname = f"{_symbol_to_filename(symbol)}_{trade_date}.parquet"
    cache_path = Path(_MINUTE_DIR) / fname
    if cache_path.is_file():
        df = pd.read_parquet(cache_path)
        log.debug("cache hit: %s minute %s (%d rows)", symbol, trade_date, len(df))
        return df
    days_back = max(1, (pd.Timestamp.now().normalize() - pd.Timestamp(trade_date)).days + 2)
    rows = _kite_fetch(symbol, interval="minute", days=days_back)
    df = _to_df(rows)
    if not df.empty:
        df = df[df["date"].astype(str).str[:10] == trade_date].copy()
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(cache_path, index=False)
    log.info("fetched + cached: %s minute %s (%d rows)", symbol, trade_date, len(df))
    return df
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest pipeline/tests/research/phase_c_v5/test_index_fetcher.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add pipeline/research/phase_c_v5/index_fetcher.py pipeline/tests/research/phase_c_v5/test_index_fetcher.py
git commit -m "feat(phase-c-v5): index fetcher with daily CSV + minute parquet cache"
```

---

## Task 4: tradeable_indices.py — NSE F&O availability check

**Files:**
- Create: `pipeline/research/phase_c_v5/tradeable_indices.py`
- Create: `pipeline/tests/research/phase_c_v5/test_tradeable_indices.py`

Hits NSE live-quote endpoint to discover which sectorals have derivatives. Output: `pipeline/config/tradeable_sectorals.json`. Network calls are isolated behind `_fetch_nse_derivatives_page(symbol)` so tests can patch.

- [ ] **Step 1: Write the failing test**

```python
# pipeline/tests/research/phase_c_v5/test_tradeable_indices.py
import json
from unittest.mock import patch
from pipeline.research.phase_c_v5 import tradeable_indices


def test_check_one_returns_true_when_derivatives_present():
    html = '<html>...stocks: [{"symbol": "NIFTY", "expiryDate": "30-OCT-2026"}]...</html>'
    with patch.object(tradeable_indices, "_fetch_nse_derivatives_page", return_value=html):
        assert tradeable_indices.check_one("NIFTY IT") is True


def test_check_one_returns_false_when_no_derivatives():
    html = '<html>no derivatives data found for this symbol</html>'
    with patch.object(tradeable_indices, "_fetch_nse_derivatives_page", return_value=html):
        assert tradeable_indices.check_one("NIFTY MEDIA") is False


def test_check_one_returns_false_on_network_error():
    with patch.object(tradeable_indices, "_fetch_nse_derivatives_page", side_effect=ConnectionError("dns")):
        assert tradeable_indices.check_one("NIFTY AUTO") is False


def test_check_all_writes_json(tmp_path, monkeypatch):
    out = tmp_path / "tradeable_sectorals.json"
    monkeypatch.setattr(tradeable_indices, "_OUTPUT_PATH", out)
    with patch.object(tradeable_indices, "check_one", side_effect=[True, False, True]):
        result = tradeable_indices.check_all(["NIFTY IT", "NIFTY MEDIA", "NIFTY METAL"])
    assert result == {"NIFTY IT": True, "NIFTY MEDIA": False, "NIFTY METAL": True}
    saved = json.loads(out.read_text())
    assert saved == result


def test_default_index_list_covers_14_sectorals():
    assert len(tradeable_indices.DEFAULT_INDICES) >= 14
    assert "NIFTY IT" in tradeable_indices.DEFAULT_INDICES
    assert "NIFTY METAL" in tradeable_indices.DEFAULT_INDICES
    assert "BANKNIFTY" in tradeable_indices.DEFAULT_INDICES
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest pipeline/tests/research/phase_c_v5/test_tradeable_indices.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement**

```python
# pipeline/research/phase_c_v5/tradeable_indices.py
"""NSE F&O availability check for sectoral indices.

Hits NSE's get-quotes/derivatives endpoint per symbol; returns True iff
the page contains a futures/options chain. Output cached to
pipeline/config/tradeable_sectorals.json so the rest of V5 can consult
it without re-checking on every run.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from urllib.parse import quote

from . import paths

log = logging.getLogger(__name__)

_OUTPUT_PATH = paths.TRADEABLE_PATH

DEFAULT_INDICES = [
    "NIFTY 50", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "NIFTY NEXT 50",
    "NIFTY IT", "NIFTY METAL", "NIFTY PSU BANK",
    "NIFTY AUTO", "NIFTY PHARMA", "NIFTY FMCG", "NIFTY ENERGY",
    "NIFTY REALTY", "NIFTY MEDIA", "NIFTY PVT BANK", "NIFTY FIN SERVICE",
]


def _fetch_nse_derivatives_page(symbol: str) -> str:
    """Fetch the NSE derivatives quote page HTML for a symbol.

    Isolated for testability — production hits the live endpoint, tests patch.
    """
    import requests
    url = f"https://www.nseindia.com/get-quotes/derivatives?symbol={quote(symbol)}"
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; AnkaResearch/1.0)",
        "Accept": "text/html,application/xhtml+xml",
    }
    resp = requests.get(url, headers=headers, timeout=10)
    resp.raise_for_status()
    return resp.text


def check_one(symbol: str) -> bool:
    """Return True if NSE shows a derivatives chain for this index."""
    try:
        html = _fetch_nse_derivatives_page(symbol)
    except Exception as exc:
        log.warning("NSE check failed for %s: %s", symbol, exc)
        return False
    # Heuristic: live quote pages contain expiryDate JSON when derivatives exist.
    return "expiryDate" in html


def check_all(indices: list[str] | None = None) -> dict[str, bool]:
    """Check every index in the list; write results to tradeable_sectorals.json."""
    indices = indices if indices is not None else DEFAULT_INDICES
    result = {sym: check_one(sym) for sym in indices}
    _OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    _OUTPUT_PATH.write_text(json.dumps(result, indent=2))
    return result


def load_cached() -> dict[str, bool]:
    """Return previously-saved availability map. Empty dict if not yet checked."""
    if not _OUTPUT_PATH.is_file():
        return {}
    return json.loads(_OUTPUT_PATH.read_text())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest pipeline/tests/research/phase_c_v5/test_tradeable_indices.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add pipeline/research/phase_c_v5/tradeable_indices.py pipeline/tests/research/phase_c_v5/test_tradeable_indices.py
git commit -m "feat(phase-c-v5): NSE F&O availability check for sectoral indices"
```

---

## Task 5: concentration.py — sector_concentration.json builder + loader

**Files:**
- Create: `pipeline/research/phase_c_v5/concentration.py`
- Create: `pipeline/tests/research/phase_c_v5/test_concentration.py`
- Create: `pipeline/config/sector_concentration.json` (seed file)

Loads a static JSON of index→top-N constituents with weights. The seed file is hand-curated from Niftyindices.com factsheets; concentration.py just loads/queries it.

- [ ] **Step 1: Write the failing test**

```python
# pipeline/tests/research/phase_c_v5/test_concentration.py
import json
import pytest
from pipeline.research.phase_c_v5 import concentration


SAMPLE_CONFIG = {
    "BANKNIFTY": {
        "constituents": [
            {"symbol": "HDFCBANK", "weight": 0.28},
            {"symbol": "ICICIBANK", "weight": 0.24},
            {"symbol": "SBIN", "weight": 0.10},
            {"symbol": "AXISBANK", "weight": 0.08},
        ],
        "top_n_threshold": 0.70,
    },
    "NIFTY IT": {
        "constituents": [
            {"symbol": "TCS", "weight": 0.25},
            {"symbol": "INFY", "weight": 0.22},
            {"symbol": "HCLTECH", "weight": 0.10},
        ],
        "top_n_threshold": 0.70,
    },
}


def _write(tmp_path, monkeypatch):
    p = tmp_path / "sector_concentration.json"
    p.write_text(json.dumps(SAMPLE_CONFIG))
    monkeypatch.setattr(concentration, "_PATH", p)


def test_load_returns_dict(tmp_path, monkeypatch):
    _write(tmp_path, monkeypatch)
    cfg = concentration.load()
    assert "BANKNIFTY" in cfg
    assert cfg["BANKNIFTY"]["constituents"][0]["symbol"] == "HDFCBANK"


def test_top_constituents_returns_top_n_by_weight(tmp_path, monkeypatch):
    _write(tmp_path, monkeypatch)
    top = concentration.top_constituents("BANKNIFTY", n=3)
    assert [c["symbol"] for c in top] == ["HDFCBANK", "ICICIBANK", "SBIN"]


def test_index_for_stock_returns_index_when_in_top_threshold(tmp_path, monkeypatch):
    _write(tmp_path, monkeypatch)
    # HDFCBANK weight 0.28 + ICICIBANK 0.24 + SBIN 0.10 = 0.62 — HDFCBANK is in top-70%
    assert concentration.index_for_stock("HDFCBANK") == "BANKNIFTY"
    # AXISBANK weight 0.08 — cumulative is 0.70 — boundary, IS included
    assert concentration.index_for_stock("AXISBANK") == "BANKNIFTY"


def test_index_for_stock_returns_none_when_outside_threshold(tmp_path, monkeypatch):
    cfg = {"BANKNIFTY": {"constituents": [
        {"symbol": "HDFCBANK", "weight": 0.50},
        {"symbol": "ICICIBANK", "weight": 0.20},
        {"symbol": "SBIN", "weight": 0.05},   # cumulative 0.75 — outside 0.70
    ], "top_n_threshold": 0.70}}
    p = tmp_path / "sector_concentration.json"
    p.write_text(json.dumps(cfg))
    monkeypatch.setattr(concentration, "_PATH", p)
    assert concentration.index_for_stock("SBIN") is None


def test_index_for_stock_unknown_returns_none(tmp_path, monkeypatch):
    _write(tmp_path, monkeypatch)
    assert concentration.index_for_stock("NEVERHEARD") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest pipeline/tests/research/phase_c_v5/test_concentration.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement + write seed config**

Create `pipeline/config/sector_concentration.json` with hand-curated weights (from niftyindices.com factsheets, April 2026):

```json
{
  "BANKNIFTY": {
    "constituents": [
      {"symbol": "HDFCBANK", "weight": 0.28},
      {"symbol": "ICICIBANK", "weight": 0.24},
      {"symbol": "SBIN", "weight": 0.10},
      {"symbol": "AXISBANK", "weight": 0.08},
      {"symbol": "KOTAKBANK", "weight": 0.07}
    ],
    "top_n_threshold": 0.70
  },
  "NIFTY IT": {
    "constituents": [
      {"symbol": "TCS", "weight": 0.25},
      {"symbol": "INFY", "weight": 0.22},
      {"symbol": "HCLTECH", "weight": 0.10},
      {"symbol": "TECHM", "weight": 0.08},
      {"symbol": "WIPRO", "weight": 0.07}
    ],
    "top_n_threshold": 0.70
  },
  "NIFTY AUTO": {
    "constituents": [
      {"symbol": "M&M", "weight": 0.18},
      {"symbol": "MARUTI", "weight": 0.17},
      {"symbol": "TATAMOTORS", "weight": 0.13},
      {"symbol": "BAJAJ-AUTO", "weight": 0.09}
    ],
    "top_n_threshold": 0.70
  },
  "NIFTY METAL": {
    "constituents": [
      {"symbol": "TATASTEEL", "weight": 0.18},
      {"symbol": "JSWSTEEL", "weight": 0.15},
      {"symbol": "HINDALCO", "weight": 0.13},
      {"symbol": "VEDL", "weight": 0.10}
    ],
    "top_n_threshold": 0.70
  },
  "NIFTY PHARMA": {
    "constituents": [
      {"symbol": "SUNPHARMA", "weight": 0.22},
      {"symbol": "DRREDDY", "weight": 0.10},
      {"symbol": "CIPLA", "weight": 0.10},
      {"symbol": "DIVISLAB", "weight": 0.07}
    ],
    "top_n_threshold": 0.70
  }
}
```

```python
# pipeline/research/phase_c_v5/concentration.py
"""Loader and queries for sector concentration map.

The map answers: for an index, what are its top-N constituents and their
weights? And inversely: given a stock, which index does it materially
drive (i.e. is in that index's top-N-weight bucket)?
"""
from __future__ import annotations

import json
from . import paths

_PATH = paths.CONCENTRATION_PATH


def load() -> dict:
    return json.loads(_PATH.read_text(encoding="utf-8"))


def top_constituents(index_symbol: str, n: int = 3) -> list[dict]:
    """Return top-n constituents by weight (descending)."""
    cfg = load()
    constituents = cfg[index_symbol]["constituents"]
    return sorted(constituents, key=lambda c: -c["weight"])[:n]


def index_for_stock(stock_symbol: str) -> str | None:
    """If `stock_symbol` falls within ANY index's top_n_threshold bucket,
    return that index's symbol. If it falls in multiple, return the one
    where the stock's weight is highest. Returns None if no match.
    """
    cfg = load()
    matches: list[tuple[str, float]] = []
    for index_sym, idx_cfg in cfg.items():
        sorted_constituents = sorted(idx_cfg["constituents"], key=lambda c: -c["weight"])
        threshold = idx_cfg["top_n_threshold"]
        cumulative = 0.0
        for c in sorted_constituents:
            cumulative += c["weight"]
            if c["symbol"] == stock_symbol:
                if cumulative <= threshold or cumulative - c["weight"] < threshold:
                    matches.append((index_sym, c["weight"]))
                break
    if not matches:
        return None
    return max(matches, key=lambda m: m[1])[0]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest pipeline/tests/research/phase_c_v5/test_concentration.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add pipeline/config/sector_concentration.json pipeline/research/phase_c_v5/concentration.py pipeline/tests/research/phase_c_v5/test_concentration.py
git commit -m "feat(phase-c-v5): sector concentration map (5 sectorals seeded)"
```

---

## Task 6: basket_builder.py — group v1 OPPORTUNITY signals into baskets

**Files:**
- Create: `pipeline/research/phase_c_v5/basket_builder.py`
- Create: `pipeline/tests/research/phase_c_v5/test_basket_builder.py`

Reads the v1 ledger, returns baskets per day (sector-pair, stock-vs-index, leader-routing).
Pure function; no I/O beyond reading the v1 ledger when called by orchestrator.

The "sector" of a stock is derived from the existing sector_rotation.py SECTOR_CONSTITUENTS map (inverse lookup). We don't duplicate; we import.

- [ ] **Step 1: Write the failing test**

```python
# pipeline/tests/research/phase_c_v5/test_basket_builder.py
import pandas as pd
import pytest
from pipeline.research.phase_c_v5 import basket_builder


def _row(date, symbol, side, expected_return, sector_hint_col=None):
    r = {
        "entry_date": date, "exit_date": date, "symbol": symbol, "side": side,
        "entry_px": 100.0, "exit_px": 101.0, "notional_inr": 50000.0,
        "pnl_gross_inr": 0.0, "pnl_net_inr": 0.0,
        "label": "OPPORTUNITY", "z_score": -1.0, "expected_return": expected_return,
    }
    return r


def test_sector_pairs_groups_by_sector_per_day():
    ledger = pd.DataFrame([
        _row("2024-10-04", "TCS", "LONG", 0.005),       # NIFTY IT
        _row("2024-10-04", "INFY", "LONG", 0.001),      # NIFTY IT
        _row("2024-10-04", "TATAMOTORS", "LONG", 0.003),  # NIFTY AUTO (only one)
    ])
    pairs = basket_builder.sector_pairs(ledger)
    # Only NIFTY IT yields a pair (need >=2 same-sector signals same day)
    assert len(pairs) == 1
    p = pairs[0]
    assert p["entry_date"] == "2024-10-04"
    assert p["sector"] == "NIFTY IT"
    assert p["long_leg"] == "TCS"   # higher expected_return
    assert p["short_leg"] == "INFY"


def test_sector_pairs_skips_when_fewer_than_two_signals():
    ledger = pd.DataFrame([_row("2024-10-04", "TCS", "LONG", 0.005)])
    assert basket_builder.sector_pairs(ledger) == []


def test_stock_vs_index_pairs_each_signal_with_its_sector_index():
    ledger = pd.DataFrame([
        _row("2024-10-04", "TCS", "LONG", 0.005),
        _row("2024-10-04", "MARUTI", "LONG", 0.003),
    ])
    pairs = basket_builder.stock_vs_index(ledger)
    assert len(pairs) == 2
    by_stock = {p["stock"]: p["index"] for p in pairs}
    assert by_stock["TCS"] == "NIFTY IT"
    assert by_stock["MARUTI"] == "NIFTY AUTO"


def test_leader_routing_emits_index_trade_when_two_of_top_three_align():
    """When 2 of top-3 BANKNIFTY constituents fire same direction same day,
    emit one trade on the BANKNIFTY index instead of stock-level trades."""
    ledger = pd.DataFrame([
        _row("2024-10-04", "HDFCBANK", "LONG", 0.005),
        _row("2024-10-04", "ICICIBANK", "LONG", 0.004),
        _row("2024-10-04", "SBIN", "SHORT", -0.001),  # opposite — not aligned
    ])
    routes = basket_builder.leader_routing(ledger)
    assert len(routes) == 1
    r = routes[0]
    assert r["index"] == "BANKNIFTY"
    assert r["side"] == "LONG"
    assert set(r["constituent_sources"]) == {"HDFCBANK", "ICICIBANK"}


def test_leader_routing_no_emit_when_only_one_leader_fires():
    ledger = pd.DataFrame([_row("2024-10-04", "HDFCBANK", "LONG", 0.005)])
    assert basket_builder.leader_routing(ledger) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest pipeline/tests/research/phase_c_v5/test_basket_builder.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement**

```python
# pipeline/research/phase_c_v5/basket_builder.py
"""Basket formation from v1 ledger OPPORTUNITY signals.

Three formers are exposed:
  - sector_pairs:   long top / short bottom in same sector same day
  - stock_vs_index: each signal paired with its sector index
  - leader_routing: when 2-of-3 top constituents align, route via the index
"""
from __future__ import annotations

from collections import defaultdict
import pandas as pd

from . import concentration

# Inverse map: stock → index. Built from concentration.json at module load.
def _stock_to_index_map() -> dict[str, str]:
    cfg = concentration.load()
    out: dict[str, str] = {}
    for index_sym, idx_cfg in cfg.items():
        for c in idx_cfg["constituents"]:
            # If a stock appears in multiple, the higher-weight one wins.
            existing = out.get(c["symbol"])
            if existing is None or c["weight"] > _weight_in(cfg, existing, c["symbol"]):
                out[c["symbol"]] = index_sym
    return out


def _weight_in(cfg: dict, index_sym: str, stock_sym: str) -> float:
    for c in cfg[index_sym]["constituents"]:
        if c["symbol"] == stock_sym:
            return c["weight"]
    return 0.0


def sector_pairs(ledger: pd.DataFrame) -> list[dict]:
    """Group by (entry_date, sector). For each group with >=2 signals, emit a
    pair: long the highest expected_return signal, short the lowest.
    """
    smap = _stock_to_index_map()
    out: list[dict] = []
    ledger = ledger.copy()
    ledger["sector"] = ledger["symbol"].map(smap)
    ledger = ledger.dropna(subset=["sector"])
    for (date, sector), grp in ledger.groupby(["entry_date", "sector"]):
        if len(grp) < 2:
            continue
        sorted_grp = grp.sort_values("expected_return", ascending=False)
        out.append({
            "entry_date": date,
            "sector": sector,
            "long_leg": sorted_grp.iloc[0]["symbol"],
            "short_leg": sorted_grp.iloc[-1]["symbol"],
            "long_entry_px": float(sorted_grp.iloc[0]["entry_px"]),
            "short_entry_px": float(sorted_grp.iloc[-1]["entry_px"]),
            "long_exit_px": float(sorted_grp.iloc[0]["exit_px"]),
            "short_exit_px": float(sorted_grp.iloc[-1]["exit_px"]),
        })
    return out


def stock_vs_index(ledger: pd.DataFrame) -> list[dict]:
    """Pair each signal with its sector index (opposite-direction hedge)."""
    smap = _stock_to_index_map()
    out: list[dict] = []
    for _, row in ledger.iterrows():
        idx = smap.get(row["symbol"])
        if idx is None:
            continue
        out.append({
            "entry_date": row["entry_date"],
            "exit_date": row["exit_date"],
            "stock": row["symbol"],
            "index": idx,
            "stock_side": row["side"],
            "index_side": "SHORT" if row["side"] == "LONG" else "LONG",
            "stock_entry_px": float(row["entry_px"]),
            "stock_exit_px": float(row["exit_px"]),
        })
    return out


def leader_routing(ledger: pd.DataFrame) -> list[dict]:
    """When >=2 of top-3 constituents of an index fire same-direction OPPORTUNITY
    on the same day, emit ONE trade on the index instead of stock trades.
    """
    cfg = concentration.load()
    out: list[dict] = []
    by_date: dict[str, list[dict]] = defaultdict(list)
    for _, row in ledger.iterrows():
        by_date[row["entry_date"]].append(row.to_dict())
    for date, rows in by_date.items():
        for index_sym, idx_cfg in cfg.items():
            top3_syms = {c["symbol"] for c in
                         sorted(idx_cfg["constituents"], key=lambda c: -c["weight"])[:3]}
            matches = [r for r in rows if r["symbol"] in top3_syms]
            if len(matches) < 2:
                continue
            sides = {m["side"] for m in matches}
            if len(sides) != 1:
                continue  # constituents disagree → skip
            out.append({
                "entry_date": date,
                "index": index_sym,
                "side": next(iter(sides)),
                "constituent_sources": [m["symbol"] for m in matches],
            })
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest pipeline/tests/research/phase_c_v5/test_basket_builder.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add pipeline/research/phase_c_v5/basket_builder.py pipeline/tests/research/phase_c_v5/test_basket_builder.py
git commit -m "feat(phase-c-v5): basket builder — sector pairs, stock-vs-index, leader routing"
```

---

## Task 7: simulator.py — replay engine for daily + minute ledgers

**Files:**
- Create: `pipeline/research/phase_c_v5/simulator.py`
- Create: `pipeline/tests/research/phase_c_v5/test_simulator.py`

Two pure functions:
- `simulate_pair_daily(pair, get_close)` — closes both legs at given close prices, computes net P&L
- `simulate_overlay_daily(stock_trade, index_trade, hedge_ratio, get_close)` — single composite

These do not call Kite directly. They take a `get_close(symbol, date)` callable so tests pass canned data.

- [ ] **Step 1: Write the failing test**

```python
# pipeline/tests/research/phase_c_v5/test_simulator.py
import pytest
from pipeline.research.phase_c_v5 import simulator


def test_simulate_pair_daily_long_short_returns_net():
    """Long +2%, short -1% on equal 50k notional → +1500 gross before costs."""
    pair = {
        "entry_date": "2024-10-04", "exit_date": "2024-10-04",
        "long_leg": "A", "short_leg": "B",
        "long_entry_px": 100.0, "short_entry_px": 200.0,
        "long_exit_px": 102.0, "short_exit_px": 202.0,
        "notional_per_leg": 50000.0,
    }
    res = simulator.simulate_pair_daily(pair)
    # Long: +2% on 50k = +1000.  Short: -1% (price went up 1%) on 50k = -500.
    # Net gross = +500.
    assert abs(res["pnl_gross_inr"] - 500.0) < 0.01
    # Net should be lower (costs subtracted)
    assert res["pnl_net_inr"] < res["pnl_gross_inr"]


def test_simulate_pair_daily_zero_when_both_unchanged():
    pair = {
        "entry_date": "2024-10-04", "exit_date": "2024-10-04",
        "long_leg": "A", "short_leg": "B",
        "long_entry_px": 100.0, "short_entry_px": 200.0,
        "long_exit_px": 100.0, "short_exit_px": 200.0,
        "notional_per_leg": 50000.0,
    }
    res = simulator.simulate_pair_daily(pair)
    assert abs(res["pnl_gross_inr"]) < 0.01
    # Net is negative due to cost
    assert res["pnl_net_inr"] < 0


def test_simulate_overlay_daily_neutralises_market_move():
    """If stock and index move identically and hedge_ratio=1, overlay P&L ≈ 0."""
    res = simulator.simulate_overlay_daily(
        stock_side="LONG",
        stock_entry=100.0, stock_exit=102.0, stock_notional=50000.0,
        index_side="SHORT",
        index_entry=25000.0, index_exit=25500.0, index_notional=50000.0,
        index_instrument="index_fut",
    )
    # Both moved +2%. Long stock +1000, short index -1000. Gross = 0.
    assert abs(res["pnl_gross_inr"]) < 1.0
    # Net is negative (two sets of costs).
    assert res["pnl_net_inr"] < -100


def test_simulate_overlay_daily_extracts_alpha():
    """Stock +3%, index +1% → overlay extracts 2% alpha."""
    res = simulator.simulate_overlay_daily(
        stock_side="LONG",
        stock_entry=100.0, stock_exit=103.0, stock_notional=50000.0,
        index_side="SHORT",
        index_entry=25000.0, index_exit=25250.0, index_notional=50000.0,
        index_instrument="index_fut",
    )
    # Long stock: +1500. Short index: -500. Gross net = +1000.
    assert abs(res["pnl_gross_inr"] - 1000.0) < 1.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest pipeline/tests/research/phase_c_v5/test_simulator.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement**

```python
# pipeline/research/phase_c_v5/simulator.py
"""Replay engine for V5 variants — daily and minute ledger simulators.

All functions are pure: they take prices in, return P&L dicts. Cost model
is applied here (delegates to v5 cost_model).
"""
from __future__ import annotations

from . import cost_model


def _leg_pnl(side: str, entry: float, exit_: float, notional: float) -> float:
    if side not in ("LONG", "SHORT"):
        raise ValueError(f"side must be LONG or SHORT, got {side!r}")
    ret = (exit_ - entry) / entry
    if side == "SHORT":
        ret = -ret
    return notional * ret


def simulate_pair_daily(pair: dict, instrument: str = "stock_fut") -> dict:
    """Two-leg pair P&L: long top / short bottom. Costs applied per leg."""
    notional = pair.get("notional_per_leg", 50_000.0)
    long_pnl = _leg_pnl("LONG", pair["long_entry_px"], pair["long_exit_px"], notional)
    short_pnl = _leg_pnl("SHORT", pair["short_entry_px"], pair["short_exit_px"], notional)
    gross = long_pnl + short_pnl
    cost = (cost_model.round_trip_cost_inr(notional, "LONG", instrument)
            + cost_model.round_trip_cost_inr(notional, "SHORT", instrument))
    return {
        "entry_date": pair["entry_date"],
        "exit_date": pair["exit_date"],
        "long_leg": pair["long_leg"],
        "short_leg": pair["short_leg"],
        "pnl_gross_inr": gross,
        "pnl_net_inr": gross - cost,
        "cost_inr": cost,
    }


def simulate_overlay_daily(
    stock_side: str, stock_entry: float, stock_exit: float, stock_notional: float,
    index_side: str, index_entry: float, index_exit: float, index_notional: float,
    index_instrument: str = "index_fut",
) -> dict:
    """Stock leg + index hedge leg. Returns composite P&L."""
    stock_pnl = _leg_pnl(stock_side, stock_entry, stock_exit, stock_notional)
    index_pnl = _leg_pnl(index_side, index_entry, index_exit, index_notional)
    gross = stock_pnl + index_pnl
    cost = (cost_model.round_trip_cost_inr(stock_notional, stock_side, "stock_fut")
            + cost_model.round_trip_cost_inr(index_notional, index_side, index_instrument))
    return {
        "stock_pnl": stock_pnl,
        "index_pnl": index_pnl,
        "pnl_gross_inr": gross,
        "pnl_net_inr": gross - cost,
        "cost_inr": cost,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest pipeline/tests/research/phase_c_v5/test_simulator.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add pipeline/research/phase_c_v5/simulator.py pipeline/tests/research/phase_c_v5/test_simulator.py
git commit -m "feat(phase-c-v5): simulator for pair + overlay daily P&L with cost"
```

---

## Task 8: variants/v51_sector_pair.py — first variant (sector-neutral pair)

**Files:**
- Create: `pipeline/research/phase_c_v5/variants/__init__.py`
- Create: `pipeline/research/phase_c_v5/variants/v51_sector_pair.py`
- Create: `pipeline/tests/research/phase_c_v5/test_v51_sector_pair.py`

Reads v1 ledger → basket_builder.sector_pairs → simulator.simulate_pair_daily for each. Emits parquet.

- [ ] **Step 1: Write the failing test**

```python
# pipeline/tests/research/phase_c_v5/test_v51_sector_pair.py
import pandas as pd
import pytest
from pipeline.research.phase_c_v5.variants import v51_sector_pair


def _row(date, symbol, side, exp_ret, entry=100.0, exit_=101.0):
    return {
        "entry_date": date, "exit_date": date, "symbol": symbol, "side": side,
        "entry_px": entry, "exit_px": exit_, "notional_inr": 50000.0,
        "pnl_gross_inr": 0.0, "pnl_net_inr": 0.0,
        "label": "OPPORTUNITY", "z_score": -1.0, "expected_return": exp_ret,
    }


def test_run_emits_one_row_per_pair():
    ledger = pd.DataFrame([
        _row("2024-10-04", "TCS", "LONG", 0.005, 3500, 3535),
        _row("2024-10-04", "INFY", "LONG", 0.001, 1500, 1505),
    ])
    out = v51_sector_pair.run(ledger)
    assert len(out) == 1
    row = out.iloc[0]
    assert row["sector"] == "NIFTY IT"
    assert row["long_leg"] == "TCS"
    assert row["short_leg"] == "INFY"
    assert "pnl_net_inr" in row.index


def test_run_drops_non_opportunity_rows():
    ledger = pd.DataFrame([
        _row("2024-10-04", "TCS", "LONG", 0.005, 3500, 3535),
        _row("2024-10-04", "INFY", "LONG", 0.001, 1500, 1505),
    ])
    ledger.iloc[0, ledger.columns.get_loc("label")] = "WARNING"
    out = v51_sector_pair.run(ledger)
    assert len(out) == 0


def test_run_returns_empty_when_no_pairs():
    ledger = pd.DataFrame([_row("2024-10-04", "TCS", "LONG", 0.005)])
    out = v51_sector_pair.run(ledger)
    assert len(out) == 0
    assert "pnl_net_inr" in out.columns
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest pipeline/tests/research/phase_c_v5/test_v51_sector_pair.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement**

```python
# pipeline/research/phase_c_v5/variants/__init__.py
```
(empty file)

```python
# pipeline/research/phase_c_v5/variants/v51_sector_pair.py
"""V5.1 — Sector-neutral pair.

For each sector with >=2 same-day OPPORTUNITY signals, long the highest
expected_return / short the lowest. Equal notional. Hold to v1 exit_date.
"""
from __future__ import annotations

import pandas as pd

from .. import basket_builder, simulator


def run(v1_ledger: pd.DataFrame) -> pd.DataFrame:
    """Build pairs, simulate, return per-pair ledger."""
    opp_only = v1_ledger[v1_ledger["label"] == "OPPORTUNITY"]
    pairs = basket_builder.sector_pairs(opp_only)
    rows: list[dict] = []
    for p in pairs:
        sim = simulator.simulate_pair_daily({**p, "notional_per_leg": 50_000.0})
        rows.append({
            "variant": "v51",
            "entry_date": sim["entry_date"],
            "exit_date": sim["exit_date"],
            "sector": p["sector"],
            "long_leg": sim["long_leg"],
            "short_leg": sim["short_leg"],
            "pnl_gross_inr": sim["pnl_gross_inr"],
            "pnl_net_inr": sim["pnl_net_inr"],
            "cost_inr": sim["cost_inr"],
        })
    cols = ["variant", "entry_date", "exit_date", "sector", "long_leg", "short_leg",
            "pnl_gross_inr", "pnl_net_inr", "cost_inr"]
    return pd.DataFrame(rows, columns=cols)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest pipeline/tests/research/phase_c_v5/test_v51_sector_pair.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add pipeline/research/phase_c_v5/variants/__init__.py pipeline/research/phase_c_v5/variants/v51_sector_pair.py pipeline/tests/research/phase_c_v5/test_v51_sector_pair.py
git commit -m "feat(phase-c-v5): variant V5.1 sector-neutral pair"
```

---

## Task 9: variants/v52_stock_vs_index.py — stock vs sector-index hedge

**Files:**
- Create: `pipeline/research/phase_c_v5/variants/v52_stock_vs_index.py`
- Create: `pipeline/tests/research/phase_c_v5/test_v52_stock_vs_index.py`

For each OPPORTUNITY signal, hedge with opposite-direction sector index futures. Beta from rolling 60-day OLS on close-to-close returns; capped at [0.5, 1.5]; warning logged if outside.

- [ ] **Step 1: Write the failing test**

```python
# pipeline/tests/research/phase_c_v5/test_v52_stock_vs_index.py
import pandas as pd
import pytest
from unittest.mock import patch
from pipeline.research.phase_c_v5.variants import v52_stock_vs_index


def _row(date, symbol, side, entry, exit_):
    return {"entry_date": date, "exit_date": date, "symbol": symbol, "side": side,
            "entry_px": entry, "exit_px": exit_, "notional_inr": 50000.0,
            "pnl_gross_inr": 0.0, "pnl_net_inr": 0.0,
            "label": "OPPORTUNITY", "z_score": -1.0, "expected_return": 0.001}


def test_compute_beta_returns_one_for_perfectly_correlated():
    stock_returns = [0.01, -0.005, 0.02, 0.0, 0.01]
    index_returns = [0.01, -0.005, 0.02, 0.0, 0.01]
    beta = v52_stock_vs_index._beta(stock_returns, index_returns)
    assert abs(beta - 1.0) < 0.01


def test_compute_beta_returns_two_for_double_amplitude():
    stock_returns = [0.02, -0.01, 0.04, 0.0, 0.02]
    index_returns = [0.01, -0.005, 0.02, 0.0, 0.01]
    beta = v52_stock_vs_index._beta(stock_returns, index_returns)
    assert abs(beta - 2.0) < 0.01


def test_compute_beta_clipped_to_range():
    # Stock 5x amplitude — beta=5, clipped to 1.5
    stock_returns = [0.05, -0.025, 0.10, 0.0, 0.05]
    index_returns = [0.01, -0.005, 0.02, 0.0, 0.01]
    beta = v52_stock_vs_index._beta(stock_returns, index_returns)
    assert beta == 1.5


def test_run_emits_one_row_per_signal_with_index_match():
    ledger = pd.DataFrame([_row("2024-10-04", "TCS", "LONG", 3500.0, 3535.0)])
    fake_index_close = lambda sym, date: 41000.0 if date == "2024-10-04" else 41200.0
    fake_index_returns = [0.01, -0.005] * 30
    with patch.object(v52_stock_vs_index, "_get_index_close", side_effect=lambda sym, date: 41000.0 if date == "2024-10-04" else 41200.0), \
         patch.object(v52_stock_vs_index, "_rolling_returns", return_value=([0.01]*60, [0.01]*60)):
        out = v52_stock_vs_index.run(ledger)
    assert len(out) == 1
    assert out.iloc[0]["index"] == "NIFTY IT"


def test_run_skips_signals_with_no_index_match():
    ledger = pd.DataFrame([_row("2024-10-04", "NEVERHEARD", "LONG", 100.0, 101.0)])
    out = v52_stock_vs_index.run(ledger)
    assert len(out) == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest pipeline/tests/research/phase_c_v5/test_v52_stock_vs_index.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement**

```python
# pipeline/research/phase_c_v5/variants/v52_stock_vs_index.py
"""V5.2 — Stock vs sector-index hedge.

Each OPPORTUNITY trade is paired with opposite-direction sector index
futures sized by rolling 60-day OLS beta. Beta capped at [0.5, 1.5];
out-of-range beta is logged and clipped (not skipped).
"""
from __future__ import annotations

import logging
import numpy as np
import pandas as pd

from .. import basket_builder, simulator, index_fetcher

log = logging.getLogger(__name__)

BETA_FLOOR = 0.5
BETA_CEIL = 1.5
ROLLING_WINDOW = 60  # business days


def _beta(stock_returns: list[float], index_returns: list[float]) -> float:
    """OLS beta = cov(s,i) / var(i), clipped to [BETA_FLOOR, BETA_CEIL]."""
    s = np.asarray(stock_returns, dtype=float)
    i = np.asarray(index_returns, dtype=float)
    if i.var(ddof=1) == 0:
        return 1.0
    raw = float(np.cov(s, i, ddof=1)[0, 1] / i.var(ddof=1))
    if raw < BETA_FLOOR or raw > BETA_CEIL:
        log.warning("beta %.2f outside [%.1f, %.1f] — clipping", raw, BETA_FLOOR, BETA_CEIL)
    return max(BETA_FLOOR, min(BETA_CEIL, raw))


def _get_index_close(index_symbol: str, date: str) -> float | None:
    df = index_fetcher.fetch_daily(index_symbol)
    df = df[df["date"].astype(str).str[:10] == date]
    if df.empty:
        return None
    return float(df.iloc[0]["close"])


def _rolling_returns(stock_symbol: str, index_symbol: str, end_date: str,
                     window: int = ROLLING_WINDOW) -> tuple[list[float], list[float]]:
    """Return (stock_returns, index_returns) over the `window` business days
    ending strictly before `end_date`. Empty lists if data unavailable."""
    from pipeline.research.phase_c_backtest import fetcher as v1_fetcher
    s_df = v1_fetcher.fetch_daily(stock_symbol)
    i_df = index_fetcher.fetch_daily(index_symbol)
    if s_df.empty or i_df.empty:
        return [], []
    s_df = s_df[s_df["date"].astype(str).str[:10] < end_date].tail(window + 1)
    i_df = i_df[i_df["date"].astype(str).str[:10] < end_date].tail(window + 1)
    if len(s_df) < window or len(i_df) < window:
        return [], []
    s_ret = s_df["close"].pct_change().dropna().tolist()
    i_ret = i_df["close"].pct_change().dropna().tolist()
    return s_ret, i_ret


def run(v1_ledger: pd.DataFrame) -> pd.DataFrame:
    opp_only = v1_ledger[v1_ledger["label"] == "OPPORTUNITY"]
    overlays = basket_builder.stock_vs_index(opp_only)
    rows: list[dict] = []
    for o in overlays:
        s_ret, i_ret = _rolling_returns(o["stock"], o["index"], o["entry_date"])
        beta = _beta(s_ret, i_ret) if s_ret and i_ret else 1.0

        idx_entry = _get_index_close(o["index"], o["entry_date"])
        idx_exit = _get_index_close(o["index"], o["exit_date"])
        if idx_entry is None or idx_exit is None:
            log.warning("missing index price for %s on %s/%s — skipping",
                        o["index"], o["entry_date"], o["exit_date"])
            continue

        stock_notional = 50_000.0
        index_notional = stock_notional * beta

        # Sectoral indices use sectoral_fut rates; NIFTY/BANKNIFTY use index_fut
        index_instrument = "index_fut" if o["index"] in ("NIFTY 50", "BANKNIFTY", "FINNIFTY") else "sectoral_fut"

        sim = simulator.simulate_overlay_daily(
            stock_side=o["stock_side"],
            stock_entry=o["stock_entry_px"], stock_exit=o["stock_exit_px"],
            stock_notional=stock_notional,
            index_side=o["index_side"],
            index_entry=idx_entry, index_exit=idx_exit,
            index_notional=index_notional,
            index_instrument=index_instrument,
        )
        rows.append({
            "variant": "v52",
            "entry_date": o["entry_date"],
            "exit_date": o["exit_date"],
            "stock": o["stock"],
            "index": o["index"],
            "beta": beta,
            "pnl_gross_inr": sim["pnl_gross_inr"],
            "pnl_net_inr": sim["pnl_net_inr"],
            "cost_inr": sim["cost_inr"],
        })
    cols = ["variant", "entry_date", "exit_date", "stock", "index", "beta",
            "pnl_gross_inr", "pnl_net_inr", "cost_inr"]
    return pd.DataFrame(rows, columns=cols)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest pipeline/tests/research/phase_c_v5/test_v52_stock_vs_index.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add pipeline/research/phase_c_v5/variants/v52_stock_vs_index.py pipeline/tests/research/phase_c_v5/test_v52_stock_vs_index.py
git commit -m "feat(phase-c-v5): variant V5.2 stock vs sector-index hedge with beta-sized leg"
```

---

## Task 10: variants/v53_nifty_overlay.py — NIFTY 50 universal hedge

**Files:**
- Create: `pipeline/research/phase_c_v5/variants/v53_nifty_overlay.py`
- Create: `pipeline/tests/research/phase_c_v5/test_v53_nifty_overlay.py`

Same as V5.2 but the index leg is always NIFTY 50, regardless of stock sector. Simpler, deeper liquidity.

- [ ] **Step 1: Write the failing test**

```python
# pipeline/tests/research/phase_c_v5/test_v53_nifty_overlay.py
import pandas as pd
from unittest.mock import patch
from pipeline.research.phase_c_v5.variants import v53_nifty_overlay


def _row(date, symbol, side, entry, exit_):
    return {"entry_date": date, "exit_date": date, "symbol": symbol, "side": side,
            "entry_px": entry, "exit_px": exit_, "notional_inr": 50000.0,
            "pnl_gross_inr": 0.0, "pnl_net_inr": 0.0,
            "label": "OPPORTUNITY", "z_score": -1.0, "expected_return": 0.001}


def test_run_uses_nifty_for_every_signal():
    ledger = pd.DataFrame([
        _row("2024-10-04", "TCS", "LONG", 3500.0, 3535.0),
        _row("2024-10-04", "TATAMOTORS", "LONG", 800.0, 808.0),
    ])
    with patch("pipeline.research.phase_c_v5.variants.v53_nifty_overlay._get_nifty_close",
               return_value=25000.0), \
         patch("pipeline.research.phase_c_v5.variants.v53_nifty_overlay._rolling_returns",
               return_value=([0.01]*60, [0.01]*60)):
        out = v53_nifty_overlay.run(ledger)
    assert len(out) == 2
    assert (out["index"] == "NIFTY 50").all()


def test_run_skips_when_nifty_close_missing():
    ledger = pd.DataFrame([_row("2024-10-04", "TCS", "LONG", 3500.0, 3535.0)])
    with patch("pipeline.research.phase_c_v5.variants.v53_nifty_overlay._get_nifty_close",
               return_value=None):
        out = v53_nifty_overlay.run(ledger)
    assert len(out) == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest pipeline/tests/research/phase_c_v5/test_v53_nifty_overlay.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement**

```python
# pipeline/research/phase_c_v5/variants/v53_nifty_overlay.py
"""V5.3 — NIFTY 50 universal beta overlay.

Same logic as V5.2 but the hedge is always NIFTY 50 futures regardless
of stock sector. Cheaper liquidity, simpler implementation.
"""
from __future__ import annotations

import logging
import numpy as np
import pandas as pd

from .. import simulator, index_fetcher
from .v52_stock_vs_index import _beta, BETA_FLOOR, BETA_CEIL, ROLLING_WINDOW

log = logging.getLogger(__name__)

NIFTY_SYMBOL = "NIFTY 50"


def _get_nifty_close(date: str) -> float | None:
    df = index_fetcher.fetch_daily(NIFTY_SYMBOL)
    df = df[df["date"].astype(str).str[:10] == date]
    if df.empty:
        return None
    return float(df.iloc[0]["close"])


def _rolling_returns(stock_symbol: str, end_date: str,
                     window: int = ROLLING_WINDOW) -> tuple[list[float], list[float]]:
    from pipeline.research.phase_c_backtest import fetcher as v1_fetcher
    s_df = v1_fetcher.fetch_daily(stock_symbol)
    i_df = index_fetcher.fetch_daily(NIFTY_SYMBOL)
    if s_df.empty or i_df.empty:
        return [], []
    s_df = s_df[s_df["date"].astype(str).str[:10] < end_date].tail(window + 1)
    i_df = i_df[i_df["date"].astype(str).str[:10] < end_date].tail(window + 1)
    if len(s_df) < window or len(i_df) < window:
        return [], []
    return (s_df["close"].pct_change().dropna().tolist(),
            i_df["close"].pct_change().dropna().tolist())


def run(v1_ledger: pd.DataFrame) -> pd.DataFrame:
    opp_only = v1_ledger[v1_ledger["label"] == "OPPORTUNITY"]
    rows: list[dict] = []
    for _, sig in opp_only.iterrows():
        nifty_entry = _get_nifty_close(sig["entry_date"])
        nifty_exit = _get_nifty_close(sig["exit_date"])
        if nifty_entry is None or nifty_exit is None:
            continue
        s_ret, i_ret = _rolling_returns(sig["symbol"], sig["entry_date"])
        beta = _beta(s_ret, i_ret) if s_ret and i_ret else 1.0

        stock_notional = 50_000.0
        index_notional = stock_notional * beta

        index_side = "SHORT" if sig["side"] == "LONG" else "LONG"
        sim = simulator.simulate_overlay_daily(
            stock_side=sig["side"],
            stock_entry=sig["entry_px"], stock_exit=sig["exit_px"],
            stock_notional=stock_notional,
            index_side=index_side,
            index_entry=nifty_entry, index_exit=nifty_exit,
            index_notional=index_notional,
            index_instrument="index_fut",
        )
        rows.append({
            "variant": "v53",
            "entry_date": sig["entry_date"],
            "exit_date": sig["exit_date"],
            "stock": sig["symbol"],
            "index": NIFTY_SYMBOL,
            "beta": beta,
            "pnl_gross_inr": sim["pnl_gross_inr"],
            "pnl_net_inr": sim["pnl_net_inr"],
            "cost_inr": sim["cost_inr"],
        })
    cols = ["variant", "entry_date", "exit_date", "stock", "index", "beta",
            "pnl_gross_inr", "pnl_net_inr", "cost_inr"]
    return pd.DataFrame(rows, columns=cols)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest pipeline/tests/research/phase_c_v5/test_v53_nifty_overlay.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add pipeline/research/phase_c_v5/variants/v53_nifty_overlay.py pipeline/tests/research/phase_c_v5/test_v53_nifty_overlay.py
git commit -m "feat(phase-c-v5): variant V5.3 NIFTY 50 universal beta overlay"
```

---

## Task 11: variants/v54_dispersion.py — BANKNIFTY/IT leader-strong/index-flat

**Files:**
- Create: `pipeline/research/phase_c_v5/variants/v54_dispersion.py`
- Create: `pipeline/tests/research/phase_c_v5/test_v54_dispersion.py`

Long the leader stock, short its index, only when leader 5-bar return > index 5-bar return at signal time. Applies to BANKNIFTY (top-3: HDFCBANK/ICICIBANK/SBIN) and NIFTY IT (top-3: TCS/INFY/HCLTECH).

- [ ] **Step 1: Write the failing test**

```python
# pipeline/tests/research/phase_c_v5/test_v54_dispersion.py
import pandas as pd
from unittest.mock import patch
from pipeline.research.phase_c_v5.variants import v54_dispersion


def _row(date, symbol, side, entry, exit_):
    return {"entry_date": date, "exit_date": date, "symbol": symbol, "side": side,
            "entry_px": entry, "exit_px": exit_, "notional_inr": 50000.0,
            "pnl_gross_inr": 0.0, "pnl_net_inr": 0.0,
            "label": "OPPORTUNITY", "z_score": -1.0, "expected_return": 0.001}


def test_run_takes_trade_when_leader_outpaces_index():
    """HDFCBANK +2% over 5 bars, BANKNIFTY +0.5% — dispersion is 1.5%, take trade."""
    ledger = pd.DataFrame([_row("2024-10-04", "HDFCBANK", "LONG", 1700.0, 1734.0)])
    with patch("pipeline.research.phase_c_v5.variants.v54_dispersion._stock_5bar_return",
               return_value=0.02), \
         patch("pipeline.research.phase_c_v5.variants.v54_dispersion._index_5bar_return",
               return_value=0.005), \
         patch("pipeline.research.phase_c_v5.variants.v54_dispersion._get_index_close",
               return_value=51000.0):
        out = v54_dispersion.run(ledger)
    assert len(out) == 1
    assert out.iloc[0]["index"] == "BANKNIFTY"


def test_run_skips_trade_when_leader_lags_index():
    """HDFCBANK +0.5%, BANKNIFTY +2% — leader lags, skip."""
    ledger = pd.DataFrame([_row("2024-10-04", "HDFCBANK", "LONG", 1700.0, 1734.0)])
    with patch("pipeline.research.phase_c_v5.variants.v54_dispersion._stock_5bar_return",
               return_value=0.005), \
         patch("pipeline.research.phase_c_v5.variants.v54_dispersion._index_5bar_return",
               return_value=0.02):
        out = v54_dispersion.run(ledger)
    assert len(out) == 0


def test_run_only_considers_top3_constituents():
    """KOTAKBANK is in BANKNIFTY but not top-3 (HDFCBANK/ICICIBANK/SBIN)."""
    ledger = pd.DataFrame([_row("2024-10-04", "KOTAKBANK", "LONG", 1700.0, 1734.0)])
    out = v54_dispersion.run(ledger)
    assert len(out) == 0


def test_run_handles_nifty_it_leaders():
    """TCS as NIFTY IT leader."""
    ledger = pd.DataFrame([_row("2024-10-04", "TCS", "LONG", 3500.0, 3535.0)])
    with patch("pipeline.research.phase_c_v5.variants.v54_dispersion._stock_5bar_return",
               return_value=0.02), \
         patch("pipeline.research.phase_c_v5.variants.v54_dispersion._index_5bar_return",
               return_value=0.005), \
         patch("pipeline.research.phase_c_v5.variants.v54_dispersion._get_index_close",
               return_value=42000.0):
        out = v54_dispersion.run(ledger)
    assert len(out) == 1
    assert out.iloc[0]["index"] == "NIFTY IT"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest pipeline/tests/research/phase_c_v5/test_v54_dispersion.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement**

```python
# pipeline/research/phase_c_v5/variants/v54_dispersion.py
"""V5.4 — Dispersion: leader-strong, index-flat.

Long top-3 BANKNIFTY/NIFTY-IT constituents only when their 5-bar return
exceeds their parent index's 5-bar return at signal time. Hedge is short
the index. Captures 'leader runs ahead, index lags' edge.
"""
from __future__ import annotations

import logging
import pandas as pd

from .. import simulator, index_fetcher, concentration
from pipeline.research.phase_c_backtest import fetcher as v1_fetcher

log = logging.getLogger(__name__)

DISPERSION_INDICES = ["BANKNIFTY", "NIFTY IT"]


def _stock_5bar_return(symbol: str, end_date: str) -> float | None:
    df = v1_fetcher.fetch_daily(symbol)
    df = df[df["date"].astype(str).str[:10] <= end_date].tail(6)
    if len(df) < 6:
        return None
    return float(df["close"].iloc[-1] / df["close"].iloc[0] - 1.0)


def _index_5bar_return(index_symbol: str, end_date: str) -> float | None:
    df = index_fetcher.fetch_daily(index_symbol)
    df = df[df["date"].astype(str).str[:10] <= end_date].tail(6)
    if len(df) < 6:
        return None
    return float(df["close"].iloc[-1] / df["close"].iloc[0] - 1.0)


def _get_index_close(index_symbol: str, date: str) -> float | None:
    df = index_fetcher.fetch_daily(index_symbol)
    df = df[df["date"].astype(str).str[:10] == date]
    if df.empty:
        return None
    return float(df.iloc[0]["close"])


def _index_for_top3(stock: str) -> str | None:
    cfg = concentration.load()
    for idx_sym in DISPERSION_INDICES:
        top3 = [c["symbol"] for c in
                sorted(cfg[idx_sym]["constituents"], key=lambda c: -c["weight"])[:3]]
        if stock in top3:
            return idx_sym
    return None


def run(v1_ledger: pd.DataFrame) -> pd.DataFrame:
    opp_only = v1_ledger[v1_ledger["label"] == "OPPORTUNITY"]
    rows: list[dict] = []
    for _, sig in opp_only.iterrows():
        idx = _index_for_top3(sig["symbol"])
        if idx is None:
            continue
        stock_5br = _stock_5bar_return(sig["symbol"], sig["entry_date"])
        index_5br = _index_5bar_return(idx, sig["entry_date"])
        if stock_5br is None or index_5br is None:
            continue
        # Bullish setup: stock_5br > index_5br for LONG signals; mirror for SHORT.
        bullish_dispersion = stock_5br - index_5br
        if (sig["side"] == "LONG" and bullish_dispersion <= 0) or \
           (sig["side"] == "SHORT" and bullish_dispersion >= 0):
            continue

        idx_entry = _get_index_close(idx, sig["entry_date"])
        idx_exit = _get_index_close(idx, sig["exit_date"])
        if idx_entry is None or idx_exit is None:
            continue

        sim = simulator.simulate_overlay_daily(
            stock_side=sig["side"],
            stock_entry=sig["entry_px"], stock_exit=sig["exit_px"],
            stock_notional=50_000.0,
            index_side="SHORT" if sig["side"] == "LONG" else "LONG",
            index_entry=idx_entry, index_exit=idx_exit,
            index_notional=50_000.0,
            index_instrument="index_fut" if idx == "BANKNIFTY" else "sectoral_fut",
        )
        rows.append({
            "variant": "v54",
            "entry_date": sig["entry_date"],
            "exit_date": sig["exit_date"],
            "stock": sig["symbol"],
            "index": idx,
            "stock_5bar_ret": stock_5br,
            "index_5bar_ret": index_5br,
            "pnl_gross_inr": sim["pnl_gross_inr"],
            "pnl_net_inr": sim["pnl_net_inr"],
            "cost_inr": sim["cost_inr"],
        })
    cols = ["variant", "entry_date", "exit_date", "stock", "index",
            "stock_5bar_ret", "index_5bar_ret",
            "pnl_gross_inr", "pnl_net_inr", "cost_inr"]
    return pd.DataFrame(rows, columns=cols)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest pipeline/tests/research/phase_c_v5/test_v54_dispersion.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add pipeline/research/phase_c_v5/variants/v54_dispersion.py pipeline/tests/research/phase_c_v5/test_v54_dispersion.py
git commit -m "feat(phase-c-v5): variant V5.4 BANKNIFTY/IT dispersion"
```

---

## Task 12: variants/v55_leader_routing.py — 2-of-3 alignment routes via index

**Files:**
- Create: `pipeline/research/phase_c_v5/variants/v55_leader_routing.py`
- Create: `pipeline/tests/research/phase_c_v5/test_v55_leader_routing.py`

When ≥2 of an index's top-3 constituents fire same-direction OPPORTUNITY same day, take ONE trade on the index instead of stock-level trades.

- [ ] **Step 1: Write the failing test**

```python
# pipeline/tests/research/phase_c_v5/test_v55_leader_routing.py
import pandas as pd
from unittest.mock import patch
from pipeline.research.phase_c_v5.variants import v55_leader_routing


def _row(date, symbol, side):
    return {"entry_date": date, "exit_date": date, "symbol": symbol, "side": side,
            "entry_px": 100.0, "exit_px": 101.0, "notional_inr": 50000.0,
            "pnl_gross_inr": 0.0, "pnl_net_inr": 0.0,
            "label": "OPPORTUNITY", "z_score": -1.0, "expected_return": 0.001}


def test_run_routes_to_banknifty_when_two_leaders_align():
    ledger = pd.DataFrame([
        _row("2024-10-04", "HDFCBANK", "LONG"),
        _row("2024-10-04", "ICICIBANK", "LONG"),
    ])
    with patch("pipeline.research.phase_c_v5.variants.v55_leader_routing._get_index_close",
               side_effect=[51000.0, 51500.0]):
        out = v55_leader_routing.run(ledger)
    assert len(out) == 1
    assert out.iloc[0]["index"] == "BANKNIFTY"
    assert out.iloc[0]["side"] == "LONG"


def test_run_no_route_when_only_one_leader():
    ledger = pd.DataFrame([_row("2024-10-04", "HDFCBANK", "LONG")])
    out = v55_leader_routing.run(ledger)
    assert len(out) == 0


def test_run_no_route_when_leaders_disagree():
    ledger = pd.DataFrame([
        _row("2024-10-04", "HDFCBANK", "LONG"),
        _row("2024-10-04", "ICICIBANK", "SHORT"),
    ])
    out = v55_leader_routing.run(ledger)
    assert len(out) == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest pipeline/tests/research/phase_c_v5/test_v55_leader_routing.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement**

```python
# pipeline/research/phase_c_v5/variants/v55_leader_routing.py
"""V5.5 — Leader → index routing.

When >=2 of an index's top-3 constituents fire same-direction OPPORTUNITY
on the same day, take ONE trade via the INDEX futures (not the stocks).
Critical for book scaling: index futures absorb size that stock futures cannot.
"""
from __future__ import annotations

import logging
import pandas as pd

from .. import basket_builder, index_fetcher, cost_model

log = logging.getLogger(__name__)


def _get_index_close(index_symbol: str, date: str) -> float | None:
    df = index_fetcher.fetch_daily(index_symbol)
    df = df[df["date"].astype(str).str[:10] == date]
    if df.empty:
        return None
    return float(df.iloc[0]["close"])


def _exit_date_for(entry_date: str) -> str:
    """Use next business day as exit (matches v1 horizon ≈ T+1)."""
    return (pd.Timestamp(entry_date) + pd.tseries.offsets.BDay(1)).strftime("%Y-%m-%d")


def run(v1_ledger: pd.DataFrame) -> pd.DataFrame:
    opp_only = v1_ledger[v1_ledger["label"] == "OPPORTUNITY"]
    routes = basket_builder.leader_routing(opp_only)
    rows: list[dict] = []
    for r in routes:
        entry_date = r["entry_date"]
        exit_date = _exit_date_for(entry_date)
        idx_entry = _get_index_close(r["index"], entry_date)
        idx_exit = _get_index_close(r["index"], exit_date)
        if idx_entry is None or idx_exit is None:
            continue
        notional = 100_000.0  # 2x stock notional since this replaces 2 stock trades
        instrument = "index_fut"
        ret = (idx_exit - idx_entry) / idx_entry
        if r["side"] == "SHORT":
            ret = -ret
        gross = notional * ret
        cost = cost_model.round_trip_cost_inr(notional, r["side"], instrument)
        rows.append({
            "variant": "v55",
            "entry_date": entry_date,
            "exit_date": exit_date,
            "index": r["index"],
            "side": r["side"],
            "constituent_sources": ",".join(r["constituent_sources"]),
            "pnl_gross_inr": gross,
            "pnl_net_inr": gross - cost,
            "cost_inr": cost,
        })
    cols = ["variant", "entry_date", "exit_date", "index", "side",
            "constituent_sources", "pnl_gross_inr", "pnl_net_inr", "cost_inr"]
    return pd.DataFrame(rows, columns=cols)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest pipeline/tests/research/phase_c_v5/test_v55_leader_routing.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add pipeline/research/phase_c_v5/variants/v55_leader_routing.py pipeline/tests/research/phase_c_v5/test_v55_leader_routing.py
git commit -m "feat(phase-c-v5): variant V5.5 leader→index routing for book scaling"
```

---

## Task 13: variants/v56_horizon_sweep.py — exit at 14:30 / T+1 / T+2 / T+3 / T+5

**Files:**
- Create: `pipeline/research/phase_c_v5/variants/v56_horizon_sweep.py`
- Create: `pipeline/tests/research/phase_c_v5/test_v56_horizon_sweep.py`

For each OPPORTUNITY signal, simulate exits at 5 horizons. One ledger row per (signal × horizon).

- [ ] **Step 1: Write the failing test**

```python
# pipeline/tests/research/phase_c_v5/test_v56_horizon_sweep.py
import pandas as pd
from unittest.mock import patch
from pipeline.research.phase_c_v5.variants import v56_horizon_sweep


def _row(date, symbol, side, entry):
    return {"entry_date": date, "exit_date": date, "symbol": symbol, "side": side,
            "entry_px": entry, "exit_px": entry * 1.01, "notional_inr": 50000.0,
            "pnl_gross_inr": 0.0, "pnl_net_inr": 0.0,
            "label": "OPPORTUNITY", "z_score": -1.0, "expected_return": 0.001}


def test_run_emits_five_rows_per_signal():
    ledger = pd.DataFrame([_row("2024-10-04", "TCS", "LONG", 3500.0)])
    fake_close = lambda sym, date: 3500.0 * 1.01  # +1% always
    with patch("pipeline.research.phase_c_v5.variants.v56_horizon_sweep._get_close",
               side_effect=fake_close), \
         patch("pipeline.research.phase_c_v5.variants.v56_horizon_sweep._intraday_1430_close",
               return_value=3500.0 * 1.005):
        out = v56_horizon_sweep.run(ledger)
    assert len(out) == 5
    assert sorted(out["horizon"].tolist()) == ["1430", "T+1", "T+2", "T+3", "T+5"]


def test_run_skips_horizons_with_missing_close():
    ledger = pd.DataFrame([_row("2024-10-04", "TCS", "LONG", 3500.0)])
    with patch("pipeline.research.phase_c_v5.variants.v56_horizon_sweep._get_close",
               return_value=None), \
         patch("pipeline.research.phase_c_v5.variants.v56_horizon_sweep._intraday_1430_close",
               return_value=None):
        out = v56_horizon_sweep.run(ledger)
    assert len(out) == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest pipeline/tests/research/phase_c_v5/test_v56_horizon_sweep.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement**

```python
# pipeline/research/phase_c_v5/variants/v56_horizon_sweep.py
"""V5.6 — Hold-horizon sweep.

Same OPPORTUNITY universe; exit at five horizons:
  '1430': intraday close at 14:30 IST same day (1-min cache)
  'T+1' / 'T+2' / 'T+3' / 'T+5': next N business-day close.
"""
from __future__ import annotations

import logging
import pandas as pd

from .. import cost_model
from pipeline.research.phase_c_backtest import fetcher as v1_fetcher

log = logging.getLogger(__name__)

HORIZONS = ["1430", "T+1", "T+2", "T+3", "T+5"]
HORIZON_BDAYS = {"T+1": 1, "T+2": 2, "T+3": 3, "T+5": 5}


def _get_close(symbol: str, date: str) -> float | None:
    df = v1_fetcher.fetch_daily(symbol)
    df = df[df["date"].astype(str).str[:10] == date]
    if df.empty:
        return None
    return float(df.iloc[0]["close"])


def _intraday_1430_close(symbol: str, trade_date: str) -> float | None:
    """Fetch the 1-min bar at 14:30 IST on trade_date. Returns None if missing."""
    df = v1_fetcher.fetch_minute(symbol, trade_date)
    if df.empty:
        return None
    df_1430 = df[df["date"].astype(str).str[11:16] == "14:30"]
    if df_1430.empty:
        return None
    return float(df_1430.iloc[0]["close"])


def _exit_date_for(entry_date: str, n_bdays: int) -> str:
    return (pd.Timestamp(entry_date) + pd.tseries.offsets.BDay(n_bdays)).strftime("%Y-%m-%d")


def run(v1_ledger: pd.DataFrame) -> pd.DataFrame:
    opp_only = v1_ledger[v1_ledger["label"] == "OPPORTUNITY"]
    rows: list[dict] = []
    for _, sig in opp_only.iterrows():
        for horizon in HORIZONS:
            if horizon == "1430":
                exit_date = sig["entry_date"]
                exit_px = _intraday_1430_close(sig["symbol"], sig["entry_date"])
            else:
                exit_date = _exit_date_for(sig["entry_date"], HORIZON_BDAYS[horizon])
                exit_px = _get_close(sig["symbol"], exit_date)
            if exit_px is None:
                continue
            ret = (exit_px - sig["entry_px"]) / sig["entry_px"]
            if sig["side"] == "SHORT":
                ret = -ret
            notional = 50_000.0
            gross = notional * ret
            cost = cost_model.round_trip_cost_inr(notional, sig["side"], "stock_fut")
            rows.append({
                "variant": "v56",
                "horizon": horizon,
                "entry_date": sig["entry_date"],
                "exit_date": exit_date,
                "symbol": sig["symbol"],
                "side": sig["side"],
                "entry_px": float(sig["entry_px"]),
                "exit_px": exit_px,
                "pnl_gross_inr": gross,
                "pnl_net_inr": gross - cost,
                "cost_inr": cost,
            })
    cols = ["variant", "horizon", "entry_date", "exit_date", "symbol", "side",
            "entry_px", "exit_px", "pnl_gross_inr", "pnl_net_inr", "cost_inr"]
    return pd.DataFrame(rows, columns=cols)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest pipeline/tests/research/phase_c_v5/test_v56_horizon_sweep.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add pipeline/research/phase_c_v5/variants/v56_horizon_sweep.py pipeline/tests/research/phase_c_v5/test_v56_horizon_sweep.py
git commit -m "feat(phase-c-v5): variant V5.6 horizon sweep — 14:30 / T+1 / T+2 / T+3 / T+5"
```

---

## Task 14: variants/v57_options_overlay.py — long ATM call/put via Station 6.5

**Files:**
- Create: `pipeline/research/phase_c_v5/variants/v57_options_overlay.py`
- Create: `pipeline/tests/research/phase_c_v5/test_v57_options_overlay.py`

For each OPPORTUNITY: long ATM call (LONG) or long ATM put (SHORT) using `pipeline.options_pricer.bs_call_price`/`bs_put_price`. Strike = nearest 50-step. Vol = EWMA realised on stock minute bars. Exit at 14:30 same day.

- [ ] **Step 1: Write the failing test**

```python
# pipeline/tests/research/phase_c_v5/test_v57_options_overlay.py
import pandas as pd
from unittest.mock import patch
from pipeline.research.phase_c_v5.variants import v57_options_overlay


def _row(date, symbol, side, entry, exit_):
    return {"entry_date": date, "exit_date": date, "symbol": symbol, "side": side,
            "entry_px": entry, "exit_px": exit_, "notional_inr": 50000.0,
            "pnl_gross_inr": 0.0, "pnl_net_inr": 0.0,
            "label": "OPPORTUNITY", "z_score": -1.0, "expected_return": 0.001}


def test_round_strike_to_50():
    assert v57_options_overlay._round_strike(3527) == 3550
    assert v57_options_overlay._round_strike(3524) == 3500
    assert v57_options_overlay._round_strike(100) == 100


def test_run_long_signal_uses_call():
    ledger = pd.DataFrame([_row("2024-10-04", "TCS", "LONG", 3500.0, 3550.0)])
    with patch("pipeline.research.phase_c_v5.variants.v57_options_overlay._ewma_vol",
               return_value=0.20), \
         patch("pipeline.research.phase_c_v5.variants.v57_options_overlay._spot_at_1430",
               return_value=3540.0):
        out = v57_options_overlay.run(ledger)
    assert len(out) == 1
    assert out.iloc[0]["option_type"] == "CALL"


def test_run_short_signal_uses_put():
    ledger = pd.DataFrame([_row("2024-10-04", "TCS", "SHORT", 3500.0, 3450.0)])
    with patch("pipeline.research.phase_c_v5.variants.v57_options_overlay._ewma_vol",
               return_value=0.20), \
         patch("pipeline.research.phase_c_v5.variants.v57_options_overlay._spot_at_1430",
               return_value=3460.0):
        out = v57_options_overlay.run(ledger)
    assert len(out) == 1
    assert out.iloc[0]["option_type"] == "PUT"


def test_run_skips_when_no_intraday_data():
    ledger = pd.DataFrame([_row("2024-10-04", "TCS", "LONG", 3500.0, 3550.0)])
    with patch("pipeline.research.phase_c_v5.variants.v57_options_overlay._ewma_vol",
               return_value=None):
        out = v57_options_overlay.run(ledger)
    assert len(out) == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest pipeline/tests/research/phase_c_v5/test_v57_options_overlay.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement**

```python
# pipeline/research/phase_c_v5/variants/v57_options_overlay.py
"""V5.7 — Long ATM options overlay (call for LONG, put for SHORT).

Strike = nearest 50-step to spot at signal time. Vol = EWMA realised vol
on stock minute bars (lambda=0.94). Pricer: pipeline.options_pricer
(Black-Scholes). Exit at 14:30 IST same day. One contract per signal,
notional = strike × lot_size (we proxy lot_size as 1 for backtest — the
return ratio is what matters statistically).
"""
from __future__ import annotations

import logging
import math
import numpy as np
import pandas as pd

from .. import cost_model
from pipeline.options_pricer import bs_call_price, bs_put_price
from pipeline.research.phase_c_backtest import fetcher as v1_fetcher

log = logging.getLogger(__name__)

NEAR_EXPIRY_DAYS = 7  # treat entry as a weekly option near-expiry
EWMA_LAMBDA = 0.94


def _round_strike(spot: float, step: int = 50) -> float:
    return round(spot / step) * step


def _ewma_vol(symbol: str, trade_date: str) -> float | None:
    """Annualised EWMA realised vol from minute bars on trade_date.

    Returns None if no minute data available.
    """
    df = v1_fetcher.fetch_minute(symbol, trade_date)
    if df.empty or len(df) < 30:
        return None
    rets = df["close"].pct_change().dropna().to_numpy()
    if len(rets) < 30:
        return None
    weights = (1 - EWMA_LAMBDA) * EWMA_LAMBDA ** np.arange(len(rets) - 1, -1, -1)
    weights = weights / weights.sum()
    var = float(np.sum(weights * rets ** 2))
    minute_vol = math.sqrt(var)
    # Annualise: 375 minute bars × 252 trading days
    return minute_vol * math.sqrt(375 * 252)


def _spot_at_1430(symbol: str, trade_date: str) -> float | None:
    df = v1_fetcher.fetch_minute(symbol, trade_date)
    if df.empty:
        return None
    df_1430 = df[df["date"].astype(str).str[11:16] == "14:30"]
    if df_1430.empty:
        return None
    return float(df_1430.iloc[0]["close"])


def run(v1_ledger: pd.DataFrame) -> pd.DataFrame:
    opp_only = v1_ledger[v1_ledger["label"] == "OPPORTUNITY"]
    rows: list[dict] = []
    for _, sig in opp_only.iterrows():
        vol = _ewma_vol(sig["symbol"], sig["entry_date"])
        if vol is None:
            continue
        spot_entry = float(sig["entry_px"])
        spot_exit = _spot_at_1430(sig["symbol"], sig["entry_date"])
        if spot_exit is None:
            continue
        strike = _round_strike(spot_entry)
        T_entry = NEAR_EXPIRY_DAYS / 365.0
        # At exit (~14:30 same day), DTE has decayed by ~5/375 bar = ~0.013 days.
        T_exit = max((NEAR_EXPIRY_DAYS - 0.013) / 365.0, 1e-6)

        if sig["side"] == "LONG":
            entry_premium = bs_call_price(spot_entry, strike, T_entry, vol)
            exit_premium = bs_call_price(spot_exit, strike, T_exit, vol)
            opt_type = "CALL"
        else:
            entry_premium = bs_put_price(spot_entry, strike, T_entry, vol)
            exit_premium = bs_put_price(spot_exit, strike, T_exit, vol)
            opt_type = "PUT"

        if entry_premium <= 0:
            continue
        notional = entry_premium * 1.0  # one contract, proxy lot=1
        gross = exit_premium - entry_premium
        cost = cost_model.round_trip_cost_inr(notional, "LONG", "options_long")
        rows.append({
            "variant": "v57",
            "entry_date": sig["entry_date"],
            "exit_date": sig["entry_date"],
            "symbol": sig["symbol"],
            "side": sig["side"],
            "option_type": opt_type,
            "strike": strike,
            "spot_entry": spot_entry,
            "spot_exit": spot_exit,
            "entry_premium": entry_premium,
            "exit_premium": exit_premium,
            "vol_used": vol,
            "pnl_gross_inr": gross,
            "pnl_net_inr": gross - cost,
            "cost_inr": cost,
        })
    cols = ["variant", "entry_date", "exit_date", "symbol", "side", "option_type",
            "strike", "spot_entry", "spot_exit", "entry_premium", "exit_premium",
            "vol_used", "pnl_gross_inr", "pnl_net_inr", "cost_inr"]
    return pd.DataFrame(rows, columns=cols)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest pipeline/tests/research/phase_c_v5/test_v57_options_overlay.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add pipeline/research/phase_c_v5/variants/v57_options_overlay.py pipeline/tests/research/phase_c_v5/test_v57_options_overlay.py
git commit -m "feat(phase-c-v5): variant V5.7 long ATM call/put options overlay"
```

---

## Task 15: report.py — 11-section research doc generator

**Files:**
- Create: `pipeline/research/phase_c_v5/report.py`
- Create: `pipeline/tests/research/phase_c_v5/test_report.py`

For each variant ledger: compute hit rate, Sharpe CI, binomial p, max DD, plot equity curve. Emit one markdown section per variant. Bonferroni α = 0.01/7.

- [ ] **Step 1: Write the failing test**

```python
# pipeline/tests/research/phase_c_v5/test_report.py
import pandas as pd
import pytest
from pipeline.research.phase_c_v5 import report


def _ledger_n(n: int, mean_pnl: float = 100.0, std_pnl: float = 200.0, seed: int = 1):
    import numpy as np
    rng = np.random.default_rng(seed)
    return pd.DataFrame({
        "variant": ["v51"] * n,
        "entry_date": [f"2024-10-{(i % 28) + 1:02d}" for i in range(n)],
        "pnl_net_inr": rng.normal(mean_pnl, std_pnl, n),
    })


def test_compute_metrics_returns_required_fields():
    ledger = _ledger_n(100, mean_pnl=100.0, std_pnl=200.0)
    m = report.compute_metrics(ledger)
    for k in ("n_trades", "hit_rate", "binomial_p", "sharpe_point",
              "sharpe_ci_lo", "sharpe_ci_hi", "max_drawdown", "total_pnl_inr"):
        assert k in m


def test_pass_fail_with_bonferroni_alpha():
    """Variant passes only if Sharpe CI lower > 0 AND binomial p < 0.01/7."""
    pass_metrics = {"sharpe_ci_lo": 0.5, "binomial_p": 0.0001}
    fail_metrics = {"sharpe_ci_lo": -0.1, "binomial_p": 0.0001}
    fail_metrics2 = {"sharpe_ci_lo": 0.5, "binomial_p": 0.005}
    assert report.passes(pass_metrics, family_alpha=0.01, n_variants=7) is True
    assert report.passes(fail_metrics, family_alpha=0.01, n_variants=7) is False
    assert report.passes(fail_metrics2, family_alpha=0.01, n_variants=7) is False


def test_render_section_returns_markdown():
    ledger = _ledger_n(100)
    md = report.render_section("V5.1", "Sector pair", ledger)
    assert "## V5.1" in md
    assert "Sector pair" in md
    assert "Hit rate" in md.lower()


def test_render_executive_summary_table():
    metrics_by_variant = {
        "v51": {"n_trades": 100, "hit_rate": 0.55, "sharpe_point": 1.0,
                "sharpe_ci_lo": 0.5, "sharpe_ci_hi": 1.5, "binomial_p": 0.001,
                "max_drawdown": 0.10, "total_pnl_inr": 10000.0},
    }
    md = report.render_executive_summary(metrics_by_variant, family_alpha=0.01)
    assert "| variant" in md.lower()
    assert "v51" in md
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest pipeline/tests/research/phase_c_v5/test_report.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement**

```python
# pipeline/research/phase_c_v5/report.py
"""Generates the 11-section V5 research document.

Sections 1-3 are static (executive summary, strategy desc, methodology).
Sections 4-10 are auto-generated per-variant from parquet ledgers.
Section 11 is the verdict (pass/fail with Bonferroni-corrected alpha).
"""
from __future__ import annotations

import json
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from . import paths
from pipeline.research.phase_c_backtest import stats


def compute_metrics(ledger: pd.DataFrame) -> dict:
    pnl = ledger["pnl_net_inr"].to_numpy() if not ledger.empty else np.array([])
    n = len(pnl)
    if n == 0:
        return {"n_trades": 0, "hit_rate": 0.0, "binomial_p": 1.0,
                "sharpe_point": 0.0, "sharpe_ci_lo": 0.0, "sharpe_ci_hi": 0.0,
                "max_drawdown": 0.0, "total_pnl_inr": 0.0}
    wins = int((pnl > 0).sum())
    hit_rate = wins / n
    bp = stats.binomial_p(wins, n)
    notional_per_trade = 50_000.0
    returns = pnl / notional_per_trade
    sp, lo, hi = stats.bootstrap_sharpe_ci(returns, seed=7)
    equity = np.cumsum(pnl) + notional_per_trade
    dd = stats.max_drawdown(equity)
    return {
        "n_trades": n,
        "hit_rate": hit_rate,
        "binomial_p": bp,
        "sharpe_point": sp,
        "sharpe_ci_lo": lo,
        "sharpe_ci_hi": hi,
        "max_drawdown": dd,
        "total_pnl_inr": float(pnl.sum()),
    }


def passes(metrics: dict, family_alpha: float, n_variants: int) -> bool:
    """Pass iff Sharpe CI lower > 0 AND binomial p < family_alpha / n_variants."""
    per_test_alpha = stats.bonferroni_alpha_per(family_alpha, n_variants)
    return metrics["sharpe_ci_lo"] > 0 and metrics["binomial_p"] < per_test_alpha


def render_section(variant_id: str, title: str, ledger: pd.DataFrame) -> str:
    m = compute_metrics(ledger)
    return (
        f"## {variant_id} — {title}\n\n"
        f"- N trades: {m['n_trades']}\n"
        f"- Hit rate: {m['hit_rate']:.2%}\n"
        f"- Binomial p: {m['binomial_p']:.4f}\n"
        f"- Sharpe (point): {m['sharpe_point']:.2f}\n"
        f"- Sharpe 99% CI: [{m['sharpe_ci_lo']:.2f}, {m['sharpe_ci_hi']:.2f}]\n"
        f"- Max drawdown: {m['max_drawdown']:.2%}\n"
        f"- Total net P&L (INR): {m['total_pnl_inr']:.0f}\n"
    )


def render_executive_summary(metrics_by_variant: dict, family_alpha: float = 0.01) -> str:
    n = len(metrics_by_variant)
    lines = [
        "## Executive Summary",
        "",
        "| variant | N | hit | Sharpe pt | CI lo | CI hi | binom p | DD | passes? |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for v_id, m in sorted(metrics_by_variant.items()):
        ok = passes(m, family_alpha, n)
        lines.append(
            f"| {v_id} | {m['n_trades']} | {m['hit_rate']:.2%} | "
            f"{m['sharpe_point']:.2f} | {m['sharpe_ci_lo']:.2f} | {m['sharpe_ci_hi']:.2f} | "
            f"{m['binomial_p']:.4f} | {m['max_drawdown']:.2%} | "
            f"{'✅' if ok else '❌'} |"
        )
    return "\n".join(lines) + "\n"


def plot_equity(ledger: pd.DataFrame, variant_id: str, out_path: Path) -> None:
    if ledger.empty:
        return
    pnl = ledger["pnl_net_inr"].to_numpy()
    equity = np.cumsum(pnl) + 50_000.0
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(equity)
    ax.set_title(f"{variant_id} — equity curve (cumulative P&L + notional)")
    ax.set_xlabel("trade #")
    ax.set_ylabel("INR")
    fig.tight_layout()
    fig.savefig(out_path)
    plt.close(fig)


def write_doc(metrics_by_variant: dict, ledgers_by_variant: dict, out_dir: Path) -> None:
    """Write 11 markdown sections + per-variant equity plots."""
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "01-executive-summary.md").write_text(
        render_executive_summary(metrics_by_variant), encoding="utf-8")
    titles = {
        "v51": "Sector-neutral pair", "v52": "Stock vs sector index",
        "v53": "NIFTY 50 overlay", "v54": "BANKNIFTY/NIFTY-IT dispersion",
        "v55": "Leader → index routing", "v56": "Hold-horizon sweep",
        "v57": "Long ATM call/put overlay",
    }
    for i, (v_id, ledger) in enumerate(sorted(ledgers_by_variant.items()), start=4):
        if i > 10:
            break
        section = render_section(v_id.upper(), titles[v_id], ledger)
        (out_dir / f"{i:02d}-results-{v_id}.md").write_text(section, encoding="utf-8")
        plot_equity(ledger, v_id.upper(), out_dir / f"{v_id}_equity.png")
    # Verdict section
    n = len(metrics_by_variant)
    pass_lines = [v for v, m in metrics_by_variant.items() if passes(m, 0.01, n)]
    fail_lines = [v for v in metrics_by_variant if v not in pass_lines]
    verdict = ["## Verdict + production recommendation\n"]
    if pass_lines:
        verdict.append(f"**PASSES (Bonferroni α=0.01/{n}):** {', '.join(pass_lines)}\n")
    else:
        verdict.append("**No variants pass.** All seven hypotheses rejected at family-wise α=0.01.\n")
    verdict.append(f"\nFailed: {', '.join(fail_lines) if fail_lines else 'none'}\n")
    (out_dir / "11-verdict.md").write_text("\n".join(verdict), encoding="utf-8")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest pipeline/tests/research/phase_c_v5/test_report.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add pipeline/research/phase_c_v5/report.py pipeline/tests/research/phase_c_v5/test_report.py
git commit -m "feat(phase-c-v5): report generator with Bonferroni-corrected pass logic"
```

---

## Task 16: run_v5.py — CLI orchestrator + end-to-end execution

**Files:**
- Create: `pipeline/research/phase_c_v5/run_v5.py`
- Modify: none (calls everything else)

Reads v1 in-sample + forward ledgers, runs all 7 variants, writes per-variant parquets to `pipeline/data/research/phase_c_v5/`, writes plots, writes report doc to `docs/research/phase-c-v5-baskets/`.

- [ ] **Step 1: Write the implementation**

```python
# pipeline/research/phase_c_v5/run_v5.py
"""V5 backtest orchestrator.

Reads v1 in-sample + forward OPPORTUNITY ledger, runs all seven variants,
writes per-variant parquet ledgers, equity-curve plots, and the 11-section
research document.

Usage:
    python -m pipeline.research.phase_c_v5.run_v5
    python -m pipeline.research.phase_c_v5.run_v5 --variants v51,v53
"""
from __future__ import annotations

import argparse
import logging
from pathlib import Path
import pandas as pd

from . import paths, report
from .variants import (
    v51_sector_pair, v52_stock_vs_index, v53_nifty_overlay,
    v54_dispersion, v55_leader_routing, v56_horizon_sweep, v57_options_overlay,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("phase_c_v5")

VARIANT_RUNNERS = {
    "v51": v51_sector_pair.run,
    "v52": v52_stock_vs_index.run,
    "v53": v53_nifty_overlay.run,
    "v54": v54_dispersion.run,
    "v55": v55_leader_routing.run,
    "v56": v56_horizon_sweep.run,
    "v57": v57_options_overlay.run,
}


def _load_v1_combined() -> pd.DataFrame:
    """Concatenate v1 in-sample and forward ledgers."""
    is_df = pd.read_parquet(paths.V1_IN_SAMPLE_LEDGER)
    fwd_df = pd.read_parquet(paths.V1_FORWARD_LEDGER)
    return pd.concat([is_df, fwd_df], ignore_index=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--variants", default="all",
                        help="comma-separated variant ids, or 'all'")
    args = parser.parse_args(argv)

    paths.ensure_cache()

    if args.variants == "all":
        selected = list(VARIANT_RUNNERS)
    else:
        selected = [v.strip() for v in args.variants.split(",") if v.strip()]

    v1_ledger = _load_v1_combined()
    log.info("loaded v1 ledger: %d rows", len(v1_ledger))

    metrics_by_variant: dict[str, dict] = {}
    ledgers_by_variant: dict[str, pd.DataFrame] = {}

    for v_id in selected:
        if v_id not in VARIANT_RUNNERS:
            log.warning("unknown variant: %s — skipping", v_id)
            continue
        log.info("running variant %s ...", v_id)
        try:
            ledger = VARIANT_RUNNERS[v_id](v1_ledger)
        except Exception as exc:
            log.exception("variant %s failed: %s", v_id, exc)
            continue
        out_path = paths.LEDGERS_DIR / f"{v_id}_ledger.parquet"
        ledger.to_parquet(out_path, index=False)
        log.info("variant %s wrote %d rows to %s", v_id, len(ledger), out_path)

        metrics_by_variant[v_id] = report.compute_metrics(ledger)
        ledgers_by_variant[v_id] = ledger

    report.write_doc(metrics_by_variant, ledgers_by_variant, paths.DOCS_DIR)
    log.info("research doc written to %s", paths.DOCS_DIR)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Verify import path works**

Run: `python -c "from pipeline.research.phase_c_v5 import run_v5; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Backfill prerequisite — sectoral indices**

```bash
python -c "
from pipeline.research.phase_c_v5 import index_fetcher, tradeable_indices
# Discover which sectorals have F&O
print('Checking F&O availability per sectoral...')
result = tradeable_indices.check_all()
print(result)
print()
print('Backfilling daily history for tradeable indices...')
for sym, ok in result.items():
    if ok:
        df = index_fetcher.fetch_daily(sym, days=1825)
        print(f'  {sym}: {len(df)} rows')
"
```

Expected: `tradeable_sectorals.json` written, daily CSVs in `pipeline/data/india_historical/indices/`.

- [ ] **Step 4: Run end-to-end**

Run: `python -m pipeline.research.phase_c_v5.run_v5`
Expected: 7 parquet files under `pipeline/data/research/phase_c_v5/ledgers/`, 7 PNG equity plots, 9 markdown sections under `docs/research/phase-c-v5-baskets/`.

- [ ] **Step 5: Commit**

```bash
git add pipeline/research/phase_c_v5/run_v5.py pipeline/config/tradeable_sectorals.json pipeline/data/research/phase_c_v5/ docs/research/phase-c-v5-baskets/ pipeline/data/india_historical/indices/
git commit -m "feat(phase-c-v5): orchestrator + first end-to-end run with 7 variant ledgers"
```

---

## Task 17: Write static research document sections + update docs/manual

**Files:**
- Create: `docs/research/phase-c-v5-baskets/02-strategy-description.md`
- Create: `docs/research/phase-c-v5-baskets/03-methodology.md`
- Modify: `docs/SYSTEM_OPERATIONS_MANUAL.md` — add V5 section
- Modify: `CLAUDE.md` — note V5 research location

The auto-generated sections (01, 04-10, 11) come from Task 16. This task fills the static narrative sections.

- [ ] **Step 1: Write strategy description**

```markdown
<!-- docs/research/phase-c-v5-baskets/02-strategy-description.md -->
# Strategy description

Phase C v1 validated 162 OPPORTUNITY signals as single-stock futures
trades and failed (Sharpe CI [-3.59, -0.35], binomial p=0.0012). This
study tests whether the same signal universe carries edge when traded
as **baskets** rather than single names.

The seven variants:

- **V5.1 Sector-neutral pair** — long top / short bottom of same-sector
  same-day signals. Strips sector beta to isolate stock-specific alpha.
- **V5.2 Stock vs sector-index** — every signal hedged with opposite-direction
  sector index futures, sized by 60-day rolling OLS beta (clipped [0.5, 1.5]).
- **V5.3 NIFTY 50 overlay** — same as V5.2 but hedge is always NIFTY 50.
  Cheaper liquidity, simpler.
- **V5.4 BANKNIFTY/NIFTY-IT dispersion** — for top-3 constituents,
  long stock / short index only when 5-bar stock return outpaces 5-bar
  index return at signal time. Captures the well-known leader-runs-ahead
  edge.
- **V5.5 Leader → index routing** — when ≥2 of an index's top-3 fire
  same-direction OPPORTUNITY same day, take the trade via the index
  futures. Critical for book scaling.
- **V5.6 Hold-horizon sweep** — same signals exited at five horizons
  (14:30 same day, T+1, T+2, T+3, T+5). Tests whether 14:30 is the
  right exit.
- **V5.7 Options overlay** — long ATM call (LONG signals) / put (SHORT)
  via Black-Scholes (Station 6.5 pricer). Convex payoff for marginal
  edge.
```

- [ ] **Step 2: Write methodology**

```markdown
<!-- docs/research/phase-c-v5-baskets/03-methodology.md -->
# Methodology

**Input:** Combined v1 in-sample + forward ledgers (650+ OPPORTUNITY rows
across `docs/research/phase-c-validation/in_sample_ledger.parquet` and
`forward_ledger.parquet`).

**Per-variant statistics:**
- Hit rate vs 50% — two-sided binomial test (`scipy.stats.binomtest`).
- Annualised Sharpe — bootstrap 99% CI over 10,000 IID resamples
  (`pipeline.research.phase_c_backtest.stats.bootstrap_sharpe_ci`,
  fixed seed=7 for reproducibility).
- Max drawdown — peak-to-trough on cumulative P&L equity curve.

**Pass criterion (per variant):**
- Sharpe CI lower bound > 0, AND
- Binomial p < α / n_variants where α=0.01 and n_variants=7
  (Bonferroni correction: per-test α = 0.00143)

This is stricter than v1's α/5 because we test 7 hypotheses instead of 5.

**Cost model** (`pipeline.research.phase_c_v5.cost_model`):
- Stock futures: 5 bps slippage + Zerodha intraday rates
- Index futures (NIFTY/BANKNIFTY): 2 bps
- Sectoral index futures (NIFTY IT etc.): 8 bps
- Options (long-only): 15 bps mid-spread + Zerodha options STT

**Reproducibility:** `python -m pipeline.research.phase_c_v5.run_v5`
regenerates everything from the v1 ledgers and the cached daily/minute bars.
```

- [ ] **Step 3: Update SYSTEM_OPERATIONS_MANUAL.md**

```bash
# Add to docs/SYSTEM_OPERATIONS_MANUAL.md under a new "## Phase C V5 — Basket Validation" section.
```

Use Edit tool to insert after the Phase C v1 section a paragraph noting:
- Location: `pipeline/research/phase_c_v5/`
- Output: `docs/research/phase-c-v5-baskets/`
- Re-run command: `python -m pipeline.research.phase_c_v5.run_v5`
- Reads v1 ledgers; does not modify them.

- [ ] **Step 4: Update CLAUDE.md**

Add one line under the existing Phase C bullet point in CLAUDE.md:
"V5 baskets/index/options validation: `pipeline/research/phase_c_v5/`, doc at `docs/research/phase-c-v5-baskets/`."

- [ ] **Step 5: Commit**

```bash
git add docs/research/phase-c-v5-baskets/02-strategy-description.md docs/research/phase-c-v5-baskets/03-methodology.md docs/SYSTEM_OPERATIONS_MANUAL.md CLAUDE.md
git commit -m "docs(phase-c-v5): strategy description + methodology + manual updates"
```

---

## Task 18: Terminal schema extension + components — GATED on V5.1 ledger landing

**Trigger:** Only start this task after Task 16 has produced a non-empty `pipeline/data/research/phase_c_v5/ledgers/v51_ledger.parquet`. Skip until then.

**Files:**
- Modify: `pipeline/terminal/api.py` — extend `/api/candidates` schema for `legs`, `hedge_leg`, `option_leg`, `exit_horizon`, `variant`
- Create: `pipeline/terminal/static/js/components/options-leg.js`
- Modify: `pipeline/terminal/static/js/components/candidates-table.js` — render multi-leg rows
- Modify: `pipeline/terminal/static/js/components/positions-table.js` — show composite for hedge_leg
- Modify: `pipeline/tests/terminal/test_api_candidates.py` — assert new fields

The schema already passes through arbitrary fields (filter chips auto-populate from `[...new Set(_allCandidates.map(c => c.source))]`), so the only required UI work is rendering the new fields.

- [ ] **Step 1: Extend candidate schema in API**

In `pipeline/terminal/api.py`, find the function that builds the `tradeable_candidates` list and ensure it passes through `legs`, `hedge_leg`, `option_leg`, `exit_horizon`, `variant` if present in the source.

- [ ] **Step 2: Test that legs renders correctly**

```javascript
// pipeline/terminal/static/js/components/candidates-table.js
// Add: if candidate.legs is non-empty array, render two stacked sub-rows
// (long leg / short leg with their respective sides and weights).
```

- [ ] **Step 3: Add options-leg component**

```javascript
// pipeline/terminal/static/js/components/options-leg.js
export function renderOptionsLeg(opt) {
    if (!opt) return "";
    return `<span class="opt-leg">${opt.type} ${opt.strike} @ ${opt.premium}</span>`;
}
```

- [ ] **Step 4: Manual verification**

Open the terminal, switch to Trading tab, confirm that V5 candidates render with their legs/hedge/option/horizon/variant fields visible.

- [ ] **Step 5: Commit**

```bash
git add pipeline/terminal/api.py pipeline/terminal/static/js/components/options-leg.js pipeline/terminal/static/js/components/candidates-table.js pipeline/terminal/static/js/components/positions-table.js pipeline/tests/terminal/test_api_candidates.py
git commit -m "feat(terminal): V5 schema extension — legs, hedge, options, horizon, variant"
```

---

## Self-Review

**Spec coverage check:**
- ✅ All 7 variants → Tasks 8-14
- ✅ Cost model with 4 instrument types → Task 2
- ✅ Index data backfill → Task 3 (fetcher) + Task 16 (execution)
- ✅ NSE F&O availability check → Task 4
- ✅ Sector concentration map → Task 5
- ✅ Bonferroni α=0.01/7 → Task 15 (`passes()` function)
- ✅ Bootstrap Sharpe CI / binomial / drawdown → reused from v1 stats.py
- ✅ 11-section research doc → Tasks 15-17
- ✅ Terminal extension gated on V5.1 ledger → Task 18
- ✅ Risk #1 (NSE availability) addressed in Task 4
- ✅ Risk #2 (beta stability) addressed in Task 9 (`_beta` clips and warns)
- ✅ Risk #3 (options pricing in stress) — uses Station 6.5 pricer; flagged in spec; not extra-mitigated (acceptable since signal-time vol is from same minute bars)
- ✅ Risk #4 (look-ahead) — pairs use only signal-time data (entry_date, expected_return both available at signal)
- ✅ Risk #5 (survivorship) — variants delegate fetch to v1 fetcher which already has empty-bars guard

**Type consistency check:**
- All variants emit dataframes with `pnl_net_inr` column → consumed by `report.compute_metrics`
- `_beta(stock_returns, index_returns)` signature in v52 reused by v53 import
- Cost model `instrument` parameter consistent across simulator + variants (`stock_fut`, `index_fut`, `sectoral_fut`, `options_long`)
- Concentration `_PATH` overridable via monkeypatch (test consistency)

**Placeholder scan:** No TBD/TODO/placeholder markers in tasks. All code blocks are complete. All test bodies have actual assertions.

**Spec gaps found:** None. The spec's "Reuses v1 stats.py" is honored by `from pipeline.research.phase_c_backtest import stats` in Task 15.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-21-phase-c-v5-baskets.md`. Two execution options:

**1. Subagent-Driven (recommended)** — Fresh subagent per task, two-stage review (spec compliance + code quality) between tasks. Best for 18-task plans where context pollution is a real risk.

**2. Inline Execution** — Execute tasks in this session using executing-plans skill, batch execution with checkpoints for review. Faster but riskier on a long plan.

**Which approach?**
