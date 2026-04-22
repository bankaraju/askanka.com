# News Impact Engine — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an evidence-based daily trade recommendation engine that combines static trust scorecards with classified daily news, backtested historical impact data, and regime filters to produce spread trade baskets with entry, stop-loss, target, holding period, and confidence levels.

**Architecture:** Three-layer pipeline. Layer 1 (Data Ingestion) pulls live stock data from indianapi.in and historical prices from EODHD into per-stock artifact directories. Layer 2 (News Classifier) uses Gemini/Haiku to classify each announcement against the stock's trust scorecard as execution-signal, pump-noise, or material-pivot. Layer 3 (Backtest + Recommendation) runs a 2×2 matrix study (good/bad scorecard × positive/negative news) on historical data to extract empirical holding periods, stop-losses, and targets, then produces daily trade baskets.

**Tech Stack:** Python 3.13, requests, EODHD API, indianapi.in API, Gemini 2.5 Flash (primary LLM), Haiku 4.5 (fallback), existing trust score artifacts, existing eodhd_client.py.

**Data sources reference:** See `memory/project_overview.md` for all API keys, endpoints, and file locations.

---

## File Structure

```
askanka.com/opus/
├── indianapi_client.py          ← NEW: indianapi.in API client (stock, news, announcements, corporate actions)
├── news_classifier.py           ← NEW: LLM-based news classification against scorecard
├── news_impact_backtest.py      ← NEW: 2×2 backtest matrix engine
├── daily_recommendation.py      ← NEW: daily basket generation with stop/target/hold
├── run_news_enrichment.py       ← NEW: CLI — pull indianapi data for all/subset of stocks
├── run_backtest.py              ← NEW: CLI — run backtest study, output empirical parameters
├── run_daily_basket.py          ← NEW: CLI — produce today's trade recommendations
└── data/
    ├── news_archive/            ← NEW: historical classified news per stock (JSON)
    ├── price_cache/             ← NEW: cached EODHD price series per stock (JSON)
    └── backtest_results.json    ← NEW: empirical parameters from 2×2 backtest
```

```
askanka.com/pipeline/
└── eodhd_client.py              ← EXISTING: reuse for historical prices (import from here)
```

---

### Task 1: indianapi.in Client

**Files:**
- Create: `opus/indianapi_client.py`
- Create: `opus/tests/test_indianapi_client.py`

- [ ] **Step 1: Write failing test for stock data fetch**

```python
# opus/tests/test_indianapi_client.py
import os
import pytest
from indianapi_client import IndianAPIClient

@pytest.fixture
def client():
    key = os.getenv("INDIANAPI_KEY")
    if not key:
        pytest.skip("INDIANAPI_KEY not set")
    return IndianAPIClient(api_key=key)

def test_fetch_stock_returns_company_name(client):
    data = client.fetch_stock("TCS")
    assert data is not None
    assert "companyName" in data
    assert data["companyName"] == "Tata Consultancy Services"

def test_fetch_stock_has_financials(client):
    data = client.fetch_stock("TCS")
    assert "financials" in data
    assert len(data["financials"]) >= 10

def test_fetch_announcements_returns_list(client):
    items = client.fetch_announcements("TCS")
    assert isinstance(items, list)
    assert len(items) > 0
    assert "title" in items[0]

def test_fetch_news_returns_list(client):
    items = client.fetch_news("TCS")
    assert isinstance(items, list)
    assert len(items) > 0
    assert "title" in items[0]
    assert "summary" in items[0]

def test_fetch_corporate_actions_has_board_meetings(client):
    data = client.fetch_corporate_actions("TCS")
    assert "board_meetings" in data

def test_fetch_stock_unknown_returns_none(client):
    data = client.fetch_stock("ZZZZNOTASTOCK")
    assert data is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd opus && python -m pytest tests/test_indianapi_client.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'indianapi_client'`

- [ ] **Step 3: Implement indianapi_client.py**

