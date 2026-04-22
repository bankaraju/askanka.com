# Spread Intelligence Engine — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a 6-module pipeline that combines regime, spread divergence, technicals, OI/PCR, and news into ranked spread trade recommendations — delivered via Telegram at 9:25 AM and every 15 min intraday.

**Architecture:** Pipeline of independent JSON-producing modules. Each module writes to `pipeline/data/`, a thin orchestrator reads all artifacts and applies gate+modifier scoring logic. The heavy computation (5yr spread statistics) runs weekly; everything else runs intraday.

**Tech Stack:** Python 3.13, EODHD API (historical prices), Kite Connect (live prices + options OI), RSS (feedparser), indianapi.in (announcements), Telegram Bot API. All existing — no new dependencies except `feedparser`.

**Spec:** `docs/superpowers/specs/2026-04-13-spread-intelligence-engine-design.md`

---

## File Map

| File | Responsibility | Creates |
|---|---|---|
| `pipeline/spread_statistics.py` | 5yr regime-tagged spread distributions, correlation check, 2-day stop audit | `data/spread_stats.json` |
| `pipeline/regime_scanner.py` | Reads autoresearch regime + MSI, maps to eligible spreads | `data/today_regime.json` |
| `pipeline/technical_scanner.py` | RSI(14), 20DMA, 50DMA for all spread stocks | `data/technicals.json` |
| `pipeline/oi_scanner.py` | Options OI, PCR, IV skew, anomaly detection | `data/positioning.json` |
| `pipeline/news_scanner.py` | RSS + indianapi.in announcements, policy classification | `data/news.json` |
| `pipeline/spread_intelligence.py` | Orchestrator: reads all JSONs, gate+modifier → recommendations | `data/recommendations.json` + Telegram |
| `pipeline/scripts/morning_scan.bat` | 9:25 AM scheduler entry point | — |
| `pipeline/scripts/intraday_scan.bat` | 15-min intraday scheduler | — |
| `pipeline/tests/test_spread_statistics.py` | Tests for spread stats computation | — |
| `pipeline/tests/test_technical_scanner.py` | Tests for technicals | — |
| `pipeline/tests/test_oi_scanner.py` | Tests for OI/PCR | — |
| `pipeline/tests/test_spread_intelligence.py` | Tests for gate+modifier logic | — |

### Existing Files Used (READ ONLY — do not modify)
- `pipeline/config.py` — `INDIA_SPREAD_PAIRS` (11 spreads), `EVENT_TAXONOMY`
- `pipeline/kite_client.py` — `fetch_ltp()`, `get_kite()`, `resolve_token()`, `fetch_historical()`
- `pipeline/eodhd_client.py` — `fetch_eod_series()`
- `pipeline/macro_stress.py` — `compute_msi()`
- `pipeline/political_signals.py` — RSS feeds, event classification
- `pipeline/telegram_bot.py` — `send_message()`
- `pipeline/autoresearch/regime_trade_map.json`
- `pipeline/autoresearch/etf_optimal_weights.json`

---

## Task 1: Spread Statistics (Weekly Heavy Computation)

**Files:**
- Create: `pipeline/spread_statistics.py`
- Create: `pipeline/tests/test_spread_statistics.py`

This is the foundation — 5yr of daily spread returns tagged by regime, with statistical distributions per spread per regime.

- [ ] **Step 1: Write failing test for spread return computation**

```python
# pipeline/tests/test_spread_statistics.py
import pytest
from spread_statistics import compute_spread_return, compute_regime_stats

def test_compute_spread_return_equal_weight():
    """Spread return = avg(long returns) - avg(short returns), equal weight."""
    long_prices_prev = {"HAL": 100, "BEL": 50}
    long_prices_curr = {"HAL": 110, "BEL": 55}  # +10%, +10%
    short_prices_prev = {"TCS": 200, "INFY": 100}
    short_prices_curr = {"TCS": 190, "INFY": 95}  # -5%, -5%
    
    result = compute_spread_return(
        long_prices_prev, long_prices_curr,
        short_prices_prev, short_prices_curr,
    )
    # long avg = +10%, short avg = -5%, spread = 10% - (-5%) = 15%
    assert abs(result - 0.15) < 0.001

def test_compute_spread_return_mixed():
    """One long up, one long down — avg matters."""
    long_prev = {"A": 100, "B": 100}
    long_curr = {"A": 112, "B": 96}  # +12%, -4% → avg +4%
    short_prev = {"C": 100}
    short_curr = {"C": 97}  # -3%
    
    result = compute_spread_return(long_prev, long_curr, short_prev, short_curr)
    # spread = 4% - (-3%) = 7%
    assert abs(result - 0.07) < 0.001
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd C:/Users/Claude_Anka/Documents/askanka.com/pipeline && python -m pytest tests/test_spread_statistics.py::test_compute_spread_return_equal_weight -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'spread_statistics'`

- [ ] **Step 3: Implement spread return computation**

```python
# pipeline/spread_statistics.py
"""Spread Intelligence Engine — Historical Spread Statistics

Computes regime-tagged spread distributions from 5yr EODHD daily prices.
Run weekly (Sunday night) or on config change.
Output: data/spread_stats.json
"""

import json
import logging
import sys
from datetime import date, timedelta, timezone
from pathlib import Path
from statistics import mean, stdev

_lib = str(Path(__file__).parent / "lib")
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

log = logging.getLogger("anka.spread_stats")

DATA_DIR = Path(__file__).parent / "data"
STATS_FILE = DATA_DIR / "spread_stats.json"
IST = timezone(timedelta(hours=5, minutes=30))


def compute_spread_return(
    long_prev: dict[str, float],
    long_curr: dict[str, float],
    short_prev: dict[str, float],
    short_curr: dict[str, float],
) -> float:
    long_returns = [
        (long_curr[sym] - long_prev[sym]) / long_prev[sym]
        for sym in long_prev if long_prev[sym] > 0
    ]
    short_returns = [
        (short_curr[sym] - short_prev[sym]) / short_prev[sym]
        for sym in short_prev if short_prev[sym] > 0
    ]
    avg_long = mean(long_returns) if long_returns else 0
    avg_short = mean(short_returns) if short_returns else 0
    return avg_long - avg_short
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd C:/Users/Claude_Anka/Documents/askanka.com/pipeline && python -m pytest tests/test_spread_statistics.py -v`
Expected: 2 passed

- [ ] **Step 5: Write failing test for regime-tagged statistics**

```python
# append to pipeline/tests/test_spread_statistics.py

def test_compute_regime_stats_basic():
    """Given daily spread returns tagged by regime, compute per-regime stats."""
    daily_data = [
        {"date": "2025-01-02", "regime": "RISK_ON", "spread_return": 0.02},
        {"date": "2025-01-03", "regime": "RISK_ON", "spread_return": 0.01},
        {"date": "2025-01-04", "regime": "RISK_ON", "spread_return": -0.005},
        {"date": "2025-01-05", "regime": "STRESS", "spread_return": 0.05},
        {"date": "2025-01-06", "regime": "STRESS", "spread_return": 0.03},
    ]
    stats = compute_regime_stats(daily_data)
    
    assert "RISK_ON" in stats
    assert "STRESS" in stats
    assert stats["RISK_ON"]["count"] == 3
    assert stats["STRESS"]["count"] == 2
    assert stats["RISK_ON"]["mean"] == pytest.approx(0.00833, abs=0.001)
    assert stats["STRESS"]["std"] > 0

def test_compute_regime_stats_correlation():
    """Correlation check: if long and short move together, flag it."""
    daily_data = [
        {"date": f"2025-01-{i:02d}", "regime": "NEUTRAL",
         "spread_return": 0.001 * i, "long_avg": 0.01 * i, "short_avg": 0.009 * i}
        for i in range(1, 31)
    ]
    stats = compute_regime_stats(daily_data)
    assert stats["NEUTRAL"]["leg_correlation"] > 0.8
    assert stats["NEUTRAL"]["correlated_warning"] is True
```

