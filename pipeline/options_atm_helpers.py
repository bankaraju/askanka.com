"""ATM strike + monthly-expiry helpers for the Phase C paired-shadow sidecar.

Reads the Kite NFO instrument master (kite_cache/instruments_nfo.csv) and
exposes pure functions for: nearest-monthly expiry resolution, ATM strike
picking via argmin(|strike - spot|), and NSE tradingsymbol composition.

Spec: docs/superpowers/specs/2026-04-27-phase-c-options-paired-shadow-design.md §6.2
"""
from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Literal

import pandas as pd


def load_nfo_master(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["expiry"] = pd.to_datetime(df["expiry"])
    return df


def resolve_nearest_monthly_expiry(
    today: date, ticker: str, nfo_master_df: pd.DataFrame
) -> date:
    today_ts = pd.Timestamp(today)
    mask = (
        (nfo_master_df["name"] == ticker)
        & (nfo_master_df["instrument_type"].isin(["CE", "PE"]))
        & (nfo_master_df["expiry"] >= today_ts)
    )
    sub = nfo_master_df.loc[mask, "expiry"]
    if sub.empty:
        raise ValueError(f"no monthly contracts for {ticker} on or after {today}")
    return sub.min().date()


def resolve_atm_strike(
    spot: float, ticker: str, expiry: date, nfo_master_df: pd.DataFrame
) -> int:
    expiry_ts = pd.Timestamp(expiry)
    mask = (
        (nfo_master_df["name"] == ticker)
        & (nfo_master_df["expiry"] == expiry_ts)
        & (nfo_master_df["instrument_type"].isin(["CE", "PE"]))
    )
    sub = nfo_master_df.loc[mask, "strike"]
    if sub.empty:
        raise ValueError(f"no strikes listed for {ticker} {expiry}")
    strikes = sorted(sub.unique().tolist())
    diffs = [abs(s - spot) for s in strikes]
    idx = diffs.index(min(diffs))  # left-bias on ties
    return int(strikes[idx])


def compose_tradingsymbol(
    ticker: str, expiry: date, strike: int, option_type: Literal["CE", "PE"]
) -> str:
    return f"{ticker}{expiry.strftime('%y%b').upper()}{int(strike)}{option_type}"


def get_lot_size_for_ticker(ticker: str, nfo_master_df: pd.DataFrame) -> int:
    mask = (
        (nfo_master_df["name"] == ticker)
        & (nfo_master_df["instrument_type"] == "FUT")
    )
    sub = nfo_master_df.loc[mask, "lot_size"]
    if sub.empty:
        raise ValueError(f"no futures contracts for {ticker} in NFO master")
    return int(sub.mode().iloc[0])