```python
# opus/indianapi_client.py
"""Client for indianapi.in Indian Stock Market API.

Base URL: https://stock.indianapi.in
Auth: X-Api-Key header
Docs: https://indianapi.in/indian-stock-market-api-documentation
"""
import logging
import os
import time
from pathlib import Path
from typing import Optional

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / "config" / ".env")
load_dotenv(Path("C:/Users/Claude_Anka/Documents/askanka.com/pipeline/.env"))

log = logging.getLogger("anka.indianapi")

BASE_URL = "https://stock.indianapi.in"
_TIMEOUT = 20


class IndianAPIClient:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("INDIANAPI_KEY")
        if not self.api_key:
            raise RuntimeError("INDIANAPI_KEY not set")
        self.session = requests.Session()
        self.session.headers["X-Api-Key"] = self.api_key

    def _get(self, path: str, params: dict = None) -> Optional[dict | list]:
        try:
            resp = self.session.get(f"{BASE_URL}{path}", params=params, timeout=_TIMEOUT)
            if resp.status_code == 404:
                return None
            if resp.status_code == 429:
                log.warning("indianapi rate limited, sleeping 30s")
                time.sleep(30)
                resp = self.session.get(f"{BASE_URL}{path}", params=params, timeout=_TIMEOUT)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            log.warning("indianapi %s failed: %s", path, e)
            return None

    def fetch_stock(self, name: str) -> Optional[dict]:
        """Full stock data: profile, financials, analyst views, shareholding, news."""
        data = self._get("/stock", params={"name": name})
        if isinstance(data, dict) and "companyName" in data:
            return data
        return None

    def fetch_announcements(self, stock_name: str) -> list[dict]:
        """Recent exchange announcements/filings."""
        data = self._get("/recent_announcements", params={"stock_name": stock_name})
        return data if isinstance(data, list) else []

    def fetch_news(self, stock_name: str) -> list[dict]:
        """Recent news articles with summaries."""
        data = self._get("/news", params={"stock": stock_name})
        return data if isinstance(data, list) else []

    def fetch_corporate_actions(self, stock_name: str) -> dict:
        """Board meetings, dividends, splits, bonus, rights."""
        data = self._get("/corporate_actions", params={"stock_name": stock_name})
        return data if isinstance(data, dict) else {}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd opus && python -m pytest tests/test_indianapi_client.py -v`
Expected: All 6 tests PASS (requires INDIANAPI_KEY in env)

- [ ] **Step 5: Commit**

```bash
cd C:/Users/Claude_Anka/opus-anka
git add indianapi_client.py tests/test_indianapi_client.py
git commit -m "feat: add indianapi.in client for stock data, news, announcements, corporate actions"
```

---

### Task 2: News Enrichment CLI — Pull indianapi Data for All Stocks

**Files:**
- Create: `opus/run_news_enrichment.py`
- Modify: `opus/indianapi_client.py` (add save_to_artifacts helper)

- [ ] **Step 1: Write failing test for enrichment**

```python
# opus/tests/test_news_enrichment.py
import json
import os
import pytest
from pathlib import Path
from indianapi_client import IndianAPIClient

@pytest.fixture
def client():
    key = os.getenv("INDIANAPI_KEY")
    if not key:
        pytest.skip("INDIANAPI_KEY not set")
    return IndianAPIClient(api_key=key)

def test_enrichment_saves_news_to_artifact(client, tmp_path):
    from run_news_enrichment import enrich_stock
    result = enrich_stock("TRENT", client, artifacts_dir=tmp_path)
    assert result["symbol"] == "TRENT"
    assert result["news_count"] > 0
    news_file = tmp_path / "TRENT" / "indianapi_news.json"
    assert news_file.exists()
    data = json.loads(news_file.read_text())
    assert len(data) > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd opus && python -m pytest tests/test_news_enrichment.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'run_news_enrichment'`

- [ ] **Step 3: Implement run_news_enrichment.py**

```python
# opus/run_news_enrichment.py
"""Pull indianapi.in data for scored stocks and save to artifacts.

Usage:
    python run_news_enrichment.py                    # all 210 stocks
    python run_news_enrichment.py TRENT LUPIN HAL    # specific stocks
    python run_news_enrichment.py --insufficient     # only INSUFFICIENT_DATA stocks
"""
import argparse
import json
import time
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from indianapi_client import IndianAPIClient

ARTIFACTS = Path(__file__).resolve().parent / "artifacts"


def enrich_stock(symbol: str, client: IndianAPIClient, artifacts_dir: Path = None) -> dict:
    out_dir = (artifacts_dir or ARTIFACTS) / symbol
    out_dir.mkdir(parents=True, exist_ok=True)

    result = {"symbol": symbol, "news_count": 0, "announcements_count": 0, "has_stock_data": False}

    stock_data = client.fetch_stock(symbol)
    if stock_data:
        result["has_stock_data"] = True
        (out_dir / "indianapi_stock.json").write_text(
            json.dumps(stock_data, indent=2, default=str), encoding="utf-8"
        )
        financials = stock_data.get("financials", [])
        result["financial_periods"] = len(financials)
        analyst = stock_data.get("analystView", [])
        result["analyst_ratings"] = len(analyst)

    news = client.fetch_news(symbol)
    if news:
        result["news_count"] = len(news)
        (out_dir / "indianapi_news.json").write_text(
            json.dumps(news, indent=2, default=str), encoding="utf-8"
        )

    announcements = client.fetch_announcements(symbol)
    if announcements:
        result["announcements_count"] = len(announcements)
        (out_dir / "indianapi_announcements.json").write_text(
            json.dumps(announcements, indent=2, default=str), encoding="utf-8"
        )

    corporate = client.fetch_corporate_actions(symbol)
    if corporate:
        (out_dir / "indianapi_corporate_actions.json").write_text(
            json.dumps(corporate, indent=2, default=str), encoding="utf-8"
        )

    return result


def load_universe(artifacts_dir: Path = None) -> list[str]:
    arts = artifacts_dir or ARTIFACTS
    return sorted(d.name for d in arts.iterdir() if d.is_dir() and (d / "trust_score.json").exists())


def load_insufficient(artifacts_dir: Path = None) -> list[str]:
    arts = artifacts_dir or ARTIFACTS
    result = []
    for d in sorted(arts.iterdir()):
        ts = d / "trust_score.json"
        if ts.exists():
            data = json.loads(ts.read_text())
            if data.get("verdict") == "INSUFFICIENT_DATA":
                result.append(d.name)
    return result


def main():
    parser = argparse.ArgumentParser(description="Pull indianapi.in data for stocks")
    parser.add_argument("symbols", nargs="*", help="Specific symbols (default: all)")
    parser.add_argument("--insufficient", action="store_true", help="Only INSUFFICIENT_DATA stocks")
    parser.add_argument("--delay", type=int, default=5, help="Seconds between API calls (default: 5)")
    args = parser.parse_args()

    client = IndianAPIClient()

    if args.symbols:
        symbols = [s.upper() for s in args.symbols]
    elif args.insufficient:
        symbols = load_insufficient()
        print(f"Found {len(symbols)} INSUFFICIENT_DATA stocks")
    else:
        symbols = load_universe()
        print(f"Found {len(symbols)} stocks in universe")

    results = []
    for i, sym in enumerate(symbols, 1):
        if i > 1:
            time.sleep(args.delay)
        print(f"[{i:3}/{len(symbols)}] {sym:14}", end=" ", flush=True)
        r = enrich_stock(sym, client)
        results.append(r)
        print(f"stock={'Y' if r['has_stock_data'] else 'N'} news={r['news_count']} ann={r['announcements_count']}")

    success = sum(1 for r in results if r["has_stock_data"])
    print(f"\nDone: {success}/{len(symbols)} enriched successfully")

    summary_path = ARTIFACTS / "news_enrichment_summary.json"
    json.dump(results, open(summary_path, "w"), indent=2)
    print(f"Summary: {summary_path}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd opus && python -m pytest tests/test_news_enrichment.py -v`
