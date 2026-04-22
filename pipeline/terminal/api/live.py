"""Live LTP endpoint — 5s-pollable current prices.

/api/live_ltp?tickers=HAL,BEL,TCS → {ticker: last_price, ...}

Backed by the same Kite session signal_tracker uses for batch fetches.
The public `live_status.json` snapshot stays the source-of-truth for
entry prices, stops, and P&L; this endpoint is a presentation-layer
refresh to keep LTPs from looking frozen between 15-min batches.

Route decorator uses no /api prefix because pipeline/terminal/app.py
mounts every router with prefix="/api" (convention).
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query


router = APIRouter()


def fetch_ltps(tickers: list[str]) -> dict[str, float]:
    """Resolve tickers -> LTPs via signal_tracker's Kite-backed fetch.

    Split out as a module-level shim so tests can monkeypatch without
    reaching into signal_tracker internals.
    """
    try:
        from signal_tracker import fetch_current_prices
    except ImportError:
        from pipeline.signal_tracker import fetch_current_prices
    result = fetch_current_prices(tickers) or {}
    return result


_MAX_TICKERS = 50


@router.get("/live_ltp")
def live_ltp(tickers: str = Query(...)):
    requested = [t.strip().upper() for t in tickers.split(",") if t.strip()]
    if not requested:
        raise HTTPException(400, "tickers parameter is empty")
    if len(requested) > _MAX_TICKERS:
        raise HTTPException(400, f"max {_MAX_TICKERS} tickers per request (got {len(requested)})")
    prices = fetch_ltps(requested)
    return {t: float(prices.get(t, 0.0)) for t in requested}
