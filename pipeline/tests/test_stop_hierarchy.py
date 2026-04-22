"""
B9 — Stop hierarchy tests: trail dominates daily once armed.

Design spec (user-approved):
  Peak <= |daily_stop|          → daily_stop is the floor (pre-profit phase)
  Peak > |daily_stop| AND trail → trail dominates; daily becomes INERT

Once trail arms, a single bad day should NOT close a deeply-profitable position.
The question becomes "did we give back too much of the peak?" not "bad day today?".
"""
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import signal_tracker


_DEFAULT_LEVELS = {
    "daily_std": 2.11,
    "avg_favorable_move": 1.96,
    "entry_level": 0.0,
    "stop_level": -0.98,
    "cum_percentile": 50.0,
    "cum_peak": 11.11,
    "cum_trough": -2.0,
}


def _sovereign_fixture(**overrides):
    """Sovereign Shield Alpha replica — peak 11.11%, current 8.66%, daily stop -0.98%.

    At this state:
      trail_budget = avg_favorable * 1.0 * sqrt(1) = 1.96
      trail_arm:   peak 11.11 >= budget 1.96 → ARMED
      trail_stop:  11.11 - 1.96 = 9.15
      daily_stop:  -0.98
      today's move: -1.10 (crosses daily_stop)
      cumulative:   8.66 (still above trail_stop 9.15? No — 8.66 < 9.15)

    Under OLD logic: daily fires on today=-1.10 → STOPPED_OUT (bad!)
    Under NEW logic: trail is armed & cumulative 8.66 <= trail_stop 9.15 → STOPPED_OUT_TRAIL
    Either way, the position closes — but via the TRAIL mechanism, not daily stop.
    The key test is that daily is INERT once trail arms.
    """
    base = {
        "signal_id": "TEST-SOVEREIGN",
        "spread_name": "Defence vs IT",
        "open_timestamp": "2026-04-09T04:29:29.000000",
        "long_legs": [
            {"ticker": "HAL", "yf": "HAL.NS", "price": 3581.4, "weight": 0.333},
            {"ticker": "BEL", "yf": "BEL.NS", "price": 415.0, "weight": 0.333},
            {"ticker": "BDL", "yf": "BDL.NS", "price": 1132.2, "weight": 0.333},
        ],
        "short_legs": [
            {"ticker": "TCS", "yf": "TCS.NS", "price": 2429.0, "weight": 0.333},
            {"ticker": "INFY", "yf": "INFY.NS", "price": 1290.0, "weight": 0.333},
            {"ticker": "WIPRO", "yf": "WIPRO.NS", "price": 191.5, "weight": 0.333},
        ],
        "peak_spread_pnl_pct": 11.11,
    }
    base.update(overrides)
    return base


def _run_check(sig, cumulative_pnl, todays_move, avg_favorable=1.96):
    """Helper: patch internals and run check_signal_status."""
    levels = dict(_DEFAULT_LEVELS)
    levels["avg_favorable_move"] = avg_favorable

    with patch.object(signal_tracker, "compute_signal_pnl",
                      return_value={"spread_pnl_pct": cumulative_pnl}), \
         patch.object(signal_tracker, "_compute_todays_spread_move",
                      return_value=todays_move), \
         patch.object(signal_tracker, "get_levels_for_spread",
                      return_value=levels), \
         patch.object(signal_tracker, "_load_current_breaks_for_zcross",
                      return_value={"breaks": []}):
        return signal_tracker.check_signal_status(sig, current_prices={})


# ---------------------------------------------------------------------------
# Test 1: Trail armed — daily must NOT be the exit mechanism
# ---------------------------------------------------------------------------

def test_trail_armed_daily_stop_is_inert_when_cumulative_above_trail():
    """Trail armed + cumulative still above trail_stop → OPEN despite bad single day.

    Scenario: position peaked at 11.11%, trail_budget=1.96, trail_stop=9.15.
    Today's move: -1.10% (crosses daily_stop of -0.98).
    But cumulative is 10.0% which is above trail_stop 9.15 → position stays OPEN.
    """
    sig = _sovereign_fixture(peak_spread_pnl_pct=11.11)
    # cumulative 10.0 > trail_stop (11.11 - 1.96 = 9.15) → no trail fire
    # today=-1.10 crosses daily_stop=-0.98 → daily would fire under OLD logic
    status, pnl = _run_check(sig, cumulative_pnl=10.0, todays_move=-1.10)
    assert status == "OPEN", (
        f"Daily stop must be INERT once trail is armed. "
        f"Got status={status!r} with cumulative=10.0% > trail_stop=9.15%"
    )


# ---------------------------------------------------------------------------
# Test 2: Trail armed and cumulative falls below trail_stop → TRAIL fires
# ---------------------------------------------------------------------------

