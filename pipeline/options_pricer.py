"""Black-Scholes options pricing engine — pure math, no I/O."""
import math

FRICTION_RATE = 0.02
RISK_FREE_RATE = 0.0


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _d1(S: float, K: float, T: float, sigma: float, r: float) -> float:
    return (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))


def _d2(S: float, K: float, T: float, sigma: float, r: float) -> float:
    return _d1(S, K, T, sigma, r) - sigma * math.sqrt(T)


def bs_call_price(S: float, K: float, T: float, sigma: float, r: float = RISK_FREE_RATE) -> float:
    if T <= 0:
        return max(S - K, 0.0)
    d1 = _d1(S, K, T, sigma, r)
    d2 = _d2(S, K, T, sigma, r)
    return S * _norm_cdf(d1) - K * math.exp(-r * T) * _norm_cdf(d2)


def bs_put_price(S: float, K: float, T: float, sigma: float, r: float = RISK_FREE_RATE) -> float:
    if T <= 0:
        return max(K - S, 0.0)
    d1 = _d1(S, K, T, sigma, r)
    d2 = _d2(S, K, T, sigma, r)
    return K * math.exp(-r * T) * _norm_cdf(-d2) - S * _norm_cdf(-d1)


def bs_greeks(S: float, K: float, T: float, sigma: float, r: float = RISK_FREE_RATE) -> dict:
    if T <= 0:
        return {"delta": 1.0 if S > K else 0.0, "gamma": 0.0, "theta_daily": 0.0, "vega": 0.0}
    d1 = _d1(S, K, T, sigma, r)
    d2 = _d2(S, K, T, sigma, r)
    pdf_d1 = math.exp(-0.5 * d1 ** 2) / math.sqrt(2.0 * math.pi)

    delta = _norm_cdf(d1)
    gamma = pdf_d1 / (S * sigma * math.sqrt(T))
    theta_annual = (
        -(S * pdf_d1 * sigma) / (2.0 * math.sqrt(T))
        - r * K * math.exp(-r * T) * _norm_cdf(d2)
    )
    theta_daily = theta_annual / 365.0
    vega = S * pdf_d1 * math.sqrt(T) / 100.0

    return {"delta": delta, "gamma": gamma, "theta_daily": theta_daily, "vega": vega}


def atm_option_cost(spot: float, vol: float, days_to_expiry: int) -> dict:
    T = max(days_to_expiry, 1) / 365.0
    K = spot
    call = bs_call_price(spot, K, T, vol)
    put = bs_put_price(spot, K, T, vol)
    call_greeks = bs_greeks(spot, K, T, vol)
    put_d1 = _d1(spot, K, T, vol, RISK_FREE_RATE)
    put_pdf = math.exp(-0.5 * put_d1 ** 2) / math.sqrt(2.0 * math.pi)
    put_theta_annual = (
        -(spot * put_pdf * vol) / (2.0 * math.sqrt(T))
        + RISK_FREE_RATE * K * math.exp(-RISK_FREE_RATE * T) * _norm_cdf(-_d2(spot, K, T, vol, RISK_FREE_RATE))
    )
    put_theta_daily = put_theta_annual / 365.0

    return {
        "call_price": call,
        "put_price": put,
        "call_theta_daily": call_greeks["theta_daily"],
        "put_theta_daily": put_theta_daily,
        "call_delta": call_greeks["delta"],
        "put_delta": _norm_cdf(put_d1) - 1.0,
        "combined_daily_theta": call_greeks["theta_daily"] + put_theta_daily,
    }


def five_day_rent(spot: float, vol: float, days_to_expiry: int) -> dict:
    cost = atm_option_cost(spot, vol, days_to_expiry)
    premium_pct = (cost["call_price"] + cost["put_price"]) / spot * 100.0
    theta_decay_5d_pct = abs(cost["combined_daily_theta"]) * 5.0 / spot * 100.0
    friction_pct = premium_pct * FRICTION_RATE
    return {
        "premium_pct": premium_pct,
        "theta_decay_5d_pct": theta_decay_5d_pct,
        "friction_pct": friction_pct,
        "total_rent_pct": theta_decay_5d_pct + friction_pct,
    }
