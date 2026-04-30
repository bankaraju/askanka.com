"""GET /api/news/macro and GET /api/news/{ticker} — news feeds.

Source priority:
  1. data/fno_news.json — populated by morning_scan; preferred when fresh.
  2. pipeline/data/news_verdicts.json — backstop populated by the
     news-impact engine, **filtered to today's IST date only**. Falling
     through to yesterday's verdicts is exactly the silent-staleness
     failure mode that bit 2026-04-30 (dashboard showed 04-29 NO_IMPACT
     items because EOD clobbered fno_news.json before today's verdicts
     ran at 16:20).
"""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from fastapi import APIRouter

router = APIRouter()

_HERE = Path(__file__).resolve().parent.parent
_FNO_NEWS_FILE = _HERE.parent.parent / "data" / "fno_news.json"
_VERDICTS_FILE = _HERE.parent / "data" / "news_verdicts.json"
_IST = timezone(timedelta(hours=5, minutes=30))


def _read_json(path: Path, default=None):
    if default is None:
        default = {}
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _items_from_fno(raw) -> list:
    if not raw:
        return []
    items = raw if isinstance(raw, list) else raw.get("headlines", raw.get("items", raw.get("news", [])))
    out = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        if "headline" not in item and "title" in item:
            item["headline"] = item["title"]
        out.append(item)
    return out


def _items_from_verdicts(raw) -> list:
    """Map news_verdicts.json rows into the macro-news shape the UI expects."""
    if not isinstance(raw, list):
        return []
    out = []
    for v in raw:
        if not isinstance(v, dict):
            continue
        title = v.get("event_title") or ""
        if not title:
            continue
        symbol = v.get("symbol") or ""
        impact = v.get("impact") or ""
        out.append({
            "headline": title,
            "title": title,
            "symbol": symbol,
            "ticker": symbol,
            "category": v.get("category") or "",
            "impact": impact,
            "recommendation": v.get("recommendation") or "",
            "direction": v.get("direction"),
            "published_at": v.get("event_date") or "",
            "date": v.get("event_date") or "",
            "source": "news_verdicts",
        })
    out.sort(key=lambda x: x.get("date") or "", reverse=True)
    return out


def _today_ist() -> str:
    return datetime.now(_IST).strftime("%Y-%m-%d")


def _filter_to_today(items: list) -> list:
    """Drop items whose published_at/date isn't today (IST). Items missing
    a date are kept — pre-empting silent fall-through to yesterday's data
    matters more than perfect coverage of legacy rows.
    """
    today = _today_ist()
    out = []
    for item in items:
        if not isinstance(item, dict):
            continue
        d = (item.get("date") or item.get("published_at") or "")[:10]
        if d and d != today:
            continue
        out.append(item)
    return out


def _load_items() -> list:
    items = _items_from_fno(_read_json(_FNO_NEWS_FILE, default=[]))
    if items:
        return items
    # Backstop: only fall through to verdicts if today's verdicts exist.
    # Yesterday's NO_IMPACT items are not "news" — they're stale rows
    # presented as fresh, which is the bug pattern we're guarding against.
    verdict_items = _items_from_verdicts(_read_json(_VERDICTS_FILE, default=[]))
    return _filter_to_today(verdict_items)


@router.get("/news/macro")
def news_macro():
    items = _load_items()
    return {"items": items[:50], "total": len(items)}


@router.get("/news/{ticker}")
def news_stock(ticker: str):
    ticker = ticker.upper()
    items = _load_items()
    filtered = [item for item in items if _matches_ticker(item, ticker)]
    return {"ticker": ticker, "items": filtered[:20], "total": len(filtered)}


def _matches_ticker(item: dict, ticker: str) -> bool:
    text = json.dumps(item).upper()
    return ticker in text
