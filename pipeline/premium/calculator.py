"""
Step 11: ANKA Trust Score Calculation
The proprietary signal. Adjusts valuation based on management execution credibility.

Components:
1. Execution Score: % of promises delivered over multi-year cycles
2. Theme Diversity: How many strategic themes are being pursued
3. Dropped Theme Penalty: Deduction for quietly abandoned narratives
4. Digital Leadership: Bonus for sustained tech/digital investment with results

The ANKA Trust Score is a % adjustment to fair value:
- Positive = management over-delivers → valuation premium justified
- Negative = management under-delivers → valuation discount warranted
- "DCF Not Applicable" if forensic triggers met (DSO > 200, negative OCF)
"""


def calculate_trust_score(promise_results: list, ratios: dict) -> float:
    """Calculate the ANKA Trust Score adjustment.

    Returns: float percentage adjustment (e.g., +12.5 or -8.3)
    """
    # Check forensic abort conditions first
    if _should_abort_valuation(ratios):
        return float("-inf")  # Signal: DCF Not Applicable

    execution = _execution_score(promise_results)
    theme_div = _theme_diversity_score(promise_results)
    dropped_penalty = _dropped_theme_penalty(promise_results)
    digital_bonus = _digital_leadership_bonus(promise_results, ratios)

    # Weighted composite
    premium = (
        execution * 0.50 +
        theme_div * 0.15 +
        dropped_penalty * 0.25 +
        digital_bonus * 0.10
    )

    return round(premium, 1)


def _should_abort_valuation(ratios: dict) -> bool:
    """Check if forensic triggers mandate aborting DCF.

    Triggers:
    - DSO > 200 days
    - Negative OCF exposure
    """
    dso_values = ratios.get("receivable_days", [])
    if dso_values and any(v > 200 for _, v in dso_values if isinstance(v, (int, float))):
        return True

    ocf_values = ratios.get("ocf_to_pat", [])
    if ocf_values and any(v < 0 for _, v in ocf_values if isinstance(v, (int, float))):
        return True

    return False


def _execution_score(promise_results: list) -> float:
    """Score: % of promises delivered."""
    if not promise_results:
        return 0.0
    delivered = sum(1 for r in promise_results if r.status == "delivered")
    partial = sum(1 for r in promise_results if r.status == "partially_delivered")
    total = len(promise_results)
    return ((delivered + 0.5 * partial) / total) * 20 - 10  # Scale to [-10, +10]


def _theme_diversity_score(promise_results: list) -> float:
    """Score: breadth of strategic themes being pursued."""
    if not promise_results:
        return 0.0
    themes = {r.claim_text.split(":")[0] if ":" in r.claim_text else "general" for r in promise_results}
    # 3-5 themes is healthy, <2 is concentrated risk, >7 is unfocused
    n = len(themes)
    if n < 2:
        return -5.0
    elif n <= 5:
        return 5.0
    else:
        return 0.0  # Too many → unfocused


def _dropped_theme_penalty(promise_results: list) -> float:
    """Penalty for quietly dropped narratives."""
    dropped = sum(1 for r in promise_results if r.status == "quietly_dropped")
    return -dropped * 3.0  # -3% per dropped theme


def _digital_leadership_bonus(promise_results: list, ratios: dict) -> float:
    """Bonus for sustained digital/tech investment with measurable results."""
    # TODO: Identify digital-themed claims with delivered status
    return 0.0