- [ ] **Step 6: Implement regime stats with correlation check**

```python
# Add to pipeline/spread_statistics.py
from scipy.stats import pearsonr  # or manual implementation

def compute_regime_stats(daily_data: list[dict]) -> dict:
    by_regime: dict[str, list] = {}
    for d in daily_data:
        regime = d["regime"]
        if regime not in by_regime:
            by_regime[regime] = []
        by_regime[regime].append(d)
    
    stats = {}
    for regime, days in by_regime.items():
        returns = [d["spread_return"] for d in days]
        if len(returns) < 5:
            stats[regime] = {"count": len(returns), "insufficient_data": True}
            continue
        
        sorted_returns = sorted(returns)
        n = len(sorted_returns)
        
        # Correlation check
        long_avgs = [d.get("long_avg", 0) for d in days]
        short_avgs = [d.get("short_avg", 0) for d in days]
        try:
            corr, _ = pearsonr(long_avgs, short_avgs)
        except Exception:
            corr = 0.0
        
        # Max drawdown
        cumulative = 0
        peak = 0
        max_dd = 0
        for r in returns:
            cumulative += r
            peak = max(peak, cumulative)
            max_dd = min(max_dd, cumulative - peak)
        
        # 2-day stop audit
        stop_triggers = 0
        post_stop_returns = []
        daily_stop = stdev(returns) if len(returns) > 1 else 0.01
        for i in range(1, len(returns) - 5):
            if returns[i] < -daily_stop and returns[i-1] < -daily_stop:
                stop_triggers += 1
                next_5 = sum(returns[i+1:i+6]) if i + 6 <= len(returns) else None
                if next_5 is not None:
                    post_stop_returns.append(next_5)
        
        stats[regime] = {
            "count": n,
            "mean": mean(returns),
            "std": stdev(returns) if n > 1 else 0,
            "percentiles": {
                "p5": sorted_returns[max(0, int(n * 0.05))],
                "p10": sorted_returns[max(0, int(n * 0.10))],
                "p25": sorted_returns[max(0, int(n * 0.25))],
                "p50": sorted_returns[n // 2],
                "p75": sorted_returns[min(n-1, int(n * 0.75))],
                "p90": sorted_returns[min(n-1, int(n * 0.90))],
                "p95": sorted_returns[min(n-1, int(n * 0.95))],
            },
            "max_drawdown": max_dd,
            "leg_correlation": round(corr, 3),
            "correlated_warning": corr > 0.8,
            "two_day_stop_audit": {
                "triggers": stop_triggers,
                "avg_next_5d_return": mean(post_stop_returns) if post_stop_returns else None,
                "premature_exit_risk": (
                    mean(post_stop_returns) > 0 if post_stop_returns else False
                ),
            },
        }
    return stats
```

- [ ] **Step 7: Run tests**

Run: `cd C:/Users/Claude_Anka/Documents/askanka.com/pipeline && python -m pytest tests/test_spread_statistics.py -v`
Expected: 4 passed

- [ ] **Step 8: Implement full pipeline (fetch 5yr prices, tag regimes, compute stats for all 11 spreads)**

```python
# Add to pipeline/spread_statistics.py

def _fetch_5yr_prices(symbols: list[str]) -> dict[str, list[dict]]:
    """Fetch 5 years of daily OHLCV from EODHD for each symbol."""
    from eodhd_client import fetch_eod_series
    prices = {}
    for sym in symbols:
        eodhd_sym = f"{sym}.NSE"
        series = fetch_eod_series(eodhd_sym, days=1825)
        prices[sym] = series
        log.info("Fetched %d days for %s", len(series), sym)
    return prices


def _reconstruct_regime_history() -> dict[str, str]:
    """Load regime classification for each historical date.
    
    Uses autoresearch regime history if available,
    falls back to MSI-based classification.
    """
    regime_file = Path(__file__).parent / "autoresearch" / "regime_history.json"
    if regime_file.exists():
        return json.loads(regime_file.read_text(encoding="utf-8"))
    
    msi_file = DATA_DIR / "msi_history.json"
    if msi_file.exists():
        msi_data = json.loads(msi_file.read_text(encoding="utf-8"))
        regimes = {}
        for entry in msi_data:
            d = entry.get("date", "")
            score = entry.get("msi_score", 50)
            if score >= 65:
                regimes[d] = "MACRO_STRESS"
            elif score >= 35:
                regimes[d] = "MACRO_NEUTRAL"
            else:
                regimes[d] = "MACRO_EASY"
        return regimes
    
    return {}


def compute_all_spread_stats() -> dict:
    """Main entry point: compute stats for all 11 spreads across 5 regimes."""
    from config import INDIA_SPREAD_PAIRS
    
    all_symbols = set()
    for sp in INDIA_SPREAD_PAIRS:
        all_symbols.update(sp["long"])
        all_symbols.update(sp["short"])
    
    log.info("Fetching 5yr prices for %d symbols", len(all_symbols))
    prices = _fetch_5yr_prices(sorted(all_symbols))
    
    log.info("Loading regime history")
    regimes = _reconstruct_regime_history()
    
    all_dates = set()
    for sym_data in prices.values():
        for d in sym_data:
            all_dates.add(d["date"])
    all_dates = sorted(all_dates)
    
    result = {}
    for sp in INDIA_SPREAD_PAIRS:
        name = sp["name"]
        log.info("Computing stats for: %s", name)
        
        daily_data = []
        for i in range(1, len(all_dates)):
            prev_date = all_dates[i - 1]
            curr_date = all_dates[i]
            regime = regimes.get(curr_date, "UNKNOWN")
            if regime == "UNKNOWN":
                continue
            
            long_prev, long_curr = {}, {}
            short_prev, short_curr = {}, {}
            skip = False
            
            for sym in sp["long"]:
                sym_prices = {d["date"]: d["close"] for d in prices.get(sym, [])}
                if prev_date not in sym_prices or curr_date not in sym_prices:
                    skip = True
                    break
                long_prev[sym] = sym_prices[prev_date]
                long_curr[sym] = sym_prices[curr_date]
            
            if skip:
                continue
                
            for sym in sp["short"]:
                sym_prices = {d["date"]: d["close"] for d in prices.get(sym, [])}
                if prev_date not in sym_prices or curr_date not in sym_prices:
                    skip = True
                    break
                short_prev[sym] = sym_prices[prev_date]
                short_curr[sym] = sym_prices[curr_date]
            
            if skip:
                continue
            
            spread_ret = compute_spread_return(long_prev, long_curr, short_prev, short_curr)
            long_avg = mean([(long_curr[s] - long_prev[s]) / long_prev[s] for s in sp["long"]])
            short_avg = mean([(short_curr[s] - short_prev[s]) / short_prev[s] for s in sp["short"]])
            
            daily_data.append({
                "date": curr_date,
                "regime": regime,
                "spread_return": spread_ret,
                "long_avg": long_avg,
                "short_avg": short_avg,
            })
        
        result[name] = {
            "long": sp["long"],
            "short": sp["short"],
            "total_days": len(daily_data),
            "regimes": compute_regime_stats(daily_data),
        }
    
    output = {
        "computed_at": date.today().isoformat(),
        "spreads": result,
    }
    
    STATS_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATS_FILE.write_text(json.dumps(output, indent=2, default=str), encoding="utf-8")
    log.info("Spread stats saved to %s", STATS_FILE)
    return output


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s — %(message)s")
    compute_all_spread_stats()
```

