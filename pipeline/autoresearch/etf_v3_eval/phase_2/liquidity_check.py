"""§11.1 — 60-day ADV per ticker; 10× threshold; linear impact penalty.

compute_60d_adv() returns a dict {ticker: mean_notional} where mean_notional
is the average of daily notional (close × volume) over the trailing ``window``
trading days.  This is the correct per-day-notional approach: each day's
traded value is computed first, then averaged — giving an accurate estimate
when the price drifts over the window.

impact_penalty_bps() applies the linear impact model from §11.1 of
backtesting-specs:
    penalty_bps = 5.0 × (position_size / adv)

The 5.0 bps linear-impact constant is an empirical small-cap parameter
calibrated to NSE F&O stocks (§11.1 of backtesting-specs.txt).  For
large-cap, liquid names the actual impact is lower; for illiquid stocks it
will be higher.  The constant is intentionally conservative.
"""
from __future__ import annotations

from typing import Mapping

import pandas as pd

_REQUIRED_COLS = {"ticker", "close", "volume"}


def compute_60d_adv(daily_bars: pd.DataFrame, window: int = 60) -> Mapping[str, float]:
    """Return rolling-window mean daily notional per ticker.

    Parameters
    ----------
    daily_bars:
        DataFrame with columns ``ticker``, ``close``, ``volume``.  May also
        contain other columns (e.g. ``trade_date``) which are ignored.
    window:
        Number of most-recent trading days to average.  Default 60.

    Returns
    -------
    dict mapping ticker → mean daily notional (INR or USD, matching the
    currency of ``close``).

    Raises
    ------
    ValueError
        If any of ``ticker``, ``close``, or ``volume`` are missing from
        ``daily_bars``.  Message includes the list of columns that are present.
    """
    missing = _REQUIRED_COLS - set(daily_bars.columns)
    if missing:
        raise ValueError(
            f"compute_60d_adv: missing required column(s) {sorted(missing)}; "
            f"columns present: {sorted(daily_bars.columns)}"
        )

    df = daily_bars.copy()
    df["notional"] = df["close"] * df["volume"]
    grouped = df.groupby("ticker")["notional"].apply(
        lambda s: s.tail(window).mean()
    )
    return grouped.to_dict()


def impact_penalty_bps(position_size: float, adv: float) -> float:
    """Linear market-impact penalty in basis points per §11.1.

    Formula: penalty_bps = 5.0 × (position_size / adv)

    The 5.0 bps/unit coefficient is the empirical small-cap parameter from
    §11.1 of backtesting-specs.txt.

    Parameters
    ----------
    position_size:
        Gross notional of the position in the same currency as ``adv``.
        Must be ≥ 0.  Callers should pass abs(position_size) for short legs.
    adv:
        60-day average daily volume in notional terms (e.g. from
        ``compute_60d_adv``).  Must be > 0.

    Returns
    -------
    Estimated round-trip impact cost in basis points.

    Raises
    ------
    ValueError
        If ``adv`` ≤ 0.  A non-positive ADV means the ticker has no traded
        notional in the window, which is a data integrity issue — the caller
        must not trade it.
    ValueError
        If ``position_size`` < 0.  Short-position semantics belong to the
        caller; pass abs(position_size) for short legs.
    """
    if adv <= 0:
        raise ValueError(
            f"adv must be > 0; got {adv}. "
            "A non-positive ADV means the ticker has no traded notional in "
            "the measurement window — do not trade it."
        )
    if position_size < 0:
        raise ValueError(
            f"position_size must be >= 0; got {position_size}. "
            "For short legs, pass abs(position_size) — short-position "
            "semantics belong to the caller."
        )
    # 5.0 bps linear-impact constant: empirical small-cap parameter per §11.1
    return 5.0 * (position_size / adv)
