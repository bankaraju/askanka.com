"""Schema contract validator per Data Policy §8."""
from __future__ import annotations

import pandas as pd

REQUIRED_COLUMNS = {"ticker", "trade_date", "timestamp", "open", "high", "low", "close", "volume"}
PRICE_COLS = ["open", "high", "low", "close"]


class SchemaViolation(Exception):
    """Frame violates the §8 contract."""


def validate_minute_bars_schema(df: pd.DataFrame) -> None:
    """Raise SchemaViolation if the contract is broken; return None on pass."""
    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise SchemaViolation(f"missing columns: {sorted(missing)}")

    for col in PRICE_COLS:
        if (df[col] <= 0).any():
            raise SchemaViolation(f"non-positive value in {col}")

    if (df["high"] < df["low"]).any():
        raise SchemaViolation("high < low in at least one row")

    if (df["volume"] < 0).any():
        raise SchemaViolation("negative volume in at least one row")
