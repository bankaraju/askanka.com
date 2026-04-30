"""ATR(14)-scaled per-leg sizing for Defence momentum baskets.

Pure function — given per-ticker ATR-percent and an optional per-leg
cap, returns dollar-neutral weights normalized so |sum_long| = 1 and
|sum_short| = 1 (then sign-flipped for SHORTs by the caller).

Design rationale (spec §honest expectation):
  Equal-notional sizing exposed the in-sample basket to per-leg
  vol asymmetry — defence stocks have 2-3x daily vol of IT names, so
  a -3% basket stop fired from defence-leg moves alone. ATR-scaling
  inverse-weights by vol so each leg contributes equal expected risk;
  the AUTO-RISKON variant additionally caps any single leg at 2x the
  baseline so a defence-leg single-day blowup can't dominate.
"""
from __future__ import annotations

from typing import Mapping, Optional


def atr_scaled_weights(
    legs: list[str],
    atr_pcts: Mapping[str, float],
    cap_x_baseline: Optional[float] = None,
) -> dict[str, float]:
    """Return per-leg weights that:
      - inverse-weight by ATR-percent (so high-vol legs get smaller notional)
      - sum to 1.0 across the side
      - if `cap_x_baseline` is set, cap each weight at cap_x_baseline / n_legs
        and redistribute excess proportionally to the remaining headroom.

    Falls back to equal-weight (1/n each) if any leg has missing or
    non-positive ATR-percent.

    Args:
      legs: list of tickers on this side (e.g. ["HAL","BEL","BDL"])
      atr_pcts: per-ticker ATR(14) / Close (as a fraction, e.g. 0.025 for 2.5%)
      cap_x_baseline: e.g. 2.0 means "cap any weight at 2x the equal-weight baseline"

    Returns:
      {ticker: weight} with weights >= 0 summing to 1.0.
    """
    n = len(legs)
    if n == 0:
        return {}
    if any(t not in atr_pcts or not atr_pcts[t] or atr_pcts[t] <= 0 for t in legs):
        # graceful fallback: equal weight
        return {t: 1.0 / n for t in legs}

    inv = {t: 1.0 / float(atr_pcts[t]) for t in legs}
    s = sum(inv.values())
    if s <= 0:
        return {t: 1.0 / n for t in legs}
    w = {t: inv[t] / s for t in legs}

    if cap_x_baseline is None:
        return w

    baseline = 1.0 / n
    cap = cap_x_baseline * baseline
    if cap >= 1.0:
        # cap is non-binding (would allow >100% on a single leg)
        return w

    # Iteratively cap and redistribute. Convergence is fast (<= n iterations).
    capped: set[str] = set()
    for _ in range(n + 2):
        over = {t: w[t] - cap for t in legs if w[t] > cap + 1e-12 and t not in capped}
        if not over:
            break
        excess = sum(over.values())
        for t in over:
            w[t] = cap
            capped.add(t)
        free = [t for t in legs if t not in capped]
        if not free:
            # all legs at cap — re-normalize
            tot = sum(w.values())
            if tot > 0:
                w = {t: v / tot for t, v in w.items()}
            return w
        free_total = sum(w[t] for t in free)
        if free_total <= 0:
            break
        for t in free:
            w[t] += excess * (w[t] / free_total)
    return w
