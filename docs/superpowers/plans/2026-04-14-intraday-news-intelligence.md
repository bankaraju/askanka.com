# Intraday News Intelligence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stock-specific intraday news alerts with overnight backtest verdicts — two-phase intelligence layer on top of the existing spread intelligence engine.

**Architecture:** Extend `news_scanner.py` with BSE filings + stock name matching + F&O universe scanning. New `news_alerter.py` handles Telegram delivery. New `news_backtest.py` runs overnight pattern analysis on collected events. All wired into existing `intraday_scan.bat` and a new `overnight_news.bat`.

**Tech Stack:** Python 3.13, feedparser, requests, yfinance (for price context), existing telegram_bot.py, existing pattern_engine.py

---

### File Structure

```
pipeline/
  news_intelligence.py      ← NEW: main scanner (BSE + IndianAPI + Google News, name-match + policy-map)
  news_alerter.py            ← NEW: Telegram alert formatter + sender
  news_backtest.py           ← NEW: overnight pattern analysis on collected events
  data/
    news_events_today.json   ← NEW: today's classified events (overwritten daily)
    news_events_history.json ← NEW: append-only log (all events + outcomes)
  scripts/
    overnight_news.bat       ← NEW: runs news_backtest.py at 04:30
```

Existing files modified:
- `pipeline/scripts/intraday_scan.bat` — add `news_intelligence.py` call
- `pipeline/scripts/morning_scan.bat` — add full-universe news scan
- `pipeline/config.py` — add `FNO_TOP_40` list + `NEWS_CATEGORIES` dict

---

### Task 1: Add FNO_TOP_40 and NEWS_CATEGORIES to config.py

**Files:**
- Modify: `pipeline/config.py`

- [ ] **Step 1: Add FNO_TOP_40 list to config.py**

Add after the existing `INDIA_SPREAD_PAIRS` block:

```python
# Top 40 F&O stocks by liquidity — scanned every 15 min for news
FNO_TOP_40 = [
    "RELIANCE", "HDFCBANK", "ICICIBANK", "INFY", "TCS",
    "BHARTIARTL", "SBIN", "BAJFINANCE", "AXISBANK", "KOTAKBANK",
    "LT", "MARUTI", "HCLTECH", "SUNPHARMA", "TITAN",
    "ADANIENT", "ADANIPORTS", "TATASTEEL", "HINDUNILVR", "ITC",
    "WIPRO", "CIPLA", "COALINDIA", "HAL", "BEL",
    "NTPC", "ONGC", "GAIL", "BPCL", "M&M",
    "ASIANPAINT", "TECHM", "DLF", "VEDL", "INDIGO",
    "DRREDDY", "JSWSTEEL", "TATAPOWER", "PNB", "HDFC",
]

# Full F&O universe path
FNO_UNIVERSE_FILE = Path(__file__).parent.parent / "opus" / "config" / "fno_stocks.json"

# News categories for stock-level classification
NEWS_CATEGORIES = {
    "merger_acquisition": {
        "keywords": ["acquire", "acquisition", "merger", "takeover", "buyout", "amalgamation", "demerger"],
        "impact": "HIGH",
        "default_shelf_life_days": 5,
    },
    "results_announcement": {
        "keywords": ["quarterly result", "Q1 result", "Q2 result", "Q3 result", "Q4 result",
                     "profit rises", "profit falls", "net profit", "revenue growth", "PAT"],
        "impact": "HIGH",
        "default_shelf_life_days": 3,
    },
    "block_deal": {
        "keywords": ["block deal", "bulk deal", "stake sale", "promoter sell", "FII buying"],
        "impact": "MEDIUM",
        "default_shelf_life_days": 2,
    },
    "rating_action": {
        "keywords": ["upgrade", "downgrade", "target price", "price target", "initiating coverage",
                     "outperform", "underperform", "overweight", "underweight"],
        "impact": "MEDIUM",
        "default_shelf_life_days": 3,
    },
    "fraud_investigation": {
        "keywords": ["fraud", "SEBI penalty", "investigation", "insider trading", "manipulation",
                     "default", "NPA", "scam", "irregularities"],
        "impact": "HIGH",
        "default_shelf_life_days": 5,
    },
    "govt_policy": {
        "keywords": ["RBI", "repo rate", "rate cut", "rate hike", "monetary policy",
                     "GST", "fiscal", "budget", "subsidy", "tariff", "import duty",
                     "FAME", "EV policy", "PLI scheme", "disinvestment"],
        "impact": "HIGH",
        "default_shelf_life_days": 5,
    },
    "sector_regulation": {
        "keywords": ["SEBI regulation", "TRAI", "FSSAI", "drug pricing", "DPCO",
                     "mining policy", "coal auction", "spectrum auction", "licence"],
        "impact": "HIGH",
        "default_shelf_life_days": 5,
    },
    "management_change": {
        "keywords": ["CEO appoint", "MD appoint", "CFO resign", "board member",
                     "promoter", "succession", "chairman"],
        "impact": "MEDIUM",
        "default_shelf_life_days": 2,
    },
    "capex_expansion": {
        "keywords": ["capex", "expansion", "new plant", "capacity addition", "greenfield",
                     "brownfield", "order win", "contract win", "order book"],
        "impact": "MEDIUM",
        "default_shelf_life_days": 3,
    },
}
```

