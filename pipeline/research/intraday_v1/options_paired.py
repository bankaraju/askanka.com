"""ATM-strike resolver + paired-leg builder for the V1 forensic options sidecar.

Per spec §12 + memory `feedback_paired_shadow_pattern.md`:
- Every futures-side direction call writes a paired ATM options leg to a
  separate forensic ledger (no edge claim, no kill-switch).
- Long futures → long ATM call (CE).
- Short futures → long ATM put (PE).
"""
from __future__ import annotations

from typing import Dict, List


def resolve_atm_strike(spot: float, available_strikes: List[int]) -> int:
    """Pick the strike closest to spot. Tie → higher strike."""
    if not available_strikes:
        raise ValueError("available_strikes is empty")
    available_strikes = sorted(available_strikes)
    best = available_strikes[0]
    best_diff = abs(spot - best)
    for s in available_strikes[1:]:
        d = abs(spot - s)
        if d < best_diff or (d == best_diff and s > best):
            best = s
            best_diff = d
    return best


def build_paired_leg(
    underlying: str,
    direction: str,
    spot_at_entry: float,
    atm_strike: int,
    entry_premium: float,
    exit_premium: float,
) -> Dict:
    """Construct a paired-options leg row for the forensic sidecar.

    direction = 'LONG' → long ATM Call; 'SHORT' → long ATM Put.
    """
    if direction not in ("LONG", "SHORT"):
        raise ValueError(f"direction must be LONG or SHORT, got {direction}")
    if entry_premium <= 0:
        raise ValueError("entry_premium must be positive")
    instrument_type = "CE" if direction == "LONG" else "PE"
    pnl_pct = (exit_premium - entry_premium) / entry_premium * 100.0
    return {
        "underlying": underlying,
        "instrument_type": instrument_type,
        "atm_strike": atm_strike,
        "spot_at_entry": spot_at_entry,
        "entry_premium": entry_premium,
        "exit_premium": exit_premium,
        "pnl_pct": pnl_pct,
        "direction": direction,
    }
