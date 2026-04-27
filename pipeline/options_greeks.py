"""Options Greeks + IV back-solve for Phase C paired-shadow sidecar.

Pure Black-Scholes — no path dependence, no smile model. IV back-solved
via Newton-Raphson, bounded [0.05, 2.00]. Theta returned as DAILY decay
(annual/365). Vega returned per 1% IV move (price change per 0.01
sigma).

Reuses pipeline.options_pricer for BS price computation.

Spec: docs/superpowers/specs/2026-04-27-phase-c-options-paired-shadow-design.md §6.4
"""
from __future__ import annotations

import math
from typing import Literal

from pipeline.options_pricer import (
    bs_call_price,
    bs_put_price,
    _d1,
    _d2,
    _norm_cdf,
)


IV_LOWER: float = 0.05
IV_UPPER: float = 2.00
_PRICE_TOL: float = 0.01           # 1 paisa
_SIGMA_TOL: float = 1e-5
_MAX_ITER: int = 50
_INTRINSIC_TOL: float = 0.5


def _T_from_dte(dte_days: int) -> float:
    return max(dte_days, 1) / 365.0


def _bs_price(spot: float, strike: float, T: float, sigma: float,
              option_type: str, r: float) -> float:
    if option_type == "CE":
        return bs_call_price(spot, strike, T, sigma, r)
    return bs_put_price(spot, strike, T, sigma, r)


def _bs_vega_raw(S: float, K: float, T: float, sigma: float, r: float) -> float:
    """Vega in BS native units (dPrice/dSigma). NOT scaled per 1% IV."""
    if T <= 0 or sigma <= 0:
        return 0.0
    d1 = _d1(S, K, T, sigma, r)
    pdf_d1 = math.exp(-0.5 * d1 ** 2) / math.sqrt(2.0 * math.pi)
    return S * pdf_d1 * math.sqrt(T)


def backsolve_iv(
    spot: float,
    strike: float,
    dte_days: int,
    mid_premium: float,
    option_type: Literal["CE", "PE"],
    r: float = 0.065,
) -> float:
    """Newton-Raphson IV back-solve from BS. Bounded [0.05, 2.00].

    Raises ValueError on non-convergence (50 iters), negative premium,
    or below-intrinsic inputs.
    """
    if mid_premium <= 0:
        raise ValueError(f"mid_premium must be > 0, got {mid_premium}")
    intrinsic = (
        max(spot - strike, 0.0) if option_type == "CE"
        else max(strike - spot, 0.0)
    )
    if mid_premium < intrinsic - _INTRINSIC_TOL:
        raise ValueError(
            f"mid_premium {mid_premium} is below intrinsic {intrinsic} "
            f"({option_type} S={spot} K={strike}) — no valid IV"
        )

    T = _T_from_dte(dte_days)
    sigma = 0.30
    for _ in range(_MAX_ITER):
        price = _bs_price(spot, strike, T, sigma, option_type, r)
        diff = price - mid_premium
        if abs(diff) < _PRICE_TOL:
            return max(IV_LOWER, min(IV_UPPER, sigma))
        v = _bs_vega_raw(spot, strike, T, sigma, r)
        if v <= 0:
            break
        # Newton step: sigma -= f(sigma) / f'(sigma)
        # f(sigma) = bs_price(sigma) - target; f'(sigma) = vega_raw
        new_sigma = sigma - diff / v
        new_sigma = max(IV_LOWER, min(IV_UPPER, new_sigma))
        if abs(new_sigma - sigma) < _SIGMA_TOL:
            return new_sigma
        sigma = new_sigma

    raise ValueError(
        f"IV did not converge after {_MAX_ITER} iters; last sigma={sigma:.4f}, "
        f"target={mid_premium}, "
        f"price@last={_bs_price(spot, strike, T, sigma, option_type, r):.4f}"
    )


def compute_greeks(
    spot: float,
    strike: float,
    dte_days: int,
    iv: float,
    option_type: Literal["CE", "PE"],
    r: float = 0.065,
) -> dict:
    """Returns dict: {delta, theta, vega}. Pure BS, no path dependence.

    - delta: CE = N(d1), PE = N(d1) - 1
    - theta: daily (annual / 365), negative for long options
    - vega: per 1% IV move (price change per 0.01 sigma)
    """
    T = _T_from_dte(dte_days)
    if iv <= 0:
        return {"delta": 0.0, "theta": 0.0, "vega": 0.0}

    d1 = _d1(spot, strike, T, iv, r)
    d2 = _d2(spot, strike, T, iv, r)
    pdf_d1 = math.exp(-0.5 * d1 ** 2) / math.sqrt(2.0 * math.pi)

    if option_type == "CE":
        delta = _norm_cdf(d1)
        # CE theta (annual): -(S·N'(d1)·sigma)/(2√T) - r·K·e^{-rT}·N(d2)
        theta_annual = (
            -(spot * pdf_d1 * iv) / (2.0 * math.sqrt(T))
            - r * strike * math.exp(-r * T) * _norm_cdf(d2)
        )
    else:
        # PE: put-delta = N(d1) - 1
        delta = _norm_cdf(d1) - 1.0
        # PE theta (annual): -(S·N'(d1)·sigma)/(2√T) + r·K·e^{-rT}·N(-d2)
        theta_annual = (
            -(spot * pdf_d1 * iv) / (2.0 * math.sqrt(T))
            + r * strike * math.exp(-r * T) * _norm_cdf(-d2)
        )

    theta_daily = theta_annual / 365.0
    # Vega: per 1% IV move = S·N'(d1)·√T / 100
    vega = spot * pdf_d1 * math.sqrt(T) / 100.0

    return {"delta": delta, "theta": theta_daily, "vega": vega}