- [ ] **Step 2: Verify config imports cleanly**

Run: `cd C:/Users/Claude_Anka/askanka.com/pipeline && python -c "from config import FNO_TOP_40, NEWS_CATEGORIES, FNO_UNIVERSE_FILE; print(f'Top40: {len(FNO_TOP_40)}, Categories: {len(NEWS_CATEGORIES)}, FNO file: {FNO_UNIVERSE_FILE.exists()}')"`

Expected: `Top40: 40, Categories: 9, FNO file: True`

- [ ] **Step 3: Commit**

```bash
git add pipeline/config.py
git commit -m "feat: add FNO_TOP_40, NEWS_CATEGORIES, FNO_UNIVERSE_FILE to config"
```

---

### Task 2: Build news_intelligence.py — the unified scanner

**Files:**
- Create: `pipeline/news_intelligence.py`

This replaces the news-scanning role of `news_scanner.py` for intraday use. It adds:
- BSE corporate announcements RSS feed
- Stock name matching against F&O universe
- Two-tier classification (name-match HIGH, policy-map MEDIUM)
- Dynamic scanning (top 40 or full 213)
- Junk filtering
- Output to `data/news_events_today.json`

- [ ] **Step 1: Create news_intelligence.py**

```python
"""
Anka Research — Intraday News Intelligence Scanner
Three-source scanner (BSE filings, IndianAPI, Google News RSS) with
two-tier stock identification (name-match HIGH, policy-map MEDIUM).

Usage:
    python news_intelligence.py                  # top 40 scan (15-min cycle)
    python news_intelligence.py --full           # full 213 scan (morning + mid-session)
    python news_intelligence.py --no-telegram    # skip alerts
"""

import argparse
import json
import logging
import os
import re
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

_HERE = Path(__file__).parent
sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(_HERE / "lib"))

import requests
import feedparser
from dotenv import load_dotenv
load_dotenv(_HERE / ".env")

from config import (
    FNO_TOP_40, NEWS_CATEGORIES, FNO_UNIVERSE_FILE,
    INDIA_SPREAD_PAIRS, POLICY_KEYWORDS,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("anka.news_intelligence")

IST = timezone(timedelta(hours=5, minutes=30))
DATA_DIR = _HERE / "data"
EVENTS_TODAY = DATA_DIR / "news_events_today.json"
EVENTS_HISTORY = DATA_DIR / "news_events_history.json"

# BSE corporate announcements RSS
BSE_RSS = "https://www.bseindia.com/xml-data/corpfiling/rss_corp.xml"

# Existing RSS feeds (market news)
MARKET_RSS = [
    ("MoneyControl", "https://www.moneycontrol.com/rss/latestnews.xml"),
    ("EconomicTimes", "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms"),
    ("LiveMint", "https://www.livemint.com/rss/markets"),
]

# Junk headline patterns to skip
JUNK_PATTERNS = [
    r"market outlook", r"expert view", r"technical analysis",
    r"stock picks", r"top .* stocks", r"sensex.*nifty.*points",
    r"share price today", r"live updates", r"market wrap",
]
_JUNK_RE = re.compile("|".join(JUNK_PATTERNS), re.IGNORECASE)


def load_fno_universe() -> list[str]:
    """Load full 213 F&O stock list."""
    if FNO_UNIVERSE_FILE.exists():
        data = json.loads(FNO_UNIVERSE_FILE.read_text(encoding="utf-8"))
        return data.get("symbols", [])
    return FNO_TOP_40


def _is_junk(title: str) -> bool:
    """Filter junk headlines."""
    if len(title) < 30:
        return True
    if _JUNK_RE.search(title):
        return True
    return False


def _name_match_stocks(title: str, universe: list[str]) -> list[str]:
    """Tier 1: Find F&O stock names/tickers mentioned in headline."""
    title_upper = title.upper()
    matched = []
    for symbol in universe:
        # Match exact ticker (word boundary)
        if re.search(r'\b' + re.escape(symbol) + r'\b', title_upper):
            matched.append(symbol)
    return matched


def _policy_match(title: str) -> list[dict]:
    """Tier 2: Match against NEWS_CATEGORIES + existing POLICY_KEYWORDS."""
    title_lower = title.lower()
    matches = []

    # New NEWS_CATEGORIES
    for category, cfg in NEWS_CATEGORIES.items():
        for kw in cfg["keywords"]:
            if kw.lower() in title_lower:
                matches.append({
                    "category": category,
                    "keyword": kw,
                    "impact": cfg["impact"],
                    "shelf_life_days": cfg["default_shelf_life_days"],
                })
                break

    # Existing POLICY_KEYWORDS (spread-mapped)
    for category, cfg in POLICY_KEYWORDS.items():
        for kw in cfg["keywords"]:
            if kw.lower() in title_lower:
                matches.append({
                    "category": category,
                    "keyword": kw,
                    "impact": "MEDIUM",
                    "shelf_life_days": 3,
                    "affected_spreads": cfg["spreads"],
                    "direction": cfg["default_direction"],
                })
                break

    return matches


# ── Source 1: BSE Corporate Filings ──

def fetch_bse_filings() -> list[dict]:
    """Fetch BSE corporate announcements RSS."""
    items = []
    try:
        resp = requests.get(BSE_RSS, timeout=10, headers={
            "User-Agent": "Mozilla/5.0 (AnkaResearch/1.0)"
        })
        resp.raise_for_status()
        feed = feedparser.parse(resp.text)
        for entry in feed.entries[:30]:
            title = getattr(entry, "title", "").strip()
            link = getattr(entry, "link", "").strip()
            published = getattr(entry, "published", "") or getattr(entry, "updated", "")
            if title and not _is_junk(title):
                items.append({
                    "title": title,
                    "url": link,
                    "source": "BSE Filing",
                    "published": published,
                    "tier": "bse",
                })
        log.info(f"BSE filings: {len(items)} items")
    except Exception as exc:
        log.warning(f"BSE RSS failed: {exc}")
    return items


# ── Source 2: IndianAPI ──

def fetch_indianapi_news(symbols: list[str]) -> list[dict]:
    """Fetch stock announcements from indianapi.in."""
    api_key = os.getenv("INDIANAPI_KEY", "").strip()
    if not api_key:
        log.warning("INDIANAPI_KEY not set — skipping")
        return []

    items = []
    for symbol in symbols[:15]:  # rate limit
        try:
            resp = requests.get(
                "https://stock.indianapi.in/recent_announcements",
                params={"stock_name": symbol},
                headers={"X-Api-Key": api_key},
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            entries = data if isinstance(data, list) else data.get("announcements", data.get("data", []))
            for item in entries[:3]:
                title = (item.get("headline") or item.get("title") or item.get("subject") or "")
                if title and not _is_junk(title):
                    items.append({
                        "title": title.strip(),
                        "url": item.get("link", ""),
                        "source": "IndianAPI",
                        "published": item.get("date", ""),
                        "tier": "indianapi",
                        "symbol_hint": symbol,
                    })
        except Exception as exc:
            log.debug(f"IndianAPI {symbol}: {exc}")
        time.sleep(0.3)  # rate limit courtesy

    log.info(f"IndianAPI: {len(items)} items from {min(len(symbols), 15)} stocks")
    return items


# ── Source 3: Google News RSS ──

def fetch_google_news(symbols: list[str]) -> list[dict]:
    """Fetch per-stock news from Google News RSS."""
    items = []
    for symbol in symbols:
        try:
            url = f"https://news.google.com/rss/search?q={quote(symbol)}+NSE+stock&hl=en-IN&gl=IN&ceid=IN:en"
            resp = requests.get(url, timeout=8, headers={
                "User-Agent": "Mozilla/5.0 (AnkaResearch/1.0)"
            })
            resp.raise_for_status()
            root = ET.fromstring(resp.text)
            for item_el in root.findall(".//item")[:3]:
                title = item_el.findtext("title", "")
                link = item_el.findtext("link", "")
                pub = item_el.findtext("pubDate", "")
                source_el = item_el.find("source")
                source = source_el.text if source_el is not None else "Google News"
                if title and not _is_junk(title):
                    items.append({
                        "title": title,
                        "url": link,
                        "source": source,
                        "published": pub,
                        "tier": "google",
                        "symbol_hint": symbol,
                    })
        except Exception as exc:
            log.debug(f"Google News {symbol}: {exc}")

        if len(items) % 30 == 0 and len(items) > 0:
            time.sleep(1)

    log.info(f"Google News: {len(items)} items from {len(symbols)} stocks")
    return items


# ── Main classification engine ──

def classify_event(item: dict, universe: list[str]) -> dict | None:
    """Classify a news item. Returns enriched event or None if irrelevant."""
    title = item["title"]

    # Tier 1: name match
    matched_stocks = _name_match_stocks(title, universe)
    # Add symbol_hint if present (from IndianAPI/Google)
    if item.get("symbol_hint") and item["symbol_hint"] not in matched_stocks:
        matched_stocks.append(item["symbol_hint"])

    # Tier 2: policy match
    policy_matches = _policy_match(title)

    # Must have at least one match
    if not matched_stocks and not policy_matches:
        return None

    # Determine confidence
    if matched_stocks:
        confidence = "HIGH"
    else:
        confidence = "MEDIUM"

    # Determine impact
    impact = "LOW"
    for pm in policy_matches:
        if pm["impact"] == "HIGH":
            impact = "HIGH"
            break
        if pm["impact"] == "MEDIUM":
            impact = "MEDIUM"

    if impact == "LOW" and matched_stocks:
        impact = "MEDIUM"  # direct mention is at least MEDIUM

    return {
        "title": title,
        "url": item.get("url", ""),
        "source": item["source"],
        "published": item.get("published", ""),
        "detected_at": datetime.now(IST).isoformat(),
        "confidence": confidence,
        "impact": impact,
        "matched_stocks": matched_stocks,
        "policy_matches": policy_matches,
        "categories": [pm["category"] for pm in policy_matches],
        "tier": item.get("tier", "unknown"),
    }


def deduplicate(events: list[dict]) -> list[dict]:
    """Remove duplicate events (same title within 2 hours)."""
    seen = {}
    unique = []
    for e in events:
        key = e["title"].lower()[:80]
        if key not in seen:
            seen[key] = True
            unique.append(e)
    return unique


def scan(full_universe: bool = False, send_telegram: bool = True) -> dict:
    """Run the full news intelligence scan."""
    now = datetime.now(IST)
    log.info(f"=== News Intelligence Scan {'(FULL)' if full_universe else '(TOP 40)'} ===")

    # Determine scan universe
    if full_universe:
        universe = load_fno_universe()
        scan_symbols = universe
    else:
        universe = load_fno_universe()  # for name matching
        scan_symbols = FNO_TOP_40

    # Fetch from all 3 sources
    bse_items = fetch_bse_filings()
    api_items = fetch_indianapi_news(scan_symbols[:15])
    google_items = fetch_google_news(scan_symbols)

    all_items = bse_items + api_items + google_items
    log.info(f"Total raw items: {len(all_items)}")

    # Classify each item
    events = []
    for item in all_items:
        event = classify_event(item, universe)
        if event:
            events.append(event)

    events = deduplicate(events)
    log.info(f"Classified events: {len(events)} (after dedup)")

    # Load existing today's events to merge
    existing = []
    if EVENTS_TODAY.exists():
        try:
            existing_data = json.loads(EVENTS_TODAY.read_text(encoding="utf-8"))
            existing = existing_data.get("events", [])
        except (json.JSONDecodeError, KeyError):
            pass

    # Merge: add new events not already seen
    existing_titles = {e["title"].lower()[:80] for e in existing}
    new_events = [e for e in events if e["title"].lower()[:80] not in existing_titles]

    all_today = existing + new_events
    log.info(f"New events this scan: {len(new_events)}, total today: {len(all_today)}")

    # Save today's events
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    today_data = {
        "date": now.strftime("%Y-%m-%d"),
        "last_scan": now.isoformat(),
        "scan_type": "full" if full_universe else "top40",
        "events": all_today,
        "summary": {
            "total": len(all_today),
            "high_impact": len([e for e in all_today if e["impact"] == "HIGH"]),
            "medium_impact": len([e for e in all_today if e["impact"] == "MEDIUM"]),
            "stocks_mentioned": sorted(set(
                s for e in all_today for s in e.get("matched_stocks", [])
            )),
        },
    }
    EVENTS_TODAY.write_text(json.dumps(today_data, indent=2, ensure_ascii=False), encoding="utf-8")

    # Append new events to history
    if new_events:
        history = []
        if EVENTS_HISTORY.exists():
            try:
                history = json.loads(EVENTS_HISTORY.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, KeyError):
                pass
        history.extend(new_events)
        # Keep last 30 days (~150 events/day × 30 = 4500 max)
        cutoff = (now - timedelta(days=30)).isoformat()
        history = [e for e in history if e.get("detected_at", "") > cutoff]
        EVENTS_HISTORY.write_text(json.dumps(history, indent=2, ensure_ascii=False), encoding="utf-8")

    # Send Telegram alerts for new HIGH impact events
    if send_telegram and new_events:
        from news_alerter import send_news_alerts
        high_events = [e for e in new_events if e["impact"] == "HIGH"]
        if high_events:
            send_news_alerts(high_events)

    return today_data


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Intraday News Intelligence Scanner")
    parser.add_argument("--full", action="store_true", help="Scan full 213 F&O universe")
    parser.add_argument("--no-telegram", action="store_true", help="Skip Telegram alerts")
    args = parser.parse_args()
    result = scan(full_universe=args.full, send_telegram=not args.no_telegram)
    print(f"\nDone. {result['summary']['total']} events, "
          f"{result['summary']['high_impact']} HIGH, "
          f"{result['summary']['medium_impact']} MEDIUM.")
```

