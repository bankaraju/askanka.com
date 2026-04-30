"""Tests for the ASDE lifecycle gate.

The 234-cell theme lifecycle audit (2026-04-30) drove these test cases.
Specifically RELOMC (FAIL_RECENT-style bimodal), DEFIT (PASS, durable),
and synthetic edge cases for each verdict bucket.
"""
from __future__ import annotations

import pytest

from pipeline.research.auto_spread_discovery.lifecycle_gate import (
    YearStat, evaluate, MIN_N_PER_YEAR,
)


def test_durable_cell_passes():
    """DEFIT/NEUTRAL/5d shape: alive 2022-2026 continuously."""
    stats = [
        YearStat(2021, n=132, mean_bps=-50.6),
        YearStat(2022, n=150, mean_bps=+166.3),
        YearStat(2023, n=184, mean_bps=+107.6),
        YearStat(2024, n=174, mean_bps=+31.9),
        YearStat(2025, n=191, mean_bps=+30.7),
        YearStat(2026, n=51, mean_bps=+119.4),
    ]
    v = evaluate(stats)
    assert v.passed is True
    assert v.verdict == "LIFECYCLE_PASS"
    assert v.n_years_alive == 5
    assert v.last_alive_year == 2026


def test_bimodal_thin_data_cell_passes_at_floor():
    """RELOMC-style bimodal-but-thin cell sits at the depth floor (2 alive,
    floor=2). Passes the gate but barely. This is a deliberate design
    choice — EUPHORIA cells with structurally low n (regime fires rarely)
    cannot satisfy thicker depth gates, and the rest of the multi-gate
    bar (bootstrap + BH-FDR + holdout) carries more weight there.

    Documented in lifecycle_gate.py docstring as a known permissive case.
    """
    stats = [
        YearStat(2021, n=4, mean_bps=+168.2),    # n<5 → not alive
        YearStat(2022, n=11, mean_bps=+168.6),   # alive
        YearStat(2023, n=2, mean_bps=+5.4),      # n<5 → not alive
        YearStat(2024, n=10, mean_bps=+443.0),   # alive
        YearStat(2025, n=1, mean_bps=+721.3),    # n<5 → not alive
    ]
    v = evaluate(stats)
    # Depth floor: max(2, floor(5*0.5)=2) = 2; n_alive=2 → exactly at floor → PASS.
    # Recent: 2024 alive in last 2 → pass. Reversal: 721.3 > p25 → pass.
    assert v.passed is True
    assert v.verdict == "LIFECYCLE_PASS"
    assert v.n_years_alive == 2


def test_decayed_king_fails_recent():
    """OLD-ONLY pattern: alive 2021-2023, dead 2024+."""
    stats = [
        YearStat(2021, n=100, mean_bps=+80.0),
        YearStat(2022, n=120, mean_bps=+90.0),
        YearStat(2023, n=110, mean_bps=+50.0),
        YearStat(2024, n=130, mean_bps=-20.0),  # dead
        YearStat(2025, n=140, mean_bps=-10.0),  # dead
    ]
    v = evaluate(stats)
    assert v.passed is False
    assert v.verdict == "FAIL_RECENT"
    assert "no alive year in last 2" in v.reason


def test_recent_only_passes_when_depth_met():
    """RECENT-ONLY pattern: dead 2021-2023, alive 2024-2026.

    With 3 alive years out of 6, depth gate passes (need >= 3). Recent
    gate passes (alive in last 2). No-reversal passes (recent above p25).
    """
    stats = [
        YearStat(2021, n=100, mean_bps=-50.0),
        YearStat(2022, n=120, mean_bps=-30.0),
        YearStat(2023, n=110, mean_bps=-20.0),
        YearStat(2024, n=130, mean_bps=+40.0),
        YearStat(2025, n=140, mean_bps=+60.0),
        YearStat(2026, n=50, mean_bps=+80.0),
    ]
    v = evaluate(stats)
    assert v.passed is True, v.reason
    assert v.verdict == "LIFECYCLE_PASS"