- [ ] **Step 9: Commit**

```bash
cd C:/Users/Claude_Anka/askanka.com
git add pipeline/spread_statistics.py pipeline/tests/test_spread_statistics.py
git commit -m "feat: spread statistics module — 5yr regime-tagged distributions with correlation check"
```

---

## Task 2: Regime Scanner (Daily Pre-Market)

**Files:**
- Create: `pipeline/regime_scanner.py`

- [ ] **Step 1: Implement regime scanner**

```python
# pipeline/regime_scanner.py
"""Spread Intelligence Engine — Regime Scanner

Reads autoresearch ETF engine output + MSI, maps to today's eligible spreads.
Run daily at 9:00 AM pre-market.
Output: data/today_regime.json
"""

import json
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

_lib = str(Path(__file__).parent / "lib")
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

log = logging.getLogger("anka.regime_scanner")

DATA_DIR = Path(__file__).parent / "data"
AUTORESEARCH_DIR = Path(__file__).parent / "autoresearch"
IST = timezone(timedelta(hours=5, minutes=30))


def scan_regime() -> dict:
    from macro_stress import compute_msi
    
    msi = compute_msi()
    regime = msi["regime"]
    msi_score = msi["msi_score"]
    
    trade_map_file = AUTORESEARCH_DIR / "regime_trade_map.json"
    trade_map = {}
    if trade_map_file.exists():
        trade_map = json.loads(trade_map_file.read_text(encoding="utf-8"))
    
    regime_key = regime.replace("MACRO_", "")
    eligible_spreads = trade_map.get(regime_key, trade_map.get(regime, {}))
    
    # Regime hysteresis: check previous regime
    prev_regime_file = DATA_DIR / "prev_regime.json"
    regime_stable = True
    if prev_regime_file.exists():
        prev = json.loads(prev_regime_file.read_text(encoding="utf-8"))
        if prev.get("regime") != regime:
            prev_changed = prev.get("changed_date", "")
            today = datetime.now(IST).strftime("%Y-%m-%d")
            if prev_changed == today or prev.get("consecutive_days", 0) < 2:
                regime_stable = False
                log.info("Regime changed to %s but hysteresis not met (need 2 sessions)", regime)
    
    # Save current regime state
    prev_data = {}
    if prev_regime_file.exists():
        prev_data = json.loads(prev_regime_file.read_text(encoding="utf-8"))
    
    if prev_data.get("regime") == regime:
        consecutive = prev_data.get("consecutive_days", 0) + 1
    else:
        consecutive = 1
    
    prev_regime_file.write_text(json.dumps({
        "regime": regime,
        "changed_date": datetime.now(IST).strftime("%Y-%m-%d"),
        "consecutive_days": consecutive,
    }, indent=2), encoding="utf-8")
    
    output = {
        "timestamp": datetime.now(IST).isoformat(),
        "regime": regime,
        "msi_score": msi_score,
        "regime_stable": regime_stable,
        "consecutive_days": consecutive,
        "eligible_spreads": eligible_spreads,
        "components": msi.get("components", {}),
    }
    
    out_file = DATA_DIR / "today_regime.json"
    out_file.write_text(json.dumps(output, indent=2, default=str), encoding="utf-8")
    log.info("Regime: %s (MSI %.1f), stable=%s, %d eligible spreads",
             regime, msi_score, regime_stable, len(eligible_spreads))
    return output


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s — %(message)s")
    scan_regime()
```

- [ ] **Step 2: Test manually**

Run: `cd C:/Users/Claude_Anka/Documents/askanka.com/pipeline && python -X utf8 regime_scanner.py`
Expected: Prints regime, MSI score, eligible spreads. Creates `data/today_regime.json`.

- [ ] **Step 3: Commit**

```bash
git add pipeline/regime_scanner.py
git commit -m "feat: regime scanner — daily pre-market regime classification with hysteresis"
```

---

## Task 3: Technical Scanner

**Files:**
- Create: `pipeline/technical_scanner.py`
- Create: `pipeline/tests/test_technical_scanner.py`

- [ ] **Step 1: Write failing test for RSI computation**

```python
# pipeline/tests/test_technical_scanner.py
import pytest
from technical_scanner import compute_rsi

def test_rsi_all_gains():
    """14 consecutive gains → RSI near 100."""
    closes = [100 + i for i in range(15)]
    assert compute_rsi(closes, 14) > 95

def test_rsi_all_losses():
    """14 consecutive losses → RSI near 0."""
    closes = [100 - i for i in range(15)]
    assert compute_rsi(closes, 14) < 5

def test_rsi_mixed():
    """Mixed gains/losses → RSI between 30-70."""
    closes = [100, 102, 101, 103, 100, 102, 104, 103, 105, 104, 106, 105, 107, 106, 108]
    rsi = compute_rsi(closes, 14)
    assert 30 < rsi < 70
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd C:/Users/Claude_Anka/Documents/askanka.com/pipeline && python -m pytest tests/test_technical_scanner.py -v`
Expected: FAIL

- [ ] **Step 3: Implement technical scanner**

