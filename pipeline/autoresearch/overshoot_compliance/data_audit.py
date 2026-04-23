"""Data-quality audit per §5A of backtesting-specs.txt v1.0."""
from __future__ import annotations

import pandas as pd


def audit_ticker(
    ticker: str,
    df: pd.DataFrame,
    business_days: pd.DatetimeIndex,
    stale_run_min: int = 3,
) -> dict:
    """Audit one ticker's OHLC frame against the expected business-day grid.

    Returns a dict with missing, duplicate, stale-run, zero-price, zero-volume
    counts and the total impaired-bar count.
    """
    observed = pd.DatetimeIndex(df.index).normalize()
    observed_set = set(observed)
    # Listing-effect guard: a ticker that starts trading mid-window cannot
    # be penalised for pre-listing days. Clip the expected calendar to
    # start at its first observed bar.
    first_obs = observed.min() if len(observed) else None
    expected_all = pd.DatetimeIndex(business_days).normalize()
    expected = {dt for dt in expected_all if first_obs is None or dt >= first_obs}
    missing = len(expected - observed_set)
    duplicate = int(observed.duplicated().sum())

    # identify runs of identical OHLC of length >= stale_run_min
    stale = 0
    if len(df) > 0:
        key = (
            df["Open"].astype(float).astype(str) + "|"
            + df["High"].astype(float).astype(str) + "|"
            + df["Low"].astype(float).astype(str) + "|"
            + df["Close"].astype(float).astype(str)
        )
        run_id = (key != key.shift()).cumsum()
        run_sizes = run_id.value_counts()
        for size in run_sizes.values:
            if size >= stale_run_min:
                stale += int(size)

    zero_price = int(((df[["Open", "High", "Low", "Close"]] <= 0).any(axis=1)).sum())
    zero_volume = 0
    if "Volume" in df.columns:
        zero_volume = int((df["Volume"].fillna(0) <= 0).sum())

    impaired_bars = missing + duplicate + stale + zero_price + zero_volume
    total_bars = max(1, len(expected))
    return {
        "ticker": ticker,
        "missing_bar_count": missing,
        "duplicate_timestamp_count": duplicate,
        "stale_quote_count": stale,
        "zero_or_negative_price_count": zero_price,
        "zero_volume_bar_count": zero_volume,
        "impaired_bars": impaired_bars,
        "total_bars": total_bars,
    }


def aggregate(per_ticker: dict[str, dict]) -> dict:
    """Aggregate per-ticker audit results and classify overall data quality."""
    total = sum(r["total_bars"] for r in per_ticker.values())
    impaired = sum(r["impaired_bars"] for r in per_ticker.values())
    pct = (impaired / total * 100.0) if total else 0.0
    if pct > 3.0:
        cls = "AUTO-FAIL"
    elif pct > 1.0:
        cls = "DATA-IMPAIRED"
    else:
        cls = "CLEAN"
    return {
        "total_bars": total,
        "impaired_bars": impaired,
        "impaired_pct": round(pct, 3),
        "classification": cls,
        "per_ticker": per_ticker,
    }
