"""VIX history (India VIX close) via yfinance primary + NSE archive fallback.

Forward-fill policy: gap <= 2 bars (for holidays), longer gaps left NaN so
the downstream feature builder can flag them.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

import pandas as pd
import yfinance as yf

REPO_ROOT = Path(__file__).resolve().parents[4]
OUT_CSV = REPO_ROOT / "pipeline/data/vix_history.csv"
NSE_FALLBACK = REPO_ROOT / "pipeline/data/india_historical/indices/INDIAVIX.csv"
START = "2021-04-01"
END = "2026-05-01"


def _from_yfinance() -> pd.DataFrame:
    df = yf.download("^INDIAVIX", start=START, end=END, progress=False, auto_adjust=True, threads=False)
    if df.empty:
        return df
    df = df.reset_index()
    # yfinance may return MultiIndex columns for single-ticker with newer versions
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
    df = df[["Date", "Close"]].rename(columns={"Date": "date", "Close": "vix_close"})
    df["date"] = pd.to_datetime(df["date"])
    return df


def _from_nse_archive() -> pd.DataFrame:
    if not NSE_FALLBACK.exists():
        return pd.DataFrame(columns=["date", "vix_close"])
    df = pd.read_csv(NSE_FALLBACK, parse_dates=["date"])
    col = "close" if "close" in df.columns else df.columns[-1]
    return df.rename(columns={col: "vix_close"})[["date", "vix_close"]]


def main() -> int:
    df_yf = _from_yfinance()
    if df_yf.empty:
        logging.warning("yfinance INDIAVIX empty; falling back to NSE archive")
        df_yf = _from_nse_archive()
    df_nse = _from_nse_archive()

    combined = pd.concat([df_yf, df_nse], ignore_index=True).dropna()
    combined = combined.drop_duplicates(subset=["date"], keep="first").sort_values("date")
    # Forward-fill gaps of <= 2 bars only
    combined = combined.set_index("date").asfreq("B")
    combined["vix_close"] = combined["vix_close"].ffill(limit=2)
    combined = combined.reset_index().dropna()

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    combined.to_csv(OUT_CSV, index=False)
    print(f"wrote {len(combined)} rows to {OUT_CSV}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
