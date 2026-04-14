"""
Anka Research Pipeline — News Scanner
Polls RSS feeds + indianapi.in for sector-relevant news and classifies
headlines against policy categories mapped to spread pairs.
"""

import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import feedparser
import requests
from dotenv import load_dotenv

# Load .env from pipeline directory
_HERE = Path(__file__).parent
load_dotenv(_HERE / ".env")

# Add pipeline dir to path so config is importable
sys.path.insert(0, str(_HERE))
import config

# ── Logging ────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ── RSS feeds ───────────────────────────────────────────────────────────────
RSS_FEEDS = [
    ("MoneyControl", "https://www.moneycontrol.com/rss/latestnews.xml"),
    ("EconomicTimes", "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms"),
    ("LiveMint",      "https://www.livemint.com/rss/markets"),
]

# ── Policy keyword classification ──────────────────────────────────────────
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

# ── Output path ─────────────────────────────────────────────────────────────
DATA_DIR = _HERE / "data"
NEWS_JSON = DATA_DIR / "news.json"


# ── Internal helpers ────────────────────────────────────────────────────────

def _poll_rss() -> list[dict]:
    """Parse all RSS feeds. Return up to 10 entries per feed."""
    entries: list[dict] = []
    for source, url in RSS_FEEDS:
        try:
            log.info(f"  Polling RSS: {source}")
            feed = feedparser.parse(url)
            count = 0
            for entry in feed.entries[:10]:
                title = getattr(entry, "title", "").strip()
                link  = getattr(entry, "link",  "").strip()
                # published: try multiple attrs
                published = (
                    getattr(entry, "published", None)
                    or getattr(entry, "updated",   None)
                    or ""
                )
                if title:
                    entries.append({
                        "source":    source,
                        "title":     title,
                        "link":      link,
                        "published": published,
                    })
                    count += 1
            log.info(f"    {source}: {count} entries")
        except Exception as exc:
            log.warning(f"    {source} RSS failed: {exc}")
    return entries


def _poll_announcements(symbols: list[str]) -> list[dict]:
    """
    Query indianapi.in /recent_announcements for each symbol.
    Returns up to 3 announcements per symbol, limited to 10 symbols.
    Requires INDIANAPI_KEY env var.
    """
    api_key = os.getenv("INDIANAPI_KEY", "").strip()
    if not api_key:
        log.warning("INDIANAPI_KEY not set — skipping announcements")
        return []

    announcements: list[dict] = []
    for symbol in symbols[:10]:
        try:
            log.info(f"  Announcements: {symbol}")
            resp = requests.get(
                "https://stock.indianapi.in/recent_announcements",
                params={"stock_name": symbol},
                headers={"X-Api-Key": api_key},
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            # API may return a list directly or wrapped in a key
            items = data if isinstance(data, list) else data.get("announcements", data.get("data", []))
            for item in items[:3]:
                title = (
                    item.get("headline")
                    or item.get("title")
                    or item.get("subject")
                    or str(item)[:120]
                )
                announcements.append({
                    "symbol":    symbol,
                    "title":     title.strip() if isinstance(title, str) else str(title),
                    "published": item.get("date") or item.get("published") or "",
                    "link":      item.get("link") or item.get("url") or "",
                    "source":    "indianapi.in",
                })
            log.info(f"    {symbol}: {min(len(items), 3)} announcements")
        except requests.HTTPError as exc:
            log.warning(f"    {symbol} announcements HTTP error: {exc}")
        except Exception as exc:
            log.warning(f"    {symbol} announcements error: {exc}")
    return announcements


def _classify_headline(title: str) -> list[dict]:
    """
    Match title against POLICY_KEYWORDS (case-insensitive).
    Returns list of classification dicts.
    """
    title_lower = title.lower()
    matches: list[dict] = []
    for category, cfg in POLICY_KEYWORDS.items():
        for kw in cfg["keywords"]:
            if kw.lower() in title_lower:
                matches.append({
                    "category":        category,
                    "keyword_matched": kw,
                    "affected_spreads": cfg["spreads"],
                    "direction":       cfg["default_direction"],
                })
                break  # one match per category is enough
    return matches


# ── Main public function ────────────────────────────────────────────────────

def scan_news() -> dict:
    """
    Full news scan:
      1. Gather unique symbols from INDIA_SPREAD_PAIRS
      2. Poll RSS feeds
      3. Poll indianapi.in announcements
      4. Classify all headlines
      5. Group by affected spread
      6. Persist to data/news.json
    Returns the saved dict.
    """
    log.info("=== News Scanner starting ===")
    timestamp = datetime.now(timezone.utc).isoformat()

    # 1 — Collect symbols from spread pairs
    all_symbols: set[str] = set()
    for pair in config.INDIA_SPREAD_PAIRS:
        all_symbols.update(pair.get("long",  []))
        all_symbols.update(pair.get("short", []))
    symbols = sorted(all_symbols)
    log.info(f"Unique symbols from spread pairs: {len(symbols)}")

    # 2 — RSS
    log.info("Polling RSS feeds ...")
    rss_headlines = _poll_rss()
    log.info(f"RSS total: {len(rss_headlines)} headlines")

    # 3 — Announcements
    log.info("Polling indianapi.in announcements ...")
    announcements = _poll_announcements(symbols)
    log.info(f"Announcements total: {len(announcements)}")

    # 4 — Classify all headlines (RSS + announcements)
    classified_events: list[dict] = []
    all_items = rss_headlines + [
        {
            "source":    a["source"],
            "title":     a["title"],
            "link":      a["link"],
            "published": a["published"],
            "symbol":    a["symbol"],
        }
        for a in announcements
    ]
    for item in all_items:
        matches = _classify_headline(item["title"])
        if matches:
            classified_events.append({
                **item,
                "classifications": matches,
            })

    log.info(f"Classified events: {len(classified_events)} / {len(all_items)} headlines matched")

    # 5 — Group by spread name
    spread_news: dict[str, list[dict]] = {}
    for event in classified_events:
        for cls in event["classifications"]:
            for spread_name in cls["affected_spreads"]:
                spread_news.setdefault(spread_name, []).append({
                    "title":           event["title"],
                    "source":          event["source"],
                    "published":       event["published"],
                    "link":            event.get("link", ""),
                    "category":        cls["category"],
                    "keyword_matched": cls["keyword_matched"],
                    "direction":       cls["direction"],
                })

    # 6 — Persist
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    result = {
        "timestamp":           timestamp,
        "headlines_polled":    len(rss_headlines),
        "announcements_polled": len(announcements),
        "classified_events":   classified_events,
        "spread_news":         spread_news,
        "announcements":       announcements,
    }
    with open(NEWS_JSON, "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2)
    log.info(f"Saved to {NEWS_JSON}")

    # Summary
    log.info("=== Scan complete ===")
    log.info(f"  headlines_polled:    {result['headlines_polled']}")
    log.info(f"  announcements_polled:{result['announcements_polled']}")
    log.info(f"  classified_events:  {len(classified_events)}")
    log.info(f"  spreads with news:  {len(spread_news)}")
    for spread, items in spread_news.items():
        log.info(f"    [{spread}] → {len(items)} event(s)")

    return result


# ── CLI entry point ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    result = scan_news()
    print(f"\nDone. {result['headlines_polled']} RSS headlines, "
          f"{result['announcements_polled']} announcements, "
          f"{len(result['classified_events'])} classified.")