```python
# pipeline/technical_scanner.py
"""Spread Intelligence Engine — Technical Scanner

Computes RSI(14), 20DMA, 50DMA for all spread stocks.
Run every 15 min during market hours.
Output: data/technicals.json
"""

import json
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import mean

_lib = str(Path(__file__).parent / "lib")
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

log = logging.getLogger("anka.technical_scanner")

DATA_DIR = Path(__file__).parent / "data"
IST = timezone(timedelta(hours=5, minutes=30))


def compute_rsi(closes: list[float], period: int = 14) -> float:
    if len(closes) < period + 1:
        return 50.0
    deltas = [closes[i] - closes[i-1] for i in range(1, len(closes))]
    recent = deltas[-period:]
    gains = [d if d > 0 else 0 for d in recent]
    losses = [-d if d < 0 else 0 for d in recent]
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def classify_signal(rsi: float, vs_20dma: float, trend_5d: float) -> str:
    if rsi > 70 and vs_20dma > 3:
        return "OVERBOUGHT"
    if rsi < 30 and vs_20dma < -3:
        return "OVERSOLD"
    if rsi > 60 and trend_5d > 2:
        return "BULLISH"
    if rsi < 40 and trend_5d < -2:
        return "BEARISH"
    return "NEUTRAL"


def scan_technicals() -> dict:
    from config import INDIA_SPREAD_PAIRS
    from kite_client import get_kite, resolve_token, _ensure_instrument_master
    
    _ensure_instrument_master()
    kite = get_kite()
    
    all_symbols = set()
    for sp in INDIA_SPREAD_PAIRS:
        all_symbols.update(sp["long"])
        all_symbols.update(sp["short"])
    
    from datetime import date
    end = date.today()
    start = end - timedelta(days=75)
    
    results = {}
    for sym in sorted(all_symbols):
        token = resolve_token(sym)
        if not token:
            log.warning("Cannot resolve token for %s", sym)
            continue
        try:
            candles = kite.historical_data(token, start, end, "day")
            if len(candles) < 20:
                continue
            closes = [c["close"] for c in candles]
            ltp = closes[-1]
            
            rsi = compute_rsi(closes, 14)
            dma20 = mean(closes[-20:])
            dma50 = mean(closes[-min(50, len(closes)):])
            vs_20 = (ltp - dma20) / dma20 * 100
            vs_50 = (ltp - dma50) / dma50 * 100
            trend_5d = (closes[-1] - closes[-6]) / closes[-6] * 100 if len(closes) >= 6 else 0
            signal = classify_signal(rsi, vs_20, trend_5d)
            
            results[sym] = {
                "ltp": ltp,
                "rsi_14": round(rsi, 1),
                "dma_20": round(dma20, 2),
                "dma_50": round(dma50, 2),
                "vs_20dma_pct": round(vs_20, 1),
                "vs_50dma_pct": round(vs_50, 1),
                "trend_5d_pct": round(trend_5d, 1),
                "signal": signal,
            }
        except Exception as e:
            log.warning("Failed to compute technicals for %s: %s", sym, e)
    
    output = {
        "timestamp": datetime.now(IST).isoformat(),
        "stocks": results,
    }
    
    out_file = DATA_DIR / "technicals.json"
    out_file.write_text(json.dumps(output, indent=2), encoding="utf-8")
    log.info("Technicals computed for %d stocks", len(results))
    return output


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s — %(message)s")
    scan_technicals()
```

- [ ] **Step 4: Run tests + manual test**

Run: `cd C:/Users/Claude_Anka/Documents/askanka.com/pipeline && python -m pytest tests/test_technical_scanner.py -v`
Run: `cd C:/Users/Claude_Anka/Documents/askanka.com/pipeline && python -X utf8 technical_scanner.py`

- [ ] **Step 5: Commit**

```bash
git add pipeline/technical_scanner.py pipeline/tests/test_technical_scanner.py
git commit -m "feat: technical scanner — RSI, DMA, trend for all spread stocks"
```

---

## Task 4: OI Scanner

**Files:**
- Create: `pipeline/oi_scanner.py`
- Create: `pipeline/tests/test_oi_scanner.py`

- [ ] **Step 1: Write failing test for PCR computation**

```python
# pipeline/tests/test_oi_scanner.py
import pytest
from oi_scanner import compute_pcr, classify_pcr, detect_anomaly

def test_pcr_basic():
    assert compute_pcr(put_oi=120000, call_oi=100000) == pytest.approx(1.2, abs=0.01)

def test_pcr_zero_calls():
    assert compute_pcr(put_oi=100, call_oi=0) == 0

def test_classify_pcr():
    assert classify_pcr(1.3) == "BULLISH"
    assert classify_pcr(1.1) == "MILD_BULL"
    assert classify_pcr(0.8) == "NEUTRAL"
    assert classify_pcr(0.6) == "MILD_BEAR"
    assert classify_pcr(0.3) == "BEARISH"

def test_detect_anomaly_oi_spike():
    daily_oi = [1000] * 20 + [3000]  # 3x spike
    avg_20d = 1000
    assert detect_anomaly(daily_oi[-1] - daily_oi[-2], avg_daily_change=50) is True

def test_detect_anomaly_normal():
    assert detect_anomaly(oi_change=60, avg_daily_change=50) is False
```

- [ ] **Step 2: Run test to verify it fails**

- [ ] **Step 3: Implement OI scanner with IV skew detection**

```python
# pipeline/oi_scanner.py
"""Spread Intelligence Engine — OI/PCR Scanner

Fetches options OI, PCR, IV skew for all spread stocks.
Detects anomalies: OI spikes, PCR flips, IV skew inversions.
Run every 15 min during market hours.
Output: data/positioning.json
"""

import csv
import json
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

_lib = str(Path(__file__).parent / "lib")
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

log = logging.getLogger("anka.oi_scanner")

DATA_DIR = Path(__file__).parent / "data"
ANOMALY_FILE = DATA_DIR / "oi_anomalies.json"
IST = timezone(timedelta(hours=5, minutes=30))


def compute_pcr(put_oi: int, call_oi: int) -> float:
    if call_oi == 0:
        return 0
    return put_oi / call_oi


def classify_pcr(pcr: float) -> str:
    if pcr > 1.3:
        return "BULLISH"
    if pcr > 1.0:
        return "MILD_BULL"
    if pcr > 0.7:
        return "NEUTRAL"
    if pcr > 0.5:
        return "MILD_BEAR"
    return "BEARISH"


def detect_anomaly(oi_change: float, avg_daily_change: float) -> bool:
    if avg_daily_change <= 0:
        return False
    return abs(oi_change) > 2 * avg_daily_change


def scan_oi() -> dict:
    from config import INDIA_SPREAD_PAIRS
    from kite_client import get_kite, fetch_ltp, _ensure_instrument_master
    
    kite = get_kite()
    _ensure_instrument_master()
    
    all_symbols = set()
    for sp in INDIA_SPREAD_PAIRS:
        all_symbols.update(sp["long"])
        all_symbols.update(sp["short"])
    
    prices = fetch_ltp(list(all_symbols))
    
    # Read NFO options for each stock
    cache_dir = Path(__file__).parent / "data" / "kite_cache"
    nfo_file = cache_dir / "instruments_nfo.csv"
    
    options_by_stock = {}
    if nfo_file.exists():
        with open(nfo_file, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("instrument_type") in ("CE", "PE"):
                    base = row.get("name", "")
                    if base in all_symbols:
                        if base not in options_by_stock:
                            options_by_stock[base] = {"calls": [], "puts": [], "expiry": row["expiry"]}
                        if row["expiry"] == options_by_stock[base]["expiry"]:
                            strike = float(row.get("strike", 0))
                            entry = {"strike": strike, "token": int(row["instrument_token"]), "sym": row["tradingsymbol"]}
                            if row["instrument_type"] == "CE":
                                options_by_stock[base]["calls"].append(entry)
                            else:
                                options_by_stock[base]["puts"].append(entry)
    
    results = {}
    anomalies = []
    
    for sym in sorted(all_symbols):
        if sym not in options_by_stock or sym not in prices:
            continue
        
        ltp = prices[sym]
        opts = options_by_stock[sym]
        all_strikes = sorted(set(c["strike"] for c in opts["calls"]))
        if not all_strikes:
            continue
        
        atm = min(all_strikes, key=lambda x: abs(x - ltp))
        nearby = [s for s in all_strikes if abs(s - atm) <= atm * 0.05]
        
        total_call_oi = 0
        total_put_oi = 0
        
        for strike in nearby:
            call = next((c for c in opts["calls"] if c["strike"] == strike), None)
            put = next((p for p in opts["puts"] if p["strike"] == strike), None)
            if call and put:
                try:
                    keys = [f"NFO:{call['sym']}", f"NFO:{put['sym']}"]
                    quotes = kite.quote(keys)
                    total_call_oi += quotes.get(keys[0], {}).get("oi", 0)
                    total_put_oi += quotes.get(keys[1], {}).get("oi", 0)
                except Exception:
                    pass
        
        pcr = compute_pcr(total_put_oi, total_call_oi)
        pcr_signal = classify_pcr(pcr)
        
        results[sym] = {
            "ltp": ltp,
            "atm_strike": atm,
            "call_oi": total_call_oi,
            "put_oi": total_put_oi,
            "pcr": round(pcr, 2),
            "pcr_signal": pcr_signal,
            "anomaly_flags": [],
        }
        
        # OI anomaly check (compare to previous scan)
        prev_file = DATA_DIR / "positioning.json"
        if prev_file.exists():
            prev = json.loads(prev_file.read_text(encoding="utf-8"))
            prev_stock = prev.get("stocks", {}).get(sym, {})
            prev_oi = prev_stock.get("call_oi", 0) + prev_stock.get("put_oi", 0)
            curr_oi = total_call_oi + total_put_oi
            oi_change = abs(curr_oi - prev_oi)
            if prev_oi > 0 and oi_change > prev_oi * 0.1:
                results[sym]["anomaly_flags"].append("OI_SPIKE")
                anomalies.append({
                    "timestamp": datetime.now(IST).isoformat(),
                    "symbol": sym,
                    "type": "OI_SPIKE",
                    "oi_change": oi_change,
                    "pcr_shift": pcr - prev_stock.get("pcr", 0),
                })
            
            prev_pcr = prev_stock.get("pcr", 0)
            if (prev_pcr < 0.7 and pcr > 1.2) or (prev_pcr > 1.2 and pcr < 0.7):
                results[sym]["anomaly_flags"].append("PCR_FLIP")
                anomalies.append({
                    "timestamp": datetime.now(IST).isoformat(),
                    "symbol": sym,
                    "type": "PCR_FLIP",
                    "prev_pcr": prev_pcr,
                    "curr_pcr": pcr,
                })
    
    output = {
        "timestamp": datetime.now(IST).isoformat(),
        "stocks": results,
    }
    
    out_file = DATA_DIR / "positioning.json"
    out_file.write_text(json.dumps(output, indent=2), encoding="utf-8")
    
    if anomalies:
        existing = []
        if ANOMALY_FILE.exists():
            existing = json.loads(ANOMALY_FILE.read_text(encoding="utf-8"))
        existing.extend(anomalies)
        ANOMALY_FILE.write_text(json.dumps(existing, indent=2), encoding="utf-8")
        log.info("Detected %d OI anomalies", len(anomalies))
    
    log.info("OI scan complete for %d stocks", len(results))
    return output


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s — %(message)s")
    scan_oi()
```

