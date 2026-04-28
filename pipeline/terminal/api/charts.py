"""GET /api/charts/{ticker} — OHLCV data for Lightweight Charts."""
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from fastapi import APIRouter, HTTPException

router = APIRouter()

_HERE = Path(__file__).resolve().parent.parent
_DAILY_DIR = _HERE.parent / "data" / "daily"
_CACHE_DIR = _HERE.parent / "data" / "chart_cache"
_PHASE_C_BARS = _HERE.parent / "data" / "research" / "phase_c" / "daily_bars"
_INDIA_HIST = _HERE.parent / "data" / "india_historical"

logger = logging.getLogger(__name__)


@router.get("/charts/{ticker}")
def charts(ticker: str):
    """Return daily OHLCV candles for a ticker.

    Source priority (Indian F&O has rich local history; falling all the way
    to yfinance is a last resort because of rate limiting):
      1. phase_c/daily_bars/{ticker}.parquet — 4y PIT canonical bars, best.
      2. india_historical/{ticker}.csv — daily OHLCV from the data pipeline.
      3. data/daily/*.json — only useful when daily files contain Indian
         stocks (most are US right now; kept for back-compat).
      4. chart_cache/{ticker}.json — local cache populated by yfinance.
      5. yfinance live download — fallback, rate-limited.
    """
    ticker = ticker.upper()

    candles = _from_phase_c_parquet(ticker)
    if not candles:
        candles = _from_india_historical_csv(ticker)
    if not candles:
        candles = _from_daily_files(ticker)
    if not candles:
        candles = _from_cache(ticker)
    if not candles:
        candles = _from_yfinance(ticker)

    if not candles:
        raise HTTPException(status_code=404, detail=f"No chart data for {ticker}")

    candles.sort(key=lambda c: c["time"])
    return {"ticker": ticker, "candles": candles, "count": len(candles)}


def _from_phase_c_parquet(ticker: str) -> list:
    path = _PHASE_C_BARS / f"{ticker}.parquet"
    if not path.exists():
        return []
    try:
        import pandas as pd
        df = pd.read_parquet(path)
        # phase_c/daily_bars columns: date, open, high, low, close, volume.
        rows = df.tail(500)  # 2 years should be enough for the modal chart
        candles = []
        for _, r in rows.iterrows():
            d = r.get("date")
            if hasattr(d, "strftime"):
                d = d.strftime("%Y-%m-%d")
            else:
                d = str(d)[:10]
            candles.append({
                "time": d,
                "open": round(float(r["open"]), 2),
                "high": round(float(r["high"]), 2),
                "low": round(float(r["low"]), 2),
                "close": round(float(r["close"]), 2),
                "volume": int(r.get("volume") or 0),
            })
        return candles
    except Exception as e:
        logger.warning("phase_c parquet read failed for %s: %s", ticker, e)
        return []


def _from_india_historical_csv(ticker: str) -> list:
    path = _INDIA_HIST / f"{ticker}.csv"
    if not path.exists():
        return []
    try:
        import pandas as pd
        df = pd.read_csv(path)
        rows = df.tail(500)
        candles = []
        for _, r in rows.iterrows():
            d = str(r.get("Date") or "")[:10]
            try:
                candles.append({
                    "time": d,
                    "open": round(float(r["Open"]), 2),
                    "high": round(float(r["High"]), 2),
                    "low": round(float(r["Low"]), 2),
                    "close": round(float(r["Close"]), 2),
                    "volume": int(r.get("Volume") or 0),
                })
            except Exception:
                continue
        return candles
    except Exception as e:
        logger.warning("india_historical csv read failed for %s: %s", ticker, e)
        return []


def _from_daily_files(ticker: str) -> list:
    candles = []
    if not _DAILY_DIR.exists():
        return candles
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
    return candles


def _from_cache(ticker: str) -> list:
    cache_file = _CACHE_DIR / f"{ticker}.json"
    if not cache_file.exists():
        return []
    try:
        data = json.loads(cache_file.read_text(encoding="utf-8"))
        cached_at = data.get("cached_at", "")
        if cached_at:
            age = datetime.now() - datetime.fromisoformat(cached_at)
            if age > timedelta(hours=12):
                return []
        return data.get("candles", [])
    except Exception:
        return []


def _from_yfinance(ticker: str) -> list:
    try:
        import yfinance as yf
    except ImportError:
        logger.warning("yfinance not installed — cannot fetch chart data for %s", ticker)
        return []

    nse_ticker = f"{ticker}.NS"
    try:
        df = yf.download(nse_ticker, period="1y", interval="1d", progress=False, auto_adjust=True)
        if df is None or df.empty:
            return []

        candles = []
        for date, row in df.iterrows():
            try:
                candles.append({
                    "time": date.strftime("%Y-%m-%d"),
                    "open": round(float(row["Open"].iloc[0] if hasattr(row["Open"], "iloc") else row["Open"]), 2),
                    "high": round(float(row["High"].iloc[0] if hasattr(row["High"], "iloc") else row["High"]), 2),
                    "low": round(float(row["Low"].iloc[0] if hasattr(row["Low"], "iloc") else row["Low"]), 2),
                    "close": round(float(row["Close"].iloc[0] if hasattr(row["Close"], "iloc") else row["Close"]), 2),
                    "volume": int(row["Volume"].iloc[0] if hasattr(row["Volume"], "iloc") else row["Volume"]),
                })
            except Exception:
                continue

        if candles:
            _CACHE_DIR.mkdir(parents=True, exist_ok=True)
            cache_file = _CACHE_DIR / f"{ticker}.json"
            cache_file.write_text(json.dumps({
                "ticker": ticker,
                "cached_at": datetime.now().isoformat(),
                "candles": candles,
            }), encoding="utf-8")

        return candles
    except Exception as e:
        logger.warning("yfinance fetch failed for %s: %s", ticker, e)
        return []


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
