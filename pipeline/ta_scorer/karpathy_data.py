"""H-2026-04-29-ta-karpathy-v1 data fetcher.

Pulls 5y daily OHLCV via yfinance for the frozen NIFTY-10 universe and
caches under `pipeline/data/research/h_2026_04_29_ta_karpathy_v1/bars/`.

Spec ref: docs/superpowers/specs/2026-04-29-ta-karpathy-v1-design.md §3, §4.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import yfinance as yf

log = logging.getLogger("karpathy.data")

# Frozen at registration time per spec §3
NIFTY_TOP_10 = (
    "RELIANCE", "HDFCBANK", "ICICIBANK", "INFY", "TCS",
    "BHARTIARTL", "KOTAKBANK", "LT", "AXISBANK", "SBIN",
)

# yfinance ticker overrides (none currently — these 10 all map directly to <SYMBOL>.NS)
_TICKER_OVERRIDES: dict[str, str] = {}

REPO_ROOT = Path(__file__).resolve().parents[2]
CACHE_DIR = REPO_ROOT / "pipeline" / "data" / "research" / "h_2026_04_29_ta_karpathy_v1" / "bars"


def yf_symbol(ticker: str) -> str:
    return _TICKER_OVERRIDES.get(ticker, f"{ticker}.NS")


def fetch_one(ticker: str, *, days: int = 1825, force: bool = False) -> pd.DataFrame:
    """Download 5y daily OHLCV for one ticker. Returns DataFrame with
    columns: date, open, high, low, close, volume (lowercase, dividend-adjusted close).
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = CACHE_DIR / f"{ticker}.parquet"
    if cache_path.exists() and not force:
        df = pd.read_parquet(cache_path)
        log.info("cached %s: %d rows %s -> %s",
                 ticker, len(df), df["date"].min(), df["date"].max())
        return df

    sym = yf_symbol(ticker)
    end = datetime.now()
    start = end - timedelta(days=days)
    raw = yf.download(sym, start=start, end=end, progress=False, auto_adjust=True)
    if raw is None or len(raw) < 100:
        raise RuntimeError(f"insufficient data for {ticker} ({sym}): "
                           f"{0 if raw is None else len(raw)} rows")

    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)

    df = raw.reset_index().rename(columns={
        "Date": "date", "Open": "open", "High": "high",
        "Low": "low", "Close": "close", "Volume": "volume",
    })[["date", "open", "high", "low", "close", "volume"]]
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)
    df.to_parquet(cache_path, index=False)
    log.info("fetched %s: %d rows %s -> %s",
             ticker, len(df), df["date"].min(), df["date"].max())
    return df


def fetch_universe(*, days: int = 1825, force: bool = False) -> dict[str, pd.DataFrame]:
    """Fetch all 10 NIFTY top names. Returns {ticker: df}."""
    out: dict[str, pd.DataFrame] = {}
    for tk in NIFTY_TOP_10:
        try:
            out[tk] = fetch_one(tk, days=days, force=force)
        except Exception as exc:
            log.error("fetch FAILED %s: %s", tk, exc)
    return out


# Sector mapping for the 10 stocks (yfinance index symbols)
SECTOR_MAP: dict[str, str] = {
    "RELIANCE":   "^CNXENERGY",   # Nifty Energy
    "HDFCBANK":   "^NSEBANK",     # Nifty Bank
    "ICICIBANK":  "^NSEBANK",
    "KOTAKBANK":  "^NSEBANK",
    "AXISBANK":   "^NSEBANK",
    "SBIN":       "^NSEBANK",
    "INFY":       "^CNXIT",       # Nifty IT
    "TCS":        "^CNXIT",
    "BHARTIARTL": "^NSEI",        # Nifty 50 (no clean telecom index)
    "LT":         "^CNXINFRA",    # Nifty Infra
}

NIFTY_SYMBOL = "^NSEI"
INDIAVIX_SYMBOL = "^INDIAVIX"


def _fetch_index_series(symbol: str, days: int = 1825, force: bool = False) -> pd.DataFrame:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    safe = symbol.replace("^", "_idx_")
    path = CACHE_DIR / f"{safe}.parquet"
    if path.exists() and not force:
        return pd.read_parquet(path)
    end = datetime.now()
    start = end - timedelta(days=days)
    raw = yf.download(symbol, start=start, end=end, progress=False, auto_adjust=True)
    if raw is None or len(raw) < 100:
        raise RuntimeError(f"insufficient {symbol}: {0 if raw is None else len(raw)}")
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)
    df = raw.reset_index().rename(columns={
        "Date": "date", "Open": "open", "High": "high",
        "Low": "low", "Close": "close", "Volume": "volume",
    })
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)
    df.to_parquet(path, index=False)
    log.info("fetched %s: %d rows %s -> %s",
             symbol, len(df), df["date"].min().date(), df["date"].max().date())
    return df


def fetch_macro(*, days: int = 1825, force: bool = False) -> dict[str, pd.DataFrame]:
    """Fetch NIFTY, INDIAVIX, and the 4 sector indices used by SECTOR_MAP."""
    sectors = sorted(set(SECTOR_MAP.values()))
    out = {NIFTY_SYMBOL: _fetch_index_series(NIFTY_SYMBOL, days, force)}
    out[INDIAVIX_SYMBOL] = _fetch_index_series(INDIAVIX_SYMBOL, days, force)
    for s in sectors:
        if s == NIFTY_SYMBOL:
            continue
        out[s] = _fetch_index_series(s, days, force)
    return out


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    bars = fetch_universe(force=False)
    print(f"\nStocks: {len(bars)}/{len(NIFTY_TOP_10)}")
    for tk, df in bars.items():
        print(f"  {tk:12s} {len(df):4d} rows  {df['date'].min().date()} -> {df['date'].max().date()}")
    macro = fetch_macro(force=False)
    print(f"\nMacro indices: {len(macro)}")
    for sym, df in macro.items():
        print(f"  {sym:14s} {len(df):4d} rows  {df['date'].min().date()} -> {df['date'].max().date()}")
