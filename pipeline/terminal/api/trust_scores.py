"""GET /api/trust-scores — Scorecard V2 with sector context."""
import json
from pathlib import Path
from fastapi import APIRouter, Query

router = APIRouter()

_HERE = Path(__file__).resolve().parent.parent
_V2_FILE = _HERE.parent.parent / "data" / "trust_scores_v2.json"
_V1_FILE = _HERE.parent.parent / "data" / "trust_scores.json"


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
def trust_scores(sector: str = Query(None), grade: str = Query(None)):
    raw = _read_json(_V2_FILE) if _V2_FILE.exists() else _read_json(_V1_FILE)
    stocks = raw.get("stocks", [])

    if sector:
        stocks = [s for s in stocks if s.get("sector", "").lower() == sector.lower()]
    if grade:
        grades = set(g.strip().upper() for g in grade.split(","))
        stocks = [s for s in stocks if s.get("sector_grade", s.get("trust_grade", "?")).upper() in grades]

    return {
        "stocks": stocks,
        "total": len(stocks),
        "updated_at": raw.get("updated_at"),
        "version": raw.get("version", "1.0"),
    }


@router.get("/trust-scores/sectors")
def trust_score_sectors():
    raw = _read_json(_V2_FILE) if _V2_FILE.exists() else _read_json(_V1_FILE)
    stocks = raw.get("stocks", [])
    sectors = {}
    for s in stocks:
        sec = s.get("sector", "Unknown")
        if sec not in sectors:
            sectors[sec] = {"name": s.get("display_name", sec), "count": 0}
        sectors[sec]["count"] += 1
    return {"sectors": sectors}


@router.get("/trust-scores/{ticker}")
def trust_score_detail(ticker: str):
    ticker = ticker.upper()
    raw = _read_json(_V2_FILE) if _V2_FILE.exists() else _read_json(_V1_FILE)
    for s in raw.get("stocks", []):
        if (s.get("symbol") or "").upper() == ticker:
            return s
    return {"symbol": ticker, "sector_grade": "?", "composite_score": None, "grade_reason": "Not scored"}
