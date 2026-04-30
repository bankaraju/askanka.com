"""Live LTP endpoint — 5s-pollable current prices.

/api/live_ltp?tickers=HAL,BEL,TCS → {ticker: last_price, ...}
/api/options/live_ltp?tradingsymbols=RELIANCE26APR2400PE,HAL26APR4300CE
    → {tradingsymbol: {ltp, bid, ask}, ...}

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
    from pipeline.signal_tracker import fetch_current_prices
    return fetch_current_prices(tickers) or {}


_MAX_TICKERS = 50


@router.get("/live_ltp")
def live_ltp(tickers: str = Query(...)):
    requested = [t.strip().upper() for t in tickers.split(",") if t.strip()]
    if not requested:
        raise HTTPException(400, "tickers parameter is empty")
    if len(requested) > _MAX_TICKERS:
        raise HTTPException(400, f"max {_MAX_TICKERS} tickers per request (got {len(requested)})")
    prices = fetch_ltps(requested)
    # Unknown tickers return null (not 0.0) so the frontend falls back to
    # the live_status.json snapshot value instead of painting a fake ₹0.00.
    return {t: (float(prices[t]) if t in prices and prices[t] is not None else None)
            for t in requested}


# ---------------------------------------------------------------------------
# Options live LTP — Phase B for the Phase C paired-shadow ledger.
# Kite's quote() endpoint accepts NFO:<tradingsymbol> keys and returns
# last_price + bid/ask depth. We surface ltp + best bid + best ask so the
# frontend can show "live feel" + a live MTM P&L computed against entry_mid.
# ---------------------------------------------------------------------------

_MAX_OPTIONS = 50  # Kite quote() handles 200; we cap lower for latency.


def fetch_option_quotes(tradingsymbols: list[str]) -> dict[str, dict]:
    """Resolve NFO tradingsymbols -> {tradingsymbol: {ltp, bid, ask}}.

    Module-level shim so tests can monkeypatch without standing up Kite.
    Returns an empty dict on session/network failure — the endpoint then
    surfaces nulls so the frontend keeps the snapshot values visible
    instead of painting fake zeros.
    """
    try:
        from pipeline.kite_client import get_kite
        kite = get_kite()
    except Exception:
        return {}
    keys = [f"NFO:{ts}" for ts in tradingsymbols]
    try:
        resp = kite.quote(keys) or {}
    except Exception:
        return {}
    out: dict[str, dict] = {}
    for key, data in resp.items():
        ts = key.split(":", 1)[-1]
        ltp = data.get("last_price")
        depth = (data.get("depth") or {}) if isinstance(data, dict) else {}
        bid_list = depth.get("buy") or []
        ask_list = depth.get("sell") or []
        bid = bid_list[0].get("price") if bid_list else None
        ask = ask_list[0].get("price") if ask_list else None
        out[ts] = {
            "ltp": float(ltp) if ltp is not None else None,
            "bid": float(bid) if bid is not None else None,
            "ask": float(ask) if ask is not None else None,
        }
    return out


@router.get("/options/live_ltp")
def options_live_ltp(tradingsymbols: str = Query(...)):
    requested = [t.strip().upper() for t in tradingsymbols.split(",") if t.strip()]
    if not requested:
        raise HTTPException(400, "tradingsymbols parameter is empty")
    if len(requested) > _MAX_OPTIONS:
        raise HTTPException(
            400,
            f"max {_MAX_OPTIONS} tradingsymbols per request (got {len(requested)})",
        )
    quotes = fetch_option_quotes(requested)
    # Missing tradingsymbols (delisted, illiquid, bad NFO key) get null
    # entries so the frontend keeps the snapshot value visible.
    return {ts: quotes.get(ts) for ts in requested}
