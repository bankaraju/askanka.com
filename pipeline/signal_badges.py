"""
Shared badge renderer module for signal rendering.

Single source of truth for rendering trust/break/rank/conviction labels.
Both website (index.html JS) and Telegram (telegram_bot.py) import from here.

Each function returns {"emoji": str, "label": str, "tone": str}
where tone is "strong"/"ok"/"weak"/"none".
"""

from typing import Dict, Optional


def trust_badge(grade: Optional[str]) -> Dict[str, str]:
    """
    Render a trust/grade badge.

    Args:
        grade: Grade string (A+, A, B+, B, C, C+, D, F) or None

    Returns:
        Dict with emoji, label, and tone
    """
    if grade is None:
        return {"emoji": "⚪", "label": "—", "tone": "none"}

    if grade in ("A+", "A"):
        return {"emoji": "🟢", "label": grade, "tone": "strong"}
    elif grade in ("B+", "B"):
        return {"emoji": "🟡", "label": grade, "tone": "ok"}
    else:  # C, C+, D, F
        return {"emoji": "🔴", "label": grade, "tone": "weak"}


def break_badge(classification: Optional[str]) -> Dict[str, str]:
    """
    Render a break/correlation badge.

    Args:
        classification: Classification string or None

    Returns:
        Dict with emoji, label, and tone
    """
    if classification is None:
        return {"emoji": "⚪", "label": "—", "tone": "none"}

    if classification == "MOMENTUM_CONFIRM":
        return {"emoji": "🟢", "label": "CONFIRM", "tone": "strong"}
    elif classification == "POSSIBLE_OPPORTUNITY":
        return {"emoji": "🟡", "label": "OPPO", "tone": "ok"}
    elif classification == "DIVERGENCE_WARNING":
        return {"emoji": "🔴", "label": "DIVERGE", "tone": "weak"}
    else:
        # Unknown type: show first 7 chars
        label = classification[:7]
        return {"emoji": "⚪", "label": label, "tone": "none"}


def rank_badge(hit_rate: Optional[float]) -> Dict[str, str]:
    """
    Render a rank/hit-rate badge.

    Args:
        hit_rate: Hit rate as decimal (0.0-1.0) or None

    Returns:
        Dict with emoji, label (pct%), and tone
    """
    if hit_rate is None:
        return {"emoji": "⚪", "label": "—", "tone": "none"}

    pct = int(round(hit_rate * 100))

    if hit_rate >= 0.60:
        return {"emoji": "🟢", "label": f"{pct}%", "tone": "strong"}
    elif hit_rate >= 0.50:
        return {"emoji": "🟡", "label": f"{pct}%", "tone": "ok"}
    else:
        return {"emoji": "🔴", "label": f"{pct}%", "tone": "weak"}


def conviction_badge(score: Optional[float]) -> Dict[str, str]:
    """
    Render a conviction/confidence badge.

    Args:
        score: Score (0-100) or None

    Returns:
        Dict with emoji, label (rounded score), and tone
    """
    if score is None:
        return {"emoji": "⚪", "label": "—", "tone": "none"}

    rounded = int(round(score))

    if score >= 65:
        return {"emoji": "🟢", "label": str(rounded), "tone": "strong"}
    elif score >= 40:
        return {"emoji": "🟡", "label": str(rounded), "tone": "ok"}
    else:
        return {"emoji": "🔴", "label": str(rounded), "tone": "weak"}
