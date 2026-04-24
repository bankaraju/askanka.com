"""7-state lifecycle + displacement + rate limit."""
from __future__ import annotations

VALID_STATES = {
    "PROPOSED", "PRE_REGISTERED", "HOLDOUT_PASS",
    "FORWARD_SHADOW", "PROMOTED_LIVE", "RETIRED", "DEAD",
}

FORWARD_PATH = {
    "PROPOSED": "PRE_REGISTERED",
    "PRE_REGISTERED": "HOLDOUT_PASS",
    "HOLDOUT_PASS": "FORWARD_SHADOW",
    "FORWARD_SHADOW": "PROMOTED_LIVE",
}


def advance_state(current: str) -> str:
    if current not in FORWARD_PATH:
        raise ValueError(f"cannot advance from terminal state: {current}")
    return FORWARD_PATH[current]


def displace_lowest_sharpe(slots: list[dict], new_strategy_id: str,
                            new_sharpe: float) -> tuple[list[dict], dict]:
    """Returns (new slot list, retired slot). Caller commits both sides."""
    if not slots:
        return [{"strategy_id": new_strategy_id, "sharpe": new_sharpe}], {}
    lowest = min(slots, key=lambda s: s["sharpe"])
    kept = [s for s in slots if s["strategy_id"] != lowest["strategy_id"]]
    kept.append({"strategy_id": new_strategy_id, "sharpe": new_sharpe})
    return kept, lowest


def rate_limit_passes(promotions_this_quarter: int, cap: int) -> bool:
    return promotions_this_quarter < cap
