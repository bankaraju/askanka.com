"""User rule: avoid shorting defense stocks (rallies are global-driven).

Does not drop defense tickers from the backtest; flags (defense, UP→SHORT)
pairs so the §11C portfolio gate can exclude them from its survivor set.
"""
from __future__ import annotations

HARDCODED_DEFENSE = {"BEL", "HAL", "BDL", "MIDHANI", "GRSE", "MAZDOCK"}


def is_defense(ticker: str, sector_of: dict[str, str]) -> bool:
    if ticker in HARDCODED_DEFENSE:
        return True
    return sector_of.get(ticker, "") == "Defence"


def is_defense_short(row: dict, sector_of: dict[str, str]) -> bool:
    """UP direction = fade-SHORT. Flag only when both conditions hold."""
    return row["direction"] == "UP" and is_defense(row["ticker"], sector_of)


def partition(
    survivors: list[dict],
    sector_of: dict[str, str],
) -> tuple[list[dict], list[dict]]:
    kept, flagged = [], []
    for r in survivors:
        if is_defense_short(r, sector_of):
            flagged.append({**r, "reason": "defense_short_user_rule"})
        else:
            kept.append(r)
    return kept, flagged
