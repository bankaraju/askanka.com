"""Feature extractors for the Feature Coincidence Scorer.

Each function is pure (no I/O) and returns a feature value given its inputs.
The caller is responsible for loading prices / sector frames and passing
point-in-time data (no look-ahead).
"""
from __future__ import annotations
from typing import Any
import numpy as np
import pandas as pd

REGIMES = ["RISK-OFF", "NEUTRAL", "RISK-ON", "EUPHORIA", "CRISIS"]
GRADE_MAP = {"A": 5, "B": 4, "C": 3, "D": 2, "F": 1}


def _close_on_or_before(df: pd.DataFrame, as_of: str) -> float | None:
    if df is None or len(df) == 0:
        return None
    as_of_ts = pd.Timestamp(as_of)
    mask = pd.to_datetime(df["date"]) <= as_of_ts
    if not mask.any():
        return None
    return float(df.loc[mask, "close"].iloc[-1])


def _close_n_days_before(df: pd.DataFrame, as_of: str, n_days: int) -> float | None:
    if df is None or len(df) == 0:
        return None
    as_of_ts = pd.Timestamp(as_of)
    sorted_df = df.sort_values("date")
    mask = pd.to_datetime(sorted_df["date"]) <= as_of_ts
    on_or_before = sorted_df.loc[mask].reset_index(drop=True)
    if len(on_or_before) <= n_days:
        return None
    return float(on_or_before["close"].iloc[-1 - n_days])


def sector_n_day_return(sector_df: pd.DataFrame, as_of: str, n_days: int) -> float | None:
    c_now = _close_on_or_before(sector_df, as_of)
    c_then = _close_n_days_before(sector_df, as_of, n_days)
    if c_now is None or c_then is None or c_then == 0:
        return None
    return (c_now - c_then) / c_then


def ticker_n_day_momentum(prices_df: pd.DataFrame, as_of: str, n_days: int) -> float | None:
    return sector_n_day_return(prices_df, as_of, n_days)


def ticker_rs_vs_sector(prices_df, sector_df, as_of: str, n_days: int) -> float | None:
    t = ticker_n_day_momentum(prices_df, as_of, n_days)
    s = sector_n_day_return(sector_df, as_of, n_days)
    if t is None or s is None:
        return None
    return t - s


def realized_vol(prices_df: pd.DataFrame, as_of: str, n_days: int = 60) -> float | None:
    """Annualized stdev of log returns over trailing n_days."""
    if prices_df is None or len(prices_df) < n_days + 1:
        return None
    as_of_ts = pd.Timestamp(as_of)
    sorted_df = prices_df.sort_values("date")
    mask = pd.to_datetime(sorted_df["date"]) <= as_of_ts
    tail = sorted_df.loc[mask].tail(n_days + 1)
    if len(tail) < n_days + 1:
        return None
    returns = np.log(tail["close"].to_numpy())
    diffs = np.diff(returns)
    return float(np.std(diffs) * np.sqrt(252))


def regime_one_hot(zone: str | None) -> list[int]:
    return [1 if r == (zone or "") else 0 for r in REGIMES]


def dte_bucket(dte: int | None) -> list[int]:
    if dte is None:
        return [0, 0, 0]
    if dte <= 5:
        return [1, 0, 0]
    if dte <= 15:
        return [0, 1, 0]
    return [0, 0, 1]


def trust_grade_ordinal(grade: str | None) -> int:
    if not grade:
        return 0
    return GRADE_MAP.get(grade.strip().upper(), 0)


def build_feature_vector(
    *,
    prices: pd.DataFrame,
    sector: pd.DataFrame,
    as_of: str,
    regime: str,
    dte: int,
    trust_grade: str | None,
    nifty_breadth_5d: float | None,
    pcr_z_score: float | None,
) -> dict[str, Any]:
    if sector is None:
        raise ValueError("sector DataFrame is required (pass the sector index bars)")
    if prices is None:
        raise ValueError("prices DataFrame is required")

    out: dict[str, Any] = {
        "sector_5d_return": sector_n_day_return(sector, as_of, 5),
        "sector_20d_return": sector_n_day_return(sector, as_of, 20),
        "ticker_rs_10d": ticker_rs_vs_sector(prices, sector, as_of, 10),
        "ticker_3d_momentum": ticker_n_day_momentum(prices, as_of, 3),
        "nifty_breadth_5d": nifty_breadth_5d if nifty_breadth_5d is not None else 0.5,
        "pcr_z_score": pcr_z_score if pcr_z_score is not None else 0.0,
        "trust_grade_ordinal": trust_grade_ordinal(trust_grade),
        "realized_vol_60d": realized_vol(prices, as_of, 60),
    }
    for i, label in enumerate(["RISK-OFF", "NEUTRAL", "RISK-ON", "EUPHORIA", "CRISIS"]):
        out[f"regime_{label}"] = regime_one_hot(regime)[i]
    for i, bucket in enumerate(["dte_0_5", "dte_6_15", "dte_16_plus"]):
        out[bucket] = dte_bucket(dte)[i]
    return out
