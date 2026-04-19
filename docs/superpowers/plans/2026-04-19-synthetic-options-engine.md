# Synthetic Options Engine ("Station 6.5") Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a 3-layer enrichment engine that evaluates whether high-conviction spread signals would be profitable as long options trades, using EWMA volatility and Black-Scholes synthetic pricing.

**Architecture:** Vol Engine (Kite OHLCV → EWMA vol) → Options Pricer (pure BS math) → Orchestrator (leverage matrix builder). The orchestrator feeds the research digest API and a new Options sub-tab under Intelligence. A separate shadow file tracks forward-test P&L linked by signal_id.

**Tech Stack:** Python 3 (math, json, pathlib), FastAPI, vanilla JS, existing Kite client, existing terminal design system.

**Spec:** `docs/superpowers/specs/2026-04-19-synthetic-options-engine-design.md`

---

## File Structure

| Action | File | Responsibility |
|--------|------|---------------|
| Create | `pipeline/vol_engine.py` | EWMA vol from Kite OHLCV, per-ticker caching |
| Create | `pipeline/options_pricer.py` | Pure BS math: call/put prices, greeks, five_day_rent |
| Create | `pipeline/synthetic_options.py` | Orchestrator: builds leverage matrix, caution badges |
| Create | `pipeline/tests/test_options_pricer.py` | BS math unit tests |
| Create | `pipeline/tests/test_vol_engine.py` | EWMA + cache tests |
| Create | `pipeline/tests/test_synthetic_options.py` | Orchestrator + matrix tests |
| Create | `pipeline/terminal/static/js/components/leverage-matrix.js` | Leverage matrix card UI component |
| Modify | `pipeline/terminal/api/research.py` | Add `leverage_matrices` to digest, new `/api/research/options-shadow` |
| Modify | `pipeline/terminal/static/js/pages/intelligence.js` | Add "Options" sub-tab |
| Modify | `pipeline/terminal/static/js/lib/api.js` | Add `getOptionsShadow()` export |
| Modify | `pipeline/run_signals.py` | Hook synthetic options shadow recording after shadow trade creation |

---

### Task 1: Options Pricer — BS Math + Tests

**Files:**
- Create: `pipeline/options_pricer.py`
- Create: `pipeline/tests/test_options_pricer.py`

This is a pure-math module with zero I/O. We build it first because everything depends on it and it's trivially testable.

- [ ] **Step 1: Write failing tests for BS call/put prices**

Create `pipeline/tests/test_options_pricer.py`:

```python
"""
Tests for pipeline/options_pricer.py — Black-Scholes math engine.

Run: pytest pipeline/tests/test_options_pricer.py -v
"""
import pytest
import math


class TestBSCallPrice:
    def test_atm_call_known_value(self):
        """ATM call: S=100, K=100, T=30/365, sigma=0.30, r=0 should be ~2.38."""
        from pipeline.options_pricer import bs_call_price
        price = bs_call_price(S=100, K=100, T=30/365, sigma=0.30, r=0.0)
        assert abs(price - 2.38) < 0.1  # within 10 paise of known value

    def test_deep_itm_call(self):
        """Deep ITM call should be close to intrinsic value."""
        from pipeline.options_pricer import bs_call_price
        price = bs_call_price(S=150, K=100, T=30/365, sigma=0.30, r=0.0)
        assert price > 49.0  # at least intrinsic value of 50 minus small time value

    def test_deep_otm_call(self):
        """Deep OTM call should be near zero."""
        from pipeline.options_pricer import bs_call_price
        price = bs_call_price(S=50, K=100, T=30/365, sigma=0.30, r=0.0)
        assert price < 0.01

    def test_call_price_non_negative(self):
        from pipeline.options_pricer import bs_call_price
        price = bs_call_price(S=100, K=100, T=1/365, sigma=0.50, r=0.0)
        assert price >= 0.0


class TestBSPutPrice:
    def test_atm_put_known_value(self):
        """ATM put should equal ATM call when r=0 (put-call parity)."""
        from pipeline.options_pricer import bs_call_price, bs_put_price
        call = bs_call_price(S=100, K=100, T=30/365, sigma=0.30, r=0.0)
        put = bs_put_price(S=100, K=100, T=30/365, sigma=0.30, r=0.0)
        assert abs(call - put) < 0.01  # put-call parity with r=0: C = P for ATM

    def test_put_price_non_negative(self):
        from pipeline.options_pricer import bs_put_price
        price = bs_put_price(S=100, K=100, T=1/365, sigma=0.50, r=0.0)
        assert price >= 0.0


class TestBSGreeks:
    def test_call_delta_positive(self):
        from pipeline.options_pricer import bs_greeks
        g = bs_greeks(S=100, K=100, T=30/365, sigma=0.30, r=0.0)
        assert g["delta"] > 0.0

    def test_atm_delta_near_half(self):
        """ATM call delta should be near 0.5."""
        from pipeline.options_pricer import bs_greeks
        g = bs_greeks(S=100, K=100, T=30/365, sigma=0.30, r=0.0)
        assert abs(g["delta"] - 0.5) < 0.05

    def test_theta_negative(self):
        """Theta (daily) should always be negative for long options."""
        from pipeline.options_pricer import bs_greeks
        g = bs_greeks(S=100, K=100, T=30/365, sigma=0.30, r=0.0)
        assert g["theta_daily"] < 0.0

    def test_gamma_positive(self):
        from pipeline.options_pricer import bs_greeks
        g = bs_greeks(S=100, K=100, T=30/365, sigma=0.30, r=0.0)
        assert g["gamma"] > 0.0

    def test_vega_positive(self):
        from pipeline.options_pricer import bs_greeks
        g = bs_greeks(S=100, K=100, T=30/365, sigma=0.30, r=0.0)
        assert g["vega"] > 0.0


class TestATMOptionCost:
    def test_returns_all_fields(self):
        from pipeline.options_pricer import atm_option_cost
        result = atm_option_cost(spot=100.0, vol=0.30, days_to_expiry=30)
        expected_keys = {"call_price", "put_price", "call_theta_daily",
                         "put_theta_daily", "call_delta", "put_delta",
                         "combined_daily_theta"}
        assert set(result.keys()) == expected_keys

    def test_combined_theta_is_sum(self):
        from pipeline.options_pricer import atm_option_cost
        r = atm_option_cost(spot=100.0, vol=0.30, days_to_expiry=30)
        assert abs(r["combined_daily_theta"] - (r["call_theta_daily"] + r["put_theta_daily"])) < 1e-10

    def test_atm_call_equals_put_at_r_zero(self):
        """With r=0, ATM call price equals ATM put price."""
        from pipeline.options_pricer import atm_option_cost
        r = atm_option_cost(spot=100.0, vol=0.30, days_to_expiry=30)
        assert abs(r["call_price"] - r["put_price"]) < 0.01


class TestFiveDayRent:
    def test_returns_all_fields(self):
        from pipeline.options_pricer import five_day_rent
        r = five_day_rent(spot=100.0, vol=0.30, days_to_expiry=30)
        expected_keys = {"premium_pct", "theta_decay_5d_pct", "friction_pct", "total_rent_pct"}
        assert set(r.keys()) == expected_keys

    def test_total_rent_is_theta_plus_friction(self):
        from pipeline.options_pricer import five_day_rent
        r = five_day_rent(spot=100.0, vol=0.30, days_to_expiry=30)
        assert abs(r["total_rent_pct"] - (r["theta_decay_5d_pct"] + r["friction_pct"])) < 1e-10

    def test_friction_is_two_percent_of_premium(self):
        from pipeline.options_pricer import five_day_rent
        r = five_day_rent(spot=100.0, vol=0.30, days_to_expiry=30)
        assert abs(r["friction_pct"] - r["premium_pct"] * 0.02) < 1e-10

    def test_higher_vol_means_higher_rent(self):
        from pipeline.options_pricer import five_day_rent
        low = five_day_rent(spot=100.0, vol=0.20, days_to_expiry=30)
        high = five_day_rent(spot=100.0, vol=0.50, days_to_expiry=30)
        assert high["total_rent_pct"] > low["total_rent_pct"]

    def test_shorter_expiry_means_higher_theta_pct(self):
        from pipeline.options_pricer import five_day_rent
        long_exp = five_day_rent(spot=100.0, vol=0.30, days_to_expiry=30)
        short_exp = five_day_rent(spot=100.0, vol=0.30, days_to_expiry=15)
        assert short_exp["theta_decay_5d_pct"] > long_exp["theta_decay_5d_pct"]

    def test_near_zero_expiry(self):
        """Same-day (T=1/365) should not crash."""
        from pipeline.options_pricer import five_day_rent
        r = five_day_rent(spot=100.0, vol=0.30, days_to_expiry=1)
        assert r["total_rent_pct"] > 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd C:/Users/Claude_Anka/askanka.com && python -m pytest pipeline/tests/test_options_pricer.py -v`
