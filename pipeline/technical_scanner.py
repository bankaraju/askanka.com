"""
Anka Research Pipeline — Technical Scanner
Computes RSI, 20DMA, 50DMA, trend, and signal classification for all
stocks used in INDIA_SPREAD_PAIRS.

Outputs: data/technicals.json
"""

import json
import logging
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from statistics import mean
from typing import Optional

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("anka.technical_scanner")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_PIPELINE_DIR = Path(__file__).parent
_DATA_DIR = _PIPELINE_DIR / "data"
_DATA_DIR.mkdir(parents=True, exist_ok=True)
_OUTPUT = _DATA_DIR / "technicals.json"

IST = timezone(timedelta(hours=5, minutes=30))


# ---------------------------------------------------------------------------
# Core indicator functions
# ---------------------------------------------------------------------------

def compute_rsi(closes: list[float], period: int = 14) -> float:
    """
    Standard RSI calculation using average gains and losses.

    Args:
        closes:  List of closing prices (oldest first).
        period:  RSI lookback period (default 14).

    Returns:
        RSI as a float in [0, 100].
        Returns 50.0 if there are fewer than period+1 data points.
        Returns 100.0 if there are no losses in the window.
        Returns ~0.0 if there are no gains in the window.
    """
    if len(closes) < period + 1:
        return 50.0

    # Use the most recent `period` changes
    changes = [closes[i] - closes[i - 1] for i in range(len(closes) - period, len(closes))]

    gains = [c for c in changes if c > 0]
    losses = [abs(c) for c in changes if c < 0]

    avg_gain = mean(gains) if gains else 0.0
    avg_loss = mean(losses) if losses else 0.0

    if avg_loss == 0:
        return 100.0

    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def classify_signal(rsi: float, vs_20dma: float, trend_5d: float) -> str:
    """
    Classify technical posture based on RSI, deviation from 20DMA, and 5-day trend.

    Args:
        rsi:       14-period RSI value.
        vs_20dma:  % deviation above/below the 20-day moving average.
        trend_5d:  % price change over the last 5 days.

    Returns:
        One of: "OVERBOUGHT", "OVERSOLD", "BULLISH", "BEARISH", "NEUTRAL"
    """
    if rsi > 70 and vs_20dma > 3:
        return "OVERBOUGHT"
    if rsi < 30 and vs_20dma < -3:
        return "OVERSOLD"
    if rsi > 60 and trend_5d > 2:
        return "BULLISH"
    if rsi < 40 and trend_5d < -2:
        return "BEARISH"
    return "NEUTRAL"


# ---------------------------------------------------------------------------
# Main scan
# ---------------------------------------------------------------------------

def _get_unique_symbols() -> list[str]:
    """Extract all unique stock symbols from INDIA_SPREAD_PAIRS."""
    from config import INDIA_SPREAD_PAIRS

    seen: set[str] = set()
    symbols: list[str] = []
    for spread in INDIA_SPREAD_PAIRS:
        for sym in spread.get("long", []) + spread.get("short", []):
            if sym not in seen:
                seen.add(sym)
                symbols.append(sym)
    return symbols


def _fetch_candles(kite, token: int, days: int = 75) -> list[dict]:
    """Fetch daily candles from Kite for the given token."""
    end = date.today()
    start = end - timedelta(days=days)
    try:
        candles = kite.historical_data(token, start, end, "day")
        return candles or []
    except Exception as exc:
        log.warning("historical_data failed for token %d: %s", token, exc)
        return []


