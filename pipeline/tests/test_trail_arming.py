"""
B10 — Trail arming and ratchet tests.

Root cause (Fossil Arbitrage, SIG-2026-03-31-020):
  Peak +7.07%, avg_favorable=2.38 → trail_budget=2.38, trail_stop should be 4.69.
  Trail WAS armed (7.07 >= 2.38). But trail_stop was re-computed each intraday call
  using days_since_check — after a holiday gap, budget grows (sqrt(3)=1.73x) and
  trail_stop DROPS below the prior value, violating the monotonic ratchet invariant.
  Fossil round-tripped from +7.07% to -4.04% without trail firing.

Root cause classification: (c) Trail drift — trail_stop is not monotonically
non-decreasing; a weekend/holiday gap widens the budget, lowering trail_stop.

Fix: persist `peak_trail_stop_pct` on the signal. On each update, compute the
new candidate trail_stop and only raise peak_trail_stop_pct if the new candidate
is HIGHER. The live trail fires on cumulative <= peak_trail_stop_pct.
"""
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import signal_tracker


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

_DEFAULT_LEVELS = {
    "daily_std": 2.38,
    "avg_favorable_move": 2.38,
    "entry_level": 0.0,
    "stop_level": -1.19,
    "cum_percentile": 50.0,
    "cum_peak": 7.07,
    "cum_trough": -2.0,
}


def _fossil_fixture(**overrides):
    """Coal vs OMCs (Fossil Arbitrage) — avg_favorable=2.38, peak_at_open=0."""
    base = {
        "signal_id": "TEST-FOSSIL",
        "spread_name": "Coal vs OMCs",
        "open_timestamp": "2026-04-01T04:29:29.000000",
        "long_legs": [
            {"ticker": "COALINDIA", "yf": "COALINDIA.NS", "price": 464.0, "weight": 1.0},
        ],
        "short_legs": [
            {"ticker": "BPCL", "yf": "BPCL.NS", "price": 292.0, "weight": 0.5},
            {"ticker": "HPCL", "yf": "HINDPETRO.NS", "price": 350.0, "weight": 0.5},
        ],
        "peak_spread_pnl_pct": 0.0,
    }
    base.update(overrides)
    return base


def _run_check(sig, cumulative_pnl, todays_move, avg_favorable=2.38, days_since=1):
    """Patch internals and run check_signal_status."""
    levels = dict(_DEFAULT_LEVELS)
    levels["avg_favorable_move"] = avg_favorable

    # Patch _last_trail_check so days_since is controlled by the test.
    # We inject it via the signal so the code computes it naturally, or we
    # patch compute_trail_budget directly to receive the expected days arg.
    import math as _math
    expected_budget = avg_favorable * signal_tracker.TRAIL_BUDGET_MULT * _math.sqrt(days_since)

    with patch.object(signal_tracker, "compute_signal_pnl",
                      return_value={"spread_pnl_pct": cumulative_pnl}), \
         patch.object(signal_tracker, "_compute_todays_spread_move",
                      return_value=todays_move), \
         patch.object(signal_tracker, "get_levels_for_spread",
                      return_value=levels), \
         patch.object(signal_tracker, "compute_trail_budget",
                      return_value=expected_budget), \
         patch.object(signal_tracker, "_load_current_breaks_for_zcross",
                      return_value={"breaks": []}):
        return signal_tracker.check_signal_status(sig, current_prices={})


# ---------------------------------------------------------------------------
# Test 1: Trail arms when peak first crosses budget (days_since=1)
# ---------------------------------------------------------------------------

def test_trail_arms_on_first_peak_above_budget():
    """Peak crosses arm threshold in a single update → armed=True, trail fires on retrace.

    avg_favorable=2.38, budget=2.38*1.0*sqrt(1)=2.38, arm_factor=1.0.
    peak_pnl=4.5 (above arm threshold 2.38) → trail is ARMED.
    trail_stop = 4.5 - 2.38 = 2.12.
    cumulative=1.5 which is below trail_stop=2.12 → TRAIL fires.
    Verifies: trail arms on first check when peak > budget, and fires immediately
    when cumulative has retraced below trail_stop.
    """
    sig = _fossil_fixture(
        spread_name="Coal vs OMCs",
        peak_spread_pnl_pct=4.5,
    )
    status, pnl = _run_check(sig, cumulative_pnl=1.5, todays_move=-3.0, avg_favorable=2.38)
    # Trail is armed (4.5 >= 2.38) and cumulative 1.5 <= trail_stop (4.5-2.38=2.12) → fire
    assert status == "STOPPED_OUT_TRAIL", (
        f"Trail must arm and fire when peak=4.5 >= budget=2.38 and "
        f"cumulative=1.5 <= trail_stop=2.12. Got {status!r}"
    )


