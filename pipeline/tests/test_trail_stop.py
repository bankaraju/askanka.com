"""Tests for trail_stop budget and breach logic in signal_tracker."""
import math
import sys
from pathlib import Path
import pytest

# Ensure pipeline/ is on the path so imports work
sys.path.insert(0, str(Path(__file__).parent.parent))

from signal_tracker import compute_trail_budget, trail_stop_triggered


class TestComputeTrailBudget:
    def test_single_day_returns_half_favorable(self):
        # 1 day gap: budget = favorable * 0.5 * sqrt(1) = favorable * 0.5
        assert compute_trail_budget(avg_favorable=2.38, days_since_check=1) == pytest.approx(1.19)

    def test_three_day_gap_widens_budget(self):
        # 3 day gap: budget = 2.38 * 0.5 * sqrt(3) ~= 2.06
        result = compute_trail_budget(avg_favorable=2.38, days_since_check=3)
        assert result == pytest.approx(2.38 * 0.5 * math.sqrt(3), rel=1e-6)

    def test_zero_days_clamped_to_one(self):
        # Edge: same-day re-check shouldn't produce 0 budget
        assert compute_trail_budget(avg_favorable=2.0, days_since_check=0) == pytest.approx(1.0)

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