Expected: `ModuleNotFoundError: No module named 'pipeline.options_pricer'`

- [ ] **Step 3: Implement options_pricer.py**

Create `pipeline/options_pricer.py`:

```python
"""Black-Scholes options pricing engine — pure math, no I/O."""
import math

FRICTION_RATE = 0.02
RISK_FREE_RATE = 0.0


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _d1(S: float, K: float, T: float, sigma: float, r: float) -> float:
    return (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))


def _d2(S: float, K: float, T: float, sigma: float, r: float) -> float:
    return _d1(S, K, T, sigma, r) - sigma * math.sqrt(T)


def bs_call_price(S: float, K: float, T: float, sigma: float, r: float = RISK_FREE_RATE) -> float:
    if T <= 0:
        return max(S - K, 0.0)
    d1 = _d1(S, K, T, sigma, r)
    d2 = _d2(S, K, T, sigma, r)
    return S * _norm_cdf(d1) - K * math.exp(-r * T) * _norm_cdf(d2)


def bs_put_price(S: float, K: float, T: float, sigma: float, r: float = RISK_FREE_RATE) -> float:
    if T <= 0:
        return max(K - S, 0.0)
    d1 = _d1(S, K, T, sigma, r)
    d2 = _d2(S, K, T, sigma, r)
    return K * math.exp(-r * T) * _norm_cdf(-d2) - S * _norm_cdf(-d1)


def bs_greeks(S: float, K: float, T: float, sigma: float, r: float = RISK_FREE_RATE) -> dict:
    if T <= 0:
        return {"delta": 1.0 if S > K else 0.0, "gamma": 0.0, "theta_daily": 0.0, "vega": 0.0}
    d1 = _d1(S, K, T, sigma, r)
    d2 = _d2(S, K, T, sigma, r)
    pdf_d1 = math.exp(-0.5 * d1 ** 2) / math.sqrt(2.0 * math.pi)

    delta = _norm_cdf(d1)
    gamma = pdf_d1 / (S * sigma * math.sqrt(T))
    theta_annual = (
        -(S * pdf_d1 * sigma) / (2.0 * math.sqrt(T))
        - r * K * math.exp(-r * T) * _norm_cdf(d2)
    )
    theta_daily = theta_annual / 365.0
    vega = S * pdf_d1 * math.sqrt(T) / 100.0

    return {"delta": delta, "gamma": gamma, "theta_daily": theta_daily, "vega": vega}


def atm_option_cost(spot: float, vol: float, days_to_expiry: int) -> dict:
    T = max(days_to_expiry, 1) / 365.0
    K = spot
    call = bs_call_price(spot, K, T, vol)
    put = bs_put_price(spot, K, T, vol)
    call_greeks = bs_greeks(spot, K, T, vol)
    put_d1 = _d1(spot, K, T, vol, RISK_FREE_RATE)
    put_pdf = math.exp(-0.5 * put_d1 ** 2) / math.sqrt(2.0 * math.pi)
    put_theta_annual = (
        -(spot * put_pdf * vol) / (2.0 * math.sqrt(T))
        + RISK_FREE_RATE * K * math.exp(-RISK_FREE_RATE * T) * _norm_cdf(-_d2(spot, K, T, vol, RISK_FREE_RATE))
    )
    put_theta_daily = put_theta_annual / 365.0

    return {
        "call_price": call,
        "put_price": put,
        "call_theta_daily": call_greeks["theta_daily"],
        "put_theta_daily": put_theta_daily,
        "call_delta": call_greeks["delta"],
        "put_delta": _norm_cdf(put_d1) - 1.0,
        "combined_daily_theta": call_greeks["theta_daily"] + put_theta_daily,
    }


def five_day_rent(spot: float, vol: float, days_to_expiry: int) -> dict:
    cost = atm_option_cost(spot, vol, days_to_expiry)
    premium_pct = (cost["call_price"] + cost["put_price"]) / spot * 100.0
    theta_decay_5d_pct = abs(cost["combined_daily_theta"]) * 5.0 / spot * 100.0
    friction_pct = premium_pct * FRICTION_RATE
    return {
        "premium_pct": premium_pct,
        "theta_decay_5d_pct": theta_decay_5d_pct,
        "friction_pct": friction_pct,
        "total_rent_pct": theta_decay_5d_pct + friction_pct,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd C:/Users/Claude_Anka/askanka.com && python -m pytest pipeline/tests/test_options_pricer.py -v`
Expected: All 19 tests PASS

- [ ] **Step 5: Commit**

```bash
git add pipeline/options_pricer.py pipeline/tests/test_options_pricer.py
git commit -m "feat(station6.5): Black-Scholes options pricer with full test coverage"
```

---

### Task 2: Vol Engine — EWMA + Kite Cache + Tests

**Files:**
- Create: `pipeline/vol_engine.py`
- Create: `pipeline/tests/test_vol_engine.py`

- [ ] **Step 1: Write failing tests for EWMA computation and caching**

Create `pipeline/tests/test_vol_engine.py`:

```python
"""
Tests for pipeline/vol_engine.py — EWMA volatility engine.

Run: pytest pipeline/tests/test_vol_engine.py -v
"""
import pytest
import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch, MagicMock

IST = timezone(timedelta(hours=5, minutes=30))


SAMPLE_CLOSES = [
    100.0, 101.0, 99.5, 102.0, 100.5,
    103.0, 101.5, 104.0, 102.5, 105.0,
    103.5, 106.0, 104.5, 107.0, 105.5,
    108.0, 106.5, 109.0, 107.5, 110.0,
    108.5, 111.0, 109.5, 112.0, 110.5,
    113.0, 111.5, 114.0, 112.5, 115.0,
]


class TestComputeEWMAVol:
    def test_returns_positive_float(self):
        from pipeline.vol_engine import compute_ewma_vol
        vol = compute_ewma_vol(SAMPLE_CLOSES, span=30)
        assert isinstance(vol, float)
        assert vol > 0.0

    def test_annualised_range(self):
        """Annualised vol for +/- 1-2% daily moves should be 15-50%."""
        from pipeline.vol_engine import compute_ewma_vol
        vol = compute_ewma_vol(SAMPLE_CLOSES, span=30)
        assert 0.10 < vol < 0.60

    def test_higher_variance_gives_higher_vol(self):
        from pipeline.vol_engine import compute_ewma_vol
        calm = [100.0 + 0.1 * i for i in range(30)]
        wild = [100.0 + (3.0 if i % 2 == 0 else -3.0) for i in range(30)]
        assert compute_ewma_vol(wild, span=30) > compute_ewma_vol(calm, span=30)

    def test_minimum_two_prices(self):
        """Need at least 2 closes to compute a return."""
        from pipeline.vol_engine import compute_ewma_vol
        with pytest.raises(ValueError):
            compute_ewma_vol([100.0], span=30)

    def test_constant_prices_zero_vol(self):
        from pipeline.vol_engine import compute_ewma_vol
        vol = compute_ewma_vol([100.0] * 30, span=30)
        assert vol < 0.001


class TestCacheFreshness:
    def test_fresh_cache_is_not_stale(self):
        from pipeline.vol_engine import _is_cache_stale
        now = datetime.now(IST).isoformat()
        assert _is_cache_stale(now) is False

    def test_old_cache_is_stale(self):
        from pipeline.vol_engine import _is_cache_stale
        old = (datetime.now(IST) - timedelta(days=2)).isoformat()
        assert _is_cache_stale(old) is True


class TestGetStockVol:
    @patch("pipeline.vol_engine.fetch_and_cache_ohlcv")
    def test_returns_float_on_success(self, mock_fetch):
        from pipeline.vol_engine import get_stock_vol
        mock_fetch.return_value = [{"close": c} for c in SAMPLE_CLOSES]
        vol = get_stock_vol("HAL", cache_dir=Path("/tmp/test_vol_cache"))
        assert isinstance(vol, float)
        assert vol > 0.0

    @patch("pipeline.vol_engine.fetch_and_cache_ohlcv")
    def test_returns_none_on_failure(self, mock_fetch):
        from pipeline.vol_engine import get_stock_vol
        mock_fetch.return_value = []
        vol = get_stock_vol("BADTICKER", cache_dir=Path("/tmp/test_vol_cache"))
        assert vol is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd C:/Users/Claude_Anka/askanka.com && python -m pytest pipeline/tests/test_vol_engine.py -v`
Expected: `ModuleNotFoundError: No module named 'pipeline.vol_engine'`

- [ ] **Step 3: Implement vol_engine.py**

Create `pipeline/vol_engine.py`:

```python
"""EWMA volatility engine — fetches Kite OHLCV, caches per-ticker, computes annualised vol."""
import json
import math
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

log = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))
_DEFAULT_CACHE_DIR = Path(__file__).resolve().parent / "data" / "vol_cache"


def compute_ewma_vol(closes: list[float], span: int = 30) -> float:
    if len(closes) < 2:
        raise ValueError("Need at least 2 closes to compute volatility")

    log_returns = [math.log(closes[i] / closes[i - 1]) for i in range(1, len(closes)) if closes[i - 1] > 0]

    if not log_returns or all(r == 0.0 for r in log_returns):
        return 0.0

    alpha = 2.0 / (span + 1)
    ewma_var = log_returns[0] ** 2
    for r in log_returns[1:]:
        ewma_var = alpha * r ** 2 + (1 - alpha) * ewma_var

    daily_vol = math.sqrt(ewma_var)
    return daily_vol * math.sqrt(252)


def _is_cache_stale(fetched_at_iso: str) -> bool:
    try:
        fetched = datetime.fromisoformat(fetched_at_iso)
        age = datetime.now(IST) - fetched.astimezone(IST)
        return age > timedelta(hours=20)
    except Exception:
        return True


def fetch_and_cache_ohlcv(ticker: str, days: int = 35, cache_dir: Path = _DEFAULT_CACHE_DIR) -> list[dict]:
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / f"{ticker}.json"

    if cache_file.exists():
        try:
            cached = json.loads(cache_file.read_text(encoding="utf-8"))
            if not _is_cache_stale(cached.get("fetched_at", "")):
                return cached.get("candles", [])
        except Exception:
            pass

    try:
        from pipeline.kite_client import fetch_historical
        candles = fetch_historical(ticker, interval="day", days=days)
    except Exception as exc:
        log.warning("Kite fetch failed for %s: %s", ticker, exc)
        return []

    if candles:
        payload = {
            "ticker": ticker,
            "fetched_at": datetime.now(IST).isoformat(),
            "candles": candles,
        }
        try:
            cache_file.write_text(json.dumps(payload, default=str), encoding="utf-8")
        except Exception as exc:
            log.warning("Cache write failed for %s: %s", ticker, exc)

    return candles


def get_stock_vol(ticker: str, span: int = 30, cache_dir: Path = _DEFAULT_CACHE_DIR) -> float | None:
    candles = fetch_and_cache_ohlcv(ticker, days=span + 5, cache_dir=cache_dir)
    if len(candles) < 2:
        return None

    closes = [c["close"] for c in candles if "close" in c]
    if len(closes) < 2:
        return None

    try:
        vol = compute_ewma_vol(closes, span=span)
        # Update cache with computed vol
        cache_file = cache_dir / f"{ticker}.json"
        if cache_file.exists():
            try:
                cached = json.loads(cache_file.read_text(encoding="utf-8"))
                cached["ewma_vol_annual"] = vol
                cached["closes"] = closes
                cache_file.write_text(json.dumps(cached, default=str), encoding="utf-8")
            except Exception:
                pass
        return vol
    except Exception as exc:
        log.warning("EWMA computation failed for %s: %s", ticker, exc)
        return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd C:/Users/Claude_Anka/askanka.com && python -m pytest pipeline/tests/test_vol_engine.py -v`
Expected: All 8 tests PASS

- [ ] **Step 5: Commit**

```bash
git add pipeline/vol_engine.py pipeline/tests/test_vol_engine.py
git commit -m "feat(station6.5): EWMA volatility engine with Kite cache"
```

---

### Task 3: Synthetic Options Orchestrator + Tests

**Files:**
- Create: `pipeline/synthetic_options.py`
- Create: `pipeline/tests/test_synthetic_options.py`

- [ ] **Step 1: Write failing tests for leverage matrix builder**

Create `pipeline/tests/test_synthetic_options.py`:

```python
"""
Tests for pipeline/synthetic_options.py — leverage matrix orchestrator.

Run: pytest pipeline/tests/test_synthetic_options.py -v
"""
import pytest
from unittest.mock import patch, MagicMock

SAMPLE_SIGNAL = {
    "signal_id": "SIG-2026-04-19-001-Defence_vs_IT",
    "spread_name": "Defence vs IT",
    "conviction": 68,
    "long_legs": [
        {"ticker": "HAL", "price": 4284.8, "weight": 0.5},
        {"ticker": "BEL", "price": 449.85, "weight": 0.5},
    ],
    "short_legs": [
        {"ticker": "TCS", "price": 2572.0, "weight": 0.5},
        {"ticker": "INFY", "price": 1322.1, "weight": 0.5},
    ],
}

SAMPLE_PROFILES = {
    "stock_profiles": {
        "HAL": {"summary": {"avg_drift_5d": 0.0139, "hit_rate": 0.62}},
        "BEL": {"summary": {"avg_drift_5d": 0.0120, "hit_rate": 0.58}},
        "TCS": {"summary": {"avg_drift_5d": -0.0100, "hit_rate": 0.55}},
        "INFY": {"summary": {"avg_drift_5d": -0.0090, "hit_rate": 0.54}},
    }
}


class TestClassifyTier:
    def test_positive_edge_non_sameday(self):
        from pipeline.synthetic_options import classify_tier
        assert classify_tier(0.5, "1_month") == "HIGH-ALPHA SYNTHETIC"

    def test_positive_edge_sameday(self):
        from pipeline.synthetic_options import classify_tier
        assert classify_tier(0.5, "same_day") == "EXPERIMENTAL"

    def test_negative_edge(self):
        from pipeline.synthetic_options import classify_tier
        assert classify_tier(-0.1, "1_month") == "NEGATIVE CARRY"

    def test_zero_edge(self):
        from pipeline.synthetic_options import classify_tier
        assert classify_tier(0.0, "15_day") == "NEGATIVE CARRY"


class TestBuildCautionBadges:
    def test_negative_carry_badge(self):
        from pipeline.synthetic_options import build_caution_badges
        tiers = [
            {"horizon": "1_month", "net_edge_pct": -0.5, "experimental": False},
            {"horizon": "15_day", "net_edge_pct": 0.3, "experimental": False},
            {"horizon": "same_day", "net_edge_pct": 0.2, "experimental": True},
        ]
        badges = build_caution_badges(tiers, oi_data=None)
        assert "NEGATIVE_CARRY" in badges

    def test_low_conviction_gamma_no_oi(self):
        from pipeline.synthetic_options import build_caution_badges
        tiers = [
            {"horizon": "1_month", "net_edge_pct": 0.5, "experimental": False},
            {"horizon": "15_day", "net_edge_pct": 0.3, "experimental": False},
            {"horizon": "same_day", "net_edge_pct": 0.2, "experimental": True},
        ]
        badges = build_caution_badges(tiers, oi_data=None)
        assert "LOW_CONVICTION_GAMMA" in badges

    def test_drift_exceeds_rent_badge(self):
        from pipeline.synthetic_options import build_caution_badges
        tiers = [
            {"horizon": "1_month", "net_edge_pct": 1.8, "experimental": False},
            {"horizon": "15_day", "net_edge_pct": 0.3, "experimental": False},
            {"horizon": "same_day", "net_edge_pct": 0.2, "experimental": True},
        ]
        badges = build_caution_badges(tiers, oi_data={"HAL": {"oi_anomaly_type": "CALL_BUILDUP"}})
        assert "DRIFT_EXCEEDS_RENT" in badges
        assert "LOW_CONVICTION_GAMMA" not in badges

    def test_no_badges_when_all_positive_with_oi(self):
        from pipeline.synthetic_options import build_caution_badges
        tiers = [
            {"horizon": "1_month", "net_edge_pct": 0.5, "experimental": False},
            {"horizon": "15_day", "net_edge_pct": 0.3, "experimental": False},
            {"horizon": "same_day", "net_edge_pct": 0.2, "experimental": True},
        ]
        badges = build_caution_badges(tiers, oi_data={"HAL": {"oi_anomaly_type": "CALL_BUILDUP"}})
        assert "NEGATIVE_CARRY" not in badges
        assert "LOW_CONVICTION_GAMMA" not in badges


class TestBuildLeverageMatrix:
    @patch("pipeline.synthetic_options.vol_engine")
    def test_returns_grounding_ok_true(self, mock_vol):
        from pipeline.synthetic_options import build_leverage_matrix
        mock_vol.get_stock_vol.return_value = 0.30
        result = build_leverage_matrix(SAMPLE_SIGNAL, SAMPLE_PROFILES)
        assert result["grounding_ok"] is True
        assert result["signal_id"] == "SIG-2026-04-19-001-Defence_vs_IT"

    @patch("pipeline.synthetic_options.vol_engine")
    def test_three_tiers_present(self, mock_vol):
        from pipeline.synthetic_options import build_leverage_matrix
        mock_vol.get_stock_vol.return_value = 0.30
        result = build_leverage_matrix(SAMPLE_SIGNAL, SAMPLE_PROFILES)
        horizons = [t["horizon"] for t in result["tiers"]]
        assert horizons == ["1_month", "15_day", "same_day"]

    @patch("pipeline.synthetic_options.vol_engine")
    def test_grounding_false_when_vol_unavailable(self, mock_vol):
        from pipeline.synthetic_options import build_leverage_matrix
        mock_vol.get_stock_vol.return_value = None
        result = build_leverage_matrix(SAMPLE_SIGNAL, SAMPLE_PROFILES)
        assert result["grounding_ok"] is False

    @patch("pipeline.synthetic_options.vol_engine")
    def test_tier_fields_complete(self, mock_vol):
        from pipeline.synthetic_options import build_leverage_matrix
        mock_vol.get_stock_vol.return_value = 0.30
        result = build_leverage_matrix(SAMPLE_SIGNAL, SAMPLE_PROFILES)
        tier = result["tiers"][0]
        required = {"horizon", "days_to_expiry", "premium_cost_pct", "five_day_theta_pct",
                     "friction_pct", "total_rent_pct", "expected_drift_pct",
                     "net_edge_pct", "classification", "experimental"}
        assert required.issubset(set(tier.keys()))

    @patch("pipeline.synthetic_options.vol_engine")
    def test_sameday_is_experimental(self, mock_vol):
        from pipeline.synthetic_options import build_leverage_matrix
        mock_vol.get_stock_vol.return_value = 0.30
        result = build_leverage_matrix(SAMPLE_SIGNAL, SAMPLE_PROFILES)
        sameday = [t for t in result["tiers"] if t["horizon"] == "same_day"][0]
        assert sameday["experimental"] is True

    @patch("pipeline.synthetic_options.vol_engine")
    def test_net_edge_is_drift_minus_rent(self, mock_vol):
        from pipeline.synthetic_options import build_leverage_matrix
        mock_vol.get_stock_vol.return_value = 0.30
        result = build_leverage_matrix(SAMPLE_SIGNAL, SAMPLE_PROFILES)
        for tier in result["tiers"]:
            expected = tier["expected_drift_pct"] - tier["total_rent_pct"]
            assert abs(tier["net_edge_pct"] - expected) < 0.001
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd C:/Users/Claude_Anka/askanka.com && python -m pytest pipeline/tests/test_synthetic_options.py -v`
Expected: `ModuleNotFoundError: No module named 'pipeline.synthetic_options'`

- [ ] **Step 3: Implement synthetic_options.py**

Create `pipeline/synthetic_options.py`:

```python
"""Synthetic options orchestrator — builds leverage matrix from vol + pricer + regime data."""
import json
import logging
from pathlib import Path

from pipeline import vol_engine
from pipeline import options_pricer

log = logging.getLogger(__name__)

TIERS = [
    {"horizon": "1_month", "days": 30, "experimental": False},
    {"horizon": "15_day", "days": 15, "experimental": False},
    {"horizon": "same_day", "days": 1, "experimental": True},
]

_DATA = Path(__file__).resolve().parent / "data"
_SHADOW_PATH = _DATA / "signals" / "synthetic_options_shadow.json"


def classify_tier(net_edge: float, tier_name: str) -> str:
    if net_edge <= 0:
        return "NEGATIVE CARRY"
    if tier_name == "same_day":
        return "EXPERIMENTAL"
    return "HIGH-ALPHA SYNTHETIC"


def build_caution_badges(tiers: list[dict], oi_data: dict | None) -> list[str]:
    badges = []
    has_negative_non_experimental = any(
        t["net_edge_pct"] <= 0 and not t.get("experimental", False)
        for t in tiers
    )
    if has_negative_non_experimental:
        badges.append("NEGATIVE_CARRY")

    has_sameday = any(t.get("experimental", False) for t in tiers)
    has_oi_anomaly = bool(oi_data and any(
        v.get("oi_anomaly_type") not in (None, "NONE", "")
        for v in oi_data.values()
    ))
    if has_sameday and not has_oi_anomaly:
        badges.append("LOW_CONVICTION_GAMMA")

    month_tier = next((t for t in tiers if t["horizon"] == "1_month"), None)
    if month_tier and month_tier["net_edge_pct"] > 1.5:
        badges.append("DRIFT_EXCEEDS_RENT")

    return badges


def _weighted_vol(legs: list[dict], vol_fn) -> float | None:
    vols = []
    weights = []
    for leg in legs:
        v = vol_fn(leg["ticker"])
        if v is None:
            return None
        vols.append(v)
        weights.append(leg.get("weight", 1.0))
    total_w = sum(weights)
    if total_w == 0:
        return None
    return sum(v * w for v, w in zip(vols, weights)) / total_w


def _avg_drift(legs: list[dict], profiles: dict) -> float:
    drifts = []
    for leg in legs:
        stock = profiles.get("stock_profiles", {}).get(leg["ticker"], {})
        drift = stock.get("summary", {}).get("avg_drift_5d", 0.0)
        drifts.append(abs(drift))
    return sum(drifts) / len(drifts) if drifts else 0.0


def build_leverage_matrix(signal: dict, regime_profiles: dict, oi_data: dict | None = None) -> dict:
    long_legs = signal.get("long_legs", [])
    short_legs = signal.get("short_legs", [])

    long_vol = _weighted_vol(long_legs, vol_engine.get_stock_vol)
    short_vol = _weighted_vol(short_legs, vol_engine.get_stock_vol)

    if long_vol is None or short_vol is None:
        missing = []
        for leg in long_legs + short_legs:
            if vol_engine.get_stock_vol(leg["ticker"]) is None:
                missing.append(leg["ticker"])
        return {
            "signal_id": signal.get("signal_id", ""),
            "spread_name": signal.get("spread_name", ""),
            "conviction_score": signal.get("conviction", 0),
            "grounding_ok": False,
            "reason": f"vol unavailable for {', '.join(missing)}",
            "tiers": [],
            "caution_badges": [],
            "long_side_vol": None,
            "short_side_vol": None,
        }

    avg_vol = (long_vol + short_vol) / 2.0
    long_drift = _avg_drift(long_legs, regime_profiles)
    short_drift = _avg_drift(short_legs, regime_profiles)
    expected_drift_pct = (long_drift + short_drift) * 100.0

    long_spot = sum(l.get("price", 0) * l.get("weight", 1) for l in long_legs)
    short_spot = sum(s.get("price", 0) * s.get("weight", 1) for s in short_legs)
    avg_spot = (long_spot + short_spot) / 2.0 if (long_spot + short_spot) > 0 else 100.0

    tiers = []
    for t in TIERS:
        rent = options_pricer.five_day_rent(avg_spot, avg_vol, t["days"])
        net_edge = expected_drift_pct - rent["total_rent_pct"]
        tiers.append({
            "horizon": t["horizon"],
            "days_to_expiry": t["days"],
            "premium_cost_pct": round(rent["premium_pct"], 3),
            "five_day_theta_pct": round(rent["theta_decay_5d_pct"], 3),
            "friction_pct": round(rent["friction_pct"], 3),
            "total_rent_pct": round(rent["total_rent_pct"], 3),
            "expected_drift_pct": round(expected_drift_pct, 3),
            "net_edge_pct": round(net_edge, 3),
            "classification": classify_tier(net_edge, t["horizon"]),
            "experimental": t["experimental"],
        })

    badges = build_caution_badges(tiers, oi_data)

    return {
        "signal_id": signal.get("signal_id", ""),
        "spread_name": signal.get("spread_name", ""),
        "conviction_score": signal.get("conviction", 0),
        "grounding_ok": True,
        "tiers": tiers,
        "caution_badges": badges,
        "long_side_vol": round(long_vol, 4),
        "short_side_vol": round(short_vol, 4),
    }


def record_shadow_entry(signal: dict, matrix: dict, regime: str) -> dict | None:
    if not matrix.get("grounding_ok"):
        return None

    positive_tiers = [
        t for t in matrix.get("tiers", [])
        if t["net_edge_pct"] > 0 and not t.get("experimental", False)
    ]
    if not positive_tiers:
        return None

    from datetime import datetime, timezone, timedelta
    IST = timezone(timedelta(hours=5, minutes=30))

    existing = []
    _SHADOW_PATH.parent.mkdir(parents=True, exist_ok=True)
    if _SHADOW_PATH.exists():
        try:
            existing = json.loads(_SHADOW_PATH.read_text(encoding="utf-8"))
        except Exception:
            existing = []

    count = sum(1 for e in existing if e.get("signal_id") == signal.get("signal_id", "")) + 1
    shadow_id = f"OPT-{datetime.now(IST).strftime('%Y-%m-%d')}-{count:03d}-{signal.get('spread_name', '').replace(' ', '_')}"

    long_legs = signal.get("long_legs", [])
    short_legs = signal.get("short_legs", [])
    entry_spot_long = sum(l.get("price", 0) * l.get("weight", 1) for l in long_legs)
    entry_spot_short = sum(s.get("price", 0) * s.get("weight", 1) for s in short_legs)

    entry = {
        "shadow_id": shadow_id,
        "signal_id": signal.get("signal_id", ""),
        "entry_timestamp": datetime.now(IST).isoformat(),
        "spread_name": signal.get("spread_name", ""),
        "regime_at_entry": regime,
        "conviction_score": signal.get("conviction", 0),
        "long_legs": long_legs,
        "short_legs": short_legs,
        "entry_spot_long": entry_spot_long,
        "entry_spot_short": entry_spot_short,
        "long_side_vol": matrix.get("long_side_vol"),
        "short_side_vol": matrix.get("short_side_vol"),
        "tiers_at_entry": [
            {
                "horizon": t["horizon"],
                "premium_cost_pct": t["premium_cost_pct"],
                "total_rent_pct": t["total_rent_pct"],
                "expected_drift_pct": t["expected_drift_pct"],
                "net_edge_pct": t["net_edge_pct"],
            }
            for t in matrix.get("tiers", [])
            if not t.get("experimental", False)
        ],
        "daily_marks": [{
            "date": datetime.now(IST).strftime("%Y-%m-%d"),
            "day": 0,
            "long_price": entry_spot_long,
            "short_price": entry_spot_short,
            "spread_move_pct": 0.0,
            "repriced_1m_pnl_pct": 0.0,
            "repriced_15d_pnl_pct": 0.0,
            "cumulative_theta_1m": 0.0,
            "cumulative_theta_15d": 0.0,
        }],
        "status": "OPEN",
        "exit_reason": None,
        "final_pnl_futures_pct": None,
        "final_pnl_1m_options_pct": None,
        "final_pnl_15d_options_pct": None,
    }

    existing.append(entry)
    _SHADOW_PATH.write_text(json.dumps(existing, indent=2, default=str), encoding="utf-8")
    return entry
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd C:/Users/Claude_Anka/askanka.com && python -m pytest pipeline/tests/test_synthetic_options.py -v`
Expected: All 13 tests PASS