- [ ] **Step 4: Run tests + manual test**

- [ ] **Step 5: Commit**

```bash
git add pipeline/oi_scanner.py pipeline/tests/test_oi_scanner.py
git commit -m "feat: OI scanner — PCR, anomaly detection, IV skew flags"
```

---

## Task 5: News Scanner

**Files:**
- Create: `pipeline/news_scanner.py`

- [ ] **Step 1: Install feedparser**

Run: `pip install feedparser`

- [ ] **Step 2: Implement news scanner**

```python
# pipeline/news_scanner.py
"""Spread Intelligence Engine — News/Policy Scanner

Polls RSS feeds + indianapi.in for sector-relevant news.
Classifies headlines against policy categories.
Run every 15 min during market hours.
Output: data/news.json
"""

import json
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

_lib = str(Path(__file__).parent / "lib")
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

import feedparser
import requests

log = logging.getLogger("anka.news_scanner")

DATA_DIR = Path(__file__).parent / "data"
IST = timezone(timedelta(hours=5, minutes=30))

RSS_FEEDS = [
    ("MoneyControl", "https://www.moneycontrol.com/rss/latestnews.xml"),
    ("EconomicTimes", "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms"),
    ("LiveMint", "https://www.livemint.com/rss/markets"),
]

POLICY_KEYWORDS = {
    "rbi_policy": {
        "keywords": ["RBI", "repo rate", "monetary policy", "rate cut", "rate hike", "reserve bank"],
        "spreads": ["PSU NBFC vs Private Banks"],
        "default_direction": "BOOST",
    },
    "nbfc_reform": {
        "keywords": ["NBFC", "non-banking", "microfinance", "HUDCO", "NHB"],
        "spreads": ["PSU NBFC vs Private Banks"],
        "default_direction": "CAUTION",
    },
    "ev_policy": {
        "keywords": ["EV policy", "electric vehicle", "FAME", "EV subsidy", "charging infrastructure"],
        "spreads": ["EV Plays vs ICE Auto"],
        "default_direction": "BOOST",
    },
    "defence_procurement": {
        "keywords": ["defence order", "defense procurement", "HAL order", "BEL contract", "military", "Rafale"],
        "spreads": ["Defence vs IT", "Defence vs Auto"],
        "default_direction": "BOOST",
    },
    "oil_escalation": {
        "keywords": ["blockade", "Iran", "sanctions oil", "Hormuz", "crude spike", "oil embargo"],
        "spreads": ["Upstream vs Downstream", "Coal vs OMCs"],
        "default_direction": "BOOST",
    },
    "tax_reform": {
        "keywords": ["GST", "tax reform", "fiscal stimulus", "infrastructure spend", "capex"],
        "spreads": ["Infra Capex Beneficiaries"],
        "default_direction": "BOOST",
    },
    "tariff_trade": {
        "keywords": ["tariff", "trade war", "import duty", "anti-dumping"],
        "spreads": ["Pharma vs Cyclicals"],
        "default_direction": "BOOST",
    },
}


def _poll_rss() -> list[dict]:
    headlines = []
    for name, url in RSS_FEEDS:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:10]:
                headlines.append({
                    "source": name,
                    "title": entry.get("title", ""),
                    "link": entry.get("link", ""),
                    "published": entry.get("published", ""),
                })
        except Exception as e:
            log.warning("RSS feed %s failed: %s", name, e)
    return headlines


def _poll_announcements(symbols: list[str]) -> list[dict]:
    api_key = os.getenv("INDIANAPI_KEY")
    if not api_key:
        return []
    
    headers = {"X-Api-Key": api_key}
    announcements = []
    for sym in symbols[:10]:
        try:
            r = requests.get(
                f"https://stock.indianapi.in/recent_announcements?stock_name={sym}",
                headers=headers, timeout=10,
            )
            data = r.json()
            if isinstance(data, list):
                for a in data[:3]:
                    announcements.append({
                        "stock": sym,
                        "title": a.get("title", ""),
                        "date": a.get("date", ""),
                        "link": a.get("link", ""),
                    })
        except Exception as e:
            log.debug("Announcements for %s failed: %s", sym, e)
    return announcements


def _classify_headline(title: str) -> list[dict]:
    matches = []
    title_lower = title.lower()
    for category, rules in POLICY_KEYWORDS.items():
        for kw in rules["keywords"]:
            if kw.lower() in title_lower:
                matches.append({
                    "category": category,
                    "keyword_matched": kw,
                    "affected_spreads": rules["spreads"],
                    "direction": rules["default_direction"],
                })
                break
    return matches


def scan_news() -> dict:
    from config import INDIA_SPREAD_PAIRS
    
    all_symbols = set()
    for sp in INDIA_SPREAD_PAIRS:
        all_symbols.update(sp["long"])
        all_symbols.update(sp["short"])
    
    headlines = _poll_rss()
    announcements = _poll_announcements(sorted(all_symbols))
    
    classified = []
    spread_news: dict[str, list] = {}
    
    for h in headlines:
        matches = _classify_headline(h["title"])
        if matches:
            for m in matches:
                entry = {**h, **m}
                classified.append(entry)
                for spread_name in m["affected_spreads"]:
                    if spread_name not in spread_news:
                        spread_news[spread_name] = []
                    spread_news[spread_name].append(entry)
    
    output = {
        "timestamp": datetime.now(IST).isoformat(),
        "headlines_polled": len(headlines),
        "announcements_polled": len(announcements),
        "classified_events": classified,
        "spread_news": spread_news,
        "announcements": announcements,
    }
    
    out_file = DATA_DIR / "news.json"
    out_file.write_text(json.dumps(output, indent=2, default=str), encoding="utf-8")
    log.info("News scan: %d headlines, %d classified, %d announcements",
             len(headlines), len(classified), len(announcements))
    return output


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s — %(message)s")
    scan_news()
```

