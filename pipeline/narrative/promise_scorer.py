"""
Step 10: Promise-vs-Delivery Scoring
Match historical management claims against subsequent financial results.

This is the core of the Pattern Premium — did management deliver on promises?
Boolean verification: 'Delivered' vs 'Dropped' for every target.

Key forensic signal: "Quietly Dropped" narratives — when a strategic theme
disappears from filings without explanation, automatic credibility deduction.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class PromiseResult:
    """Result of scoring a management claim against reality."""
    claim_quarter: str
    claim_text: str
    target_metric: str
    target_value: str
    verification_quarter: str       # When we check the outcome
    actual_value: Optional[str]     # What actually happened
    status: str                     # "delivered" | "partially_delivered" | "missed" | "quietly_dropped"
    evidence: str                   # Source reference for the outcome
    gap_pct: Optional[float]        # % gap between promise and delivery


def score_promises(claims: list, quarterly_filings: list) -> list[PromiseResult]:
    """Score each management claim against subsequent results.

    For each claim:
    1. Find the target timeline quarter in filings
    2. Extract the actual metric value
    3. Compare: delivered / partially / missed / quietly dropped

    "Quietly Dropped" detection:
    - If a claim's theme (e.g., "digital transformation") appears in Q1-Q3
      but vanishes from Q4 onwards with no explanation → QUIETLY_DROPPED
    """
    results = []

    for claim in claims:
        result = _verify_claim(claim, quarterly_filings)
        if result:
            results.append(result)

    return results


def _verify_claim(claim, quarterly_filings: list) -> Optional[PromiseResult]:
    """Verify a single claim against subsequent filings."""
    # TODO: Implement claim verification logic
    # 1. Parse target timeline
    # 2. Find matching quarter in filings
    # 3. Extract actual metric
    # 4. Score delivery
    return None


def detect_quietly_dropped(claims: list, quarterly_filings: list) -> list[str]:
    """Detect themes that disappeared without explanation.

    Returns list of dropped theme descriptions.
    """
    # TODO: Track theme presence across quarters
    # Flag any theme that appears 2+ times then vanishes
    return []