- [ ] **Step 5: Commit**

```bash
git add pipeline/synthetic_options.py pipeline/tests/test_synthetic_options.py
git commit -m "feat(station6.5): synthetic options orchestrator with leverage matrix"
```

---

### Task 4: API Integration — Digest Extension + Options Shadow Endpoint

**Files:**
- Modify: `pipeline/terminal/api/research.py`
- Modify: `pipeline/terminal/static/js/lib/api.js`

- [ ] **Step 1: Add leverage_matrices to the digest endpoint**

In `pipeline/terminal/api/research.py`, add imports and a builder function after the existing `_build_backtest_validation` function (after line 141), then wire it into the endpoint.

Add at the top of the file (after line 5):

```python
from pathlib import Path
```

This import already exists. Add this new import after line 5:

```python
from pipeline.synthetic_options import build_leverage_matrix
```

Add this function after `_build_backtest_validation` (after line 141):

```python
_REGIME_PROFILE = Path(__file__).resolve().parent.parent.parent / "autoresearch" / "reverse_regime_profile.json"
_OPEN_SIGNALS = _DATA / "signals" / "open_signals.json"
_OPTIONS_SHADOW = _DATA / "signals" / "synthetic_options_shadow.json"


def _build_leverage_matrices(spread_theses: list, regime_raw: dict, positioning: dict) -> list:
    profiles = _read_json(_REGIME_PROFILE)
    signals = _read_json(_OPEN_SIGNALS, default=[])
    if not isinstance(signals, list):
        signals = []

    matrices = []
    for s in spread_theses:
        if s.get("score", 0) < 65:
            continue
        matching_signal = next(
            (sig for sig in signals if sig.get("spread_name") == s["name"] and sig.get("status") == "OPEN"),
            None,
        )
        if not matching_signal:
            matching_signal = {
                "signal_id": f"DIGEST-{s['name'].replace(' ', '_')}",
                "spread_name": s["name"],
                "conviction": s.get("score", 0),
                "long_legs": [],
                "short_legs": [],
            }
        try:
            matrix = build_leverage_matrix(matching_signal, profiles, oi_data=positioning)
            matrices.append(matrix)
        except Exception as exc:
            log.warning("Leverage matrix failed for %s: %s", s["name"], exc)
    return matrices
```

Add a logger at the top of the file (after imports):

```python
import logging
log = logging.getLogger(__name__)
```

Update the `research_digest()` function return (modify lines 219-226) to:

```python
    leverage_matrices = _build_leverage_matrices(spread_theses, regime_raw, positioning_raw)

    return {
        "generated_at": regime_raw.get("timestamp", datetime.now(IST).isoformat()),
        "regime_thesis": thesis,
        "spread_theses": spread_theses,
        "correlation_breaks": corr_breaks,
        "backtest_validation": backtest,
        "grounding_failures": grounding_failures,
        "leverage_matrices": leverage_matrices,
    }
```

- [ ] **Step 2: Add the options-shadow endpoint**

Add at the end of `pipeline/terminal/api/research.py`:

```python
@router.get("/research/options-shadow")
def options_shadow():
    data = _read_json(_OPTIONS_SHADOW, default=[])
    if not isinstance(data, list):
        data = []
    return data
```

- [ ] **Step 3: Add API function in api.js**

In `pipeline/terminal/static/js/lib/api.js`, add after line 20 (the `getDigest` line):

```javascript
export async function getOptionsShadow() { return get('/research/options-shadow'); }
```

- [ ] **Step 4: Verify the terminal still starts**

Run: `cd C:/Users/Claude_Anka/askanka.com/pipeline/terminal && python -c "from api.research import router; print('Router loaded OK')"`
Expected: `Router loaded OK`

- [ ] **Step 5: Commit**

```bash
git add pipeline/terminal/api/research.py pipeline/terminal/static/js/lib/api.js
git commit -m "feat(station6.5): leverage matrices in digest API + options-shadow endpoint"
```

---

### Task 5: Signal Hook — Record Synthetic Shadow on Signal Emission

**Files:**
- Modify: `pipeline/run_signals.py`

- [ ] **Step 1: Add synthetic options shadow recording**

In `pipeline/run_signals.py`, after the shadow trade creation block (after line 331, the `except` block for shadow trade), add:

```python
                    # ── Synthetic options shadow ──
                    try:
                        from pipeline.synthetic_options import build_leverage_matrix, record_shadow_entry
                        import json as _json
                        profile_path = Path(__file__).parent / "autoresearch" / "reverse_regime_profile.json"
                        profiles = _json.loads(profile_path.read_text(encoding="utf-8")) if profile_path.exists() else {}
                        positioning_path = Path(__file__).parent / "data" / "positioning.json"
                        oi_data = _json.loads(positioning_path.read_text(encoding="utf-8")) if positioning_path.exists() else {}
                        opt_signal = {
                            "signal_id": trackable["signal_id"],
                            "spread_name": spread_name,
                            "conviction": spread.get("hit_rate", 0) * 100,
                            "long_legs": spread.get("long_leg", []),
                            "short_legs": spread.get("short_leg", []),
                        }
                        matrix = build_leverage_matrix(opt_signal, profiles, oi_data=oi_data)
                        entry = record_shadow_entry(opt_signal, matrix, regime)
                        if entry:
                            print(f"  🎯 Synthetic options shadow: {entry['shadow_id']}")
                        elif matrix.get("grounding_ok"):
                            print(f"  ⚪ Synthetic options: all tiers negative carry")
                        else:
                            print(f"  ⚪ Synthetic options: {matrix.get('reason', 'vol unavailable')}")
                    except Exception as e:
                        print(f"  Synthetic options shadow failed: {e}")
```

- [ ] **Step 2: Verify run_signals.py still imports cleanly**

Run: `cd C:/Users/Claude_Anka/askanka.com && python -c "import pipeline.run_signals; print('OK')"`
Expected: `OK` (no import errors)

- [ ] **Step 3: Commit**

```bash
git add pipeline/run_signals.py
git commit -m "feat(station6.5): record synthetic options shadow on signal emission"
```

---

### Task 6: Leverage Matrix UI Component

**Files:**
- Create: `pipeline/terminal/static/js/components/leverage-matrix.js`

- [ ] **Step 1: Create the leverage matrix card component**

Create `pipeline/terminal/static/js/components/leverage-matrix.js`:

