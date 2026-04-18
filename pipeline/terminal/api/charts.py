"""GET /api/charts/{ticker} — OHLCV data for Lightweight Charts."""
import json
from pathlib import Path
from fastapi import APIRouter, HTTPException

router = APIRouter()

_HERE = Path(__file__).resolve().parent.parent
_DAILY_DIR = _HERE.parent / "data" / "daily"


@router.get("/charts/{ticker}")
def charts(ticker: str):
    ticker = ticker.upper()
    candles = []

    if not _DAILY_DIR.exists():
        raise HTTPException(status_code=404, detail=f"Daily data directory not found")

    for f in sorted(_DAILY_DIR.glob("*.json")):
        if "_fundamentals" in f.name:
            continue
        try:
            raw = json.loads(f.read_text(encoding="utf-8"))
            stocks = raw if isinstance(raw, list) else raw.get("stocks", raw.get("data", []))
            if isinstance(stocks, dict):
                stock = stocks.get(ticker, {})
                if stock:
                    candle = _extract_candle(f.stem, stock)
                    if candle:
                        candles.append(candle)
            elif isinstance(stocks, list):
                for s in stocks:
                    sym = s.get("symbol") or s.get("ticker") or ""
                    if sym.upper() == ticker or sym.upper().replace(".NS", "") == ticker:
                        candle = _extract_candle(f.stem, s)
                        if candle:
                            candles.append(candle)
                            break
        except Exception:
            continue

    if not candles:
        raise HTTPException(status_code=404, detail=f"No chart data for {ticker}")

    candles.sort(key=lambda c: c["time"])
    return {"ticker": ticker, "candles": candles, "count": len(candles)}


def _extract_candle(date_str: str, data: dict) -> dict | None:
    close = data.get("close") or data.get("Close") or data.get("last_price")
    if close is None:
        return None
    return {
        "time": date_str[:10],
        "open": data.get("open") or data.get("Open") or close,
        "high": data.get("high") or data.get("High") or close,
        "low": data.get("low") or data.get("Low") or close,
        "close": close,
        "volume": data.get("volume") or data.get("Volume") or 0,
    }