- [ ] **Step 2: Run a test scan (no Telegram)**

Run: `cd C:/Users/Claude_Anka/askanka.com/pipeline && python news_intelligence.py --no-telegram`

Expected: Events detected and saved to `data/news_events_today.json`

- [ ] **Step 3: Commit**

```bash
git add -f pipeline/news_intelligence.py
git commit -m "feat: news intelligence scanner — BSE + IndianAPI + Google, two-tier classification"
```

---

### Task 3: Build news_alerter.py — Telegram formatter

**Files:**
- Create: `pipeline/news_alerter.py`

- [ ] **Step 1: Create news_alerter.py**

```python
"""
Anka Research — News Alert Formatter + Telegram Sender
Formats classified news events into readable Telegram messages.
"""

import json
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

_HERE = Path(__file__).parent
sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(_HERE / "lib"))

from telegram_bot import send_message

log = logging.getLogger("anka.news_alerter")
IST = timezone(timedelta(hours=5, minutes=30))
DATA_DIR = _HERE / "data"


def _load_positions() -> list[dict]:
    """Load current open positions to check if news affects them."""
    signals_dir = DATA_DIR / "signals"
    open_file = signals_dir / "open_signals.json"
    if not open_file.exists():
        return []
    try:
        return json.loads(open_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, KeyError):
        return []


def _check_position_impact(stocks: list[str], positions: list[dict]) -> str | None:
    """Check if any matched stocks are in current positions."""
    for pos in positions:
        pos_stocks = set()
        for leg in pos.get("long_legs", []):
            pos_stocks.add(leg.get("ticker", ""))
        for leg in pos.get("short_legs", []):
            pos_stocks.add(leg.get("ticker", ""))
        overlap = set(stocks) & pos_stocks
        if overlap:
            return f"Your position: {pos.get('spread_name', 'Unknown')} — {', '.join(overlap)} affected"
    return None


def format_news_alert(event: dict, positions: list[dict] = None) -> str:
    """Format a single news event as Telegram message."""
    confidence = event.get("confidence", "MEDIUM")
    impact = event.get("impact", "MEDIUM")
    title = event["title"]
    source = event.get("source", "Unknown")
    stocks = event.get("matched_stocks", [])
    categories = event.get("categories", [])

    # Header
    if impact == "HIGH":
        header = f"NEWS ALERT: [{confidence}] — {impact} IMPACT"
    else:
        header = f"NEWS: [{confidence}]"

    # Stocks line
    stocks_str = ", ".join(stocks) if stocks else "Sector-wide"

    # Categories
    cat_str = ", ".join(c.upper().replace("_", " ") for c in categories) if categories else "GENERAL"

    # Position impact
    pos_impact = ""
    if positions:
        impact_msg = _check_position_impact(stocks, positions)
        if impact_msg:
            pos_impact = f"\n{impact_msg}"

    msg = (
        f"{header}\n\n"
        f"{title}\n"
        f"Source: {source}\n\n"
        f"Affected: {stocks_str}\n"
        f"Category: {cat_str}"
        f"{pos_impact}\n\n"
        f"Overnight backtest will assess impact by 04:45 AM."
    )
    return msg


def send_news_alerts(events: list[dict]):
    """Send Telegram alerts for a list of events."""
    positions = _load_positions()

    for event in events[:5]:  # max 5 alerts per scan cycle
        msg = format_news_alert(event, positions)
        try:
            send_message(msg)
            log.info(f"Alert sent: {event['title'][:60]}")
        except Exception as exc:
            log.warning(f"Telegram failed: {exc}")


if __name__ == "__main__":
    # Test with today's events
    today_file = DATA_DIR / "news_events_today.json"
    if today_file.exists():
        data = json.loads(today_file.read_text(encoding="utf-8"))
        high = [e for e in data.get("events", []) if e["impact"] == "HIGH"]
        print(f"HIGH impact events: {len(high)}")
        for e in high[:3]:
            print(format_news_alert(e))
            print("---")
    else:
        print("No events today. Run news_intelligence.py first.")
```