def scan_technicals() -> dict:
    """
    Main scan: compute technical indicators for all INDIA_SPREAD_PAIRS stocks.

    Returns a dict with structure:
      {
        "timestamp": "<ISO datetime>",
        "stocks": {
          "<SYMBOL>": {
            "ltp":          float | None,
            "rsi_14":       float,
            "dma_20":       float | None,
            "dma_50":       float | None,
            "vs_20dma_pct": float | None,
            "vs_50dma_pct": float | None,
            "trend_5d_pct": float | None,
            "signal":       str,
          },
          ...
        }
      }
    """
    from kite_client import get_kite, resolve_token, _ensure_instrument_master

    kite = get_kite()
    _ensure_instrument_master()

    symbols = _get_unique_symbols()
    log.info("Scanning %d unique symbols from INDIA_SPREAD_PAIRS", len(symbols))

    results: dict[str, dict] = {}

    for sym in symbols:
        log.info("Processing %s ...", sym)
        token = resolve_token(sym)

        if token is None:
            log.warning("No token for %s — skipping", sym)
            results[sym] = {
                "ltp": None,
                "rsi_14": 50.0,
                "dma_20": None,
                "dma_50": None,
                "vs_20dma_pct": None,
                "vs_50dma_pct": None,
                "trend_5d_pct": None,
                "signal": "NEUTRAL",
                "error": "no_token",
            }
            continue

        candles = _fetch_candles(kite, token, days=75)

        if not candles:
            log.warning("No candles for %s — skipping", sym)
            results[sym] = {
                "ltp": None,
                "rsi_14": 50.0,
                "dma_20": None,
                "dma_50": None,
                "vs_20dma_pct": None,
                "vs_50dma_pct": None,
                "trend_5d_pct": None,
                "signal": "NEUTRAL",
                "error": "no_candles",
            }
            continue

        closes = [c["close"] for c in candles if "close" in c]

        ltp = closes[-1] if closes else None

        rsi_14 = compute_rsi(closes, period=14)

        # Moving averages (use as many candles as available, up to N)
        dma_20: Optional[float] = mean(closes[-20:]) if len(closes) >= 20 else None
        dma_50: Optional[float] = mean(closes[-50:]) if len(closes) >= 50 else None

        vs_20dma_pct: Optional[float] = None
        vs_50dma_pct: Optional[float] = None
        trend_5d_pct: Optional[float] = None

        if ltp is not None and dma_20 is not None and dma_20 != 0:
            vs_20dma_pct = round((ltp - dma_20) / dma_20 * 100, 2)

        if ltp is not None and dma_50 is not None and dma_50 != 0:
            vs_50dma_pct = round((ltp - dma_50) / dma_50 * 100, 2)

        if len(closes) >= 6:
            price_5d_ago = closes[-6]  # 5 trading days back
            if price_5d_ago != 0:
                trend_5d_pct = round((ltp - price_5d_ago) / price_5d_ago * 100, 2)

        signal = classify_signal(
            rsi=rsi_14,
            vs_20dma=vs_20dma_pct if vs_20dma_pct is not None else 0.0,
            trend_5d=trend_5d_pct if trend_5d_pct is not None else 0.0,
        )

        results[sym] = {
            "ltp": round(ltp, 2) if ltp is not None else None,
            "rsi_14": round(rsi_14, 2),
            "dma_20": round(dma_20, 2) if dma_20 is not None else None,
            "dma_50": round(dma_50, 2) if dma_50 is not None else None,
            "vs_20dma_pct": vs_20dma_pct,
            "vs_50dma_pct": vs_50dma_pct,
            "trend_5d_pct": trend_5d_pct,
            "signal": signal,
        }
        log.info(
            "  %s: LTP=%.2f RSI=%.1f vs20DMA=%s%% signal=%s",
            sym,
            ltp or 0,
            rsi_14,
            vs_20dma_pct,
            signal,
        )

    output = {
        "timestamp": datetime.now(IST).isoformat(),
        "stocks": results,
    }

    _OUTPUT.write_text(json.dumps(output, indent=2), encoding="utf-8")
    log.info("Saved technical scan to %s", _OUTPUT)
    return output


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    result = scan_technicals()
    log.info(
        "Scan complete — %d stocks processed",
        len(result.get("stocks", {})),
    )
