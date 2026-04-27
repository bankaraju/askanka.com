"""Unit tests for pipeline.options_greeks — Phase C paired-shadow T3."""
import math
import pytest

from pipeline.options_greeks import backsolve_iv, compute_greeks
from pipeline.options_pricer import bs_call_price, bs_put_price


def test_backsolve_iv_call_round_trip():
    """Synthetic CE: price an option at known sigma, then back-solve.
    Expect IV recovers to within 0.5%."""
    S, K, T, sigma_true, r = 2400.0, 2400.0, 30 / 365.0, 0.276, 0.065
    target = bs_call_price(S, K, T, sigma_true, r)
    iv = backsolve_iv(spot=S, strike=K, dte_days=30,
                      mid_premium=target, option_type="CE", r=r)
    assert abs(iv - sigma_true) / sigma_true < 0.005


def test_backsolve_iv_put_round_trip():
    """Synthetic PE round-trip."""
    S, K, T, sigma_true, r = 2400.0, 2400.0, 30 / 365.0, 0.31, 0.065
    target = bs_put_price(S, K, T, sigma_true, r)
    iv = backsolve_iv(spot=S, strike=K, dte_days=30,
                      mid_premium=target, option_type="PE", r=r)
    assert abs(iv - sigma_true) / sigma_true < 0.005


def test_backsolve_iv_otm_call():
    """OTM call (S=2400, K=2500) at sigma=0.30."""
    S, K, T, sigma_true, r = 2400.0, 2500.0, 30 / 365.0, 0.30, 0.065
    target = bs_call_price(S, K, T, sigma_true, r)
    iv = backsolve_iv(spot=S, strike=K, dte_days=30,
                      mid_premium=target, option_type="CE", r=r)
    assert abs(iv - sigma_true) / sigma_true < 0.01


def test_backsolve_iv_bounded_below():
    """At very high IV (sigma_true=1.5), back-solver should still converge
    and stay in the [0.05, 2.00] band."""
    S, K, T, sigma_true, r = 2400.0, 2400.0, 30 / 365.0, 1.5, 0.065
    target = bs_call_price(S, K, T, sigma_true, r)
    iv = backsolve_iv(spot=S, strike=K, dte_days=30,
                      mid_premium=target, option_type="CE", r=r)
    assert 0.05 <= iv <= 2.00
    assert abs(iv - sigma_true) / sigma_true < 0.01


def test_backsolve_iv_raises_on_negative_premium():
    with pytest.raises(ValueError):
        backsolve_iv(spot=2400.0, strike=2400.0, dte_days=30,
                      mid_premium=-1.0, option_type="CE")


def test_backsolve_iv_raises_below_intrinsic():
    """Deep ITM call (S=2500, K=2400) priced below intrinsic (100) → impossible."""
    with pytest.raises(ValueError):
        backsolve_iv(spot=2500.0, strike=2400.0, dte_days=30,
                      mid_premium=10.0, option_type="CE")


def test_compute_greeks_atm_call_delta_near_half():
    g = compute_greeks(spot=2400.0, strike=2400.0, dte_days=30,
                        iv=0.276, option_type="CE")
    assert 0.45 < g["delta"] < 0.65


def test_compute_greeks_atm_put_delta_negative():
    g = compute_greeks(spot=2400.0, strike=2400.0, dte_days=30,
                        iv=0.276, option_type="PE")
    assert -0.55 < g["delta"] < -0.35


def test_compute_greeks_returns_three_keys():
    g = compute_greeks(spot=2400.0, strike=2400.0, dte_days=30,
                        iv=0.276, option_type="CE")
    assert set(g.keys()) == {"delta", "theta", "vega"}


def test_compute_greeks_theta_negative_for_long():
    """Long options always lose to theta — call theta is negative."""
    g_call = compute_greeks(spot=2400.0, strike=2400.0, dte_days=30,
                              iv=0.276, option_type="CE")
    g_put = compute_greeks(spot=2400.0, strike=2400.0, dte_days=30,
                            iv=0.276, option_type="PE")
    assert g_call["theta"] < 0
    assert g_put["theta"] < 0


def test_compute_greeks_vega_positive():
    """Vega is always positive for long options."""
    g = compute_greeks(spot=2400.0, strike=2400.0, dte_days=30,
                        iv=0.276, option_type="CE")
    assert g["vega"] > 0


def test_compute_greeks_expiry_day_dte_floor():
    """DTE=0 must not cause divide-by-zero. Floors to T=1/365 internally."""
    g = compute_greeks(spot=2400.0, strike=2400.0, dte_days=0,
                        iv=0.276, option_type="CE")
    # Should produce valid (if extreme) values, not NaN/inf
    assert math.isfinite(g["delta"])
    assert math.isfinite(g["theta"])
    assert math.isfinite(g["vega"])
