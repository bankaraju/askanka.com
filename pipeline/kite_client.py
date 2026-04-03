"""
Anka Research Pipeline — Kite Connect Data Client
Primary source for all Indian market live prices and historical candles.

Replaces eodhd_client + yfinance for NSE stocks, indices, and MCX commodities.
EODHD remains for global indices (S&P 500, Nikkei, USD/INR).

Key functions:
  fetch_ltp(symbols)          → {ticker: last_price}   (live, from Kite)
  fetch_historical(sym, ...)  → list[OHLCV dict]        (Kite candles)
  get_kite()                  → authenticated KiteConnect instance

Instrument token resolution:
  - Downloads NSE + MCX instrument master from Kite on first call, caches for the day
  - Plain tickers ("HAL", "NIFTY BANK") resolved automatically
  - MCX: picks nearest active expiry for CRUDEOIL, GOLD, etc.

Fallback:
  - If Kite token is expired / unavailable → falls back to eodhd_client
"""

import csv
import io
import logging
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

_lib = str(Path(__file__).parent / "lib")
if _lib not in sys.path:
    sys.path.insert(0, _lib)

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

log = logging.getLogger("anka.kite_client")

IST = timezone(timedelta(hours=5, minutes=30))

# ---------------------------------------------------------------------------
# Instrument master cache
# ---------------------------------------------------------------------------

_CACHE_DIR = Path(__file__).parent / "data" / "kite_cache"
_CACHE_DIR.mkdir(parents=True, exist_ok=True)

_NSE_CACHE = _CACHE_DIR / "instruments_nse.csv"
_MCX_CACHE = _CACHE_DIR / "instruments_mcx.csv"
_INDICES_CACHE = _CACHE_DIR / "instruments_indices.csv"

# In-memory token map: {tradingsymbol_upper: instrument_token}
_TOKEN_MAP: dict[str, int] = {}
_LOADED_DATE: Optional[date] = None


def _cache_is_fresh(path: Path) -> bool:
    """True if the cache file was written today (IST)."""
    if not path.exists():
        return False
    mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=IST).date()
    return mtime == datetime.now(IST).date()


def _download_instruments(exchange: str) -> str:
    """Download Kite instrument master CSV for an exchange. Returns CSV text."""
    resp = requests.get(
        f"https://api.kite.trade/instruments/{exchange}",
        timeout=30,
    )
    resp.raise_for_status()
    return resp.text


def _ensure_instrument_master() -> None:
    """Load / refresh instrument token maps into _TOKEN_MAP."""
    global _TOKEN_MAP, _LOADED_DATE

    today = datetime.now(IST).date()
    if _LOADED_DATE == today and _TOKEN_MAP:
        return

    log.info("Loading Kite instrument master (NSE + MCX)")

    for exchange, cache_path in [
        ("NSE", _NSE_CACHE),   # includes NSE equities AND indices (segment=INDICES)
        ("MCX", _MCX_CACHE),
    ]:
        try:
            if _cache_is_fresh(cache_path):
                text = cache_path.read_text(encoding="utf-8")
            else:
                text = _download_instruments(exchange)
                cache_path.write_text(text, encoding="utf-8")
                log.debug("Refreshed %s instrument master", exchange)

            reader = csv.DictReader(io.StringIO(text))
            for row in reader:
                sym = row.get("tradingsymbol", "").upper()
                token = row.get("instrument_token", "")
                expiry_str = row.get("expiry", "")
                if sym and token:
                    try:
                        tok_int = int(token)
                    except ValueError:
                        continue
                    # For futures/options, store with expiry suffix AND without (keep nearest)
                    # Base symbol (no expiry) → keep the earliest active expiry
                    if expiry_str:
                        # Store full key e.g. "CRUDEOIL25APRFUT"
                        _TOKEN_MAP[sym] = tok_int
                        # Also store base name (e.g. "CRUDEOIL") → nearest expiry wins
                        # since CSV is sorted by expiry ascending
                        base = _strip_expiry(sym)
                        if base not in _TOKEN_MAP:
                            _TOKEN_MAP[base] = tok_int
                    else:
                        _TOKEN_MAP[sym] = tok_int

        except Exception as exc:
            log.warning("Instrument master load failed for %s: %s", exchange, exc)

    _LOADED_DATE = today
    log.info("Instrument master: %d symbols loaded", len(_TOKEN_MAP))