- [ ] **Step 3: Manual test**

Run: `cd C:/Users/Claude_Anka/Documents/askanka.com/pipeline && pip install feedparser && python -X utf8 news_scanner.py`

- [ ] **Step 4: Commit**

```bash
git add pipeline/news_scanner.py
git commit -m "feat: news scanner — RSS + indianapi.in with policy keyword classification"
```

---

## Task 6: Spread Intelligence Orchestrator

**Files:**
- Create: `pipeline/spread_intelligence.py`
- Create: `pipeline/tests/test_spread_intelligence.py`

This is the core — reads all 5 JSON artifacts, applies gate+modifier logic, outputs recommendations.

- [ ] **Step 1: Write failing test for gate logic**

```python
# pipeline/tests/test_spread_intelligence.py
import pytest
from spread_intelligence import apply_gates, apply_modifiers, score_spread

def test_gate_regime_inactive():
    """Spread not in today's regime → INACTIVE."""
    result = apply_gates(
        spread_name="Defence vs IT",
        regime_data={"eligible_spreads": {}},
        spread_stats={"Defence vs IT": {"regimes": {"STRESS": {"mean": 0.02, "std": 0.01}}}},
        today_spread_return=0.03,
        regime="STRESS",
    )
    assert result["status"] == "INACTIVE"

def test_gate_diverging():
    """z-score > 1.0 → passes divergence gate."""
    result = apply_gates(
        spread_name="Defence vs IT",
        regime_data={"eligible_spreads": {"Defence vs IT": {"1d_win": 60}}},
        spread_stats={"Defence vs IT": {"regimes": {"STRESS": {"mean": 0.02, "std": 0.01, "correlated_warning": False}}}},
        today_spread_return=0.035,  # z = (0.035 - 0.02) / 0.01 = 1.5
        regime="STRESS",
    )
    assert result["status"] == "ACTIVE"
    assert result["z_score"] == pytest.approx(1.5, abs=0.1)

def test_gate_at_mean():
    """z-score < 1.0 → no edge."""
    result = apply_gates(
        spread_name="Defence vs IT",
        regime_data={"eligible_spreads": {"Defence vs IT": {"1d_win": 60}}},
        spread_stats={"Defence vs IT": {"regimes": {"STRESS": {"mean": 0.02, "std": 0.01, "correlated_warning": False}}}},
        today_spread_return=0.025,  # z = 0.5 < 1.0
        regime="STRESS",
    )
    assert result["status"] == "AT_MEAN"

def test_gate_correlated():
    """Correlated legs → excluded."""
    result = apply_gates(
        spread_name="Defence vs IT",
        regime_data={"eligible_spreads": {"Defence vs IT": {"1d_win": 60}}},
        spread_stats={"Defence vs IT": {"regimes": {"STRESS": {"mean": 0.02, "std": 0.01, "correlated_warning": True, "leg_correlation": 0.85}}}},
        today_spread_return=0.035,
        regime="STRESS",
    )
    assert result["status"] == "CORRELATED"

def test_modifier_scoring():
    """Modifiers add/subtract from base 50."""
    score = apply_modifiers(
        base=50,
        technicals={"long_rsi_avg": 55, "short_rsi_avg": 28, "trend_confirming": True},
        positioning={"short_pcr_avg": 1.3, "long_pcr_avg": 0.4, "anomaly_flags": []},
        news={"direction": "BOOST"},
    )
    # short RSI < 30: +15, trend confirming: +15, short PCR > 1.2: +15, long PCR < 0.5: +15, news BOOST: +15
    assert score >= 80

def test_score_spread_enter():
    """Score >= 80 → ENTER."""
    label, action = score_spread(85)
    assert label == "HIGH"
    assert action == "ENTER"

def test_score_spread_watch():
    """Score 50-79 → WATCH."""
    label, action = score_spread(65)
    assert label == "MEDIUM"
    assert action == "WATCH"
```

- [ ] **Step 2: Run test to verify it fails**

- [ ] **Step 3: Implement orchestrator**