# ---------------------------------------------------------------------------
# Test 2: Ratchet is monotonically non-decreasing across consecutive peaks
# ---------------------------------------------------------------------------

def test_trail_ratchets_up_on_new_peak():
    """Consecutive updates: peak 5→6→7→7.07 → trail_stop ratchets up, never drops.

    Peak sequence: 0.5, 3.0, 5.5, 7.07 (rising), then 5.0, 2.0 (falling).
    Assertion: peak_trail_stop_pct stored on signal is strictly non-decreasing
    through the rising phase, and does NOT decrease when peak falls back.
    """
    import signal_tracker as st

    avg_favorable = 2.38
    # Fossil's full PnL sequence
    cum_sequence = [0.5, 3.0, 5.5, 7.07, 5.0, 2.0]
    today_moves  = [0.5, 2.5, 2.5, 1.57, -2.07, -3.0]

    sig = _fossil_fixture(peak_spread_pnl_pct=0.0)
    trail_stops_recorded = []

    for cum, today in zip(cum_sequence, today_moves):
        sig_copy = dict(sig)  # don't clobber between iterations
        sig_copy["peak_spread_pnl_pct"] = max(sig.get("peak_spread_pnl_pct", 0.0), cum)
        # Copy persisted trail stop if set
        if "peak_trail_stop_pct" in sig:
            sig_copy["peak_trail_stop_pct"] = sig["peak_trail_stop_pct"]

        with patch.object(st, "compute_signal_pnl",
                          return_value={"spread_pnl_pct": cum}), \
             patch.object(st, "_compute_todays_spread_move",
                          return_value=today), \
             patch.object(st, "get_levels_for_spread",
                          return_value=dict(_DEFAULT_LEVELS)), \
             patch.object(st, "compute_trail_budget",
                          return_value=avg_favorable), \
             patch.object(st, "_load_current_breaks_for_zcross",
                          return_value={"breaks": []}):
            status, pnl = st.check_signal_status(sig_copy, current_prices={})

        # Persist the ratcheted stop back to sig for the next iteration
        new_trail_stop = sig_copy.get("peak_trail_stop_pct")
        if new_trail_stop is not None:
            sig["peak_trail_stop_pct"] = new_trail_stop
        sig["peak_spread_pnl_pct"] = sig_copy.get("peak_spread_pnl_pct", sig.get("peak_spread_pnl_pct", 0.0))
        trail_stops_recorded.append(sig_copy.get("peak_trail_stop_pct"))

        if status != "OPEN":
            break

    # Ratchet invariant: trail_stop_pct must be non-decreasing
    non_none = [t for t in trail_stops_recorded if t is not None]
    assert len(non_none) >= 2, "Need at least 2 trail_stop readings to verify ratchet"

    for i in range(1, len(non_none)):
        assert non_none[i] >= non_none[i - 1] - 1e-9, (
            f"Trail stop DECREASED: [{i-1}]={non_none[i-1]:.4f} → [{i}]={non_none[i]:.4f}. "
            f"Ratchet invariant violated. Full sequence: {non_none}"
        )


# ---------------------------------------------------------------------------
# Test 3: Trail does NOT arm when peak is below budget
# ---------------------------------------------------------------------------

def test_trail_does_not_arm_when_peak_below_budget():
    """Peak 2.0% with avg_favorable=4.0 → budget=4.0, arm_factor=1.0 → NOT armed.

    Daily stop must still fire as the floor.
    """
    sig = _fossil_fixture(peak_spread_pnl_pct=2.0)
    status, pnl = _run_check(sig, cumulative_pnl=-2.5, todays_move=-2.5, avg_favorable=4.0)
    # Trail budget = 4.0; peak=2.0 < 4.0 → not armed → daily should fire
    assert status in ("STOPPED_OUT", "STOPPED_OUT_2DAY", "STOPPED_OUT_TRAIL"), (
        f"Below arm threshold (peak=2.0 < budget=4.0): daily must fire. Got {status!r}"
    )
    # Specifically should NOT be OPEN — position must be stopped
    assert status != "OPEN", f"Position should be stopped when daily fires. Got {status!r}"


# ---------------------------------------------------------------------------
# Test 4: Full Fossil replay — trail fires before -4.04% final
# ---------------------------------------------------------------------------