Expected: PASS

- [ ] **Step 5: Test live on 3 INSUFFICIENT_DATA stocks**

Run: `cd opus && python run_news_enrichment.py TRENT LUPIN HAVELLS`
Expected: 3 stocks enriched, `indianapi_stock.json` + `indianapi_news.json` + `indianapi_announcements.json` created in each artifact dir.

- [ ] **Step 6: Commit**

```bash
git add run_news_enrichment.py tests/test_news_enrichment.py
git commit -m "feat: add news enrichment CLI — pulls indianapi.in data to artifacts"
```

---

### Task 3: Historical Price Cache via EODHD

**Files:**
- Create: `opus/price_cache.py`
- Reuse: `pipeline/eodhd_client.py`

- [ ] **Step 1: Write failing test**

```python
# opus/tests/test_price_cache.py
import os
import pytest
from pathlib import Path

def test_fetch_and_cache_prices(tmp_path):
    if not os.getenv("EODHD_API_KEY"):
        pytest.skip("EODHD_API_KEY not set")
    from price_cache import fetch_cached_prices
    prices = fetch_cached_prices("TCS", days=60, cache_dir=tmp_path)
    assert len(prices) >= 30
    assert "date" in prices[0]
    assert "close" in prices[0]
    cache_file = tmp_path / "TCS.json"
    assert cache_file.exists()

def test_cache_hit_no_api_call(tmp_path):
    import json
    fake = [{"date": "2026-04-01", "close": 100.0, "open": 99.0, "high": 101.0, "low": 98.0, "volume": 1000}]
    (tmp_path / "FAKE.json").write_text(json.dumps(fake))
    from price_cache import fetch_cached_prices
    prices = fetch_cached_prices("FAKE", days=60, cache_dir=tmp_path)
    assert len(prices) == 1
    assert prices[0]["close"] == 100.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd opus && python -m pytest tests/test_price_cache.py -v`
Expected: FAIL

- [ ] **Step 3: Implement price_cache.py**

```python
# opus/price_cache.py
"""Cache EODHD historical price data per stock.

Checks local cache first. If stale (>1 day old) or missing, fetches from EODHD.
Stores as JSON in data/price_cache/<SYMBOL>.json.
"""
import json
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))
from eodhd_client import fetch_eod_series

CACHE_DIR = Path(__file__).resolve().parent / "data" / "price_cache"


def fetch_cached_prices(symbol: str, days: int = 180, cache_dir: Path = None) -> list[dict]:
    cache = cache_dir or CACHE_DIR
    cache.mkdir(parents=True, exist_ok=True)
    cache_file = cache / f"{symbol}.json"

    if cache_file.exists():
        age = time.time() - cache_file.stat().st_mtime
        if age < 86400:
            return json.loads(cache_file.read_text())

    eodhd_sym = f"{symbol}.NSE"
    prices = fetch_eod_series(eodhd_sym, days=days)
    if not prices:
        eodhd_sym = f"{symbol}.BSE"
        prices = fetch_eod_series(eodhd_sym, days=days)

    if prices:
        cache_file.write_text(json.dumps(prices, indent=2, default=str))

    if not prices and cache_file.exists():
        return json.loads(cache_file.read_text())

    return prices
```

