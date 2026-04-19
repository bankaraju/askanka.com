"""Composite ranker: blends financial + management scores, force-ranks within sector,
assigns letter grades, and generates human-readable remarks.

Grade bands (by percentile of rank, lower rank = better):
  A: top 15%      (ranks 1 .. max(1, round(N * 0.15)))
  B: next 20%     (15-35%)
  C: middle 30%   (35-65%)
  D: next 20%     (65-85%)
  F: bottom 15%   (85-100%)

Each band is guaranteed at least 1 stock (min 1), so tiny sectors get A then maybe
B/C/D then F depending on N.
"""
from __future__ import annotations

import statistics


# ---------------------------------------------------------------------------
# Core blend
# ---------------------------------------------------------------------------

def compute_composite(fin_score: float, mgmt_score: float, weights: dict) -> float:
    """Weighted blend of financial and management scores.

    Args:
        fin_score:  Financial score 0-100.
        mgmt_score: Management score 0-100.
        weights:    {"financial": float, "management": float}

    Returns:
        Composite score 0-100.
    """
    return fin_score * weights["financial"] + mgmt_score * weights["management"]


# ---------------------------------------------------------------------------
# Confidence
# ---------------------------------------------------------------------------

def compute_confidence(coverage_pct: float, data_sources: int) -> str:
    """Derive a confidence tier from data coverage.

    Args:
        coverage_pct:  Percentage of expected data points present (0-100).
        data_sources:  Number of distinct data sources used.

    Returns:
        "high", "medium", or "low".
    """
    if coverage_pct >= 80 and data_sources >= 2:
        return "high"
    if coverage_pct >= 50:
        return "medium"
    return "low"


# ---------------------------------------------------------------------------
# Grade-band helper
# ---------------------------------------------------------------------------

def _assign_grades(n: int) -> list[str]:
    """Return a list of length n where index i has the grade for rank (i+1).

    Bands:
      A: 1 .. a_cutoff
      B: a_cutoff+1 .. b_cutoff
      C: b_cutoff+1 .. c_cutoff
      D: c_cutoff+1 .. d_cutoff
      F: d_cutoff+1 .. n
    """
    a_count = max(1, round(n * 0.15))
    b_count = max(1, round(n * 0.20))
    c_count = max(1, round(n * 0.30))
    d_count = max(1, round(n * 0.20))
    # F gets whatever is left
    f_count = n - a_count - b_count - c_count - d_count
    if f_count < 1:
        # Clamp: steal from d, then c, to ensure F gets at least 1 when n >= 5
        # For very small n, this is acceptable.
        f_count = max(0, n - a_count - b_count - c_count - d_count)

    grades = (
        ["A"] * a_count
        + ["B"] * b_count
        + ["C"] * c_count
        + ["D"] * d_count
        + ["F"] * f_count
    )
    # Trim or pad to exactly n (floating-point rounding may drift by ±1)
    if len(grades) > n:
        grades = grades[:n]
    while len(grades) < n:
        grades.append("F")

    return grades


# ---------------------------------------------------------------------------
# Forced sector ranker
# ---------------------------------------------------------------------------

def forced_rank_sector(stocks: dict[str, dict], weights: dict) -> dict[str, dict]:
    """Compute composite scores, force-rank within sector, assign grades and gaps.

    Args:
        stocks:  {symbol: {"financial_score": float, "management_score": float,
                            "sector": str, ...}}
                 All stocks are assumed to belong to the same sector.
        weights: {"financial": float, "management": float}

    Returns:
        {symbol: {
            composite_score:       float,
            sector_rank:           int,      # 1 = best
            sector_percentile:     float,    # 0-100, 0 = best
            sector_grade:          str,      # A/B/C/D/F
            sector_leader:         str,      # symbol of rank-1 stock
            sector_leader_composite: float,
            sector_gap_to_leader:  float,    # leader_composite - this_composite
            sector_gap_to_median:  float,    # this_composite - median_composite
            sector_total:          int,
        }}
    """
    if not stocks:
        return {}

    # Step 1: compute composite for every stock
    composites: dict[str, float] = {}
    for symbol, data in stocks.items():
        fin = float(data.get("financial_score", 0) or 0)
        mgmt = float(data.get("management_score", 0) or 0)
        composites[symbol] = compute_composite(fin, mgmt, weights)

    # Step 2: sort descending by composite
    ranked = sorted(composites.items(), key=lambda x: x[1], reverse=True)
    n = len(ranked)

    # Step 3: derive leader + median
    leader_symbol, leader_composite = ranked[0]
    all_scores = [score for _, score in ranked]
    median_composite = statistics.median(all_scores)

    # Step 4: build grade list
    grade_list = _assign_grades(n)

    # Step 5: assemble output
    result: dict[str, dict] = {}
    for idx, (symbol, composite) in enumerate(ranked):
        rank = idx + 1
        # percentile: 0 = best (rank 1), 100 = worst (rank N)
        # For rank 1 in a 1-stock sector: 0.0
        if n == 1:
            percentile = 0.0
        else:
            percentile = round((rank - 1) / (n - 1) * 100, 2)

        result[symbol] = {
            "composite_score": round(composite, 4),
            "sector_rank": rank,
            "sector_percentile": percentile,
            "sector_grade": grade_list[idx],
            "sector_leader": leader_symbol,
            "sector_leader_composite": round(leader_composite, 4),
            "sector_gap_to_leader": round(leader_composite - composite, 4),
            "sector_gap_to_median": round(composite - median_composite, 4),
            "sector_total": n,
        }

    return result


# ---------------------------------------------------------------------------
# Remark generator
# ---------------------------------------------------------------------------

def generate_remark(stock: dict) -> str:
    """Generate a one-line human-readable remark for a stock.

    Expected keys in *stock*:
        symbol, sector_rank, sector_total, sector (display name),
        financial_score, management_score,
        sector_leader, sector_leader_composite,
        confidence (str: high/medium/low),
        biggest_red_flag (optional str),
        biggest_strength (optional str).

    Returns:
        A single sentence summary string.
    """
    symbol = stock.get("symbol", "UNKNOWN")
    rank = stock.get("sector_rank", "?")
    total = stock.get("sector_total", "?")
    display_name = stock.get("sector", stock.get("display_name", "sector"))
    fin = stock.get("financial_score", 0)
    mgmt = stock.get("management_score", 0)
    leader = stock.get("sector_leader", "?")
    leader_composite = stock.get("sector_leader_composite", 0)
    confidence = stock.get("confidence", "low")

    red_flag = stock.get("biggest_red_flag") or ""
    strength = stock.get("biggest_strength") or ""

    # Build management suffix
    if red_flag:
        mgmt_suffix = f" — {red_flag}"
    elif strength:
        mgmt_suffix = f" — {strength}"
    else:
        mgmt_suffix = ""

    remark = (
        f"{symbol} ranks {rank}/{total} in {display_name}. "
        f"Financial {fin}/100. "
        f"Management {mgmt}/100{mgmt_suffix}. "
        f"Leader: {leader} ({leader_composite}). "
        f"Confidence: {confidence}."
    )
    return remark
