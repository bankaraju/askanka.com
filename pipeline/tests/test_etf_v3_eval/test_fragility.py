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