- [ ] **Step 4: Run tests**

Run: `cd opus && python -m pytest tests/test_price_cache.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add price_cache.py data/ tests/test_price_cache.py
git commit -m "feat: add EODHD price cache with 1-day TTL"
```

---

### Task 4: News Classifier — LLM-Based Classification

**Files:**
- Create: `opus/news_classifier.py`
- Create: `opus/tests/test_news_classifier.py`

- [ ] **Step 1: Write failing test with known examples**

```python
# opus/tests/test_news_classifier.py
import pytest

def test_classify_execution_signal():
    from news_classifier import classify_news_item
    item = {
        "title": "TCS wins $2B cloud deal in Europe",
        "summary": "Tata Consultancy Services signed a multi-year cloud transformation deal worth $2 billion with a major European bank."
    }
    scorecard_context = "Management guided: expand cloud services in Europe. Trust grade: A."
    result = classify_news_item(item, scorecard_context, provider="mock")
    assert result["classification"] in ["execution_signal", "pump_noise", "material_pivot", "neutral"]
    assert "confidence" in result
    assert "reasoning" in result

def test_classify_pump_noise():
    from news_classifier import classify_news_item
    item = {
        "title": "Company X exploring synergies",
        "summary": "Company X is exploring potential synergies in emerging markets."
    }
    scorecard_context = "Management has history of vague promises. Trust grade: F."
    result = classify_news_item(item, scorecard_context, provider="mock")
    assert result["classification"] in ["execution_signal", "pump_noise", "material_pivot", "neutral"]

def test_classify_batch():
    from news_classifier import classify_news_batch
    items = [
        {"title": "Q4 results beat estimates", "summary": "Revenue up 20%"},
        {"title": "Board approves dividend", "summary": "Rs 5 per share"},
    ]
    results = classify_news_batch(items, "Trust grade: B. Guided 15% growth.", provider="mock")
    assert len(results) == 2
    assert all("classification" in r for r in results)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd opus && python -m pytest tests/test_news_classifier.py -v`
Expected: FAIL

- [ ] **Step 3: Implement news_classifier.py**

```python
# opus/news_classifier.py
"""Classify news items against a stock's trust scorecard.

Classifications:
  - execution_signal: confirms or contradicts a specific guidance item
  - pump_noise: vague PR, no substance, management staying visible
  - material_pivot: changes the thesis (executive exit, regulatory action, M&A)
  - neutral: routine filing, no impact on scorecard

Uses Gemini 2.5 Flash (primary) or Haiku 4.5 (fallback).
"""
import json
import os
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_trust_score import call_llm

CLASSIFICATION_PROMPT = """You are a financial news classifier for OPUS ANKA Research.

Given a news item and a stock's trust scorecard context, classify the news into exactly one category:

1. **execution_signal** — confirms or contradicts a SPECIFIC guidance item or financial target. Must reference concrete numbers, deals, or operational milestones.
2. **pump_noise** — vague PR, management staying in public eye, analyst speculation, no verifiable substance. Common with low-trust management.
3. **material_pivot** — fundamentally changes the investment thesis: key executive departure, regulatory action, M&A, rights issue, debt restructuring.
4. **neutral** — routine compliance filing, AGM notice, record date, no impact on scoring.

## SCORECARD CONTEXT:
{scorecard_context}

## NEWS ITEM:
Title: {title}
Summary: {summary}

## RESPOND IN JSON:
{{"classification": "one_of_four_categories", "confidence": 0.0_to_1.0, "reasoning": "one_sentence_why", "impacts_guidance": "which_guidance_item_if_any"}}
"""


def classify_news_item(item: dict, scorecard_context: str, provider: str = "gemini") -> dict:
    if provider == "mock":
        return {"classification": "neutral", "confidence": 0.5, "reasoning": "mock", "impacts_guidance": None}

    prompt = CLASSIFICATION_PROMPT.format(
        scorecard_context=scorecard_context,
        title=item.get("title", ""),
        summary=item.get("summary", ""),
    )
    raw = call_llm(prompt, max_tokens=512, role="scoring")

    try:
        start = raw.index("{")
        end = raw.rindex("}") + 1
        return json.loads(raw[start:end])
    except (ValueError, json.JSONDecodeError):
        return {"classification": "neutral", "confidence": 0.0, "reasoning": "parse_error", "impacts_guidance": None}


def classify_news_batch(items: list[dict], scorecard_context: str, provider: str = "gemini") -> list[dict]:
    return [classify_news_item(item, scorecard_context, provider) for item in items]


def build_scorecard_context(symbol: str, artifacts_dir: Path = None) -> str:
    arts = (artifacts_dir or Path(__file__).resolve().parent / "artifacts") / symbol
    parts = [f"Symbol: {symbol}"]

    ts = arts / "trust_score.json"
    if ts.exists():
        data = json.loads(ts.read_text())
        parts.append(f"Trust Grade: {data.get('trust_score_grade', '?')}")
        parts.append(f"Verdict: {data.get('verdict', '?')}")
        parts.append(f"Score: {data.get('trust_score_pct', '?')}")

    gs = arts / "guidance_scorecard.json"
    if gs.exists():
        data = json.loads(gs.read_text())
        items = data if isinstance(data, list) else data.get("items", [])
        for g in items[:10]:
            if isinstance(g, dict):
                parts.append(f"Guidance: {g.get('category','')} — {g.get('claim','')[:100]} → {g.get('status','?')}")

    return "\n".join(parts)
```

