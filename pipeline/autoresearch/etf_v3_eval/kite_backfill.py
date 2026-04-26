"""Kite minute-bar backfill for F&O tickers — single-ticker fetcher.

Per Data Policy §6 (source registration), §7 (lineage), §11 (PIT correctness):
this module retrieves historical minute bars exactly as Kite emits them.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Protocol

import pandas as pd


class BackfillFailure(Exception):
    """Ticker could not be backfilled (no instrument token, empty response, schema violation)."""


class KiteClient(Protocol):
    def ltp(self, symbols: list[str]) -> dict: ...
    def historical_data(self, token: int, from_: datetime, to: datetime, interval: str) -> list[dict]: ...


def fetch_minute_bars(kite: KiteClient, ticker: str, start: date, end: date) -> pd.DataFrame:
    """Fetch minute bars for one ticker over [start, end] inclusive.

    Returns DataFrame with columns: ticker, trade_date, timestamp, open, high, low, close, volume.
    Raises BackfillFailure on empty response or unknown ticker.
    """
    nse_symbol = f"NSE:{ticker}"
    ltp = kite.ltp([nse_symbol])
    if nse_symbol not in ltp or "instrument_token" not in ltp[nse_symbol]:
        raise BackfillFailure(f"no instrument_token for {ticker}")
    token = ltp[nse_symbol]["instrument_token"]

    bars = kite.historical_data(
        token,
        datetime.combine(start, datetime.min.time()),
        datetime.combine(end, datetime.max.time()),
        "minute",
    )
    if not bars:
        raise BackfillFailure(f"empty response for {ticker}")

    df = pd.DataFrame(bars)
    df = df.rename(columns={"date": "timestamp"})
    df["ticker"] = ticker
    df["trade_date"] = df["timestamp"].dt.date
    cols = ["ticker", "trade_date", "timestamp", "open", "high", "low", "close", "volume"]
    return df[cols]
