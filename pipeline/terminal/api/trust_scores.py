"""GET /api/trust-scores — full trust score universe."""
import json
from pathlib import Path
from fastapi import APIRouter

router = APIRouter()

_HERE = Path(__file__).resolve().parent.parent
_TRUST_FILE = _HERE.parent.parent / "data" / "trust_scores.json"


def _read_json(path: Path, default=None):
    if default is None:
        default = {}
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


@router.get("/trust-scores")
def trust_scores():
    raw = _read_json(_TRUST_FILE)
    stocks = raw.get("stocks", [])
    return {
        "stocks": stocks,
        "total": len(stocks),
        "updated_at": raw.get("updated_at"),
    }


@router.get("/trust-scores/{ticker}")
def trust_score_detail(ticker: str):
    ticker = ticker.upper()
    raw = _read_json(_TRUST_FILE)
    for s in raw.get("stocks", []):
        if (s.get("symbol") or "").upper() == ticker:
            return s
    return {"symbol": ticker, "trust_grade": "?", "trust_score": None, "thesis": "Not scored"}