- [ ] **Step 4: Run tests**

Run: `cd opus && python -m pytest tests/test_news_classifier.py -v`
Expected: PASS (mock provider tests pass without API calls)

- [ ] **Step 5: Test live on one stock**

```bash
cd opus && python -c "
from news_classifier import classify_news_item, build_scorecard_context
import json
ctx = build_scorecard_context('MARUTI')
item = {'title': 'Maruti Q4 sales up 15%', 'summary': 'Maruti Suzuki reported 15% growth in Q4 domestic sales.'}
r = classify_news_item(item, ctx)
print(json.dumps(r, indent=2))
"
```
Expected: JSON with classification, confidence, reasoning

- [ ] **Step 6: Commit**

```bash
git add news_classifier.py tests/test_news_classifier.py
git commit -m "feat: add LLM-based news classifier against trust scorecards"
```

---

### Task 5: Backtest Engine — 2×2 Impact Matrix

**Files:**
- Create: `opus/news_impact_backtest.py`
- Create: `opus/run_backtest.py`
- Create: `opus/tests/test_backtest.py`

- [ ] **Step 1: Write failing test**

```python
# opus/tests/test_backtest.py
import pytest
from news_impact_backtest import compute_forward_returns, build_impact_matrix

def test_compute_forward_returns():
    prices = [
        {"date": "2026-01-01", "close": 100.0},
        {"date": "2026-01-02", "close": 102.0},
        {"date": "2026-01-03", "close": 101.0},
        {"date": "2026-01-06", "close": 104.0},
        {"date": "2026-01-07", "close": 103.0},
        {"date": "2026-01-08", "close": 105.0},
    ]
    returns = compute_forward_returns(prices, event_idx=0, windows=[1, 3, 5])
    assert returns[1] == pytest.approx(2.0, abs=0.1)
    assert returns[3] == pytest.approx(4.0, abs=0.1)
    assert returns[5] == pytest.approx(5.0, abs=0.1)

def test_compute_max_adverse_excursion():
    from news_impact_backtest import compute_max_adverse_excursion
    prices = [
        {"date": "2026-01-01", "close": 100.0},
        {"date": "2026-01-02", "close": 97.0},
        {"date": "2026-01-03", "close": 95.0},
        {"date": "2026-01-06", "close": 99.0},
        {"date": "2026-01-07", "close": 103.0},
    ]
    mae = compute_max_adverse_excursion(prices, event_idx=0, window=4)
    assert mae == pytest.approx(-5.0, abs=0.1)

def test_build_impact_matrix_structure():
    events = [
        {"symbol": "A", "grade": "A", "news_class": "execution_signal", "forward_returns": {1: 1.5, 5: 3.0, 20: 5.0}, "mae": -1.0, "mfe": 6.0},
        {"symbol": "B", "grade": "F", "news_class": "execution_signal", "forward_returns": {1: 0.5, 5: -1.0, 20: -2.0}, "mae": -3.0, "mfe": 1.0},
    ]
    matrix = build_impact_matrix(events)
    assert "good_positive" in matrix
    assert "bad_positive" in matrix
    assert matrix["good_positive"]["count"] == 1
    assert matrix["bad_positive"]["count"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd opus && python -m pytest tests/test_backtest.py -v`
Expected: FAIL

- [ ] **Step 3: Implement news_impact_backtest.py**

