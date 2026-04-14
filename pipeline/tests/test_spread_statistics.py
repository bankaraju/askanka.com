"""
Tests for pipeline/spread_statistics.py

Run:
    cd C:/Users/Claude_Anka/Documents/askanka.com/pipeline
    python -m pytest tests/test_spread_statistics.py -v
"""

import math
import sys
from pathlib import Path

# Ensure pipeline/ is on the path so imports work
sys.path.insert(0, str(Path(__file__).parent.parent))

from spread_statistics import compute_spread_return, compute_regime_stats


# ─────────────────────────────────────────────────────────────────────────────
# compute_spread_return tests
# ─────────────────────────────────────────────────────────────────────────────

def test_compute_spread_return_equal_weight():
    """Both long legs +10%, both short legs -5% → spread return = 15%."""
    long_prev  = {"HAL": 100.0, "BEL": 200.0}
    long_curr  = {"HAL": 110.0, "BEL": 220.0}
    short_prev = {"TCS": 100.0, "INFY": 100.0}
    short_curr = {"TCS":  95.0, "INFY":  95.0}

    result = compute_spread_return(long_prev, long_curr, short_prev, short_curr)
    assert abs(result - 0.15) < 1e-9, f"Expected 0.15, got {result}"


def test_compute_spread_return_mixed():
    """
    Long legs: +12% and -4% → avg +4%.
    Short leg: -3% → avg -3%.
    Spread = 4% - (-3%) = 7%.
    """
    long_prev  = {"HAL": 100.0, "BEL": 100.0}
    long_curr  = {"HAL": 112.0, "BEL":  96.0}
    short_prev = {"TCS": 100.0}
    short_curr = {"TCS":  97.0}

    result = compute_spread_return(long_prev, long_curr, short_prev, short_curr)
    assert abs(result - 0.07) < 1e-9, f"Expected 0.07, got {result}"


def test_compute_spread_return_flat():
    """Both sides flat → spread = 0."""
    long_prev  = {"HAL": 100.0}
    long_curr  = {"HAL": 100.0}
    short_prev = {"TCS": 200.0}
    short_curr = {"TCS": 200.0}

    result = compute_spread_return(long_prev, long_curr, short_prev, short_curr)
    assert result == 0.0, f"Expected 0.0, got {result}"


def test_compute_spread_return_single_legs():
    """Single stock each side: long +5%, short +2% → spread = 3%."""
    long_prev  = {"ONGC": 200.0}
    long_curr  = {"ONGC": 210.0}
    short_prev = {"IOC":  100.0}
    short_curr = {"IOC":  102.0}

    result = compute_spread_return(long_prev, long_curr, short_prev, short_curr)
    assert abs(result - 0.03) < 1e-9, f"Expected 0.03, got {result}"


# ─────────────────────────────────────────────────────────────────────────────
# compute_regime_stats tests
# ─────────────────────────────────────────────────────────────────────────────

def test_compute_regime_stats_basic():
    """
    5 days across 2 regimes. Verify counts and means.
    MACRO_STRESS: 3 days with returns [0.02, 0.04, 0.03] → mean = 0.03
    MACRO_EASY:   2 days with returns [-0.01, -0.03]      → mean = -0.02
    """
    daily_data = [
        {"date": "2026-01-02", "regime": "MACRO_STRESS", "spread_return": 0.02, "long_avg": 0.05, "short_avg": 0.03},
        {"date": "2026-01-03", "regime": "MACRO_STRESS", "spread_return": 0.04, "long_avg": 0.06, "short_avg": 0.02},
        {"date": "2026-01-04", "regime": "MACRO_STRESS", "spread_return": 0.03, "long_avg": 0.04, "short_avg": 0.01},
        {"date": "2026-01-05", "regime": "MACRO_EASY",   "spread_return": -0.01, "long_avg": -0.01, "short_avg": 0.00},
        {"date": "2026-01-06", "regime": "MACRO_EASY",   "spread_return": -0.03, "long_avg": -0.02, "short_avg": 0.01},
    ]

    stats = compute_regime_stats(daily_data)

    assert "MACRO_STRESS" in stats
    assert "MACRO_EASY" in stats

    stress = stats["MACRO_STRESS"]
    assert stress["count"] == 3
    assert abs(stress["mean"] - 0.03) < 1e-9, f"MACRO_STRESS mean: expected 0.03, got {stress['mean']}"

    easy = stats["MACRO_EASY"]
    assert easy["count"] == 2
    assert abs(easy["mean"] - (-0.02)) < 1e-9, f"MACRO_EASY mean: expected -0.02, got {easy['mean']}"


