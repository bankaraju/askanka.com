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

ALIASES_FILE = Path(__file__).parent / "config" / "news_aliases.json"
_ALIASES_CACHE: dict | None = None


def _load_aliases() -> dict:
    if not ALIASES_FILE.exists():
        return {}
    try:
        return json.loads(ALIASES_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _alias_match_stocks(title: str, universe: list[str]) -> list[str]:
    global _ALIASES_CACHE
    if _ALIASES_CACHE is None:
        _ALIASES_CACHE = _load_aliases()
    matches: list[str] = []
    for phrase, ticker in _ALIASES_CACHE.items():
        if ticker not in universe or ticker in matches:
            continue
        # Word-boundary match (case-insensitive) avoids substring false-positives
        # like "Jio" matching inside "JioCinema" or "Dr Reddy" matching
        # "minister Dr Reddy". Mirrors _name_match_stocks style.
        # Uses (?<!\w)/(?!\w) lookaround instead of \b — more precise for phrases
        # ending in punctuation (e.g. "Dr. Reddy's") where \b behaves unexpectedly
        # around apostrophes.
        pattern = r"(?<!\w)" + re.escape(phrase) + r"(?!\w)"
        if re.search(pattern, title, re.IGNORECASE):
            matches.append(ticker)
    return matches


BSE_RSS = "https://www.bseindia.com/xml-data/corpfiling/rss_corp.xml"

MARKET_RSS = [
    ("MoneyControl", "https://www.moneycontrol.com/rss/latestnews.xml"),
    ("EconomicTimes", "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms"),
    ("LiveMint", "https://www.livemint.com/rss/markets"),
]

JUNK_PATTERNS = [
    r"market outlook", r"expert view", r"technical analysis",
    r"stock picks", r"top .* stocks", r"sensex.*nifty.*points",
    r"share price today", r"live updates", r"market wrap",
]
_JUNK_RE = re.compile("|".join(JUNK_PATTERNS), re.IGNORECASE)


def load_fno_universe() -> list[str]:
    if FNO_UNIVERSE_FILE.exists():
        data = json.loads(FNO_UNIVERSE_FILE.read_text(encoding="utf-8"))
        return data.get("symbols", [])
    return FNO_TOP_40


def _is_junk(title: str) -> bool:
    if len(title) < 30:
        return True
    if _JUNK_RE.search(title):
        return True
    return False


def _name_match_stocks(title: str, universe: list[str]) -> list[str]:
    title_upper = title.upper()
    matched = []
    for symbol in universe:
        if re.search(r'\b' + re.escape(symbol) + r'\b', title_upper):
            matched.append(symbol)
    return matched


def _policy_match(title: str) -> list[dict]:
    title_lower = title.lower()
    matches = []
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


def fetch_bse_filings() -> list[dict]:
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
                    "title": title, "url": link, "source": "BSE Filing",
                    "published": published, "tier": "bse",
                })
        log.info(f"BSE filings: {len(items)} items")
    except Exception as exc:
        log.warning(f"BSE RSS failed: {exc}")
    return items


def fetch_indianapi_news(symbols: list[str]) -> list[dict]:
    api_key = os.getenv("INDIANAPI_KEY", "").strip()
    if not api_key:
        log.warning("INDIANAPI_KEY not set -- skipping")
        return []
    items = []
    for symbol in symbols[:15]:
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
                        "title": title.strip(), "url": item.get("link", ""),
                        "source": "IndianAPI", "published": item.get("date", ""),
                        "tier": "indianapi", "symbol_hint": symbol,
                    })
        except Exception as exc:
            log.debug(f"IndianAPI {symbol}: {exc}")
        time.sleep(0.3)
    log.info(f"IndianAPI: {len(items)} items from {min(len(symbols), 15)} stocks")
    return items


def fetch_google_news(symbols: list[str]) -> list[dict]:
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
                        "title": title, "url": link, "source": source,
                        "published": pub, "tier": "google", "symbol_hint": symbol,
                    })
        except Exception as exc:
            log.debug(f"Google News {symbol}: {exc}")
        if len(items) % 30 == 0 and len(items) > 0:
            time.sleep(1)
    log.info(f"Google News: {len(items)} items from {len(symbols)} stocks")
    return items