```python
# opus/news_impact_backtest.py
"""2×2 backtest matrix: scorecard quality × news sentiment → forward returns.

For each (scorecard_grade, news_classification) cell, computes:
  - median forward return at day +1, +3, +5, +10, +20, +30
  - max adverse excursion (worst drawdown = stop-loss calibration)
  - max favorable excursion (best profit = target calibration)
  - optimal holding period
  - sample count (confidence)
"""
import json
import statistics
from pathlib import Path
from typing import Optional

WINDOWS = [1, 3, 5, 10, 20, 30]


def compute_forward_returns(prices: list[dict], event_idx: int, windows: list[int] = None) -> dict[int, float]:
    windows = windows or WINDOWS
    base_price = prices[event_idx]["close"]
    returns = {}
    for w in windows:
        target_idx = event_idx + w
        if target_idx < len(prices):
            returns[w] = ((prices[target_idx]["close"] - base_price) / base_price) * 100
    return returns


def compute_max_adverse_excursion(prices: list[dict], event_idx: int, window: int = 20) -> float:
    base = prices[event_idx]["close"]
    worst = 0.0
    for i in range(event_idx + 1, min(event_idx + window + 1, len(prices))):
        pct = ((prices[i]["close"] - base) / base) * 100
        if pct < worst:
            worst = pct
    return worst


def compute_max_favorable_excursion(prices: list[dict], event_idx: int, window: int = 20) -> float:
    base = prices[event_idx]["close"]
    best = 0.0
    for i in range(event_idx + 1, min(event_idx + window + 1, len(prices))):
        pct = ((prices[i]["close"] - base) / base) * 100
        if pct > best:
            best = pct
    return best


def grade_bucket(grade: str) -> str:
    if grade in ("A+", "A", "B+", "B"):
        return "good"
    return "bad"


def news_bucket(classification: str) -> str:
    if classification in ("execution_signal",):
        return "positive"
    if classification in ("material_pivot",):
        return "negative"
    return "neutral"


def build_impact_matrix(events: list[dict]) -> dict:
    cells = {
        "good_positive": [], "good_negative": [], "good_neutral": [],
        "bad_positive": [], "bad_negative": [], "bad_neutral": [],
    }
    for e in events:
        gb = grade_bucket(e["grade"])
        nb = news_bucket(e["news_class"])
        key = f"{gb}_{nb}"
        if key in cells:
            cells[key].append(e)

    matrix = {}
    for key, items in cells.items():
        if not items:
            matrix[key] = {"count": 0}
            continue
        matrix[key] = {
            "count": len(items),
            "median_returns": {},
            "median_mae": statistics.median(e["mae"] for e in items),
            "median_mfe": statistics.median(e["mfe"] for e in items),
        }
        for w in WINDOWS:
            vals = [e["forward_returns"][w] for e in items if w in e["forward_returns"]]
            if vals:
                matrix[key]["median_returns"][w] = round(statistics.median(vals), 2)

    return matrix
```

- [ ] **Step 4: Run tests**

Run: `cd opus && python -m pytest tests/test_backtest.py -v`
Expected: PASS

- [ ] **Step 5: Implement run_backtest.py CLI**

```python
# opus/run_backtest.py
"""Run the 2×2 backtest across all scored stocks with historical news.

Usage: python run_backtest.py [--days 180]
Requires: indianapi data + EODHD price cache already populated.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from news_impact_backtest import (
    compute_forward_returns, compute_max_adverse_excursion,
    compute_max_favorable_excursion, build_impact_matrix, WINDOWS,
    grade_bucket, news_bucket,
)
from price_cache import fetch_cached_prices
from news_classifier import classify_news_batch, build_scorecard_context

ARTIFACTS = Path(__file__).resolve().parent / "artifacts"


def find_price_index(prices: list[dict], target_date: str) -> int:
    for i, p in enumerate(prices):
        if p["date"] >= target_date:
            return i
    return -1


def run_backtest(days: int = 180):
    all_events = []

    for sym_dir in sorted(ARTIFACTS.iterdir()):
        if not sym_dir.is_dir():
            continue
        ts_file = sym_dir / "trust_score.json"
        news_file = sym_dir / "indianapi_news.json"
        if not ts_file.exists() or not news_file.exists():
            continue

        ts = json.loads(ts_file.read_text())
        grade = ts.get("trust_score_grade", "?")
        if grade == "?":
            continue

        news = json.loads(news_file.read_text())
        if not news:
            continue

        prices = fetch_cached_prices(sym_dir.name, days=days)
        if len(prices) < 30:
            continue

        ctx = build_scorecard_context(sym_dir.name)
        classified = classify_news_batch(news, ctx)

        for item, cls in zip(news, classified):
            pub_date = item.get("pub_date", item.get("date", ""))[:10]
            if not pub_date:
                continue
            idx = find_price_index(prices, pub_date)
            if idx < 0 or idx >= len(prices) - 5:
                continue

            fwd = compute_forward_returns(prices, idx)
            mae = compute_max_adverse_excursion(prices, idx)
            mfe = compute_max_favorable_excursion(prices, idx)

            all_events.append({
                "symbol": sym_dir.name,
                "date": pub_date,
                "grade": grade,
                "news_class": cls["classification"],
                "title": item.get("title", "")[:100],
                "forward_returns": fwd,
                "mae": mae,
                "mfe": mfe,
            })

    print(f"Total events collected: {len(all_events)}")
    matrix = build_impact_matrix(all_events)

    output = {
        "total_events": len(all_events),
        "matrix": matrix,
        "events": all_events,
    }
    out_path = ARTIFACTS / "backtest_results.json"
    json.dump(output, open(out_path, "w"), indent=2, default=str)
    print(f"Results saved to {out_path}")

    print("\n2×2 IMPACT MATRIX:")
    for key, cell in matrix.items():
        if cell["count"] == 0:
            continue
        print(f"\n  {key} (n={cell['count']}):")
        print(f"    Median MAE: {cell['median_mae']:.2f}%  (stop-loss)")
        print(f"    Median MFE: {cell['median_mfe']:.2f}%  (target)")
        for w, ret in cell.get("median_returns", {}).items():
            print(f"    Day +{w}: {ret:+.2f}%")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=180, help="Price history days")
    args = parser.parse_args()
    run_backtest(args.days)


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Commit**

```bash
git add news_impact_backtest.py run_backtest.py tests/test_backtest.py
git commit -m "feat: add 2×2 news impact backtest engine with forward returns + MAE/MFE"
```

---

### Task 6: Daily Recommendation Engine

**Files:**
- Create: `opus/daily_recommendation.py`
- Create: `opus/run_daily_basket.py`

- [ ] **Step 1: Write failing test**

```python
# opus/tests/test_daily_recommendation.py
import pytest
from daily_recommendation import generate_recommendation

