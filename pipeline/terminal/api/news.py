"""GET /api/news/macro and GET /api/news/{ticker} — news feeds."""
import json
from pathlib import Path
from fastapi import APIRouter

router = APIRouter()

_HERE = Path(__file__).resolve().parent.parent
_FNO_NEWS_FILE = _HERE.parent.parent / "data" / "fno_news.json"


def _read_json(path: Path, default=None):
    if default is None:
        default = {}
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


@router.get("/news/macro")
def news_macro():
    raw = _read_json(_FNO_NEWS_FILE, default=[])
    items = raw if isinstance(raw, list) else raw.get("items", raw.get("news", []))
    return {"items": items[:50], "total": len(items)}


@router.get("/news/{ticker}")
def news_stock(ticker: str):
    ticker = ticker.upper()
    raw = _read_json(_FNO_NEWS_FILE, default=[])
    items = raw if isinstance(raw, list) else raw.get("items", raw.get("news", []))

    filtered = [item for item in items if _matches_ticker(item, ticker)]
    return {"ticker": ticker, "items": filtered[:20], "total": len(filtered)}


def _matches_ticker(item: dict, ticker: str) -> bool:
    text = json.dumps(item).upper()
    return ticker in text
