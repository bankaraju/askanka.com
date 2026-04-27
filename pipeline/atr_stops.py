"""ATR-based stop computation for single-ticker directional trades.

Correlation-break signals (LONG BHEL, SHORT YESBANK, etc.) are not spreads
and the `spread_statistics` default of `-(avg_favorable*0.5) = -1.00%` is
a one-size-fits-all fallback that under-stops volatile names and over-stops
quiet ones. This module computes per-ticker stops from 14-day ATR * 2.0.

Convention for `stop_pct`:
    Signed P&L impact at which the trade stops out.
    LONG  => negative (price drops below entry - 2*ATR)
    SHORT => negative (price rises above entry + 2*ATR — a short-squeeze loss)

Fallback: on any fetch/compute failure, returns stop_pct=-1.0 with
    source="fallback" — matches existing behaviour, flagged so UI can
    surface that these aren't real data-driven stops.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import pandas as pd

log = logging.getLogger("anka.atr_stops")

_FALLBACK_PCT = -1.0  # matches legacy spread_statistics default


def _fetch_ohlc(symbol: str, period_days: int = 60) -> pd.DataFrame:
    """Thin wrapper around yfinance so tests can monkeypatch.

    Returns a DataFrame with at least columns High / Low / Close, most
    recent day last. Empty DataFrame on failure.
    """
    import yfinance as yf
    ticker = f"{symbol}.NS"
    df = yf.Ticker(ticker).history(period=f"{period_days}d")
    if df is None or df.empty:
        return pd.DataFrame()
    return df[["High", "Low", "Close"]].dropna()


def _compute_atr(df: pd.DataFrame, window: int) -> Optional[float]:
    """True Range = max(H-L, |H-prevC|, |L-prevC|); ATR = simple mean of last `window` TRs."""
    if len(df) < window + 1:
        return None
    h, l, c = df["High"], df["Low"], df["Close"]
    prev_c = c.shift(1)
    tr = pd.concat([
        (h - l).abs(),
        (h - prev_c).abs(),
        (l - prev_c).abs(),
    ], axis=1).max(axis=1)
    atr = tr.tail(window).mean()
    return float(atr) if pd.notna(atr) else None


def compute_atr_stop(
    symbol: str,
    direction: str,
    window: int = 14,
    mult: float = 2.0,
    max_abs_pct: float | None = None,
) -> Dict[str, Any]:
    """Return {stop_pct, stop_price, atr_14, stop_source} for a single-ticker trade.

    `direction` must be "LONG" or "SHORT". `stop_pct` is SIGNED P&L impact:
    always negative, meaning "stop triggers when the trade's own P&L reaches this %".

    If `max_abs_pct` is provided, |stop_pct| is capped at that value (with
    `stop_price` recomputed to match). Used by intraday Phase C breaks where a
    high-vol name's full 2×ATR stop would land outside the 5-hour close horizon.
    """
    assert direction in ("LONG", "SHORT"), f"invalid direction: {direction}"
    try:
        df = _fetch_ohlc(symbol)
    except Exception as exc:
        log.warning("atr_stop: ohlc fetch failed for %s: %s", symbol, exc)
        return {"stop_pct": _FALLBACK_PCT, "stop_price": None,
                "atr_14": None, "stop_source": "fallback"}

    if df.empty or len(df) < window + 1:
        log.warning("atr_stop: insufficient bars for %s (have %d, need %d)",
                    symbol, len(df), window + 1)
        return {"stop_pct": _FALLBACK_PCT, "stop_price": None,
                "atr_14": None, "stop_source": "fallback"}

    atr = _compute_atr(df, window)
    if atr is None or atr <= 0:
        return {"stop_pct": _FALLBACK_PCT, "stop_price": None,
                "atr_14": None, "stop_source": "fallback"}

    last_close = float(df["Close"].iloc[-1])
    if direction == "LONG":
        stop_price = last_close - mult * atr
        stop_pct = (stop_price - last_close) / last_close * 100.0
    else:  # SHORT
        stop_price = last_close + mult * atr
        stop_pct = -(stop_price - last_close) / last_close * 100.0

    capped = False
    if max_abs_pct is not None and abs(stop_pct) > max_abs_pct:
        capped = True
        stop_pct = -max_abs_pct
        if direction == "LONG":
            stop_price = last_close * (1.0 - max_abs_pct / 100.0)
        else:
            stop_price = last_close * (1.0 + max_abs_pct / 100.0)

    return {
        "stop_pct": round(stop_pct, 2),
        "stop_price": round(stop_price, 2),
        "atr_14": round(atr, 2),
        "stop_source": f"atr_{window}_capped" if capped else f"atr_{window}",
    }
