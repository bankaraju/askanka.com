"""§13 cross-source reconciliation: aggregate minutes → daily, compare to EOD parquet."""
from __future__ import annotations

import pandas as pd

MAX_DELTA_PCT = 0.005  # §13 acceptance: max 0.5% delta


class ReconciliationFailure(Exception):
    """Aggregated minute-bar daily OHLC diverges from EOD source beyond threshold."""


def aggregate_minute_to_daily(minute_df: pd.DataFrame) -> pd.DataFrame:
    """Group minute bars into daily OHLC + volume per ticker per trade_date."""
    g = minute_df.sort_values("timestamp").groupby(["ticker", "trade_date"], as_index=False)
    return g.agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        volume=("volume", "sum"),
    )


def compare_to_eod(minute_df: pd.DataFrame, eod_df: pd.DataFrame, raise_on_failure: bool = False) -> dict:
    """Compare minute-aggregated daily close to EOD source close.

    Returns report dict with max_delta_pct + per-row deltas.
    Raises ReconciliationFailure if raise_on_failure and max_delta_pct > MAX_DELTA_PCT.
    """
    daily = aggregate_minute_to_daily(minute_df)
    merged = daily[["ticker", "trade_date", "close"]].rename(columns={"close": "close_minute"}).merge(
        eod_df[["ticker", "trade_date", "close"]].rename(columns={"close": "close_eod"}),
        on=["ticker", "trade_date"],
    )
    merged["delta_pct"] = (merged["close_minute"] - merged["close_eod"]).abs() / merged["close_eod"]
    max_delta = float(merged["delta_pct"].max()) if len(merged) else 0.0
    report = {
        "max_delta_pct": max_delta,
        "n_rows_compared": len(merged),
        "rows_above_threshold": int((merged["delta_pct"] > MAX_DELTA_PCT).sum()),
    }
    if raise_on_failure and max_delta > MAX_DELTA_PCT:
        raise ReconciliationFailure(
            f"max_delta_pct {max_delta:.4f} exceeds threshold {MAX_DELTA_PCT}"
        )
    return report
