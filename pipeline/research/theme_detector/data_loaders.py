"""Data loader helpers for theme detector signals.

Reads from existing project data sources. Returns pandas DataFrames keyed by
symbol. PIT-aware — every loader takes a `cutoff_date` and refuses to return
bars after the cutoff.

Spec data audit: docs/superpowers/specs/2026-05-01-theme-detector-data-source-audit.md
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[3]
FNO_HISTORICAL_DIR = REPO_ROOT / "pipeline" / "data" / "fno_historical"
INDICES_DIR = REPO_ROOT / "pipeline" / "data" / "india_historical" / "indices"
NIFTY_50_PATH = INDICES_DIR / "NIFTY_daily.csv"


def load_nifty_50(cutoff_date: date) -> pd.DataFrame | None:
    """Load NIFTY-50 daily bars up to (and including) cutoff_date.

    Schema is lower-case (date,open,high,low,close,volume) — different from
    fno_historical/. This loader normalizes to capitalized columns to match
    `load_daily_bars` output.
    """
    if not NIFTY_50_PATH.exists():
        return None
    df = pd.read_csv(NIFTY_50_PATH, parse_dates=["date"])
    df = df.rename(columns={
        "date": "Date", "open": "Open", "high": "High",
        "low": "Low", "close": "Close", "volume": "Volume",
    })
    df = df[df["Date"].dt.date <= cutoff_date]
    if df.empty:
        return None
    return df.sort_values("Date").reset_index(drop=True)


def load_daily_bars(symbol: str, cutoff_date: date) -> pd.DataFrame | None:
    """Load daily bars for one symbol up to (and including) cutoff_date.

    Returns DataFrame indexed by Date with columns Open/High/Low/Close/Volume,
    or None when the CSV is absent.
    """
    csv_path = FNO_HISTORICAL_DIR / f"{symbol}.csv"
    if not csv_path.exists():
        return None
    df = pd.read_csv(csv_path, parse_dates=["Date"])
    df = df[df["Date"].dt.date <= cutoff_date]
    if df.empty:
        return None
    return df.sort_values("Date").reset_index(drop=True)


def load_theme_member_bars(
    members: list[str], cutoff_date: date
) -> dict[str, pd.DataFrame]:
    """Load bars for every available theme member.

    Returns dict keyed by symbol. Symbols whose CSV is absent are silently
    omitted; caller decides how to handle thin coverage.
    """
    out: dict[str, pd.DataFrame] = {}
    for sym in members:
        df = load_daily_bars(sym, cutoff_date)
        if df is not None and len(df) > 0:
            out[sym] = df
    return out
