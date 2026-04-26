"""Loaders for canonical event-channel paths used by §14 contamination map.

These wrap the actual on-disk locations used by the live pipeline:
- News:     pipeline/data/news_events_history.json (list of {matched_stocks, published, ...})
- Earnings: pipeline/data/earnings_calendar/history.parquet (symbol, event_date, kind, ...)
"""
from __future__ import annotations

import json
from datetime import date
from email.utils import parsedate_to_datetime
from pathlib import Path

import pandas as pd

NEWS_HISTORY_PATH = Path("pipeline/data/news_events_history.json")
EARNINGS_HISTORY_PATH = Path("pipeline/data/earnings_calendar/history.parquet")


def _parse_rfc2822_to_date(s: str) -> date | None:
    try:
        return parsedate_to_datetime(s).date()
    except (TypeError, ValueError):
        return None


def load_news_events_history(path: Path = NEWS_HISTORY_PATH) -> pd.DataFrame:
    """Explode news_events_history.json to one row per (ticker, trade_date)."""
    if not path.exists():
        return pd.DataFrame(columns=["ticker", "trade_date"])
    items = json.loads(path.read_text(encoding="utf-8"))
    rows = []
    for it in items:
        d = _parse_rfc2822_to_date(it.get("published", ""))
        if d is None:
            continue
        for sym in it.get("matched_stocks", []) or []:
            rows.append({"ticker": str(sym).upper(), "trade_date": d})
    return pd.DataFrame(rows, columns=["ticker", "trade_date"])


def load_earnings_history(path: Path = EARNINGS_HISTORY_PATH) -> pd.DataFrame:
    """Load earnings_calendar/history.parquet and rename to canonical column names."""
    if not path.exists():
        return pd.DataFrame(columns=["ticker", "trade_date", "kind"])
    df = pd.read_parquet(path)
    df = df.rename(columns={"symbol": "ticker", "event_date": "trade_date"})
    df["ticker"] = df["ticker"].astype(str).str.upper()
    df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.date
    keep = ["ticker", "trade_date"] + [c for c in ("kind", "has_dividend", "has_fundraise") if c in df.columns]
    return df[keep]
