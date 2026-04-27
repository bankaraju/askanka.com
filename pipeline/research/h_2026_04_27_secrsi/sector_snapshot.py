"""SECRSI sector snapshot.

Pure functions for the 11:00 IST snapshot per spec §3.1: aggregate
per-stock %chg-from-open into per-sector median scores.

No I/O — both `take_snapshot` and the helper expect pre-fetched price
dicts and a pre-resolved sector map. Live wiring lives in
``forward_shadow.py``.
"""
from __future__ import annotations

import statistics
from typing import Mapping


def take_snapshot(
    prices_open: Mapping[str, float],
    prices_now: Mapping[str, float],
    sector_map: Mapping[str, str],
    min_stocks_per_sector: int = 4,
) -> list[dict]:
    """Aggregate per-stock %chg-from-open into per-sector medians.

    Args:
        prices_open: Per-ticker open price for today.
        prices_now: Per-ticker last price at snapshot time. Stocks missing
            from this dict (e.g., suspended, no quote) are dropped from
            sector aggregation.
        sector_map: Per-ticker → sector name. Stocks not in the map are
            excluded from any sector. Stocks mapped to "Unmapped" or empty
            string are also excluded.
        min_stocks_per_sector: Minimum sector size to qualify for the
            ranking step. Sectors with fewer surviving stocks are returned
            with ``qualified=False`` so the caller can still inspect them
            but they are not selectable in `basket_builder`.

    Returns:
        List of dicts, one per sector that had at least one surviving
        stock, with keys:

        - ``sector`` (str)
        - ``sector_score`` (float) — median of per-stock pct change
        - ``n_stocks`` (int) — count of stocks contributing
        - ``qualified`` (bool) — n_stocks ≥ min_stocks_per_sector
        - ``stock_pcts`` (dict[str, float]) — per-ticker contributions

        The list is unsorted; the caller ranks via `basket_builder`.
    """
    by_sector: dict[str, dict[str, float]] = {}

    for ticker, open_px in prices_open.items():
        sector = sector_map.get(ticker, "")
        if not sector or sector == "Unmapped":
            continue
        now_px = prices_now.get(ticker)
        if now_px is None or open_px <= 0:
            continue
        pct = (now_px - open_px) / open_px
        by_sector.setdefault(sector, {})[ticker] = pct

    out: list[dict] = []
    for sector, contribs in by_sector.items():
        n = len(contribs)
        if n == 0:
            continue
        score = statistics.median(contribs.values())
        out.append({
            "sector": sector,
            "sector_score": score,
            "n_stocks": n,
            "qualified": n >= min_stocks_per_sector,
            "stock_pcts": dict(contribs),
        })
    return out