```javascript
/**
 * Leverage Matrix card — renders 3-tier Drift vs Rent grid for a spread.
 *
 * Usage: renderLeverageCard(matrix) → HTML string
 */

const VERDICT_STYLES = {
  'HIGH-ALPHA SYNTHETIC': { cls: 'badge--green', label: 'HIGH-ALPHA' },
  'NEGATIVE CARRY': { cls: 'badge--red', label: 'NEG CARRY' },
  'EXPERIMENTAL': { cls: 'badge--amber', label: 'EXPERIMENTAL' },
};

const BADGE_STYLES = {
  'NEGATIVE_CARRY': { cls: 'badge--red', label: 'NEGATIVE CARRY' },
  'LOW_CONVICTION_GAMMA': { cls: 'badge--amber', label: 'LOW CONVICTION GAMMA' },
  'DRIFT_EXCEEDS_RENT': { cls: 'badge--green', label: 'DRIFT > RENT' },
};

export function renderLeverageCard(matrix) {
  if (!matrix) return '';

  if (!matrix.grounding_ok) {
    return `
      <div class="digest-card" style="opacity: 0.5;">
        <div class="digest-card__title">${esc(matrix.spread_name || '?')}</div>
        <div class="text-muted" style="font-size: 0.8125rem;">
          Vol data unavailable — ${esc(matrix.reason || 'Kite session may be stale')}
        </div>
      </div>`;
  }

  const convBadge = matrix.conviction_score >= 65
    ? `<span class="badge badge--green">${matrix.conviction_score}</span>`
    : `<span class="badge badge--amber">${matrix.conviction_score}</span>`;

  const tierRows = (matrix.tiers || []).map(t => {
    const v = VERDICT_STYLES[t.classification] || { cls: 'badge--muted', label: t.classification };
    const edgeCls = t.net_edge_pct > 0 ? 'text-green' : 'text-red';
    const edgeSign = t.net_edge_pct > 0 ? '+' : '';
    return `
      <tr>
        <td class="mono">${formatHorizon(t.horizon)}</td>
        <td class="mono">${t.premium_cost_pct.toFixed(2)}%</td>
        <td class="mono">${t.total_rent_pct.toFixed(2)}%</td>
        <td class="mono">${t.expected_drift_pct.toFixed(2)}%</td>
        <td class="mono ${edgeCls}">${edgeSign}${t.net_edge_pct.toFixed(2)}%</td>
        <td><span class="badge ${v.cls}">${v.label}</span></td>
      </tr>`;
  }).join('');

  const badgesHtml = (matrix.caution_badges || []).map(b => {
    const s = BADGE_STYLES[b] || { cls: 'badge--muted', label: b };
    return `<span class="badge ${s.cls}">${s.label}</span>`;
  }).join(' ');

  const volInfo = matrix.long_side_vol != null
    ? `<span class="text-muted" style="font-size: 0.6875rem;">
        Long vol: ${(matrix.long_side_vol * 100).toFixed(1)}% · Short vol: ${(matrix.short_side_vol * 100).toFixed(1)}%
       </span>`
    : '';

  return `
    <div class="digest-card">
      <div style="display: flex; justify-content: space-between; align-items: center;">
        <div class="digest-card__title">${esc(matrix.spread_name)}</div>
        ${convBadge}
      </div>
      <div class="digest-card__subtitle">Drift vs Rent — Leverage Matrix</div>
      <table class="data-table" style="margin-top: var(--spacing-sm);">
        <thead>
          <tr>
            <th>Tier</th><th>Premium</th><th>5d Rent</th>
            <th>Exp. Drift</th><th>Net Edge</th><th>Verdict</th>
          </tr>
        </thead>
        <tbody>${tierRows}</tbody>
      </table>
      ${badgesHtml ? `<div style="margin-top: var(--spacing-sm);">${badgesHtml}</div>` : ''}
      ${volInfo ? `<div style="margin-top: var(--spacing-xs);">${volInfo}</div>` : ''}
    </div>`;
}

export function renderShadowStrip(shadows) {
  if (!shadows || shadows.length === 0) {
    return `
      <div class="digest-card">
        <div class="digest-card__title">Forward Test</div>
        <div class="digest-card__subtitle">No synthetic options trades tracked yet</div>
        <p class="text-muted" style="font-size: 0.8125rem;">
          Shadow entries appear when 65+ conviction signals show positive net edge
        </p>
      </div>`;
  }

  const rows = shadows.map(s => {
    const legs = [...(s.long_legs || []), ...(s.short_legs || [])];
    const tickers = legs.map(l =>
      `<span class="clickable-ticker" data-ticker="${esc(l.ticker)}" style="cursor:pointer; text-decoration: underline;">${esc(l.ticker)}</span>`
    ).join(', ');

    const daysHeld = s.daily_marks ? s.daily_marks.length : 0;
    const lastMark = s.daily_marks && s.daily_marks.length > 0 ? s.daily_marks[s.daily_marks.length - 1] : {};

    const futPnl = s.final_pnl_futures_pct != null ? s.final_pnl_futures_pct : (lastMark.spread_move_pct || 0);
    const opt1m = s.final_pnl_1m_options_pct != null ? s.final_pnl_1m_options_pct : (lastMark.repriced_1m_pnl_pct || 0);
    const opt15d = s.final_pnl_15d_options_pct != null ? s.final_pnl_15d_options_pct : (lastMark.repriced_15d_pnl_pct || 0);

    const pnlCls = v => v >= 0 ? 'text-green' : 'text-red';
    const pnlFmt = v => `${v >= 0 ? '+' : ''}${v.toFixed(2)}%`;
    const statusBadge = s.status === 'OPEN'
      ? '<span class="badge badge--blue">OPEN</span>'
      : `<span class="badge badge--muted">${s.status}</span>`;

    return `
      <tr>
        <td>${esc(s.spread_name)}</td>
        <td>${tickers}</td>
        <td class="mono">${(s.entry_timestamp || '').slice(0, 10)}</td>
        <td class="mono">${daysHeld}d</td>
        <td class="mono ${pnlCls(futPnl)}">${pnlFmt(futPnl)}</td>
        <td class="mono ${pnlCls(opt1m)}">${pnlFmt(opt1m)}</td>
        <td class="mono ${pnlCls(opt15d)}">${pnlFmt(opt15d)}</td>
        <td>${statusBadge}</td>
      </tr>`;
  }).join('');

  return `
    <div class="digest-card">
      <div class="digest-card__title">Forward Test — Options vs Futures</div>
      <div class="digest-card__subtitle">Would options have beaten futures?</div>
      <table class="data-table" style="margin-top: var(--spacing-sm);">
        <thead>
          <tr>
            <th>Spread</th><th>Tickers</th><th>Entry</th><th>Held</th>
            <th>Futures</th><th>1M Opt</th><th>15D Opt</th><th>Status</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    </div>`;
}

function formatHorizon(h) {
  return { '1_month': '1-Month', '15_day': '15-Day', 'same_day': 'Same-Day' }[h] || h;
}

function esc(s) {
  if (!s) return '';
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}
```

- [ ] **Step 2: Commit**

```bash
git add pipeline/terminal/static/js/components/leverage-matrix.js
git commit -m "feat(station6.5): leverage matrix UI component"
```

---

### Task 7: Intelligence Page — Options Sub-tab + Right Panel Wiring

**Files:**
- Modify: `pipeline/terminal/static/js/pages/intelligence.js`

- [ ] **Step 1: Add "Options" sub-tab button and routing**

In `pipeline/terminal/static/js/pages/intelligence.js`:

Update the import at line 1 to add the new API call:

```javascript
import { get } from '../lib/api.js';
import { renderLeverageCard, renderShadowStrip } from '../components/leverage-matrix.js';
```

Update the sub-tab buttons HTML (replace lines 7-11):

```javascript
    <div class="main__subtabs">
      <button class="subtab subtab--active" data-subtab="trust-scores">Trust Scores</button>
      <button class="subtab" data-subtab="news">News</button>
      <button class="subtab" data-subtab="research">Research</button>
      <button class="subtab" data-subtab="options">Options</button>
    </div>
```

Update the switch statement (replace lines 32-36):

```javascript
  switch (tab) {
    case 'trust-scores': await renderTrustScores(el); break;
    case 'news': await renderNews(el); break;
    case 'research': await renderResearch(el); break;
    case 'options': await renderOptions(el); break;
  }
```

- [ ] **Step 2: Add the renderOptions function**

Add at the end of the file (before the closing of the module), after the `_scheduleRefresh` function:

