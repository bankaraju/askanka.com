"""Group Phase C OPPORTUNITY signals into sector-level long/short pairs.

For each (date, sector) with >=2 OPPORTUNITY signals, pair the highest
``expected_return * confidence`` candidate (long) with the lowest
(short). Equal notional.
"""
from __future__ import annotations

import pandas as pd


def build_sector_pairs(signals: pd.DataFrame) -> list[dict]:
    """Return list of pair dicts: {date, sector, long_symbol, short_symbol,
    long_conviction, short_conviction}.
    """
    if signals.empty:
        return []
    df = signals.copy()
    df = df[df["classification"] == "OPPORTUNITY"]
    if df.empty:
        return []
    df["date"] = pd.to_datetime(df["date"])
    df["_conviction"] = df["expected_return"].astype(float) * df["confidence"].astype(float)

    pairs: list[dict] = []
    for (date, sector), cohort in df.groupby(["date", "sector"]):
        if len(cohort) < 2:
            continue
        top = cohort.loc[cohort["_conviction"].idxmax()]
        bot = cohort.loc[cohort["_conviction"].idxmin()]
        if top["symbol"] == bot["symbol"]:
            continue
        pairs.append({
            "date": date, "sector": sector,
            "long_symbol": top["symbol"], "long_conviction": float(top["_conviction"]),
            "short_symbol": bot["symbol"], "short_conviction": float(bot["_conviction"]),
        })
    return pairs
