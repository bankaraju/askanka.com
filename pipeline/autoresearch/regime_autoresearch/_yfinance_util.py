"""Shared yfinance download helper for regime_autoresearch builders.

One thin wrapper around yf.download that handles the two failure modes
we actually encounter: network errors and empty responses. Returns an
empty DataFrame (not None) so callers can cleanly chain `.empty` checks.
"""
from __future__ import annotations

import sys

import pandas as pd


def download_ohlcv(
    ticker: str,
    start: str,
    end: str,
) -> pd.DataFrame:
    """Fetch daily OHLCV for one ticker via yfinance.

    Returns a DataFrame with columns [date, open, high, low, close, volume]
    (lowercased). Empty on any failure; caller must check `.empty`.
    """
    try:
        import yfinance as yf  # type: ignore
    except ImportError:
        print("error: yfinance not installed -- `pip install yfinance`", file=sys.stderr)
        return pd.DataFrame()

    try:
        raw = yf.download(
            ticker,
            start=start,
            end=end,
            progress=False,
            auto_adjust=True,
            threads=False,
        )
    except Exception as exc:
        # yfinance wraps network + parse + yahoo-side errors in many classes;
        # a broad catch is appropriate at this boundary because we have a
        # downstream fallback (NSE archive, skip-and-log) for every caller.
        print(f"warn: yfinance download failed for {ticker}: {exc}", file=sys.stderr)
        return pd.DataFrame()

    if raw is None or raw.empty:
        return pd.DataFrame()

    if isinstance(raw.columns, pd.MultiIndex):
        try:
            df = raw.xs(ticker, axis=1, level=1)
        except (KeyError, ValueError):
            df = raw.droplevel(1, axis=1)
    else:
        df = raw

    df = df.rename(columns=str.lower)
    required = {"open", "high", "low", "close", "volume"}
    missing = required - set(df.columns)
    if missing:
        print(f"warn: {ticker} missing OHLCV columns {missing}", file=sys.stderr)
        return pd.DataFrame()

    df = df.reset_index()
    date_col = "Date" if "Date" in df.columns else "index"
    df = df.rename(columns={date_col: "date"})
    df["date"] = pd.to_datetime(df["date"])
    return df[["date", "open", "high", "low", "close", "volume"]].dropna(subset=["close"])