def fetch_market_rss() -> list[dict]:
    items = []
    for source_name, url in MARKET_RSS:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:10]:
                title = getattr(entry, "title", "").strip()
                link = getattr(entry, "link", "").strip()
                published = getattr(entry, "published", "") or getattr(entry, "updated", "")
                if title and not _is_junk(title):
                    items.append({
                        "title": title, "url": link, "source": source_name,
                        "published": published, "tier": "rss",
                    })
        except Exception as exc:
            log.warning(f"{source_name} RSS failed: {exc}")
    log.info(f"Market RSS: {len(items)} items")
    return items


def classify_event(item: dict, universe: list[str]) -> dict | None:
    title = item["title"]
    matched_stocks = _name_match_stocks(title, universe)
    matched_stocks.extend(
        t for t in _alias_match_stocks(title, universe) if t not in matched_stocks
    )
    if item.get("symbol_hint") and item["symbol_hint"] not in matched_stocks:
        matched_stocks.append(item["symbol_hint"])
    policy_matches = _policy_match(title)
    if not matched_stocks and not policy_matches:
        return None
    confidence = "HIGH" if matched_stocks else "MEDIUM"
    impact = "LOW"
    for pm in policy_matches:
        if pm["impact"] == "HIGH":
            impact = "HIGH"
            break
        if pm["impact"] == "MEDIUM":
            impact = "MEDIUM"
    if impact == "LOW" and matched_stocks:
        impact = "MEDIUM"
    return {
        "title": title, "url": item.get("url", ""),
        "source": item["source"], "published": item.get("published", ""),
        "detected_at": datetime.now(IST).isoformat(),
        "confidence": confidence, "impact": impact,
        "matched_stocks": matched_stocks,
        "policy_matches": policy_matches,
        "categories": [pm["category"] for pm in policy_matches],
        "tier": item.get("tier", "unknown"),
    }


def deduplicate(events: list[dict]) -> list[dict]:
    seen = {}
    unique = []
    for e in events:
        key = e["title"].lower()[:80]
        if key not in seen:
            seen[key] = True
            unique.append(e)
    return unique


def scan(full_universe: bool = False, send_telegram: bool = True) -> dict:
    now = datetime.now(IST)
    log.info(f"=== News Intelligence Scan {'(FULL)' if full_universe else '(TOP 40)'} ===")
    universe = load_fno_universe()
    scan_symbols = universe if full_universe else FNO_TOP_40

    bse_items = fetch_bse_filings()
    rss_items = fetch_market_rss()
    api_items = fetch_indianapi_news(scan_symbols[:15])
    google_items = fetch_google_news(scan_symbols)

    all_items = bse_items + rss_items + api_items + google_items
    log.info(f"Total raw items: {len(all_items)}")

    events = []
    for item in all_items:
        event = classify_event(item, universe)
        if event:
            events.append(event)
    events = deduplicate(events)
    log.info(f"Classified events: {len(events)} (after dedup)")

    existing = []
    if EVENTS_TODAY.exists():
        try:
            existing_data = json.loads(EVENTS_TODAY.read_text(encoding="utf-8"))
            existing = existing_data.get("events", [])
        except (json.JSONDecodeError, KeyError):
            pass

    # Keep a rolling 7-day window in EVENTS_TODAY. Without this cap the file
    # grows unbounded and the website news card surfaces 2+-day-old items as
    # fresh. 7 days covers the longest NEWS_CATEGORIES shelf life so nothing
    # actionable gets evicted. Longer-term history lives in EVENTS_HISTORY.
    from datetime import timedelta as _td
    cutoff = (now - _td(days=7)).strftime("%Y-%m-%d")
    existing = [e for e in existing if (e.get("detected_at", "")[:10] >= cutoff)]

    existing_titles = {e["title"].lower()[:80] for e in existing}
    new_events = [e for e in events if e["title"].lower()[:80] not in existing_titles]
    all_today = existing + new_events
    log.info(f"New events this scan: {len(new_events)}, total today: {len(all_today)}")

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

    if new_events:
        history = []
        if EVENTS_HISTORY.exists():
            try:
                history = json.loads(EVENTS_HISTORY.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, KeyError):
                pass
        history.extend(new_events)
        cutoff = (now - timedelta(days=30)).isoformat()
        history = [e for e in history if e.get("detected_at", "") > cutoff]
        EVENTS_HISTORY.write_text(json.dumps(history, indent=2, ensure_ascii=False), encoding="utf-8")

    if send_telegram and new_events:
        try:
            from news_alerter import send_news_alerts
            high_events = [e for e in new_events if e["impact"] == "HIGH"]
            if high_events:
                send_news_alerts(high_events)
        except ImportError:
            log.warning("news_alerter not available -- skipping Telegram")

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