- [ ] **Step 2: Test formatting (no send)**

Run: `cd C:/Users/Claude_Anka/askanka.com/pipeline && python news_alerter.py`

Expected: Formatted alert messages printed to console

- [ ] **Step 3: Commit**

```bash
git add -f pipeline/news_alerter.py
git commit -m "feat: news alerter — Telegram formatter with position impact check"
```

---

### Task 4: Build news_backtest.py — overnight verdict engine

**Files:**
- Create: `pipeline/news_backtest.py`

- [ ] **Step 1: Create news_backtest.py**

```python
"""
Anka Research — Overnight News Backtest
Runs after market close. Takes today's news events, looks up historical
price reactions for similar events, and generates verdicts:
  NO_IMPACT / MODERATE / HIGH_IMPACT → ADD / CUT / EXIT

Usage:
    python news_backtest.py                    # process today's events
    python news_backtest.py --date 2026-04-13  # process specific date
"""

import argparse
import json
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

_HERE = Path(__file__).parent
sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(_HERE / "lib"))

from config import NEWS_CATEGORIES

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("anka.news_backtest")

IST = timezone(timedelta(hours=5, minutes=30))
DATA_DIR = _HERE / "data"
FNO_HIST = DATA_DIR / "fno_historical"
EVENTS_TODAY = DATA_DIR / "news_events_today.json"
EVENTS_HISTORY = DATA_DIR / "news_events_history.json"
VERDICTS_FILE = DATA_DIR / "news_verdicts.json"


def load_stock_prices(symbol: str) -> pd.DataFrame | None:
    """Load price history for a stock from fno_historical."""
    csv_path = FNO_HIST / f"{symbol}.csv"
    if not csv_path.exists():
        return None
    try:
        df = pd.read_csv(csv_path, index_col=0, parse_dates=True)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        return df
    except Exception:
        return None


def compute_forward_returns(df: pd.DataFrame, event_date: str) -> dict | None:
    """Compute 1d, 3d, 5d returns from event date."""
    try:
        event_dt = pd.Timestamp(event_date)
        # Find nearest trading day on or after event date
        future = df.index[df.index >= event_dt]
        if len(future) == 0:
            return None
        t0 = future[0]
        t0_loc = df.index.get_loc(t0)

        close_0 = df.iloc[t0_loc]["Close"]
        result = {"date": t0.strftime("%Y-%m-%d"), "close_0": float(close_0)}

        for days, label in [(1, "ret_1d"), (3, "ret_3d"), (5, "ret_5d")]:
            if t0_loc + days < len(df):
                close_n = df.iloc[t0_loc + days]["Close"]
                result[label] = round(float((close_n / close_0 - 1) * 100), 3)
            else:
                result[label] = None

        return result
    except Exception:
        return None


def lookup_historical_precedent(
    symbol: str, category: str, history: list[dict]
) -> dict:
    """Find past events of same category for same stock, compute avg returns."""
    past_events = [
        e for e in history
        if symbol in e.get("matched_stocks", [])
        and category in e.get("categories", [])
        and e.get("outcome")  # must have been backtested before
    ]

    if len(past_events) < 2:
        return {"precedent_count": len(past_events), "verdict": "INSUFFICIENT_DATA"}

    returns_5d = [e["outcome"]["ret_5d"] for e in past_events
                  if e.get("outcome", {}).get("ret_5d") is not None]

    if not returns_5d:
        return {"precedent_count": len(past_events), "verdict": "INSUFFICIENT_DATA"}

    avg_5d = np.mean(returns_5d)
    hit_rate = len([r for r in returns_5d if r > 0]) / len(returns_5d)

    return {
        "precedent_count": len(past_events),
        "avg_5d_return": round(float(avg_5d), 3),
        "hit_rate": round(float(hit_rate), 3),
    }


def classify_verdict(event: dict, price_reaction: dict, precedent: dict) -> dict:
    """Classify: NO_IMPACT / MODERATE / HIGH_IMPACT + recommendation."""
    # If we have a price reaction from today
    ret_1d = price_reaction.get("ret_1d") if price_reaction else None

    # If we have historical precedent
    avg_5d = precedent.get("avg_5d_return")
    hit_rate = precedent.get("hit_rate", 0)

    # Classify impact
    if ret_1d is not None and abs(ret_1d) > 3.0:
        impact = "HIGH_IMPACT"
    elif ret_1d is not None and abs(ret_1d) > 1.5:
        impact = "MODERATE"
    elif avg_5d is not None and abs(avg_5d) > 2.0 and hit_rate > 0.6:
        impact = "HIGH_IMPACT"
    elif avg_5d is not None and abs(avg_5d) > 1.0:
        impact = "MODERATE"
    else:
        impact = "NO_IMPACT"

    # Recommendation
    if impact == "HIGH_IMPACT":
        if (avg_5d or 0) > 0 or (ret_1d or 0) > 0:
            recommendation = "ADD"
            direction = "LONG"
        else:
            recommendation = "CUT"
            direction = "SHORT"
    elif impact == "MODERATE":
        recommendation = "MONITOR"
        direction = "LONG" if (avg_5d or ret_1d or 0) > 0 else "SHORT"
    else:
        recommendation = "NO_ACTION"
        direction = None

    # Shelf life
    category = event.get("categories", [""])[0] if event.get("categories") else ""
    shelf_cfg = NEWS_CATEGORIES.get(category, {})
    shelf_days = shelf_cfg.get("default_shelf_life_days", 3)

    # Is the move done? (gap captured most of it)
    if ret_1d is not None and avg_5d is not None and abs(ret_1d) > abs(avg_5d) * 0.7:
        shelf_life = "EXPIRED"
    elif ret_1d is not None and abs(ret_1d) < 0.5:
        shelf_life = "EMERGING"
    else:
        shelf_life = "ACTIVE"

    return {
        "impact": impact,
        "recommendation": recommendation,
        "direction": direction,
        "shelf_life": shelf_life,
        "shelf_days": shelf_days,
        "price_reaction_1d": ret_1d,
        "historical_avg_5d": avg_5d,
        "historical_hit_rate": hit_rate,
        "precedent_count": precedent.get("precedent_count", 0),
    }


def run_backtest(target_date: str = None):
    """Process today's events through the backtest engine."""
    if target_date is None:
        target_date = datetime.now(IST).strftime("%Y-%m-%d")

    log.info(f"=== News Backtest for {target_date} ===")

    # Load today's events
    if not EVENTS_TODAY.exists():
        log.info("No events file found. Run news_intelligence.py first.")
        return

    today_data = json.loads(EVENTS_TODAY.read_text(encoding="utf-8"))
    events = today_data.get("events", [])
    log.info(f"Events to process: {len(events)}")

    # Load history for precedent lookup
    history = []
    if EVENTS_HISTORY.exists():
        try:
            history = json.loads(EVENTS_HISTORY.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, KeyError):
            pass

    verdicts = []
    for event in events:
        stocks = event.get("matched_stocks", [])
        categories = event.get("categories", [])

        if not stocks:
            continue

        for symbol in stocks[:3]:  # max 3 stocks per event
            # Get price reaction
            df = load_stock_prices(symbol)
            price_reaction = compute_forward_returns(df, target_date) if df is not None else None

            # Get historical precedent
            category = categories[0] if categories else ""
            precedent = lookup_historical_precedent(symbol, category, history)

            # Classify
            verdict = classify_verdict(event, price_reaction, precedent)
            verdict["symbol"] = symbol
            verdict["event_title"] = event["title"][:100]
            verdict["event_date"] = target_date
            verdict["category"] = category

            verdicts.append(verdict)
            log.info(f"  {symbol}: {verdict['impact']} → {verdict['recommendation']} "
                     f"(1d: {verdict['price_reaction_1d']}, hist: {verdict['historical_avg_5d']})")

    # Save verdicts
    VERDICTS_FILE.write_text(json.dumps(verdicts, indent=2, ensure_ascii=False), encoding="utf-8")
    log.info(f"Saved {len(verdicts)} verdicts to {VERDICTS_FILE}")

    # Summary
    high = [v for v in verdicts if v["impact"] == "HIGH_IMPACT"]
    moderate = [v for v in verdicts if v["impact"] == "MODERATE"]
    adds = [v for v in verdicts if v["recommendation"] == "ADD"]
    cuts = [v for v in verdicts if v["recommendation"] == "CUT"]

    print(f"\n{'='*60}")
    print(f"  NEWS BACKTEST VERDICTS — {target_date}")
    print(f"{'='*60}")
    print(f"  HIGH_IMPACT: {len(high)} | MODERATE: {len(moderate)} | NO_IMPACT: {len(verdicts) - len(high) - len(moderate)}")
    print(f"  ADD: {len(adds)} | CUT: {len(cuts)}")

    for v in high:
        print(f"\n  {v['recommendation']} {v['symbol']} ({v['direction']})")
        print(f"    Event: {v['event_title']}")
        print(f"    1d reaction: {v['price_reaction_1d']}% | Historical avg 5d: {v['historical_avg_5d']}%")
        print(f"    Shelf life: {v['shelf_life']} ({v['shelf_days']} days)")

    print(f"{'='*60}\n")

    return verdicts


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", type=str, default=None, help="Target date (YYYY-MM-DD)")
    args = parser.parse_args()
    run_backtest(target_date=args.date)
```