def test_reversal_fails_no_reversal_gate():
    """Cell with positive mean overall but most-recent year is bottom-25%.

    5y mean = +50 across years; year 2025 is -200bp (well below p25).
    Even though n_alive >= 3 and recent is "in window" (the year, but
    not alive due to negative mean), let's construct: alive 4 of 5
    years, most recent year shows sign-flip.
    """
    stats = [
        YearStat(2021, n=100, mean_bps=+50.0),
        YearStat(2022, n=110, mean_bps=+60.0),
        YearStat(2023, n=120, mean_bps=+40.0),
        YearStat(2024, n=130, mean_bps=+70.0),
        YearStat(2025, n=140, mean_bps=-200.0),   # outlier negative; but we want LAST year in last-2-window to be alive too
    ]
    # With this shape, last 2 years = 2024 (alive) + 2025 (dead).
    # Recent gate: 2024 alive -> pass.
    # Depth: 4/5 alive -> pass.
    # No-reversal: 2025 mean -200 vs 25th-pct of [-200, 40, 50, 60, 70]
    #   25th-pct interpolated between sorted[1]=40 and sorted[0]=-200, at q=0.25:
    #   pos = (5-1)*0.25 = 1.0 -> exactly sorted[1] = 40. So p25 = 40.
    #   most_recent (-200) < 40 -> FAIL_REVERSAL.
    v = evaluate(stats)
    assert v.passed is False
    assert v.verdict == "FAIL_REVERSAL"
    assert "< 25th-pct" in v.reason


def test_low_n_year_treated_as_dead():
    """Year with n < MIN_N_PER_YEAR is not alive even if mean > 0."""
    stats = [
        YearStat(2024, n=4, mean_bps=+500.0),   # high mean but n<5 → not alive
        YearStat(2025, n=120, mean_bps=+50.0),  # alive
    ]
    v = evaluate(stats)
    # 2 years tested, alive in 1, required = max(2, floor(2*0.5)=1) = 2 -> fails depth
    assert v.passed is False
    assert v.verdict == "FAIL_DEPTH"
    assert v.n_years_alive == 1


def test_empty_stats_returns_fail_depth():
    v = evaluate([])
    assert v.passed is False
    assert v.verdict == "FAIL_DEPTH"
    assert v.n_years_tested == 0


def test_single_year_fails_depth_floor():
    """Single year cannot satisfy alive>=2 floor."""
    stats = [YearStat(2026, n=100, mean_bps=+100.0)]
    v = evaluate(stats)
    assert v.passed is False
    assert v.verdict == "FAIL_DEPTH"


def test_relomc_actual_data_documented_permissive_pass():
    """RELOMC's bimodal pattern PASSES the lifecycle gate at the floor.

    This is documented permissive behavior: EUPHORIA cells fire rarely so
    n-per-year is structurally small. Gate doesn't catch RELOMC; bootstrap
    + BH-FDR + holdout carry the weight there.
    """
    stats = [
        YearStat(2021, n=4, mean_bps=+168.2),
        YearStat(2022, n=11, mean_bps=+168.6),
        YearStat(2023, n=2, mean_bps=+5.4),
        YearStat(2024, n=10, mean_bps=+443.0),
        YearStat(2025, n=1, mean_bps=+721.3),
    ]
    v = evaluate(stats)
    assert v.passed is True
    assert v.verdict == "LIFECYCLE_PASS"
    assert v.n_years_alive == 2  # at floor


def test_defit_3d_actual_data_passes():
    """DEFIT/NEUTRAL/3d real data — should PASS clearly."""
    stats = [
        YearStat(2021, n=132, mean_bps=-48.7),
        YearStat(2022, n=150, mean_bps=+80.6),
        YearStat(2023, n=184, mean_bps=+49.9),
        YearStat(2024, n=174, mean_bps=+24.3),
        YearStat(2025, n=191, mean_bps=+22.9),
        YearStat(2026, n=53, mean_bps=+54.8),
    ]
    v = evaluate(stats)
    assert v.passed is True
    assert v.verdict == "LIFECYCLE_PASS"
    assert v.n_years_alive == 5  # all but 2021


def test_n_required_scales_with_history_length():
    """3-year history requires >= 2 alive (50% rounded down, but >=2 floor)."""
    stats = [
        YearStat(2024, n=100, mean_bps=+50.0),
        YearStat(2025, n=120, mean_bps=+30.0),
        YearStat(2026, n=80, mean_bps=+40.0),
    ]
    v = evaluate(stats)
    # Required = max(2, floor(3*0.5)=1) = 2; n_alive=3 -> passes
    assert v.passed is True


def test_min_n_per_year_constant_used():
    assert MIN_N_PER_YEAR == 5
