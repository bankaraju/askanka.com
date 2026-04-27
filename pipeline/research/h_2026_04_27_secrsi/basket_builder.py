"""SECRSI basket builder.

Pure function: given a sector snapshot, rank sectors and pick the
top-N / bottom-N stocks within. Spec §3.2-§3.4.

Returns 8 legs (default 2 sectors × 2 stocks per side, market-neutral
equal-weight). No I/O, no live data.
"""
from __future__ import annotations

from typing import Iterable


_DEFAULT_TOP_N_SECTORS = 2
_DEFAULT_TOP_N_STOCKS = 2


def build_basket(
    snapshot: Iterable[dict],
    top_n_sectors: int = _DEFAULT_TOP_N_SECTORS,
    top_n_stocks: int = _DEFAULT_TOP_N_STOCKS,
) -> list[dict]:
    """Pick top-N / bottom-N sectors and best/worst stocks within.

    Sector ranking is by ``sector_score`` descending for longs and
    ascending for shorts, with ties broken alphabetically. Within each
    selected sector, stocks are picked by their ``stock_pcts`` value
    (best for LONG sectors, worst for SHORT sectors), again with
    alphabetical tie-breaks.

    Args:
        snapshot: Iterable of sector dicts as produced by `take_snapshot`.
            Sectors with ``qualified=False`` are skipped.
        top_n_sectors: Number of sectors to take from each side. Default 2.
        top_n_stocks: Number of stocks to take per selected sector. Default 2.

    Returns:
        List of 2 × top_n_sectors × top_n_stocks leg dicts (8 legs at the
        default 2×2). Returns ``[]`` when fewer than 2 × top_n_sectors
        sectors are qualified.

        Each leg dict has keys: ``ticker``, ``sector``, ``side``,
        ``sector_score``, ``stock_pct_at_snap``, ``weight``.
    """
    qualified = [s for s in snapshot if s.get("qualified")]
    if len(qualified) < 2 * top_n_sectors:
        return []

    longs_sorted = sorted(qualified, key=lambda s: (-s["sector_score"], s["sector"]))
    shorts_sorted = sorted(qualified, key=lambda s: (s["sector_score"], s["sector"]))

    long_sectors = longs_sorted[:top_n_sectors]
    short_sectors = shorts_sorted[:top_n_sectors]

    if {s["sector"] for s in long_sectors} & {s["sector"] for s in short_sectors}:
        return []

    total_legs = 2 * top_n_sectors * top_n_stocks
    weight = 1.0 / total_legs

    basket: list[dict] = []
    for sector_row in long_sectors:
        ranked = sorted(
            sector_row["stock_pcts"].items(),
            key=lambda kv: (-kv[1], kv[0]),
        )
        for ticker, stock_pct in ranked[:top_n_stocks]:
            basket.append({
                "ticker": ticker,
                "sector": sector_row["sector"],
                "side": "LONG",
                "sector_score": sector_row["sector_score"],
                "stock_pct_at_snap": stock_pct,
                "weight": weight,
            })

    for sector_row in short_sectors:
        ranked = sorted(
            sector_row["stock_pcts"].items(),
            key=lambda kv: (kv[1], kv[0]),
        )
        for ticker, stock_pct in ranked[:top_n_stocks]:
            basket.append({
                "ticker": ticker,
                "sector": sector_row["sector"],
                "side": "SHORT",
                "sector_score": sector_row["sector_score"],
                "stock_pct_at_snap": stock_pct,
                "weight": weight,
            })

    return basket
