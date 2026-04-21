"""
Anka Research — F&O Stock News Scanner
Fetches recent news headlines for F&O universe stocks via Google News RSS (free, $0).
Outputs data/fno_news.json for the terminal dashboard news scroll.

Usage:
    python fno_news_scanner.py          # scan all F&O stocks
    python fno_news_scanner.py --top 30 # scan top 30 by volume

Scheduled: run every 30 minutes during market hours (09:00-16:00 IST)
"""

import json
import logging
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

_lib = str(Path(__file__).parent / "lib")
if _lib not in sys.path:
    sys.path.insert(0, _lib)

import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("fno_news")

PIPELINE_DIR = Path(__file__).parent
DATA_DIR = PIPELINE_DIR / "data"
FNO_FILE = PIPELINE_DIR.parent / "opus" / "config" / "fno_stocks.json"
OUTPUT_FILE = DATA_DIR / "fno_news.json"
IST = timezone(timedelta(hours=5, minutes=30))

# Top liquid F&O names that generate the most news
# (full 213 would hit rate limits; scan the most-traded subset)
TOP_FNO_NAMES = {
    "RELIANCE": "Reliance Industries",
    "HDFCBANK": "HDFC Bank",
    "ICICIBANK": "ICICI Bank",
    "INFY": "Infosys",
    "TCS": "TCS",
    "BHARTIARTL": "Bharti Airtel",
    "SBIN": "SBI",
    "BAJFINANCE": "Bajaj Finance",
    "AXISBANK": "Axis Bank",
    "KOTAKBANK": "Kotak Bank",
    "LT": "Larsen Toubro",
    "MARUTI": "Maruti Suzuki",
    "HCLTECH": "HCL Tech",
    "SUNPHARMA": "Sun Pharma",
    "TITAN": "Titan Company",
    "ADANIENT": "Adani Enterprises",
    "ADANIPORTS": "Adani Ports",
    "TATASTEEL": "Tata Steel",
    "HINDUNILVR": "Hindustan Unilever",
    "ITC": "ITC",
    "WIPRO": "Wipro",
    "CIPLA": "Cipla",
    "COALINDIA": "Coal India",
    "HAL": "HAL Defence",
    "BEL": "BEL Defence",
    "NTPC": "NTPC Power",
    "ONGC": "ONGC",
    "GAIL": "GAIL India",
    "BPCL": "BPCL",
    "TATAMOTORS": "Tata Motors",
    "M&M": "Mahindra",
    "ASIANPAINT": "Asian Paints",
    "TECHM": "Tech Mahindra",
    "DLF": "DLF Real Estate",
    "VEDL": "Vedanta",
    "INDIGO": "IndiGo Airlines",
    "DRREDDY": "Dr Reddys",
    "JSWSTEEL": "JSW Steel",
    "TATAPOWER": "Tata Power",
    "PNB": "PNB",
}


def fetch_google_news(query: str, max_items: int = 5) -> list[dict]:
    """Fetch news from Google News RSS for a query. Free, no API key."""
    url = (
        f"https://news.google.com/rss/search?q={quote(query)}+India+stock+when:1d"
        "&hl=en-IN&gl=IN&ceid=IN:en"
    )
    try:
        resp = requests.get(url, timeout=8, headers={
            "User-Agent": "Mozilla/5.0 (compatible; AnkaResearch/1.0)"
        })
        resp.raise_for_status()

        root = ET.fromstring(resp.text)
        items = []
        for item in root.findall(".//item"):
            title = item.findtext("title", "")
            link = item.findtext("link", "")
            pub_date = item.findtext("pubDate", "")
            source_el = item.find("source")
            source = source_el.text if source_el is not None else ""

            items.append({
                "title": title,
                "url": link,
                "source": source,
                "published_at": pub_date,
            })
            if len(items) >= max_items:
                break
        return items
    except Exception as exc:
        log.warning("Google News RSS failed for %s: %s", query, exc)
        return []


def scan_fno_news(top_n: int = 40) -> list[dict]:
    """Scan news for top F&O stocks."""
    all_news = []
    stocks = dict(list(TOP_FNO_NAMES.items())[:top_n])

    for i, (symbol, name) in enumerate(stocks.items()):
        items = fetch_google_news(name, max_items=3)
        for item in items:
            item["symbol"] = symbol
            item["stock_name"] = name
            all_news.append(item)

        if (i + 1) % 10 == 0:
            log.info("Scanned %d/%d stocks, %d headlines so far", i + 1, len(stocks), len(all_news))
            time.sleep(1)  # Courtesy pause

    # Deduplicate by title
    seen = set()
    unique = []
    for item in all_news:
        key = item["title"].lower()[:80]
        if key not in seen:
            seen.add(key)
            unique.append(item)

    # Sort by recency (newest first)
    unique.sort(key=lambda x: x.get("published_at", ""), reverse=True)

    log.info("Total unique headlines: %d from %d stocks", len(unique), len(stocks))
    return unique


def save_news(news: list[dict]):
    """Save to data/fno_news.json."""
    output = {
        "updated_at": datetime.now(IST).isoformat(),
        "count": len(news),
        "headlines": news,
    }
    OUTPUT_FILE.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    log.info("Saved %d headlines to %s", len(news), OUTPUT_FILE)


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--top", type=int, default=40, help="Number of top stocks to scan")
    args = parser.parse_args()

    log.info("Scanning F&O stock news (top %d stocks)...", args.top)
    news = scan_fno_news(top_n=args.top)
    save_news(news)


if __name__ == "__main__":
    main()