def test_trail_fires_when_cumulative_below_trail_stop():
    """Trail armed + cumulative dips below trail_stop → STOPPED_OUT_TRAIL.

    Peak=11.11, budget=1.96, trail_stop=9.15.
    Cumulative drops to 8.66 (below 9.15) → trail fires.
    The exit reason must be trail, not daily.
    """
    sig = _sovereign_fixture(peak_spread_pnl_pct=11.11)
    status, pnl = _run_check(sig, cumulative_pnl=8.66, todays_move=-1.10)
    assert status == "STOPPED_OUT_TRAIL", (
        f"Trail stop must dominate once armed. Got {status!r}. "
        f"cumulative=8.66 < trail_stop=9.15 → should be TRAIL exit."
    )


# ---------------------------------------------------------------------------
# Test 3: Pre-profit — daily stop must still fire as floor
# ---------------------------------------------------------------------------

def test_daily_stop_fires_before_trail_arms():
    """Pre-profit phase: peak has never exceeded |daily_stop|.
    Daily stop must be active as the floor for new entries.

    peak=0.5, daily_stop_mag=0.98 → trail NOT armed (0.5 < 0.98).
    today's move=-1.50 → crosses daily_stop → STOPPED_OUT (daily).
    """
    sig = _sovereign_fixture(peak_spread_pnl_pct=0.5)
    status, pnl = _run_check(sig, cumulative_pnl=-1.5, todays_move=-1.5)
    assert status in ("STOPPED_OUT", "STOPPED_OUT_DAILY"), (
        f"Daily stop must fire as floor when trail not armed. Got {status!r}"
    )


# ---------------------------------------------------------------------------
# Test 4: Trail armed, cumulative well above trail, bad single day → OPEN
# ---------------------------------------------------------------------------

def test_trail_armed_but_above_trail_even_with_2pct_daily_drop():
    """Trail armed + cumulative still comfortably above trail_stop.
    A 2.5% single-day drop should NOT close the position.

    peak=11.11, budget=1.96, trail_stop=9.15.
    cumulative=9.5 > trail_stop=9.15 → position stays OPEN.
    """
    sig = _sovereign_fixture(peak_spread_pnl_pct=11.11)
    status, pnl = _run_check(sig, cumulative_pnl=9.5, todays_move=-2.5)
    assert status == "OPEN", (
        f"Position with cumulative 9.5% above trail_stop 9.15% must stay OPEN. Got {status!r}"
    )


# ---------------------------------------------------------------------------
# Test 5: Exact arm boundary — peak == |daily_stop| (not yet armed)
# ---------------------------------------------------------------------------

def test_at_arm_boundary_trail_not_yet_armed():
    """Edge case: peak equals exactly the trail arm threshold → trail NOT armed (strict >=).

    The trail arm condition: peak >= trail_budget (where trail_budget = avg_favorable * 1.0 * sqrt(1)).
    With avg_favorable=1.96: trail_budget = 1.96.
    Peak=1.95 → 1.95 < 1.96 → trail NOT armed.
    today=-1.50 → crosses daily_stop=-0.98 → daily fires.
    """
    sig = _sovereign_fixture(peak_spread_pnl_pct=1.95)
    status, pnl = _run_check(sig, cumulative_pnl=-1.5, todays_move=-1.5, avg_favorable=1.96)
    assert status in ("STOPPED_OUT", "STOPPED_OUT_DAILY"), (
        f"Below arm threshold (peak=1.95 < trail_budget=1.96), daily must still fire. Got {status!r}"
    )


# ---------------------------------------------------------------------------
# Test 6: Trail just armed (peak = |daily_stop| + epsilon) → daily inert
# ---------------------------------------------------------------------------

def test_just_past_arm_threshold_daily_becomes_inert():
    """One basis point past the trail arm threshold → daily becomes inert.

    The trail arm condition: peak >= trail_budget * arm_factor.
    trail_budget = avg_favorable * TRAIL_BUDGET_MULT * sqrt(days_since=1).
    With avg_favorable=1.96 and defaults (mult=1.0, af=1.0):
      trail_budget = 1.96, arm_threshold = 1.96.
    Peak=2.0 → 2.0 >= 1.96 → trail ARMED.
    cumulative=1.5 (above trail_stop: 2.0 - 1.96 = 0.04) → OPEN.
    today=-2.0 → would fire daily_stop=-0.98, but daily is now INERT.
    """
    sig = _sovereign_fixture(peak_spread_pnl_pct=2.0)
    status, pnl = _run_check(sig, cumulative_pnl=1.5, todays_move=-2.0, avg_favorable=1.96)
    assert status == "OPEN", (
        f"Just past trail arm threshold (peak=2.0 >= trail_budget=1.96): "
        f"daily must be inert, cumulative 1.5 > trail_stop 0.04. Got {status!r}"
    )
