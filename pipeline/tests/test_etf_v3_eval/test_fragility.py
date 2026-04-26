import pytest

from pipeline.autoresearch.etf_v3_eval.phase_2.stats.fragility import (
    evaluate_fragility,
    FragilityVerdict,
)


def test_fragility_passes_with_robust_neighborhood():
    chosen_pnl = 0.10
    neighborhood_pnls = [0.09, 0.08, 0.11, 0.10, 0.07,
                         0.09, 0.10, 0.08, 0.11, 0.09,
                         0.10, 0.08, 0.07, 0.09, 0.10,
                         0.08, 0.11, 0.09, 0.10, 0.07,
                         0.08, 0.09, 0.10, 0.07, 0.11]
    chosen_sharpe = 1.0
    neighborhood_sharpes = [0.9]*25
    v = evaluate_fragility(chosen_pnl, neighborhood_pnls, chosen_sharpe, neighborhood_sharpes)
    assert v.verdict == FragilityVerdict.STABLE
    assert v.pct_positive >= 0.6
    assert v.median_sharpe_ratio >= 0.7


def test_fragility_fails_with_sign_flipping_neighbors():
    chosen_pnl = 0.10
    flipping = [0.10, -0.10, 0.10, -0.10] * 7
    v = evaluate_fragility(chosen_pnl, flipping, 1.0, [0.5]*28)
    assert v.verdict == FragilityVerdict.FRAGILE


def test_fragility_raises_on_zero_chosen_pnl():
    with pytest.raises(ValueError, match="chosen_pnl must be nonzero"):
        evaluate_fragility(0.0, [0.1, 0.2], 1.0, [0.9, 0.9])


def test_fragility_raises_on_empty_neighbors():
    with pytest.raises(ValueError, match="neighbor_pnls must be non-empty"):
        evaluate_fragility(0.1, [], 1.0, [])


def test_fragility_zero_chosen_sharpe_returns_fragile_with_zero_ratio():
    """chosen_sharpe=0 → median_sharpe_ratio=0.0 → fails cond_b → FRAGILE (not error)."""
    v = evaluate_fragility(0.10, [0.10]*25, 0.0, [0.5]*25)
    assert v.verdict == FragilityVerdict.FRAGILE
    assert v.median_sharpe_ratio == 0.0


def test_fragility_break_even_neighbors_not_counted_as_inverted():
    """A neighbor with pnl=0 should NOT count as inverted (it's break-even, not opposite)."""
    chosen_pnl = 0.10
    # 25 break-even (pnl=0) neighbors, all positive sharpe
    neighbors = [0.0] * 25
    sharpes = [0.9] * 25
    v = evaluate_fragility(chosen_pnl, neighbors, 1.0, sharpes)
    assert v.pct_inverted == 0.0  # zero pnl is NOT an inversion
    # but pct_positive is also 0 (zero is not > 0) → cond_a fails → FRAGILE
    assert v.pct_positive == 0.0
    assert v.verdict == FragilityVerdict.FRAGILE
