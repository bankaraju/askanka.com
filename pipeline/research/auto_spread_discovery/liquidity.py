"""ASDE liquidity ranking — 60d ADV from fno_historical.

Computes Average Daily Value (close * volume) over the last 60 trading
days for each F&O ticker, used by the proposer to pick top-3 legs per
sector. Replaces the v0 alphabetical fallback.

Why ADV not just volume
-----------------------
A 100-rupee stock with 1M volume = ₹10 cr daily turnover. A 5,000-rupee
stock with 50K volume = ₹25 cr daily turnover. ADV (price * volume) is
the canonical liquidity proxy because it captures actual cash flow, not
share count.

Why 60 trading days
-------------------
- Long enough to smooth out earnings-driven spikes.
- Short enough that recent F&O additions show up correctly.
- Matches the rolling-60d cohort used elsewhere in the pipeline.
"""
from __future__ import annotations

import csv
from functools import lru_cache
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
FNO_HIST_DIR = REPO / "pipeline" / "data" / "fno_historical"
DEFAULT_LOOKBACK_DAYS = 60


def _read_close_volume(csv_path: Path, lookback: int) -> list[tuple[float, float]]:
    """Tail of (close, volume) tuples for last `lookback` trading days."""
    rows: list[tuple[float, float]] = []
    if not csv_path.is_file():
        return rows
    with csv_path.open(encoding="utf-8", newline="") as fp:
        reader = csv.DictReader(fp)
        for row in reader:
            try:
                close = float(row["Close"])
                vol = float(row["Volume"])
            except (KeyError, ValueError, TypeError):
                continue
            rows.append((close, vol))
    return rows[-lookback:]


def adv_for_ticker(ticker: str, *, lookback: int = DEFAULT_LOOKBACK_DAYS) -> float:
    """60d mean of close * volume in INR. Returns 0.0 if data missing."""
    p = FNO_HIST_DIR / f"{ticker.upper()}.csv"
    rows = _read_close_volume(p, lookback)
    if not rows:
        return 0.0
    products = [c * v for c, v in rows if c > 0 and v > 0]
    if not products:
        return 0.0
    return sum(products) / len(products)


@lru_cache(maxsize=1)
def _cached_universe_adv() -> dict[str, float]:
    """ADV map for every fno_historical CSV — lazy + cached for one session."""
    out: dict[str, float] = {}
    if not FNO_HIST_DIR.is_dir():
        return out
    for p in FNO_HIST_DIR.glob("*.csv"):
        ticker = p.stem.upper()
        out[ticker] = adv_for_ticker(ticker)
    return out


def rank_top_k_by_adv(tickers: list[str], k: int = 3,
                      *, adv_map: dict[str, float] | None = None) -> list[str]:
    """Top-K tickers by 60d ADV, descending. Stable on ties (alphabetical
    secondary)."""
    if not tickers:
        return []
    adv = adv_map if adv_map is not None else _cached_universe_adv()
    scored = [(adv.get(t.upper(), 0.0), t.upper()) for t in tickers]
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [t for _, t in scored[:k]]


def clear_cache() -> None:
    """Force re-read of fno_historical on next call. Useful in tests."""
    _cached_universe_adv.cache_clear()