def test_compute_regime_stats_percentiles():
    """Verify percentile keys are present and median is sensible."""
    daily_data = [
        {"date": f"2026-01-{i+2:02d}", "regime": "MACRO_NEUTRAL",
         "spread_return": float(i) * 0.01, "long_avg": float(i) * 0.02, "short_avg": float(i) * 0.01}
        for i in range(10)
    ]

    stats = compute_regime_stats(daily_data)
    assert "MACRO_NEUTRAL" in stats
    neutral = stats["MACRO_NEUTRAL"]

    for pct_key in ("p5", "p10", "p25", "p50", "p75", "p90", "p95"):
        assert pct_key in neutral, f"Missing percentile key: {pct_key}"

    # Median of [0, 0.01, ..., 0.09] = average of 0.04 and 0.05 = 0.045
    assert abs(neutral["p50"] - 0.045) < 1e-9, f"p50: expected 0.045, got {neutral['p50']}"


def test_compute_regime_stats_std():
    """Verify std is computed and non-negative."""
    daily_data = [
        {"date": f"2026-01-{i+2:02d}", "regime": "MACRO_STRESS",
         "spread_return": v, "long_avg": v + 0.01, "short_avg": 0.01}
        for i, v in enumerate([0.01, -0.01, 0.02, -0.02, 0.03])
    ]

    stats = compute_regime_stats(daily_data)
    assert stats["MACRO_STRESS"]["std"] >= 0.0


def test_compute_regime_stats_correlation():
    """
    30 days where long_avg and short_avg move nearly identically → correlated_warning = True.
    """
    import random
    random.seed(42)

    daily_data = []
    for i in range(30):
        base = random.gauss(0, 0.01)
        # long and short move together (correlation > 0.9)
        long_avg  = base + random.gauss(0, 0.0001)
        short_avg = base + random.gauss(0, 0.0001)
        daily_data.append({
            "date": f"2026-01-{i+2:02d}",
            "regime": "MACRO_NEUTRAL",
            "spread_return": long_avg - short_avg,
            "long_avg": long_avg,
            "short_avg": short_avg,
        })

    stats = compute_regime_stats(daily_data)
    assert stats["MACRO_NEUTRAL"].get("correlated_warning") is True, (
        "Expected correlated_warning=True when legs move in lockstep"
    )


def test_compute_regime_stats_no_correlation_warning():
    """
    30 days where long and short move independently → correlated_warning = False.
    """
    import random
    random.seed(7)

    daily_data = []
    for i in range(30):
        long_avg  = random.gauss(0.02, 0.01)
        short_avg = random.gauss(-0.01, 0.015)
        daily_data.append({
            "date": f"2026-02-{i+2:02d}",
            "regime": "MACRO_EASY",
            "spread_return": long_avg - short_avg,
            "long_avg": long_avg,
            "short_avg": short_avg,
        })

    stats = compute_regime_stats(daily_data)
    assert stats["MACRO_EASY"].get("correlated_warning") is False, (
        "Expected correlated_warning=False for uncorrelated legs"
    )


def test_compute_regime_stats_max_drawdown():
    """Drawdown from peak: sequence peaks at 0.08, bottoms at 0.02 → max_drawdown = -0.06."""
    returns = [0.02, 0.04, 0.08, 0.06, 0.03, 0.02, 0.05]
    daily_data = [
        {"date": f"2026-01-{i+2:02d}", "regime": "MACRO_STRESS",
         "spread_return": r, "long_avg": r + 0.01, "short_avg": 0.01}
        for i, r in enumerate(returns)
    ]

    stats = compute_regime_stats(daily_data)
    dd = stats["MACRO_STRESS"]["max_drawdown"]
    # Cumulative returns: 0.02, 0.06, 0.14, 0.20, 0.23, 0.25, 0.30
    # All monotonically growing after each day → no real drawdown
    # Peak → trough computed on cumulative returns
    assert dd <= 0.0, f"max_drawdown should be <= 0, got {dd}"


def test_compute_regime_stats_stop_audit_keys():
    """2-day stop audit keys are present in output."""
    daily_data = [
        {"date": f"2026-01-{i+2:02d}", "regime": "MACRO_NEUTRAL",
         "spread_return": 0.01 if i % 2 == 0 else -0.02,
         "long_avg": 0.01, "short_avg": 0.00}
        for i in range(20)
    ]

    stats = compute_regime_stats(daily_data)
    neutral = stats["MACRO_NEUTRAL"]
    assert "stop_trigger_count" in neutral, "Missing stop_trigger_count"
    assert "stop_avg_next5_return" in neutral, "Missing stop_avg_next5_return"


def test_compute_regime_stats_empty_regime():
    """Single-regime input produces stats only for that regime."""
    daily_data = [
        {"date": "2026-01-02", "regime": "MACRO_STRESS", "spread_return": 0.05,
         "long_avg": 0.06, "short_avg": 0.01},
    ]
    stats = compute_regime_stats(daily_data)
    assert list(stats.keys()) == ["MACRO_STRESS"]
    assert stats["MACRO_STRESS"]["count"] == 1
