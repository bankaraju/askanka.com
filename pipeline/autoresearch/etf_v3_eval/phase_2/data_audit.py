"""§5A.1 mandatory per-run data quality report.

Reports counts of: zero-volume bars, zero/negative prices, duplicate timestamps,
stale-quote runs (k consecutive identical OHLC bars). Tag levels:
  - CLEAN          (impaired <= 1.0%)
  - DATA-IMPAIRED  (1.0% < impaired <= 3.0%)
  - AUTO-FAIL      (impaired > 3.0%)
"""
from __future__ import annotations

import pandas as pd


def _tag_for_pct(pct: float) -> str:
    if pct > 3.0:
        return "AUTO-FAIL"
    if pct > 1.0:
        return "DATA-IMPAIRED"
    return "CLEAN"


def audit_run_data(minute_df: pd.DataFrame, stale_window: int = 3) -> dict:
    """Return §5A.1 per-run data-quality report.

    A bar is counted as a "stale-quote-tail" iff it terminates a run of
    ``stale_window`` consecutive identical OHLC bars. The count is of TAILS,
    not of all bars within stale runs (so a 4-bar identical run with
    stale_window=3 reports two tails — bars 2 and 3).

    Parameters
    ----------
    minute_df:
        DataFrame with columns: ticker, timestamp, open, high, low, close, volume.
    stale_window:
        Minimum run length to flag as stale. Default 3.

    Returns
    -------
    dict with keys:
        n_rows, zero_volume_bar_count, zero_or_negative_price_count,
        duplicate_timestamp_count, stale_quote_count_min{stale_window},
        bad_data_pct, tag.
    """
    stale_key = f"stale_quote_count_min{stale_window}"

    if minute_df.empty:
        return {
            "n_rows": 0,
            "zero_volume_bar_count": 0,
            "zero_or_negative_price_count": 0,
            "duplicate_timestamp_count": 0,
            stale_key: 0,
            "bad_data_pct": 0.0,
            "tag": "CLEAN",
        }

    df = minute_df.copy()
    n = len(df)

    zero_vol = int((df["volume"] == 0).sum())
    neg_price = int(((df["open"] <= 0) | (df["close"] <= 0)).sum())
    duplicates = int(df.duplicated(subset=["ticker", "timestamp"]).sum())

    df = df.sort_values(["ticker", "timestamp"]).reset_index(drop=True)
    df["_ohlc"] = df[["open", "high", "low", "close"]].apply(tuple, axis=1)

    # eq_prev[i] = True iff bar i has the same OHLC as bar i-1 (within ticker)
    eq_prev = df.groupby("ticker")["_ohlc"].transform(lambda s: s.eq(s.shift()))

    # A bar is a stale-tail iff the prior (stale_window-1) consecutive bars
    # are all eq_prev=True. Rolling sum over window=(stale_window-1) equals
    # (stale_window-1) iff every value in the window is True.
    target = stale_window - 1
    stale_mask = (
        eq_prev.groupby(df["ticker"])
        .rolling(window=target, min_periods=target)
        .sum()
        .reset_index(level=0, drop=True)
    ) >= target
    stale = int(stale_mask.sum())

    impaired = zero_vol + neg_price + duplicates + stale
    pct = float(impaired) / max(n, 1) * 100.0

    return {
        "n_rows": n,
        "zero_volume_bar_count": zero_vol,
        "zero_or_negative_price_count": neg_price,
        "duplicate_timestamp_count": duplicates,
        stale_key: stale,
        "bad_data_pct": pct,
        "tag": _tag_for_pct(pct),
    }
