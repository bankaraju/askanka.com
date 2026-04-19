"""EWMA volatility engine — fetches Kite OHLCV, caches per-ticker, computes annualised vol."""
import json
import math
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

log = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))
_DEFAULT_CACHE_DIR = Path(__file__).resolve().parent / "data" / "vol_cache"


def compute_ewma_vol(closes: list[float], span: int = 30) -> float:
    if len(closes) < 2:
        raise ValueError("Need at least 2 closes to compute volatility")

    log_returns = [math.log(closes[i] / closes[i - 1]) for i in range(1, len(closes)) if closes[i - 1] > 0]

    if not log_returns or all(r == 0.0 for r in log_returns):
        return 0.0

    alpha = 2.0 / (span + 1)
    ewma_var = log_returns[0] ** 2
    for r in log_returns[1:]:
        ewma_var = alpha * r ** 2 + (1 - alpha) * ewma_var

    daily_vol = math.sqrt(ewma_var)
    return daily_vol * math.sqrt(252)


def _is_cache_stale(fetched_at_iso: str) -> bool:
    try:
        fetched = datetime.fromisoformat(fetched_at_iso)
        age = datetime.now(IST) - fetched.astimezone(IST)
        return age > timedelta(hours=20)
    except Exception:
        return True


def fetch_and_cache_ohlcv(ticker: str, days: int = 35, cache_dir: Path = _DEFAULT_CACHE_DIR) -> list[dict]:
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / f"{ticker}.json"

    if cache_file.exists():
        try:
            cached = json.loads(cache_file.read_text(encoding="utf-8"))
            if not _is_cache_stale(cached.get("fetched_at", "")):
                return cached.get("candles", [])
        except Exception:
            pass

    try:
        from pipeline.kite_client import fetch_historical
        candles = fetch_historical(ticker, interval="day", days=days)
    except Exception as exc:
        log.warning("Kite fetch failed for %s: %s", ticker, exc)
        return []

    if candles:
        payload = {
            "ticker": ticker,
            "fetched_at": datetime.now(IST).isoformat(),
            "candles": candles,
        }
        try:
            cache_file.write_text(json.dumps(payload, default=str), encoding="utf-8")
        except Exception as exc:
            log.warning("Cache write failed for %s: %s", ticker, exc)

    return candles


def get_stock_vol(ticker: str, span: int = 30, cache_dir: Path = _DEFAULT_CACHE_DIR) -> float | None:
    candles = fetch_and_cache_ohlcv(ticker, days=span + 5, cache_dir=cache_dir)
    if len(candles) < 2:
        return None

    closes = [c["close"] for c in candles if "close" in c]
    if len(closes) < 2:
        return None

    try:
        vol = compute_ewma_vol(closes, span=span)
        cache_file = cache_dir / f"{ticker}.json"
        if cache_file.exists():
            try:
                cached = json.loads(cache_file.read_text(encoding="utf-8"))
                cached["ewma_vol_annual"] = vol
                cached["closes"] = closes
                cache_file.write_text(json.dumps(cached, default=str), encoding="utf-8")
            except Exception:
                pass
        return vol
    except Exception as exc:
        log.warning("EWMA computation failed for %s: %s", ticker, exc)
        return None
