"""Percentile-based financial scorer for a sector cohort.

Takes a dict of {symbol: metrics_dict} for all stocks in ONE sector, plus a list
of KPI definitions, and returns {symbol: financial_score} where scores are 0-100.

Scoring logic (per KPI):
1. Collect metric values across all stocks (skip None/missing).
2. Winsorize at 5th / 95th percentile to dampen outliers.
3. Compute percentile rank for each stock.
4. If KPI direction is "lower" (e.g. Debt_to_Equity), invert: score = 100 - percentile.
5. Multiply by KPI weight.

Per stock: sum weighted percentile scores. If KPIs are missing, renormalize weights so
the final score is always 0-100. Single-stock sectors default to 50.
"""
from __future__ import annotations

import statistics
from typing import Any


def _winsorize(values: list[float], lower: float = 0.05, upper: float = 0.95) -> list[float]:
    """Clip extremes at lower/upper quantiles.

    Args:
        values: List of floats to winsorize.
        lower:  Lower quantile (default 5th percentile).
        upper:  Upper quantile (default 95th percentile).

    Returns:
        New list with values clipped to [lower_bound, upper_bound].
    """
    if not values:
        return []
    if len(values) == 1:
        return list(values)

    sorted_vals = sorted(values)
    n = len(sorted_vals)

    def _quantile(q: float) -> float:
        idx = q * (n - 1)
        lo = int(idx)
        hi = min(lo + 1, n - 1)
        frac = idx - lo
        return sorted_vals[lo] * (1 - frac) + sorted_vals[hi] * frac

    lo_bound = _quantile(lower)
    hi_bound = _quantile(upper)
    return [max(lo_bound, min(hi_bound, v)) for v in values]


def _percentile_rank(value: float, all_values: list[float]) -> float:
    """Return 0-100 percentile rank of value within all_values.

    Uses the fraction of values strictly below *value*, plus half the ties,
    divided by total count — the "mid-rank" convention, scaled to 0-100.
    With a one-element list the rank is 50.0 by convention.

    Args:
        value:      The value whose rank is requested.
        all_values: The full population (including *value*).

    Returns:
        Percentile rank in [0, 100].
    """
    n = len(all_values)
    if n == 0:
        return 50.0
    if n == 1:
        return 50.0
    below = sum(1 for v in all_values if v < value)
    equal = sum(1 for v in all_values if v == value)
    return (below + 0.5 * equal) / n * 100.0


def score_sector(
    sector_metrics: dict[str, dict[str, Any]],
    kpis: list[dict],
) -> dict[str, float]:
    """Score all stocks in a sector.

    Args:
        sector_metrics: {symbol: metrics_dict} — metrics dict as returned by
                        MetricExtractor.extract().
        kpis: List of KPI defs, each a dict with keys:
              - "name"      (str)   — key in metrics_dict
              - "direction" (str)   — "higher" or "lower"
              - "weight"    (float) — relative weight (need not sum to 1)

    Returns:
        {symbol: financial_score} where financial_score is 0-100.
        Single-stock sectors return {symbol: 50.0}.
    """
    symbols = list(sector_metrics.keys())

    # Edge case: single stock
    if len(symbols) <= 1:
        return {s: 50.0 for s in symbols}

    # For each symbol accumulate weighted scores and total weight used
    weighted_sum: dict[str, float] = {s: 0.0 for s in symbols}
    weight_used: dict[str, float] = {s: 0.0 for s in symbols}

    for kpi in kpis:
        metric_name: str = kpi["name"]
        direction: str = kpi.get("direction", "higher")
        weight: float = float(kpi.get("weight", 1.0))

        # Collect valid values, preserving which symbol they belong to
        valid: dict[str, float] = {}
        for sym in symbols:
            raw = sector_metrics[sym].get(metric_name)
            if raw is not None:
                try:
                    valid[sym] = float(raw)
                except (TypeError, ValueError):
                    pass

        if not valid:
            # No stock has this metric — skip entirely
            continue

        # Winsorize the raw values (order-preserving)
        sym_list = list(valid.keys())
        val_list = [valid[s] for s in sym_list]
        w_vals = _winsorize(val_list)

        # Build a flat list of winsorized values for percentile computation
        # Map back: sym -> winsorized value
        w_map = {sym_list[i]: w_vals[i] for i in range(len(sym_list))}

        for sym in sym_list:
            pct = _percentile_rank(w_map[sym], w_vals)
            if direction == "lower":
                pct = 100.0 - pct
            weighted_sum[sym] += pct * weight
            weight_used[sym] += weight

    # Normalize to 0-100
    result: dict[str, float] = {}
    for sym in symbols:
        w = weight_used[sym]
        if w == 0.0:
            # No KPIs available for this stock at all
            result[sym] = 50.0
        else:
            # Renormalize: each KPI contributes pct * weight; max possible = 100 * w
            # So score = weighted_sum / w  (already a 0-100 weighted average)
            result[sym] = round(weighted_sum[sym] / w, 2)

    return result
