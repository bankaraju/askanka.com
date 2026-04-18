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
    fp_file = _FINGERPRINTS_DIR / f"{ticker}.json"
    if not fp_file.exists():
        fp_file = _FINGERPRINTS_DIR / f"{ticker}_fingerprint.json"

    if not fp_file.exists():
        raise HTTPException(status_code=404, detail=f"No TA fingerprint for {ticker}")

    try:
        data = json.loads(fp_file.read_text(encoding="utf-8"))
    except Exception:
        raise HTTPException(status_code=500, detail=f"Error reading fingerprint for {ticker}")

    patterns = data.get("fingerprint", data.get("patterns", []))

    return {
        "ticker": ticker,
        "patterns": patterns,
        "active_patterns": [p for p in patterns if p.get("significance") in ("STRONG", "MODERATE")],
        "personality": data.get("personality"),
        "best_pattern": data.get("best_pattern"),
        "best_win_rate": data.get("best_win_rate"),
        "significant_count": data.get("significant_patterns", 0),
        "updated_at": data.get("generated") or data.get("generated_at"),
    }