def test_good_scorecard_positive_news():
    rec = generate_recommendation(
        symbol="TCS", grade="A", current_price=3500.0,
        news_class="execution_signal",
        backtest_cell={"median_returns": {20: 4.2}, "median_mae": -1.8, "median_mfe": 6.0, "count": 47},
    )
    assert rec["direction"] == "LONG"
    assert rec["stop_loss"] < rec["entry"]
    assert rec["target"] > rec["entry"]
    assert rec["hold_days"] == 20
    assert rec["confidence"] == "HIGH"

def test_bad_scorecard_positive_news():
    rec = generate_recommendation(
        symbol="WEAK", grade="F", current_price=500.0,
        news_class="execution_signal",
        backtest_cell={"median_returns": {20: -2.1}, "median_mae": -4.0, "median_mfe": 1.0, "count": 31},
    )
    assert rec["direction"] == "AVOID"
    assert "noise" in rec["reasoning"].lower() or "trap" in rec["reasoning"].lower() or "avoid" in rec["reasoning"].lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd opus && python -m pytest tests/test_daily_recommendation.py -v`
Expected: FAIL

- [ ] **Step 3: Implement daily_recommendation.py**

```python
# opus/daily_recommendation.py
"""Generate trade recommendations from scorecard + classified news + backtest data."""
import json
from pathlib import Path

ARTIFACTS = Path(__file__).resolve().parent / "artifacts"


def load_backtest_matrix() -> dict:
    path = ARTIFACTS / "backtest_results.json"
    if path.exists():
        return json.loads(path.read_text()).get("matrix", {})
    return {}


def generate_recommendation(
    symbol: str,
    grade: str,
    current_price: float,
    news_class: str,
    backtest_cell: dict,
) -> dict:
    count = backtest_cell.get("count", 0)
    median_returns = backtest_cell.get("median_returns", {})
    mae = backtest_cell.get("median_mae", -2.0)
    mfe = backtest_cell.get("median_mfe", 2.0)

    best_window = max(median_returns.items(), key=lambda x: abs(x[1]), default=(20, 0.0))
    hold_days = best_window[0]
    expected_return = best_window[1]

    confidence = "HIGH" if count >= 30 else "MEDIUM" if count >= 10 else "LOW"

    good_grade = grade in ("A+", "A", "B+", "B")
    positive_news = news_class == "execution_signal"
    negative_news = news_class == "material_pivot"

    if good_grade and positive_news:
        direction = "LONG"
        reasoning = f"Strong scorecard ({grade}) confirmed by execution signal. Historical: {expected_return:+.1f}% in {hold_days}d (n={count})."
    elif good_grade and negative_news:
        direction = "REDUCE"
        reasoning = f"Strong scorecard ({grade}) but material pivot detected. Watch next quarter. MAE: {mae:.1f}%."
    elif not good_grade and positive_news:
        direction = "AVOID"
        reasoning = f"Weak scorecard ({grade}) with positive news — likely noise or pump. Historical fades: {expected_return:+.1f}% in {hold_days}d."
    elif not good_grade and negative_news:
        direction = "SHORT"
        reasoning = f"Weak scorecard ({grade}) + material negative. Historical: {expected_return:+.1f}% in {hold_days}d."
    else:
        direction = "HOLD" if good_grade else "AVOID"
        reasoning = f"Neutral news, {'strong' if good_grade else 'weak'} scorecard ({grade}). No trade signal."

    stop_loss = round(current_price * (1 + mae / 100), 2)
    target = round(current_price * (1 + mfe / 100), 2)

    return {
        "symbol": symbol,
        "direction": direction,
        "entry": current_price,
        "stop_loss": stop_loss,
        "target": target,
        "hold_days": hold_days,
        "confidence": confidence,
        "grade": grade,
        "news_class": news_class,
        "expected_return_pct": round(expected_return, 2),
        "sample_count": count,
        "reasoning": reasoning,
    }