- [ ] **Step 2: Test backtest with today's events**

Run: `cd C:/Users/Claude_Anka/askanka.com/pipeline && python news_backtest.py`

Expected: Verdicts generated from today's events (will be mostly NO_IMPACT since today is holiday, but should run without errors)

- [ ] **Step 3: Commit**

```bash
git add -f pipeline/news_backtest.py
git commit -m "feat: overnight news backtest — historical precedent lookup + ADD/CUT/EXIT verdicts"
```

---

### Task 5: Wire into scheduled tasks

**Files:**
- Modify: `pipeline/scripts/intraday_scan.bat`
- Modify: `pipeline/scripts/morning_scan.bat`
- Create: `pipeline/scripts/overnight_news.bat`

- [ ] **Step 1: Add news_intelligence.py to intraday_scan.bat**

Add before the Phase C correlation breaks section:

```bat
REM News Intelligence (top 40, every 15 min)
python -X utf8 news_intelligence.py --no-telegram >> logs\intraday_scan.log 2>&1
```

Note: `--no-telegram` for intraday scans to avoid alert spam. Only HIGH impact events trigger alerts from the scanner itself.

Actually, remove `--no-telegram` — the scanner already filters to only send HIGH impact alerts:

```bat
python -X utf8 news_intelligence.py >> logs\intraday_scan.log 2>&1
```

