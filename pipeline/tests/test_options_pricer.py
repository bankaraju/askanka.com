"""
Tests for pipeline/options_pricer.py — Black-Scholes math engine.

Run: pytest pipeline/tests/test_options_pricer.py -v
"""
import pytest
import math


class TestBSCallPrice:
    def test_atm_call_known_value(self):
        """ATM call: S=100, K=100, T=30/365, sigma=0.30, r=0 should be ~3.43."""
        from pipeline.options_pricer import bs_call_price
        price = bs_call_price(S=100, K=100, T=30/365, sigma=0.30, r=0.0)
        assert abs(price - 3.43) < 0.1

    def test_deep_itm_call(self):
        """Deep ITM call should be close to intrinsic value."""
        from pipeline.options_pricer import bs_call_price
        price = bs_call_price(S=150, K=100, T=30/365, sigma=0.30, r=0.0)
        assert price > 49.0

    def test_deep_otm_call(self):
        """Deep OTM call should be near zero."""
        from pipeline.options_pricer import bs_call_price
        price = bs_call_price(S=50, K=100, T=30/365, sigma=0.30, r=0.0)
        assert price < 0.01

    def test_call_price_non_negative(self):
        from pipeline.options_pricer import bs_call_price
        price = bs_call_price(S=100, K=100, T=1/365, sigma=0.50, r=0.0)
        assert price >= 0.0


class TestBSPutPrice:
    def test_atm_put_known_value(self):
        """ATM put should equal ATM call when r=0 (put-call parity)."""
        from pipeline.options_pricer import bs_call_price, bs_put_price
        call = bs_call_price(S=100, K=100, T=30/365, sigma=0.30, r=0.0)
        put = bs_put_price(S=100, K=100, T=30/365, sigma=0.30, r=0.0)
        assert abs(call - put) < 0.01

    def test_put_price_non_negative(self):
        from pipeline.options_pricer import bs_put_price
        price = bs_put_price(S=100, K=100, T=1/365, sigma=0.50, r=0.0)
        assert price >= 0.0


class TestBSGreeks:
    def test_call_delta_positive(self):
        from pipeline.options_pricer import bs_greeks
        g = bs_greeks(S=100, K=100, T=30/365, sigma=0.30, r=0.0)
        assert g["delta"] > 0.0

    def test_atm_delta_near_half(self):
        """ATM call delta should be near 0.5."""
        from pipeline.options_pricer import bs_greeks
        g = bs_greeks(S=100, K=100, T=30/365, sigma=0.30, r=0.0)
        assert abs(g["delta"] - 0.5) < 0.05

    def test_theta_negative(self):
        """Theta (daily) should always be negative for long options."""
        from pipeline.options_pricer import bs_greeks
        g = bs_greeks(S=100, K=100, T=30/365, sigma=0.30, r=0.0)
        assert g["theta_daily"] < 0.0

    def test_gamma_positive(self):
        from pipeline.options_pricer import bs_greeks
        g = bs_greeks(S=100, K=100, T=30/365, sigma=0.30, r=0.0)
        assert g["gamma"] > 0.0

    def test_vega_positive(self):
        from pipeline.options_pricer import bs_greeks
        g = bs_greeks(S=100, K=100, T=30/365, sigma=0.30, r=0.0)
        assert g["vega"] > 0.0


class TestATMOptionCost:
    def test_returns_all_fields(self):
        from pipeline.options_pricer import atm_option_cost
        result = atm_option_cost(spot=100.0, vol=0.30, days_to_expiry=30)
        expected_keys = {"call_price", "put_price", "call_theta_daily",
                         "put_theta_daily", "call_delta", "put_delta",
                         "combined_daily_theta"}
        assert set(result.keys()) == expected_keys

    def test_combined_theta_is_sum(self):
        from pipeline.options_pricer import atm_option_cost
        r = atm_option_cost(spot=100.0, vol=0.30, days_to_expiry=30)
        assert abs(r["combined_daily_theta"] - (r["call_theta_daily"] + r["put_theta_daily"])) < 1e-10

    def test_atm_call_equals_put_at_r_zero(self):
        """With r=0, ATM call price equals ATM put price."""
        from pipeline.options_pricer import atm_option_cost
        r = atm_option_cost(spot=100.0, vol=0.30, days_to_expiry=30)
        assert abs(r["call_price"] - r["put_price"]) < 0.01


class TestFiveDayRent:
    def test_returns_all_fields(self):
        from pipeline.options_pricer import five_day_rent
        r = five_day_rent(spot=100.0, vol=0.30, days_to_expiry=30)
        expected_keys = {"premium_pct", "theta_decay_5d_pct", "friction_pct", "total_rent_pct"}
        assert set(r.keys()) == expected_keys

    def test_total_rent_is_theta_plus_friction(self):
        from pipeline.options_pricer import five_day_rent
        r = five_day_rent(spot=100.0, vol=0.30, days_to_expiry=30)
        assert abs(r["total_rent_pct"] - (r["theta_decay_5d_pct"] + r["friction_pct"])) < 1e-10

    def test_friction_is_two_percent_of_premium(self):
        from pipeline.options_pricer import five_day_rent
        r = five_day_rent(spot=100.0, vol=0.30, days_to_expiry=30)
        assert abs(r["friction_pct"] - r["premium_pct"] * 0.02) < 1e-10

    def test_higher_vol_means_higher_rent(self):
        from pipeline.options_pricer import five_day_rent
        low = five_day_rent(spot=100.0, vol=0.20, days_to_expiry=30)
        high = five_day_rent(spot=100.0, vol=0.50, days_to_expiry=30)
        assert high["total_rent_pct"] > low["total_rent_pct"]

    def test_shorter_expiry_means_higher_theta_pct(self):
        from pipeline.options_pricer import five_day_rent
        long_exp = five_day_rent(spot=100.0, vol=0.30, days_to_expiry=30)
        short_exp = five_day_rent(spot=100.0, vol=0.30, days_to_expiry=15)
        assert short_exp["theta_decay_5d_pct"] > long_exp["theta_decay_5d_pct"]

    def test_near_zero_expiry(self):
        """Same-day (T=1/365) should not crash."""
        from pipeline.options_pricer import five_day_rent
        r = five_day_rent(spot=100.0, vol=0.30, days_to_expiry=1)
        assert r["total_rent_pct"] > 0