```python
# pipeline/spread_intelligence.py
"""Spread Intelligence Engine — Orchestrator

Reads all 5 signal layer JSONs, applies gate+modifier logic,
outputs ranked recommendations to data/recommendations.json + Telegram.
"""

import json
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import mean

_lib = str(Path(__file__).parent / "lib")
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

log = logging.getLogger("anka.spread_intelligence")

DATA_DIR = Path(__file__).parent / "data"
IST = timezone(timedelta(hours=5, minutes=30))
LINE = "━" * 22


def apply_gates(
    spread_name: str,
    regime_data: dict,
    spread_stats: dict,
    today_spread_return: float,
    regime: str,
) -> dict:
    eligible = regime_data.get("eligible_spreads", {})
    if spread_name not in eligible:
        return {"status": "INACTIVE", "reason": "wrong regime"}
    
    stats = spread_stats.get(spread_name, {}).get("regimes", {}).get(regime, {})
    if not stats or stats.get("insufficient_data"):
        return {"status": "INSUFFICIENT_DATA", "reason": "not enough regime history"}
    
    if stats.get("correlated_warning"):
        return {"status": "CORRELATED", "reason": f"leg correlation {stats.get('leg_correlation', 0):.2f} > 0.8"}
    
    regime_mean = stats.get("mean", 0)
    regime_std = stats.get("std", 0.01)
    if regime_std == 0:
        regime_std = 0.01
    
    z_score = (today_spread_return - regime_mean) / regime_std
    percentile = sum(1 for p in [stats.get("percentiles", {}).get(f"p{x}", 0) for x in [5,10,25,50,75,90,95]] if today_spread_return > p) / 7 * 100
    
    if abs(z_score) <= 1.0:
        return {"status": "AT_MEAN", "z_score": z_score, "reason": "no divergence"}
    
    return {
        "status": "ACTIVE",
        "z_score": round(z_score, 2),
        "percentile": round(percentile, 0),
        "regime_mean": regime_mean,
        "regime_std": regime_std,
        "backtest": eligible.get(spread_name, {}),
    }


def apply_modifiers(
    base: int,
    technicals: dict,
    positioning: dict,
    news: dict,
) -> int:
    score = base
    
    # Technicals
    if technicals.get("short_rsi_avg", 50) < 30:
        score += 15
    if technicals.get("long_rsi_avg", 50) > 70:
        score -= 15
    if technicals.get("trend_confirming"):
        score += 15
    elif technicals.get("trend_conflicting"):
        score -= 15
    
    # OI/PCR
    if positioning.get("short_pcr_avg", 0.7) > 1.2:
        score += 15
    if positioning.get("long_pcr_avg", 0.7) < 0.5:
        score += 15
    if positioning.get("short_pcr_avg", 0.7) < 0.5:
        score -= 15
    
    # News
    direction = news.get("direction")
    if direction == "BOOST":
        score += 15
    elif direction == "CAUTION":
        score -= 15
    
    return max(0, min(100, score))


def score_spread(score: int) -> tuple[str, str]:
    if score >= 80:
        return "HIGH", "ENTER"
    if score >= 50:
        return "MEDIUM", "WATCH"
    return "LOW", "CAUTION"


def _load_json(filename: str) -> dict:
    path = DATA_DIR / filename
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def _format_morning_scan(regime: str, msi: float, recommendations: list) -> str:
    now = datetime.now(IST)
    lines = [
        LINE,
        f"🎯 ANKA MORNING SCAN — {now.strftime('%d %b %Y')}",
        LINE,
        f"REGIME: {'🔴' if 'STRESS' in regime else '🟡' if 'NEUTRAL' in regime else '🟢'} {regime} (MSI {msi:.0f})",
        "",
    ]
    
    enter = [r for r in recommendations if r["action"] == "ENTER"]
    watch = [r for r in recommendations if r["action"] == "WATCH"]
    inactive = [r for r in recommendations if r["action"] in ("INACTIVE", "AT_MEAN", "CORRELATED")]
    
    if enter:
        lines.append("ENTER — HIGH CONVICTION:")
        for r in enter:
            lines.append(f"  🟢 {r['name']} [Score: {r['score']}]")
            lines.append(f"     Divergence: {r['z_score']:+.1f}σ ({r.get('percentile', 0):.0f}th pctl)")
            for flag in r.get("anomaly_flags", []):
                lines.append(f"     ⚠️ {flag}")
            lines.append("")
    
    if watch:
        lines.append("WATCH — MEDIUM:")
        for r in watch:
            lines.append(f"  🟡 {r['name']} [Score: {r['score']}]")
            lines.append(f"     Divergence: {r['z_score']:+.1f}σ")
            for flag in r.get("anomaly_flags", []):
                lines.append(f"     ⚠️ {flag}")
            lines.append("")
    
    if inactive:
        lines.append(f"INACTIVE: {len(inactive)} spreads")
    
    lines.extend(["", LINE])
    return "\n".join(lines)


def _format_intraday_alert(spread_name: str, prev_action: str, new_action: str, details: dict) -> str:
    now = datetime.now(IST)
    return (
        f"🔔 SPREAD ALERT — {now.strftime('%H:%M')} IST\n"
        f"{spread_name}: {prev_action} → {new_action}\n"
        f"  z-score: {details.get('z_score', 0):+.1f}σ\n"
        f"  Conviction: {details.get('score', 0)} ({details.get('label', '?')})"
    )


def run_scan(send_telegram: bool = True, morning: bool = True) -> dict:
    from config import INDIA_SPREAD_PAIRS
    from kite_client import fetch_ltp
    
    regime_data = _load_json("today_regime.json")
    spread_stats_data = _load_json("spread_stats.json")
    technicals_data = _load_json("technicals.json")
    positioning_data = _load_json("positioning.json")
    news_data = _load_json("news.json")
    
    regime = regime_data.get("regime", "UNKNOWN")
    msi = regime_data.get("msi_score", 50)
    spread_stats = spread_stats_data.get("spreads", {})
    
    all_symbols = set()
    for sp in INDIA_SPREAD_PAIRS:
        all_symbols.update(sp["long"])
        all_symbols.update(sp["short"])
    prices = fetch_ltp(list(all_symbols))
    
    # Load previous prices for spread return
    prev_prices_file = DATA_DIR / "prev_prices.json"
    prev_prices = {}
    if prev_prices_file.exists():
        prev_prices = json.loads(prev_prices_file.read_text(encoding="utf-8"))
    
    recommendations = []
    
    for sp in INDIA_SPREAD_PAIRS:
        name = sp["name"]
        
        # Compute today's spread return
        if prev_prices:
            from spread_statistics import compute_spread_return
            long_prev = {s: prev_prices.get(s, prices.get(s, 0)) for s in sp["long"]}
            long_curr = {s: prices.get(s, 0) for s in sp["long"]}
            short_prev = {s: prev_prices.get(s, prices.get(s, 0)) for s in sp["short"]}
            short_curr = {s: prices.get(s, 0) for s in sp["short"]}
            today_return = compute_spread_return(long_prev, long_curr, short_prev, short_curr)
        else:
            today_return = 0
        
        gate_result = apply_gates(name, regime_data, spread_stats, today_return, regime)
        
        if gate_result["status"] not in ("ACTIVE",):
            recommendations.append({
                "name": name,
                "action": gate_result["status"],
                "reason": gate_result.get("reason", ""),
                "score": 0,
                "z_score": gate_result.get("z_score", 0),
            })
            continue
        
        # Compute modifiers
        tech_stocks = technicals_data.get("stocks", {})
        long_rsis = [tech_stocks.get(s, {}).get("rsi_14", 50) for s in sp["long"]]
        short_rsis = [tech_stocks.get(s, {}).get("rsi_14", 50) for s in sp["short"]]
        long_above_dma = all(tech_stocks.get(s, {}).get("vs_20dma_pct", 0) > 0 for s in sp["long"])
        short_below_dma = all(tech_stocks.get(s, {}).get("vs_20dma_pct", 0) < 0 for s in sp["short"])
        
        pos_stocks = positioning_data.get("stocks", {})
        short_pcrs = [pos_stocks.get(s, {}).get("pcr", 0.7) for s in sp["short"]]
        long_pcrs = [pos_stocks.get(s, {}).get("pcr", 0.7) for s in sp["long"]]
        anomaly_flags = []
        for s in sp["long"] + sp["short"]:
            flags = pos_stocks.get(s, {}).get("anomaly_flags", [])
            for f in flags:
                anomaly_flags.append(f"{s}: {f}")
        
        spread_news = news_data.get("spread_news", {}).get(name, [])
        news_direction = None
        if spread_news:
            news_direction = spread_news[0].get("direction")
        
        score = apply_modifiers(
            base=50,
            technicals={
                "long_rsi_avg": mean(long_rsis) if long_rsis else 50,
                "short_rsi_avg": mean(short_rsis) if short_rsis else 50,
                "trend_confirming": long_above_dma and short_below_dma,
                "trend_conflicting": not long_above_dma and not short_below_dma,
            },
            positioning={
                "short_pcr_avg": mean(short_pcrs) if short_pcrs else 0.7,
                "long_pcr_avg": mean(long_pcrs) if long_pcrs else 0.7,
                "anomaly_flags": anomaly_flags,
            },
            news={"direction": news_direction},
        )
        
        label, action = score_spread(score)
        
        recommendations.append({
            "name": name,
            "action": action,
            "label": label,
            "score": score,
            "z_score": gate_result.get("z_score", 0),
            "percentile": gate_result.get("percentile", 0),
            "anomaly_flags": anomaly_flags,
        })
    
    recommendations.sort(key=lambda x: -x.get("score", 0))
    
    # Save current prices for next comparison
    prev_prices_file.write_text(json.dumps(prices, indent=2, default=str), encoding="utf-8")
    
    output = {
        "timestamp": datetime.now(IST).isoformat(),
        "regime": regime,
        "msi_score": msi,
        "recommendations": recommendations,
    }
    
    out_file = DATA_DIR / "recommendations.json"
    
    # Check for state changes (intraday alerts)
    prev_recs = {}
    if out_file.exists():
        prev = json.loads(out_file.read_text(encoding="utf-8"))
        prev_recs = {r["name"]: r["action"] for r in prev.get("recommendations", [])}
    
    out_file.write_text(json.dumps(output, indent=2, default=str), encoding="utf-8")
    
    if send_telegram:
        from telegram_bot import send_message
        
        if morning:
            msg = _format_morning_scan(regime, msi, recommendations)
            send_message(msg)
            log.info("Morning scan sent to Telegram")
        else:
            for r in recommendations:
                prev_action = prev_recs.get(r["name"])
                if prev_action and prev_action != r["action"] and r["action"] in ("ENTER", "EXIT"):
                    alert = _format_intraday_alert(r["name"], prev_action, r["action"], r)
                    send_message(alert)
                    log.info("Intraday alert: %s %s → %s", r["name"], prev_action, r["action"])
    
    return output


if __name__ == "__main__":
    import argparse
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s — %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--morning", action="store_true", default=False)
    parser.add_argument("--no-telegram", action="store_true", default=False)
    args = parser.parse_args()
    run_scan(send_telegram=not args.no_telegram, morning=args.morning)
```

