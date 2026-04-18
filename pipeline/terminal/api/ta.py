"""GET /api/ta/{ticker} — TA fingerprint for a stock."""
import json
from pathlib import Path
from fastapi import APIRouter, HTTPException

router = APIRouter()

_HERE = Path(__file__).resolve().parent.parent
_FINGERPRINTS_DIR = _HERE.parent / "data" / "ta_fingerprints"


@router.get("/ta/{ticker}")
def ta(ticker: str):
    ticker = ticker.upper()
    fp_file = _FINGERPRINTS_DIR / f"{ticker}_fingerprint.json"

    if not fp_file.exists():
        raise HTTPException(status_code=404, detail=f"No TA fingerprint for {ticker}")

    try:
        data = json.loads(fp_file.read_text(encoding="utf-8"))
    except Exception:
        raise HTTPException(status_code=500, detail=f"Error reading fingerprint for {ticker}")

    return {
        "ticker": ticker,
        "patterns": data.get("patterns", []),
        "active_patterns": [p for p in data.get("patterns", []) if p.get("active", False)],
        "summary": data.get("summary", {}),
        "updated_at": data.get("generated_at") or data.get("timestamp"),
    }