- [ ] **Step 2: Add full-universe scan to morning_scan.bat**

Add after the existing `news_scanner.py` line:

```bat
python -X utf8 news_intelligence.py --full >> logs\morning_scan.log 2>&1
```

- [ ] **Step 3: Create overnight_news.bat**

```bat
@echo off
REM ANKA Overnight News Backtest — runs at 04:30 AM
cd /d "C:\Users\Claude_Anka\askanka.com\pipeline"
python -X utf8 news_backtest.py >> logs\overnight_news.log 2>&1
```

- [ ] **Step 4: Add mid-session full scan at 12:30**

Register via setup_tasks.bat or manually:
```bat
schtasks /create /tn "AnkaNewsMidDay" /tr "C:\Users\Claude_Anka\askanka.com\pipeline\scripts\morning_scan.bat" /sc WEEKLY /d MON,TUE,WED,THU,FRI /st 12:30 /f
schtasks /create /tn "AnkaOvernightNews" /tr "C:\Users\Claude_Anka\askanka.com\pipeline\scripts\overnight_news.bat" /sc DAILY /st 04:30 /f
```

- [ ] **Step 5: Commit**

```bash
git add pipeline/scripts/intraday_scan.bat pipeline/scripts/morning_scan.bat pipeline/scripts/overnight_news.bat
git commit -m "feat: wire news intelligence into morning + intraday + overnight schedules"
```

---

### Task 6: End-to-end test

- [ ] **Step 1: Run full scan**

```bash
cd C:/Users/Claude_Anka/askanka.com/pipeline
python news_intelligence.py --full --no-telegram
```

Expected: Events from BSE + IndianAPI + Google News classified and saved

- [ ] **Step 2: Run backtest on results**

```bash
python news_backtest.py
```

Expected: Verdicts generated for each event × stock combination

- [ ] **Step 3: Run alerter test**

```bash
python news_alerter.py
```

Expected: Formatted alerts printed to console

- [ ] **Step 4: Verify data files created**

```bash
ls -la data/news_events_today.json data/news_events_history.json data/news_verdicts.json
```

- [ ] **Step 5: Final commit**

```bash
git add -A
git commit -m "feat: intraday news intelligence layer — complete two-phase system"
```