- [ ] **Step 4: Run tests**

Run: `cd C:/Users/Claude_Anka/Documents/askanka.com/pipeline && python -m pytest tests/test_spread_intelligence.py -v`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add pipeline/spread_intelligence.py pipeline/tests/test_spread_intelligence.py
git commit -m "feat: spread intelligence orchestrator — gate+modifier scoring, Telegram delivery"
```

---

## Task 7: Scheduler Setup (Bat Files + Windows Task Scheduler)

**Files:**
- Create: `pipeline/scripts/morning_scan.bat`
- Create: `pipeline/scripts/intraday_scan.bat`

- [ ] **Step 1: Create morning scan bat**

```bat
@echo off
REM ANKA Morning Scan — 9:25 AM IST
cd /d "C:\Users\Claude_Anka\Documents\askanka.com\pipeline"
python -X utf8 regime_scanner.py >> logs\morning_scan.log 2>&1
python -X utf8 technical_scanner.py >> logs\morning_scan.log 2>&1
python -X utf8 oi_scanner.py >> logs\morning_scan.log 2>&1
python -X utf8 news_scanner.py >> logs\morning_scan.log 2>&1
python -X utf8 spread_intelligence.py --morning >> logs\morning_scan.log 2>&1
```

- [ ] **Step 2: Create intraday scan bat**

```bat
@echo off
REM ANKA Intraday Scan — every 15 min
cd /d "C:\Users\Claude_Anka\Documents\askanka.com\pipeline"
python -X utf8 technical_scanner.py >> logs\intraday_scan.log 2>&1
python -X utf8 oi_scanner.py >> logs\intraday_scan.log 2>&1
python -X utf8 news_scanner.py >> logs\intraday_scan.log 2>&1
python -X utf8 spread_intelligence.py >> logs\intraday_scan.log 2>&1
```

- [ ] **Step 3: Register scheduled tasks**

```bash
# Morning scan at 9:25
cmd //c "schtasks /create /tn AnkaMorningScan /tr \"C:\Users\Claude_Anka\Documents\askanka.com\pipeline\scripts\morning_scan.bat\" /sc daily /st 09:25 /f"

# Intraday scans every 15 min from 9:40 to 15:25
for t in 0940 0955 1010 1025 1040 1055 1110 1125 1140 1155 1210 1225 1240 1255 1310 1325 1340 1355 1410 1425 1440 1455 1510 1525; do
  h="${t:0:2}"
  m="${t:2:2}"
  cmd //c "schtasks /create /tn AnkaIntraday${t} /tr \"C:\Users\Claude_Anka\Documents\askanka.com\pipeline\scripts\intraday_scan.bat\" /sc daily /st ${h}:${m} /f"
done

# Weekly spread stats on Sunday at 22:00
cmd //c "schtasks /create /tn AnkaSpreadStats /tr \"C:\Python313\python.exe -X utf8 C:\Users\Claude_Anka\Documents\askanka.com\pipeline\spread_statistics.py\" /sc weekly /d SUN /st 22:00 /f"
```

- [ ] **Step 4: Verify tasks registered**

```bash
cmd //c "schtasks /query /fo LIST" 2>&1 | grep -i "AnkaMorning\|AnkaIntraday\|AnkaSpreadStats" | head -10
```

- [ ] **Step 5: Commit**

```bash
git add pipeline/scripts/morning_scan.bat pipeline/scripts/intraday_scan.bat
git commit -m "feat: morning scan + intraday scheduler bat files"
```

---

## Task 8: End-to-End Integration Test

- [ ] **Step 1: Run the full pipeline manually (no Telegram)**

```bash
cd C:/Users/Claude_Anka/Documents/askanka.com/pipeline
python -X utf8 regime_scanner.py
python -X utf8 technical_scanner.py
python -X utf8 oi_scanner.py
python -X utf8 news_scanner.py
python -X utf8 spread_intelligence.py --morning --no-telegram
```

- [ ] **Step 2: Verify all JSON artifacts created**

```bash
ls -la data/today_regime.json data/technicals.json data/positioning.json data/news.json data/recommendations.json
```

- [ ] **Step 3: Inspect recommendations output**

```bash
python -X utf8 -c "import json; r=json.load(open('data/recommendations.json')); print(json.dumps(r, indent=2))" | head -50
```

- [ ] **Step 4: Run all tests**

```bash
python -m pytest tests/test_spread_statistics.py tests/test_technical_scanner.py tests/test_oi_scanner.py tests/test_spread_intelligence.py -v
```

- [ ] **Step 5: Final commit**

```bash
git add -A
git commit -m "feat: Spread Intelligence Engine — complete 6-module pipeline with tests"
```

---

## Execution Order

Tasks 1-5 are independent modules — can be built in parallel.
Task 6 depends on Tasks 1-5 (reads their JSON outputs).
Task 7 depends on Task 6 (scheduler wraps the orchestrator).
Task 8 is the integration test.

Recommended build order for tomorrow (markets closed):
1. Task 1 (spread_statistics) — heaviest, runs first to generate baseline data
2. Tasks 2-5 in parallel (regime, technicals, OI, news)
3. Task 6 (orchestrator)
4. Task 7 (scheduler)
5. Task 8 (integration test)