```javascript
async function renderOptions(el) {
  el.innerHTML = '<div class="skeleton skeleton--card"></div>';

  try {
    const [digest, shadows] = await Promise.all([
      get('/research/digest'),
      get('/research/options-shadow'),
    ]);

    const matrices = digest.leverage_matrices || [];
    const genTime = digest.generated_at || '';
    const isStale = _isStale(genTime);
    const timeStr = genTime ? new Date(genTime).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata' }) : '--';
    const staleBadge = isStale ? ' <span class="badge badge--stale">STALE</span>' : '';

    const matrixCards = matrices.length > 0
      ? matrices.map(m => renderLeverageCard(m)).join('')
      : '<div class="digest-card"><p class="text-muted">No spreads with 65+ conviction — leverage matrix requires qualifying signals</p></div>';

    const shadowStrip = renderShadowStrip(shadows);

    el.innerHTML = `
      <div class="digest-header">
        <h2 class="digest-header__title">Synthetic Options — Drift vs Rent</h2>
        <span class="digest-header__time">Vol data: ${timeStr}${staleBadge}</span>
      </div>
      <div style="display: flex; flex-direction: column; gap: var(--spacing-md);">
        ${matrixCards}
        ${shadowStrip}
      </div>`;

    _wireOptionsTickers(el);

  } catch (err) {
    el.innerHTML = '<div class="empty-state"><p>Failed to load synthetic options data</p></div>';
  }
}

function _wireOptionsTickers(container) {
  container.querySelectorAll('.clickable-ticker[data-ticker]').forEach(span => {
    span.addEventListener('click', async () => {
      const ticker = span.dataset.ticker;
      const panel = document.getElementById('context-panel');
      const title = document.getElementById('context-panel-title');
      const content = document.getElementById('context-panel-content');
      if (!panel || !title || !content) return;

      title.textContent = ticker;
      content.innerHTML = '<div class="skeleton skeleton--card"></div>';
      panel.classList.add('context-panel--open');

      try {
        const [trustData, newsData, volData] = await Promise.all([
          get(`/trust-scores/${ticker}`).catch(() => ({})),
          get(`/news/${ticker}`).catch(() => ({ items: [] })),
          get('/research/digest').then(d => {
            const matrices = d.leverage_matrices || [];
            for (const m of matrices) {
              if (!m.grounding_ok) continue;
              const allLegs = [...(m.long_legs || []), ...(m.short_legs || [])];
              if (m.long_side_vol != null) return { long_vol: m.long_side_vol, short_vol: m.short_side_vol };
            }
            return {};
          }).catch(() => ({})),
        ]);

        const gradeCls = {
          'A+': 'badge--green', 'A': 'badge--green',
          'B+': 'badge--blue', 'B': 'badge--blue',
          'C': 'badge--amber', 'D': 'badge--red', 'F': 'badge--red',
        }[trustData.trust_grade] || 'badge--muted';

        const newsHtml = (newsData.items || []).slice(0, 8).map(n => `
          <div style="padding: var(--spacing-xs) 0; border-bottom: 1px solid rgba(30,41,59,0.3); font-size: 0.8125rem;">
            ${_esc(n.headline || n.title || '--')}
            <div class="text-muted" style="font-size: 0.6875rem;">${_esc(n.timestamp || n.date || '')}</div>
          </div>`).join('');

        const volHtml = volData.long_vol != null ? `
          <div class="card" style="margin-bottom: var(--spacing-md);">
            <div class="text-muted" style="font-size: 0.75rem;">SYNTHETIC VOL</div>
            <div style="display: flex; gap: var(--spacing-lg); margin-top: var(--spacing-xs);">
              <div>
                <div class="text-muted" style="font-size: 0.6875rem;">Long Side</div>
                <div class="mono">${(volData.long_vol * 100).toFixed(1)}%</div>
              </div>
              <div>
                <div class="text-muted" style="font-size: 0.6875rem;">Short Side</div>
                <div class="mono">${(volData.short_vol * 100).toFixed(1)}%</div>
              </div>
            </div>
          </div>` : '';

        content.innerHTML = `
          <div class="card" style="margin-bottom: var(--spacing-md);">
            <div class="text-muted" style="font-size: 0.75rem;">TRUST SCORE</div>
            <div style="display: flex; align-items: baseline; gap: var(--spacing-sm);">
              <span class="badge ${gradeCls}" style="font-size: 2rem;">${_esc(trustData.trust_grade || '?')}</span>
              <span class="mono">${trustData.trust_score ?? '--'}</span>
            </div>
            <div style="font-size: 0.8125rem; margin-top: var(--spacing-sm); line-height: 1.6;">${_esc(trustData.thesis || 'No thesis')}</div>
          </div>
          ${volHtml}
          <div class="card">
            <div class="text-muted" style="font-size: 0.75rem; margin-bottom: var(--spacing-sm);">RECENT NEWS</div>
            ${newsHtml || '<p class="text-muted">No news</p>'}
          </div>`;
      } catch {
        content.innerHTML = '<div class="empty-state"><p>Failed to load context</p></div>';
      }
    });
  });
}
```

- [ ] **Step 3: Verify intelligence page loads**

Start the terminal server and navigate to Intelligence → Options in a browser. Verify:
- Sub-tab appears and is clickable
- Shows "No spreads with 65+ conviction" or leverage matrix cards if signals exist
- Forward test strip renders (empty state or with data)
- Clicking a ticker in the forward test strip opens the right panel with trust score, news, and synthetic vol
- Other sub-tabs (Trust Scores, News, Research) still work correctly

- [ ] **Step 4: Commit**

```bash
git add pipeline/terminal/static/js/pages/intelligence.js
git commit -m "feat(station6.5): Options sub-tab with leverage matrix + right panel wiring"
```

---

### Task 8: Verify Full Integration + Final Commit

**Files:** None new — this is a verification task.

- [ ] **Step 1: Run the full test suite**

Run: `cd C:/Users/Claude_Anka/askanka.com && python -m pytest pipeline/tests/ -v --tb=short`
Expected: All existing tests PASS + all new tests (test_options_pricer, test_vol_engine, test_synthetic_options) PASS

- [ ] **Step 2: Verify the terminal end-to-end**

Start the terminal: `cd C:/Users/Claude_Anka/askanka.com/pipeline/terminal && python app.py`

Check in browser:
1. Dashboard tab — unchanged, no regressions
2. Intelligence → Trust Scores — works
3. Intelligence → News — works
4. Intelligence → Research — works, now includes `leverage_matrices` in API response
5. Intelligence → Options — shows leverage matrix cards or empty state
6. Trading → Signals — works
7. Trading → Scanner — works

- [ ] **Step 3: Test the API endpoints directly**

Run: `curl http://localhost:8501/api/research/digest | python -m json.tool | grep leverage`
Expected: `"leverage_matrices": [...]` key present in response

Run: `curl http://localhost:8501/api/research/options-shadow`
Expected: `[]` (empty list, no shadow entries yet)

- [ ] **Step 4: Create vol_cache directory**

Run: `mkdir -p C:/Users/Claude_Anka/askanka.com/pipeline/data/vol_cache`

Add `.gitkeep`:
```bash
touch C:/Users/Claude_Anka/askanka.com/pipeline/data/vol_cache/.gitkeep
git add pipeline/data/vol_cache/.gitkeep
```

- [ ] **Step 5: Final commit**

```bash
git add -A
git commit -m "feat(station6.5): synthetic options engine — complete integration"
```
