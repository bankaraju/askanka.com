"""GET /api/news/macro and GET /api/news/{ticker} — news feeds.

Source priority:
  1. data/fno_news.json — populated by morning_scan; preferred when fresh.
  2. pipeline/data/news_verdicts.json — backstop populated by the
     news-impact engine. Always fresh (refreshed at 16:20 IST), so it
     keeps the News tab populated even when fno_news.json is clobbered
     to empty (recurring bug — see memory project_news_intelligence).
"""
import json
from pathlib import Path
from fastapi import APIRouter

router = APIRouter()

_HERE = Path(__file__).resolve().parent.parent
_FNO_NEWS_FILE = _HERE.parent.parent / "data" / "fno_news.json"
_VERDICTS_FILE = _HERE.parent / "data" / "news_verdicts.json"


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


def _load_items() -> list:
    items = _items_from_fno(_read_json(_FNO_NEWS_FILE, default=[]))
    if items:
        return items
    return _items_from_verdicts(_read_json(_VERDICTS_FILE, default=[]))


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
