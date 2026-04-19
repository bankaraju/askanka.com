"""GET /api/oi — per-stock open interest + PCR + pinning + walls.

Reads from pipeline/data/positioning.json (written every 15 min by oi_scanner.py).
"""
import json
from pathlib import Path
from fastapi import APIRouter, Query

router = APIRouter()

_PIPELINE = Path(__file__).resolve().parent.parent.parent
_POSITIONING = _PIPELINE / "data" / "positioning.json"


def _load() -> dict:
    if not _POSITIONING.exists():
        return {}
    try:
        return json.loads(_POSITIONING.read_text(encoding="utf-8"))
    except Exception:
        return {}


@router.get("/oi")
def oi_list(
    sentiment: str = Query(None),
    pin_label: str = Query(None),
    limit: int = Query(500),
):
    """List OI summaries for all scanned stocks.

    Query params:
      sentiment  — filter by sentiment (BULLISH, MILD_BULL, NEUTRAL, MILD_BEAR, BEARISH)
      pin_label  — filter by pinning label (STRONG_PIN, MILD_PIN, FAR, UNRELIABLE)
      limit      — cap results (default 500)
    """
    data = _load()
    rows = list(data.values())

    if sentiment:
        wanted = {s.strip().upper() for s in sentiment.split(",")}
        rows = [r for r in rows if (r.get("sentiment") or "").upper() in wanted]

    if pin_label:
        wanted = {s.strip().upper() for s in pin_label.split(",")}
        rows = [r for r in rows if ((r.get("pinning") or {}).get("pin_label") or "").upper() in wanted]

    rows.sort(key=lambda r: abs((r.get("pinning") or {}).get("pin_distance_pct") or 99), reverse=False)

    timestamps = [r.get("timestamp") for r in rows if r.get("timestamp")]
    return {
        "count": min(len(rows), limit),
        "total": len(rows),
        "updated_at": max(timestamps) if timestamps else None,
        "rows": rows[:limit],
    }


@router.get("/oi/{ticker}")
def oi_detail(ticker: str):
    """Full OI snapshot for one ticker including near + next expiry."""
    data = _load()
    row = data.get(ticker.upper())
    if not row:
        return {"symbol": ticker.upper(), "found": False}
    return {"found": True, **row}


@router.get("/oi/pins/top")
def oi_top_pins(limit: int = Query(20)):
    """Stocks most strongly pinned (closest to pin + highest pin_strength, soon-to-expire)."""
    data = _load()
    rows = []
    for r in data.values():
        p = r.get("pinning") or {}
        if p.get("pin_label") not in ("STRONG_PIN", "MILD_PIN"):
            continue
        rows.append({
            "symbol": r.get("symbol"),
            "ltp": r.get("ltp"),
            "expiry": r.get("expiry"),
            "pin_strike": p.get("pin_strike"),
            "pin_distance_pct": p.get("pin_distance_pct"),
            "days_to_expiry": p.get("days_to_expiry"),
            "pin_strength": p.get("pin_strength"),
            "pin_label": p.get("pin_label"),
            "pcr": r.get("pcr"),
            "sentiment": r.get("sentiment"),
        })

    # Rank: STRONG_PIN before MILD_PIN, then lower DTE, then higher pin_strength
    label_rank = {"STRONG_PIN": 0, "MILD_PIN": 1}
    rows.sort(key=lambda r: (
        label_rank.get(r["pin_label"], 9),
        r["days_to_expiry"] if r["days_to_expiry"] is not None else 99,
        -(r["pin_strength"] or 0),
    ))
    return {"count": len(rows[:limit]), "rows": rows[:limit]}