def _strip_expiry(sym: str) -> str:
    """
    Strip date/expiry suffix from a futures symbol.
    e.g. "CRUDEOIL25APRFUT" → "CRUDEOIL"
         "GOLD26APRFUT"     → "GOLD"
         "NIFTY25APR24500CE" → "NIFTY"
    Heuristic: strip trailing 2-digit year + 3-letter month + instrument type.
    """
    import re
    m = re.match(r"^([A-Z&]+)\d{2}[A-Z]{3}", sym)
    if m:
        return m.group(1)
    return sym


# Map from our internal ticker names to Kite tradingsymbols where they differ
_TICKER_ALIASES: dict[str, str] = {
    "HPCL":  "HINDPETRO",   # NSE ticker is HINDPETRO; our config key is HPCL
    "NIFTY": "NIFTY 50",    # Index full name in Kite
    "M&M":   "M&M",         # keep as-is (has & which is fine)
}


def resolve_token(symbol: str) -> Optional[int]:
    """Resolve a plain ticker or Kite tradingsymbol to an instrument_token.

    Examples:
      "HAL"            → NSE equity token
      "NIFTY BANK"     → NSE index token (segment=INDICES in NSE master)
      "INDIA VIX"      → NSE index token
      "CRUDEOIL"       → MCX nearest front-month future token
      "CRUDEOIL26APRFUT" → exact MCX future token
    """
    _ensure_instrument_master()

    # Apply alias mapping first
    kite_sym = _TICKER_ALIASES.get(symbol, symbol)

    sym_upper = kite_sym.upper().replace(" ", "")
    # Try without spaces
    if sym_upper in _TOKEN_MAP:
        return _TOKEN_MAP[sym_upper]
    # Try with original spaces (index names like "NIFTY BANK", "INDIA VIX")
    sym_spaced = kite_sym.upper()
    if sym_spaced in _TOKEN_MAP:
        return _TOKEN_MAP[sym_spaced]
    log.warning("Cannot resolve instrument token for: %s", symbol)
    return None


# ---------------------------------------------------------------------------
# KiteConnect client
# ---------------------------------------------------------------------------

def get_kite():
    """Return an authenticated KiteConnect instance (auto-refreshes token)."""
    from kite_auth import get_kite_client
    return get_kite_client()


# ---------------------------------------------------------------------------
# Live price fetch (LTP)
# ---------------------------------------------------------------------------

def fetch_ltp(symbols: list[str]) -> dict[str, float]:
    """Fetch last traded prices for a list of plain tickers.

    Symbols are plain NSE tickers like "HAL", "NIFTY BANK", "INDIA VIX",
    or MCX base names like "CRUDEOIL", "GOLD".

    Returns {symbol: last_price}. Missing symbols are omitted.
    Falls back to eodhd_client on Kite failure.
    """
    if not symbols:
        return {}

    _ensure_instrument_master()

    # Build Kite instrument strings: "NSE:HAL", "MCX:CRUDEOIL26APRFUT", etc.
    token_to_sym: dict[int, str] = {}
    instrument_list: list[str] = []

    for sym in symbols:
        token = resolve_token(sym)
        if token is None:
            log.warning("Skipping LTP for unresolvable symbol: %s", sym)
            continue
        token_to_sym[token] = sym
        # Determine exchange prefix from where we found it
        instrument_list.append(str(token))

    if not instrument_list:
        return _fallback_ltp(symbols)

    try:
        kite = get_kite()
        # Kite ltp() accepts instrument tokens as strings
        raw = kite.ltp(instrument_list)
        # raw = {token_str: {"instrument_token": N, "last_price": F}}
        result: dict[str, float] = {}
        for token_str, data in raw.items():
            token_int = int(token_str)
            orig_sym = token_to_sym.get(token_int, token_str)
            lp = data.get("last_price")
            if lp is not None:
                result[orig_sym] = float(lp)
        log.debug("Kite LTP: %d symbols fetched", len(result))
        return result

    except Exception as exc:
        log.warning("Kite LTP failed (%s) — falling back to EODHD", exc)
        return _fallback_ltp(symbols)


def _fallback_ltp(symbols: list[str]) -> dict[str, float]:
    """EODHD real-time fallback when Kite is unavailable."""
    from config import INDIA_SIGNAL_STOCKS
    from eodhd_client import fetch_realtime

    result: dict[str, float] = {}
    for sym in symbols:
        stock_info = INDIA_SIGNAL_STOCKS.get(sym, {})
        eodhd_sym = stock_info.get("eodhd", "")
        if not eodhd_sym:
            continue
        rt = fetch_realtime(eodhd_sym)
        if rt and rt.get("close"):
            result[sym] = float(rt["close"])
    return result


