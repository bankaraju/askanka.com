"""Tests for trail_stop budget and breach logic in signal_tracker."""
import math
import sys
from pathlib import Path
import pytest

# Ensure pipeline/ is on the path so imports work
sys.path.insert(0, str(Path(__file__).parent.parent))

from signal_tracker import compute_trail_budget, trail_stop_triggered


class TestComputeTrailBudget:
    def test_live_default_uses_module_mult(self):
        # Live default: TRAIL_BUDGET_MULT = 1.0 -> budget = favorable * 1.0 * sqrt(1) = 2.38
        assert compute_trail_budget(avg_favorable=2.38, days_since_check=1) == pytest.approx(2.38)

    def test_override_mult_scales_budget(self):
        # Explicit override: budget_mult=0.5 -> budget = 2.38 * 0.5 = 1.19
        assert compute_trail_budget(avg_favorable=2.38, days_since_check=1, budget_mult=0.5) == pytest.approx(1.19)

    def test_three_day_gap_widens_budget(self):
        # 3 day gap with explicit mult=0.5: budget = 2.38 * 0.5 * sqrt(3) ~= 2.06
        result = compute_trail_budget(avg_favorable=2.38, days_since_check=3, budget_mult=0.5)
        assert result == pytest.approx(2.38 * 0.5 * math.sqrt(3), rel=1e-6)

    def test_zero_days_clamped_to_one(self):
        # Edge: same-day re-check shouldn't produce 0 budget (mult=0.5 override)
        assert compute_trail_budget(avg_favorable=2.0, days_since_check=0, budget_mult=0.5) == pytest.approx(1.0)

    def test_zero_favorable_returns_zero(self):
        # Defensive: if no historical favorable data, no budget
        assert compute_trail_budget(avg_favorable=0.0, days_since_check=1) == 0.0


class TestTrailStopTriggered:
    def test_fires_when_cum_below_peak_minus_budget(self):
        # Peak +7%, budget 1.19%, cum +5.5% -> trail_stop = +5.81, cum < stop -> FIRE
        assert trail_stop_triggered(cumulative=5.5, peak=7.0, trail_budget=1.19) is True

    def test_no_fire_when_cum_above_trail(self):
        # Peak +7%, budget 1.19%, cum +6.5% -> trail_stop = +5.81, cum > stop -> HOLD
        assert trail_stop_triggered(cumulative=6.5, peak=7.0, trail_budget=1.19) is False

    def test_guard_no_fire_before_peak_exceeds_budget(self):
        # Peak +0.5% < budget 1.19% -> guard prevents fire, daily_stop handles it
        assert trail_stop_triggered(cumulative=-2.0, peak=0.5, trail_budget=1.19) is False

    def test_fires_exactly_at_trail_boundary(self):
        # Peak +3%, budget 1%, cum +2% -> trail_stop = +2, cum <= stop -> FIRE
        assert trail_stop_triggered(cumulative=2.0, peak=3.0, trail_budget=1.0) is True

    def test_zero_budget_never_fires(self):
        # Defensive: zero budget = no historical data, don't fire
        assert trail_stop_triggered(cumulative=-50.0, peak=10.0, trail_budget=0.0) is False


from signal_tracker import check_signal_status


def _signal_with_prices(entry_long, entry_short, peak_pnl, prev_long=None, prev_short=None):
    """Build a minimal signal dict for check_signal_status."""
    sig = {
        "signal_id": "TEST-1",
        "spread_name": "Defence vs IT",  # must exist in spread_stats.json
        "long_legs":  [{"ticker": "HAL",  "price": entry_long}],
        "short_legs": [{"ticker": "TCS",  "price": entry_short}],
        "peak_spread_pnl_pct": peak_pnl,
    }
    if prev_long:
        sig["_prev_close_long"] = {"HAL": prev_long}
    if prev_short:
        sig["_prev_close_short"] = {"TCS": prev_short}
    return sig


class TestTrailStopIntegration:
    def test_trail_stop_fires_when_giving_back_from_peak(self, monkeypatch):
        # Force known historical levels + enable the feature flag for this test
        monkeypatch.setattr("signal_tracker.TRAIL_STOP_ENABLED", True)
        monkeypatch.setattr(
            "signal_tracker.get_levels_for_spread",
            lambda name: {"daily_std": 2.0, "avg_favorable_move": 2.38},
        )
        # Peak at +7%, now at +5% (gave back 2%). Budget = 1.19%.
        # Trail stop = 7 - 1.19 = 5.81. Cum 5.0 < 5.81 -> FIRE.
        sig = _signal_with_prices(
            entry_long=100.0, entry_short=100.0,
            peak_pnl=7.0,
            prev_long=104.0, prev_short=101.0,
        )
        prices = {"HAL": 103.0, "TCS": 102.0}
        status, _ = check_signal_status(sig, prices)
        assert status == "STOPPED_OUT_TRAIL"

    def test_trail_stop_suppressed_when_flag_disabled(self, monkeypatch):
        # Same setup as the firing test, but flag OFF -> trail must not fire.
        # Confirms the live gate protects us from untuned parameters.
        monkeypatch.setattr("signal_tracker.TRAIL_STOP_ENABLED", False)
        monkeypatch.setattr(
            "signal_tracker.get_levels_for_spread",
            lambda name: {"daily_std": 2.0, "avg_favorable_move": 2.38},
        )
        sig = _signal_with_prices(
            entry_long=100.0, entry_short=100.0,
            peak_pnl=7.0,
            prev_long=104.0, prev_short=101.0,
        )
        prices = {"HAL": 103.0, "TCS": 102.0}
        status, _ = check_signal_status(sig, prices)
        assert status != "STOPPED_OUT_TRAIL"

    def test_trail_stop_holds_near_peak(self, monkeypatch):
        monkeypatch.setattr("signal_tracker.TRAIL_STOP_ENABLED", True)
        # Cum at +6.5%, peak +7%, budget 1.19 -> trail = 5.81 -> HOLD
        monkeypatch.setattr(
            "signal_tracker.get_levels_for_spread",
            lambda name: {"daily_std": 2.0, "avg_favorable_move": 2.38},
        )
        sig = _signal_with_prices(
            entry_long=100.0, entry_short=100.0,
            peak_pnl=7.0,
            prev_long=106.0, prev_short=99.5,
        )
        prices = {"HAL": 106.5, "TCS": 100.0}
        status, _ = check_signal_status(sig, prices)
        assert status == "OPEN"
