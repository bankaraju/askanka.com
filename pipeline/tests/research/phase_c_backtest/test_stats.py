import numpy as np
import pytest
from pipeline.research.phase_c_backtest import stats


def test_sharpe_zero_for_zero_returns():
    assert stats.sharpe(np.zeros(100)) == 0.0


def test_sharpe_positive_for_positive_drift():
    rng = np.random.default_rng(42)
    rets = rng.normal(loc=0.001, scale=0.01, size=252)
    s = stats.sharpe(rets, periods_per_year=252)
    assert s > 0.5


def test_bootstrap_sharpe_returns_ci():
    rng = np.random.default_rng(42)
    rets = rng.normal(loc=0.001, scale=0.01, size=252)
    point, lo, hi = stats.bootstrap_sharpe_ci(rets, n_resamples=2000, alpha=0.01, periods_per_year=252, seed=7)
    assert lo < point < hi
    # 99% CI should be wider than 95%
    _, lo95, hi95 = stats.bootstrap_sharpe_ci(rets, n_resamples=2000, alpha=0.05, periods_per_year=252, seed=7)
    assert (hi - lo) > (hi95 - lo95)


def test_max_drawdown_known_curve():
    # Equity curve: 100 -> 110 -> 90 -> 95 -> 80 -> 100
    eq = np.array([100, 110, 90, 95, 80, 100], dtype=float)
    dd = stats.max_drawdown(eq)
    # Peak 110, trough 80 -> drawdown = 30/110 ~ 0.2727
    assert dd == pytest.approx(0.2727, abs=0.001)


def test_binomial_test_clear_significance():
    # 600 wins out of 1000 -- p should be << 0.01
    p = stats.binomial_p(wins=600, n=1000, p_null=0.5)
    assert p < 0.001


def test_binomial_test_no_significance():
    p = stats.binomial_p(wins=505, n=1000, p_null=0.5)
    assert p > 0.5


def test_bonferroni_alpha_per():
    assert stats.bonferroni_alpha_per(family_alpha=0.05, n_tests=5) == pytest.approx(0.01)


def test_h1_verdict_passes_when_all_criteria_met():
    result = stats.h1_verdict(
        in_sample_sharpe_lo=1.5,
        forward_sharpe_lo=0.7,
        in_sample_hit=0.58,
        forward_hit=0.56,
        in_sample_p=0.001,
        forward_p=0.005,
        in_sample_dd=0.10,
        forward_dd=0.15,
        regime_pass_count=4,
        in_sample_sharpe_point=2.0,
        forward_sharpe_point=1.5,
        degraded_ablation_positive=True,
    )
    assert result["passes"] is True
    assert "all criteria met" in result["reason"].lower()


def test_h1_verdict_fails_when_overfit_guard_triggers():
    # Sharpe diverges by > 50% -> fails
    result = stats.h1_verdict(
        in_sample_sharpe_lo=1.5,
        forward_sharpe_lo=0.7,
        in_sample_hit=0.58,
        forward_hit=0.56,
        in_sample_p=0.001,
        forward_p=0.005,
        in_sample_dd=0.10,
        forward_dd=0.15,
        regime_pass_count=4,
        in_sample_sharpe_point=3.0,
        forward_sharpe_point=1.0,  # 1.0 vs 3.0 = 67% gap -> fails 50% guard
        degraded_ablation_positive=True,
    )
    assert result["passes"] is False
    assert "overfit" in result["reason"].lower()


def test_h1_verdict_fails_when_dd_too_deep():
    result = stats.h1_verdict(
        in_sample_sharpe_lo=1.5,
        forward_sharpe_lo=0.7,
        in_sample_hit=0.58,
        forward_hit=0.56,
        in_sample_p=0.001,
        forward_p=0.005,
        in_sample_dd=0.25,  # > 0.20
        forward_dd=0.15,
        regime_pass_count=4,
        in_sample_sharpe_point=2.0,
        forward_sharpe_point=1.5,
        degraded_ablation_positive=True,
    )
    assert result["passes"] is False
    assert "drawdown" in result["reason"].lower()


def test_informational_verdict_passes_with_hits_and_p():
    # 145/240 = 60.4% hits; binomial two-sided p≈0.0015 < 0.01, hit_rate > 0.53 — both gates pass
    result = stats.informational_verdict(hits=145, n=240, alpha=0.01)
    assert result["passes"] is True
    assert result["hit_rate"] == pytest.approx(145 / 240, abs=0.001)
    assert result["p_value"] is not None
    assert result["p_value"] <= 0.01


def test_informational_verdict_fails_with_thin_sample():
    result = stats.informational_verdict(hits=20, n=29, alpha=0.01)
    assert result["passes"] is False
    assert "insufficient" in result["reason"].lower()