```

- [ ] **Step 4: Run tests**

Run: `cd opus && python -m pytest tests/test_daily_recommendation.py -v`
Expected: PASS

- [ ] **Step 5: Implement run_daily_basket.py CLI**

```python
# opus/run_daily_basket.py
"""Generate today's trade basket based on scorecards + latest news.

Usage: python run_daily_basket.py [--top 10]
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from indianapi_client import IndianAPIClient
from news_classifier import classify_news_batch, build_scorecard_context
from daily_recommendation import generate_recommendation, load_backtest_matrix
from news_impact_backtest import grade_bucket, news_bucket

ARTIFACTS = Path(__file__).resolve().parent / "artifacts"


def main():
    parser = argparse.ArgumentParser(description="Generate daily trade basket")
    parser.add_argument("--top", type=int, default=10, help="Max recommendations")
    args = parser.parse_args()

    matrix = load_backtest_matrix()
    client = IndianAPIClient()
    recommendations = []

    for sym_dir in sorted(ARTIFACTS.iterdir()):
        if not sym_dir.is_dir():
            continue
        ts_file = sym_dir / "trust_score.json"
        if not ts_file.exists():
            continue
        ts = json.loads(ts_file.read_text())
        grade = ts.get("trust_score_grade")
        if not grade or grade == "?":
            continue

        symbol = sym_dir.name
        news = client.fetch_news(symbol)
        if not news:
            continue

        ctx = build_scorecard_context(symbol)
        classified = classify_news_batch(news[:5], ctx)

        actionable = [c for c in classified if c["classification"] in ("execution_signal", "material_pivot")]
        if not actionable:
            continue

        best_cls = actionable[0]
        gb = grade_bucket(grade)
        nb = news_bucket(best_cls["classification"])
        cell_key = f"{gb}_{nb}"
        cell = matrix.get(cell_key, {"count": 0, "median_returns": {20: 0}, "median_mae": -2, "median_mfe": 2})

        stock_data = client.fetch_stock(symbol)
        if not stock_data:
            continue
        price_data = stock_data.get("currentPrice", {})
        price = float(price_data.get("NSE", price_data.get("BSE", 0)))
        if price <= 0:
            continue

        rec = generate_recommendation(symbol, grade, price, best_cls["classification"], cell)
        if rec["direction"] in ("LONG", "SHORT"):
            recommendations.append(rec)

    recommendations.sort(key=lambda r: abs(r["expected_return_pct"]), reverse=True)
    recommendations = recommendations[:args.top]

    print(f"\n{'='*70}")
    print(f"ANKA DAILY BASKET — {len(recommendations)} TRADES")
    print(f"{'='*70}\n")
    for r in recommendations:
        print(f"{r['direction']:6} {r['symbol']:14} @ {r['entry']:>10,.2f}")
        print(f"       Stop: {r['stop_loss']:>10,.2f}  Target: {r['target']:>10,.2f}  Hold: {r['hold_days']}d")
        print(f"       Grade: {r['grade']}  News: {r['news_class']}  Confidence: {r['confidence']} (n={r['sample_count']})")
        print(f"       {r['reasoning']}")
        print()

    out_path = ARTIFACTS / "daily_basket.json"
    json.dump(recommendations, open(out_path, "w"), indent=2, default=str)
    print(f"Saved to {out_path}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Commit**

```bash
git add daily_recommendation.py run_daily_basket.py tests/test_daily_recommendation.py
git commit -m "feat: add daily trade basket generator with stop/target/hold from backtest data"
```

---

### Task 7: Integration Test — End-to-End on 5 Stocks

**Files:**
- No new files — validates the full pipeline

- [ ] **Step 1: Pull indianapi data for 5 scored stocks**

```bash
cd opus && python run_news_enrichment.py MARUTI RELIANCE HDFCAMC NMDC TRENT
```
Expected: 5 stocks enriched with indianapi_stock.json, indianapi_news.json, indianapi_announcements.json

- [ ] **Step 2: Populate price cache**

```bash
cd opus && python -c "
from price_cache import fetch_cached_prices
for sym in ['MARUTI', 'RELIANCE', 'HDFCAMC', 'NMDC', 'TRENT']:
    prices = fetch_cached_prices(sym, days=180)
    print(f'{sym}: {len(prices)} price points')
"
```
Expected: 100+ price points per stock

- [ ] **Step 3: Run backtest on the 5 stocks**

```bash
cd opus && python run_backtest.py --days 180
```
Expected: 2×2 matrix with at least some non-zero cells

- [ ] **Step 4: Run daily basket**

```bash
cd opus && python run_daily_basket.py --top 5
```
Expected: Trade recommendations with entry, stop, target, hold, confidence

- [ ] **Step 5: Validate output quality**

Check that:
- Good scorecard + positive news → LONG recommendation
- Bad scorecard + positive news → AVOID (not LONG)
- Stop-losses are derived from backtest MAE, not arbitrary
- Reasoning references the specific news and scorecard

- [ ] **Step 6: Final commit**

```bash
git add -u
git commit -m "test: validate end-to-end news impact engine on 5 stocks"
```

---

## Execution Notes

- **API rate limits:** indianapi.in rate limits unknown — start with 5s delay between calls. EODHD allows 100K/day.
- **LLM cost:** News classification uses Gemini (free) or Haiku ($0.25/stock). 57 stocks × 20 news × 1 call = ~1,140 LLM calls for full backtest. Budget ~$5 on Haiku if Gemini fails.
- **Order matters:** Tasks 1-3 are data plumbing (no LLM). Task 4 introduces LLM classification. Task 5-6 use classification output. Task 7 validates everything end-to-end.
- **Incremental delivery:** After Task 2, you can already pull data for all 153 INSUFFICIENT_DATA stocks. After Task 4, you have classified news. After Task 6, you have daily trade baskets.