# ---------------------------------------------------------------------------
# Historical candles
# ---------------------------------------------------------------------------

def fetch_historical(
    symbol: str,
    interval: str = "day",
    days: int = 35,
) -> list[dict]:
    """Fetch OHLCV candle history for a symbol.

    Args:
        symbol:   Plain ticker ("HAL") or MCX base ("CRUDEOIL")
        interval: Kite interval string — "minute", "3minute", "5minute",
                  "10minute", "15minute", "30minute", "60minute", "day"
        days:     Number of calendar days of history to fetch

    Returns list of dicts (oldest first):
        {date, open, high, low, close, volume, source}
    Falls back to eodhd_client EOD if Kite fails.
    """
    token = resolve_token(symbol)
    if token is None:
        return _fallback_historical(symbol, days)

    to_dt = datetime.now(IST)
    from_dt = to_dt - timedelta(days=days + 5)  # +5 buffer for holidays

    try:
        kite = get_kite()
        candles = kite.historical_data(
            instrument_token=token,
            from_date=from_dt.strftime("%Y-%m-%d %H:%M:%S"),
            to_date=to_dt.strftime("%Y-%m-%d %H:%M:%S"),
            interval=interval,
            continuous=False,
            oi=False,
        )
        result = []
        for c in candles:
            dt = c["date"]
            if hasattr(dt, "strftime"):
                date_str = dt.strftime("%Y-%m-%d")
            else:
                date_str = str(dt)[:10]
            result.append({
                "date":   date_str,
                "open":   float(c["open"]),
                "high":   float(c["high"]),
                "low":    float(c["low"]),
                "close":  float(c["close"]),
                "volume": int(c.get("volume", 0)),
                "source": "kite",
            })
        log.debug("Kite historical: %s → %d candles (%s)", symbol, len(result), interval)
        return result

    except Exception as exc:
        log.warning("Kite historical failed for %s (%s) — falling back to EODHD", symbol, exc)
        return _fallback_historical(symbol, days)


def _fallback_historical(symbol: str, days: int) -> list[dict]:
    """EODHD EOD series fallback."""
    from config import INDIA_SIGNAL_STOCKS
    from eodhd_client import fetch_eod_series

    stock_info = INDIA_SIGNAL_STOCKS.get(symbol, {})
    eodhd_sym = stock_info.get("eodhd", "")
    if not eodhd_sym:
        return []
    rows = fetch_eod_series(eodhd_sym, days=days)
    for r in rows:
        r["source"] = "eodhd_fallback"
    return rows


# ---------------------------------------------------------------------------
# Macro / index helpers
# ---------------------------------------------------------------------------

# Kite tradingsymbol → display name
MACRO_SYMBOLS = {
    "INDIA VIX":  "India VIX",
    "NIFTY BANK": "Nifty Bank",
    "NIFTY IT":   "Nifty IT",
    "NIFTY 50":   "Nifty 50",   # Kite tradingsymbol is "NIFTY 50" not "NIFTY"
    "CRUDEOIL":   "Crude Oil (MCX)",
    "GOLD":       "Gold (MCX)",
}


def fetch_macro_snapshot() -> dict[str, float]:
    """Fetch live values for key macro indicators from Kite.

    Returns {display_name: value}. Missing symbols are omitted.
    """
    syms = list(MACRO_SYMBOLS.keys())
    prices = fetch_ltp(syms)
    return {
        MACRO_SYMBOLS[sym]: prices[sym]
        for sym in syms
        if sym in prices
    }


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    print("Loading instrument master...")
    _ensure_instrument_master()
    print(f"  {len(_TOKEN_MAP)} symbols loaded")

    print("\nFetching LTP for HAL, TCS, COALINDIA, HPCL...")
    prices = fetch_ltp(["HAL", "TCS", "COALINDIA", "HPCL"])
    for sym, px in prices.items():
        print(f"  {sym}: Rs{px:,.2f}")

    print("\nFetching macro snapshot...")
    macro = fetch_macro_snapshot()
    for name, val in macro.items():
        print(f"  {name}: {val:,.2f}")

    print("\nFetching 5 days HAL history (day candles)...")
    hist = fetch_historical("HAL", interval="day", days=5)
    for row in hist[-5:]:
        print(f"  {row['date']}  O:{row['open']:.2f}  H:{row['high']:.2f}  "
              f"L:{row['low']:.2f}  C:{row['close']:.2f}  V:{row['volume']:,}  [{row['source']}]")

    print("\nKite client: OK")
    sys.exit(0)