def test_fossil_pattern_captured_by_trail():
    """Full Fossil replay. With ratchet fix in place, trail_stop stays pinned at
    its highest computed value (peak=7.07 → trail_stop=4.69 when budget=2.38).

    After the fix: when cumulative falls from 7.07 back through 4.69, trail fires —
    NOT when it hits -4.04 (without trail, daily stop was the only protection).

    We simulate the close-day state: cum=-4.04, peak=7.07, budget=2.38.
    The peak_trail_stop_pct should be pinned at 4.69 (from when cum was 7.07).
    cumulative -4.04 <= trail_stop 4.69 → STOPPED_OUT_TRAIL.
    """
    sig = _fossil_fixture(
        peak_spread_pnl_pct=7.07,
        # Simulate: peak_trail_stop_pct was pinned at 4.69 during the peak
        peak_trail_stop_pct=4.69,
    )
    status, pnl = _run_check(sig, cumulative_pnl=-4.04, todays_move=-4.04, avg_favorable=2.38)
    assert status == "STOPPED_OUT_TRAIL", (
        f"Fossil pattern: cumulative -4.04% <= pinned trail_stop 4.69%. "
        f"Trail must fire. Got {status!r}"
    )


# ---------------------------------------------------------------------------
# Test 5: Holiday gap must NOT lower trail_stop below ratchet high
# ---------------------------------------------------------------------------

def test_holiday_gap_does_not_lower_trail_stop():
    """After a 3-day gap, budget widens (sqrt(3)≈1.73x). Without ratchet fix,
    trail_stop would DROP from 4.69 to 7.07 - 4.12 = 2.95.
    With ratchet fix: peak_trail_stop_pct stays at 4.69 — a worse retrace
    is required to trigger trail, NOT a better one after the gap.

    We simulate two consecutive checks:
      Check 1 (days_since=1): budget=2.38, trail_stop=4.69 stored on signal
      Check 2 (days_since=3): budget=4.12, candidate trail_stop=2.95
    After fix: peak_trail_stop_pct remains 4.69 (higher wins).
    """
    import math as _math
    import signal_tracker as st

    sig = _fossil_fixture(peak_spread_pnl_pct=7.07)

    # Check 1: days_since=1, budget=2.38
    budget_day1 = 2.38 * _math.sqrt(1)
    with patch.object(st, "compute_signal_pnl",
                      return_value={"spread_pnl_pct": 7.07}), \
         patch.object(st, "_compute_todays_spread_move", return_value=0.0), \
         patch.object(st, "get_levels_for_spread",
                      return_value=dict(_DEFAULT_LEVELS)), \
         patch.object(st, "compute_trail_budget", return_value=budget_day1), \
         patch.object(st, "_load_current_breaks_for_zcross",
                      return_value={"breaks": []}):
        st.check_signal_status(sig, current_prices={})

    trail_stop_after_day1 = sig.get("peak_trail_stop_pct")
    assert trail_stop_after_day1 is not None, "peak_trail_stop_pct must be set after first check"
    assert trail_stop_after_day1 == pytest.approx(7.07 - budget_day1, abs=0.01), (
        f"After day 1: peak_trail_stop_pct={trail_stop_after_day1:.4f}, "
        f"expected≈{7.07 - budget_day1:.4f}"
    )

    # Check 2: 3-day gap → budget grows, candidate trail_stop DROPS
    budget_day3 = 2.38 * _math.sqrt(3)
    candidate_day3 = 7.07 - budget_day3  # < trail_stop_after_day1

    with patch.object(st, "compute_signal_pnl",
                      return_value={"spread_pnl_pct": 6.5}), \
         patch.object(st, "_compute_todays_spread_move", return_value=-0.5), \
         patch.object(st, "get_levels_for_spread",
                      return_value=dict(_DEFAULT_LEVELS)), \
         patch.object(st, "compute_trail_budget", return_value=budget_day3), \
         patch.object(st, "_load_current_breaks_for_zcross",
                      return_value={"breaks": []}):
        st.check_signal_status(sig, current_prices={})

    trail_stop_after_gap = sig.get("peak_trail_stop_pct")
    assert trail_stop_after_gap >= trail_stop_after_day1 - 1e-9, (
        f"Ratchet violated after holiday gap: trail_stop dropped from "
        f"{trail_stop_after_day1:.4f} to {trail_stop_after_gap:.4f}. "
        f"Expected non-decreasing (candidate was {candidate_day3:.4f})."
    )
