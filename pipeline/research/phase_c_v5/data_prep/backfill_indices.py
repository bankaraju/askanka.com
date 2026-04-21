"""Backfill 5y daily + 60d 1-min bars for NSE sectoral indices.

Primary source: Kite (via V4 fetcher) with symbol map ``NIFTY -> "NSE:NIFTY 50"``.
Fallback source: yfinance with ``^``-prefixed aliases (``NIFTY -> "^NSEI"``).

Minute bars are Kite-only — yfinance does not offer minute-level history for
Indian indices. If minute backfill fails, it is not retried via yfinance.

**Deviation from plan Task 8 body:** The original plan assumed Kite availability
during backfill. In practice Kite session tokens are only valid during scheduled
task windows (AnkaRefreshKite at 09:00). A yfinance fallback is added so the
backfill can be run interactively outside those windows. Minute bars remain
Kite-only since yfinance does not provide intraday for Indian indices.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path

import pandas as pd

from pipeline.research.phase_c_backtest import fetcher as v4fetcher

log = logging.getLogger(__name__)

KNOWN_FNO_INDICES = [
    "NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "NIFTYNXT50",
    "NIFTYIT", "NIFTYMETAL", "NIFTYPSUBANK",
]
CANDIDATE_SECTORAL_INDICES = [
    "NIFTYAUTO", "NIFTYPHARMA", "NIFTYFMCG", "NIFTYENERGY",
    "NIFTYREALTY", "NIFTYMEDIA", "NIFTYPVTBANK", "NIFTYFINSRV",
]

_KITE_ALIAS = {
    "NIFTY":        "NSE:NIFTY 50",
    "BANKNIFTY":    "NSE:NIFTY BANK",
    "FINNIFTY":     "NSE:NIFTY FIN SERVICE",
    "MIDCPNIFTY":   "NSE:NIFTY MID SELECT",
    "NIFTYNXT50":   "NSE:NIFTY NEXT 50",
    "NIFTYIT":      "NSE:NIFTY IT",
    "NIFTYMETAL":   "NSE:NIFTY METAL",
    "NIFTYPSUBANK": "NSE:NIFTY PSU BANK",
    "NIFTYAUTO":    "NSE:NIFTY AUTO",
    "NIFTYPHARMA":  "NSE:NIFTY PHARMA",
    "NIFTYFMCG":    "NSE:NIFTY FMCG",
    "NIFTYENERGY":  "NSE:NIFTY ENERGY",
    "NIFTYREALTY":  "NSE:NIFTY REALTY",
    "NIFTYMEDIA":   "NSE:NIFTY MEDIA",
    "NIFTYPVTBANK": "NSE:NIFTY PVT BANK",
    "NIFTYFINSRV":  "NSE:NIFTY FIN SERVICE",
}

# yfinance uses distinctive ticker symbols for Indian indices (different from stocks).
# Reference: NSEpy-style conventions + Yahoo Finance search.
_YFINANCE_ALIAS = {
    "NIFTY":        "^NSEI",
    "BANKNIFTY":    "^NSEBANK",
    "FINNIFTY":     "NIFTY_FIN_SERVICE.NS",
    "MIDCPNIFTY":   "^CRSMID",
    "NIFTYNXT50":   "^NSEI",  # no direct Next 50 on yahoo; fallback
    "NIFTYIT":      "^CNXIT",
    "NIFTYMETAL":   "^CNXMETAL",
    "NIFTYPSUBANK": "^CNXPSUBANK",
    "NIFTYAUTO":    "^CNXAUTO",
    "NIFTYPHARMA":  "^CNXPHARMA",
    "NIFTYFMCG":    "^CNXFMCG",
    "NIFTYENERGY":  "^CNXENERGY",
    "NIFTYREALTY":  "^CNXREALTY",
    "NIFTYMEDIA":   "^CNXMEDIA",
    "NIFTYPVTBANK": "^CNXPVTBANK",
    "NIFTYFINSRV":  "NIFTY_FIN_SERVICE.NS",
}


def _yfinance_daily(yf_symbol: str, days: int) -> pd.DataFrame:
    """yfinance fallback — returns DataFrame in V4 schema or empty on failure."""
    try:
        import yfinance as yf
    except ImportError:
        log.warning("yfinance not available; cannot fall back for indices")
        return pd.DataFrame()
    try:
        end = pd.Timestamp.now().normalize()
        start = end - pd.Timedelta(days=days + 30)
        data = yf.download(yf_symbol, start=start, end=end,
                           progress=False, auto_adjust=False)
    except Exception as exc:
        log.warning("yfinance fetch failed for %s: %s", yf_symbol, exc)
        return pd.DataFrame()
    if data is None or data.empty:
        log.warning("yfinance returned no data for %s", yf_symbol)
        return pd.DataFrame()
    # yfinance returns a MultiIndex columns frame in recent versions when a
    # single ticker is passed as a list; for single-string it's flat. Normalise.
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = [c[0] for c in data.columns]
    df = data.reset_index()
    df.columns = [c.lower() for c in df.columns]
    required = {"date", "open", "high", "low", "close", "volume"}
    missing = required - set(df.columns)
    if missing:
        log.warning("yfinance missing columns for %s: %s", yf_symbol, missing)
        return pd.DataFrame()
    df = df[["date", "open", "high", "low", "close", "volume"]].copy()
    df["date"] = pd.to_datetime(df["date"])
    return df


def _fetch_daily(symbol: str, days: int) -> pd.DataFrame:
    """Kite primary, yfinance fallback. Tests patch this module-level helper."""
    kite_sym = _KITE_ALIAS.get(symbol, symbol)
    try:
        return v4fetcher.fetch_daily(kite_sym, days=days)
    except Exception as exc:
        log.info("Kite fetch failed for %s (%s); falling back to yfinance",
                 symbol, exc)
    yf_symbol = _YFINANCE_ALIAS.get(symbol)
    if not yf_symbol:
        log.warning("no yfinance alias for %s", symbol)
        return pd.DataFrame()
    return _yfinance_daily(yf_symbol, days)


def _fetch_minute(symbol: str, trade_date: str) -> pd.DataFrame:
    """Minute bars via Kite only. yfinance lacks intraday for Indian indices."""
    kite_sym = _KITE_ALIAS.get(symbol, symbol)
    return v4fetcher.fetch_minute(kite_sym, trade_date=trade_date)


def backfill_daily(symbols: list[str], days: int, out_dir: Path) -> dict[str, int]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    result: dict[str, int] = {}
    for sym in symbols:
        df = _fetch_daily(sym, days=days)
        path = out_dir / f"{sym}_daily.csv"
        df.to_csv(path, index=False)
        result[sym] = len(df)
        log.info("%s: %d daily rows -> %s", sym, len(df), path.name)
        time.sleep(0.5)  # gentle rate-limit for yfinance
    return result


def backfill_minute(symbols: list[str], trade_dates: list[str],
                     out_dir: Path) -> dict[str, dict[str, int]]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    result: dict[str, dict[str, int]] = {}
    for sym in symbols:
        per_sym: dict[str, int] = {}
        for d in trade_dates:
            df = _fetch_minute(sym, trade_date=d)
            path = out_dir / f"{sym}_{d}.parquet"
            df.to_parquet(path, index=False)
            per_sym[d] = len(df)
        result[sym] = per_sym
        log.info("%s minute bars: %d days", sym, len(per_sym))
    return result
