"""
management_quant.py — Layer 2A of Scorecard V2

Computes a management quality score (0-100) from purely quantitative proxies.
No LLM needed. Layer 2B (LLM qualitative) comes in Task 7 and blends at 50/50
via the orchestrator (Task 6).

Design spec: §5.1 weights
  - Capital Allocation (ROE stability):      30%
  - Governance (pledge):                     20%
  - Execution Consistency (margin stability): 25%
  - Accounting Conservatism (CFO/PAT):       15%
  - Skin in the Game (holding):              10%

Hard caps (applied after weighted sum):
  - promoter_pledge_pct > 30  → cap at 40
  - CFO_PAT avg < 0.3          → cap at 50
"""

from __future__ import annotations

import statistics
from typing import Union


# ---------------------------------------------------------------------------
# Sub-scorers
# ---------------------------------------------------------------------------

def _pledge_score(pledge_pct: float) -> int:
    """Score promoter pledge on a 1-5 scale.

    0%       → 5 (best)
    < 10%    → 4
    10-30%   → 3
    30-50%   → 2
    > 50%    → 1 (worst)
    """
    if pledge_pct == 0:
        return 5
    if pledge_pct < 10:
        return 4
    if pledge_pct < 30:
        return 3
    if pledge_pct <= 50:
        return 2
    return 1


def _roe_stability_score(roe_history: list[float]) -> float:
    """Capital allocation quality: high mean ROE + low std = better.

    Returns 0-20 scale.
    - If mean ROE > 20 and std < 3: score 20 (max)
    - Mean contributes 60%, inverse-std contributes 40%
    - Empty history: return 10 (midpoint)
    """
    if not roe_history:
        return 10.0

    mean_roe = statistics.mean(roe_history)
    std_roe = statistics.pstdev(roe_history) if len(roe_history) > 1 else 0.0

    # Mean component: 0-12 (60% of 20)
    # Anchored: mean <= 0 → 0, mean >= 20 → 12, linear between
    mean_component = max(0.0, min(12.0, mean_roe / 20.0 * 12.0))

    # Std component: 0-8 (40% of 20)
    # Anchored: std >= 15 → 0, std <= 0 → 8, linear between
    std_component = max(0.0, min(8.0, (1.0 - std_roe / 15.0) * 8.0))

    raw = mean_component + std_component

    # Honour the stated maximum: if mean > 20 AND std < 3 → 20
    if mean_roe > 20 and std_roe < 3:
        return 20.0

    return min(20.0, max(0.0, raw))


def _margin_stability_score(margin_history: list[float]) -> float:
    """Execution consistency: lower std of margins = better.

    Returns 0-20 scale.
    - std < 2  → 20 (max)
    - std > 15 → 2  (near min)
    - Linear between
    - Empty history: return 10 (midpoint)
    """
    if not margin_history:
        return 10.0

    std = statistics.pstdev(margin_history) if len(margin_history) > 1 else 0.0

    if std < 2:
        return 20.0
    if std > 15:
        return 2.0

    # Linear: at std=2 → 20, at std=15 → 2
    score = 20.0 - (std - 2.0) / (15.0 - 2.0) * (20.0 - 2.0)
    return round(max(2.0, min(20.0, score)), 4)


def _cfo_pat_consistency_score(cfo_pat: Union[float, list[float]]) -> float:
    """Accounting conservatism: higher average CFO/PAT + fewer negative years = better.

    Returns 0-20 scale.
    - avg >= 1.0 → 20
    - avg <= 0   → 0
    - Linear between
    - If cfo_pat is a list, average it and apply a negative-year penalty.
    """
    if isinstance(cfo_pat, list):
        if not cfo_pat:
            return 10.0
        avg = statistics.mean(cfo_pat)
        # Penalise each negative year: subtract 1 point per negative year (min 0)
        negative_years = sum(1 for v in cfo_pat if v < 0)
        penalty = negative_years * 1.0
    elif cfo_pat is None:
        return 10.0
    else:
        avg = float(cfo_pat)
        penalty = 0.0

    # Linear: avg=0 → 0, avg=1.0 → 20
    base_score = max(0.0, min(20.0, avg * 20.0))
    score = max(0.0, base_score - penalty)
    return round(score, 4)


def _skin_in_game_score(holding_pct: float) -> float:
    """Promoter holding alignment: higher holding = better.

    Returns 0-10 scale.
    >= 70% → 10
    >= 50% → 8
    >= 30% → 5
    >= 10% → 3
    <  10% → 1
    """
    if holding_pct >= 70:
        return 10.0
    if holding_pct >= 50:
        return 8.0
    if holding_pct >= 30:
        return 5.0
    if holding_pct >= 10:
        return 3.0
    return 1.0


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def compute_management_quant(metrics: dict) -> float:
    """Compute management quality score (0-100) from quantitative proxies.

    Args:
        metrics: dict with keys:
            ROE_history           list[float]  — yearly ROE values
            Margin_history        list[float]  — yearly margin values
            CFO_PAT               float | list[float]
            promoter_pledge_pct   float        — 0-100
            promoter_holding_pct  float        — 0-100

    Returns:
        float in [0, 100], after hard caps applied.
    """
    # --- safe defaults ---
    roe_history: list[float] = metrics.get("ROE_history") or []
    margin_history: list[float] = metrics.get("Margin_history") or []
    cfo_pat = metrics.get("CFO_PAT", 0.5)  # 0.5 ≈ midpoint
    pledge_pct: float = float(metrics.get("promoter_pledge_pct", 0.0))
    holding_pct: float = float(metrics.get("promoter_holding_pct", 50.0))

    # --- sub-scores ---
    roe_score = _roe_stability_score(roe_history)        # 0-20
    pledge = _pledge_score(pledge_pct)                    # 1-5
    margin_score = _margin_stability_score(margin_history)  # 0-20
    cfo_score = _cfo_pat_consistency_score(cfo_pat)       # 0-20
    skin_score = _skin_in_game_score(holding_pct)         # 0-10 (1-10 in practice)

    # --- weighted sum ---
    # Max possible raw = 20*0.30 + 5*0.20 + 20*0.25 + 20*0.15 + 10*0.10
    #                  = 6 + 1 + 5 + 3 + 1 = 16
    raw = (
        roe_score    * 0.30
        + pledge     * 0.20
        + margin_score * 0.25
        + cfo_score  * 0.15
        + skin_score * 0.10
    )

    score = min(100.0, raw / 16.0 * 100.0)

    # --- hard caps ---
    if pledge_pct > 30:
        score = min(score, 40.0)

    # Resolve CFO/PAT average for cap check
    if isinstance(cfo_pat, list):
        cfo_avg = statistics.mean(cfo_pat) if cfo_pat else 0.5
    elif cfo_pat is not None:
        cfo_avg = float(cfo_pat)
    else:
        cfo_avg = 0.5

    if cfo_avg < 0.3:
        score = min(score, 50.0)

    return round(score, 2)
