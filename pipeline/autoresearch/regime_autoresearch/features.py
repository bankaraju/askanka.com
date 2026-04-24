"""regime_features_v1 — 20 causal features over the ticker × date panel.

Every feature at date t uses only rows with date < t (strict inequality).
Unit-test `test_features_causal.py` asserts this pointwise.
"""
from __future__ import annotations

from typing import Callable

import numpy as np
import pandas as pd

from pipeline.autoresearch.regime_autoresearch.dsl import FEATURES


def _trailing(panel: pd.DataFrame, ticker: str, t: pd.Timestamp, n: int) -> pd.Series:
    df = panel[(panel["ticker"] == ticker) & (panel["date"] < t)].sort_values("date")
    return df.tail(n)["close"]


def ret_1d(panel: pd.DataFrame, ticker: str, t: pd.Timestamp) -> float:
    s = _trailing(panel, ticker, t, 2)
    if len(s) < 2 or s.iloc[0] == 0: return np.nan
    return float(s.iloc[-1] / s.iloc[0] - 1.0)


def _return_n(panel, ticker, t, n):
    s = _trailing(panel, ticker, t, n + 1)
    if len(s) < n + 1 or s.iloc[0] == 0: return np.nan
    return float(s.iloc[-1] / s.iloc[0] - 1.0)


def ret_5d(panel, ticker, t): return _return_n(panel, ticker, t, 5)
def ret_20d(panel, ticker, t): return _return_n(panel, ticker, t, 20)
def ret_60d(panel, ticker, t): return _return_n(panel, ticker, t, 60)


def mom_ratio_20_60(panel, ticker, t):
    r20 = ret_20d(panel, ticker, t); r60 = ret_60d(panel, ticker, t)
    if pd.isna(r60) or r60 == 0: return np.nan
    return r20 / r60


def vol_20d(panel, ticker, t):
    s = _trailing(panel, ticker, t, 21)
    if len(s) < 21: return np.nan
    rets = s.pct_change().dropna()
    return float(rets.std() * np.sqrt(252))


def vol_percentile_252d(panel, ticker, t):
    s = _trailing(panel, ticker, t, 253)
    if len(s) < 253: return np.nan
    rets = s.pct_change().dropna()
    if len(rets) < 20: return np.nan
    rolling = rets.rolling(20).std() * np.sqrt(252)
    rolling = rolling.dropna()
    if rolling.empty: return np.nan
    return float((rolling.iloc[-1] <= rolling).mean())


def vol_of_vol_60d(panel, ticker, t):
    s = _trailing(panel, ticker, t, 81)
    if len(s) < 81: return np.nan
    rets = s.pct_change().dropna()
    roll_vol = rets.rolling(20).std().dropna()
    if len(roll_vol) < 2: return np.nan
    return float(roll_vol.std())


def resid_vs_sector_1d(panel, ticker, t):
    # Returns this ticker's 1d return minus leave-one-out sector mean 1d return.
    # For tests without a sector map, degenerates to ticker_ret - universe_mean.
    # The runner will pass a sector-enriched panel where needed.
    my = ret_1d(panel, ticker, t)
    if pd.isna(my): return np.nan
    others = []
    for other in panel["ticker"].unique():
        if other == ticker: continue
        r = ret_1d(panel, other, t)
        if not pd.isna(r): others.append(r)
    if not others: return np.nan
    return float(my - np.mean(others))


def z_resid_vs_sector_20d(panel, ticker, t):
    # z-score of resid_vs_sector_1d over trailing 20 sector-strip days.
    # Walk back by actual dates (strictly < t) to stay causal — the prior_t
    # passed into resid_vs_sector_1d must be a Timestamp, not a positional index.
    prior_dates = (
        panel[(panel["ticker"] == ticker) & (panel["date"] < t)]
        .sort_values("date")["date"]
        .tail(20)
        .tolist()
    )
    history = []
    for prior_t in prior_dates:
        history.append(resid_vs_sector_1d(panel, ticker, prior_t))
    history = [h for h in history if not pd.isna(h)]
    if len(history) < 10: return np.nan
    sd = np.std(history)
    if sd == 0: return np.nan
    current = resid_vs_sector_1d(panel, ticker, t)
    if pd.isna(current): return np.nan
    return float((current - np.mean(history)) / sd)


def beta_nifty_60d(panel, ticker, t):
    # Requires a NIFTY series in panel; if absent, return NaN.
    s = _trailing(panel, ticker, t, 61)
    if len(s) < 61: return np.nan
    nifty = panel[(panel["ticker"] == "NIFTY") & (panel["date"] < t)].sort_values("date").tail(61)["close"]
    if len(nifty) < 61: return np.nan
    r_t = s.pct_change().dropna().values
    r_n = nifty.pct_change().dropna().values
    n = min(len(r_t), len(r_n))
    if n < 30: return np.nan
    cov = np.cov(r_t[-n:], r_n[-n:])[0, 1]
    var_n = np.var(r_n[-n:])
    if var_n == 0: return np.nan
    return float(cov / var_n)


def days_from_52w_high(panel, ticker, t):
    s = _trailing(panel, ticker, t, 252)
    if len(s) < 252: return np.nan
    idx_max = s.values.argmax()
    return float(len(s) - 1 - idx_max)


def dist_from_52w_high_pct(panel, ticker, t):
    s = _trailing(panel, ticker, t, 252)
    if len(s) < 252: return np.nan
    peak = s.max()
    if peak == 0: return np.nan
    return float((s.iloc[-1] - peak) / peak)


def beta_vix_60d(panel, ticker, t):
    s = _trailing(panel, ticker, t, 61)
    if len(s) < 61: return np.nan
    vix = panel[(panel["ticker"] == "VIX") & (panel["date"] < t)].sort_values("date").tail(61)["close"]
    if len(vix) < 61: return np.nan
    r_t = s.pct_change().dropna().values
    r_v = vix.pct_change().dropna().values
    n = min(len(r_t), len(r_v))
    if n < 30: return np.nan
    cov = np.cov(r_t[-n:], r_v[-n:])[0, 1]
    var_v = np.var(r_v[-n:])
    if var_v == 0: return np.nan
    return float(cov / var_v)


def macro_composite_60d_corr(panel, ticker, t):
    # Correlation to the ETF regime score over 60d. Runner injects 'REGIME' pseudo-ticker.
    s = _trailing(panel, ticker, t, 61)
    if len(s) < 61: return np.nan
    reg = panel[(panel["ticker"] == "REGIME") & (panel["date"] < t)].sort_values("date").tail(61)["close"]
    if len(reg) < 61: return np.nan
    r_t = s.pct_change().dropna().values
    r_r = reg.pct_change().dropna().values
    n = min(len(r_t), len(r_r))
    if n < 30: return np.nan
    return float(np.corrcoef(r_t[-n:], r_r[-n:])[0, 1])


def adv_20d(panel, ticker, t):
    df = panel[(panel["ticker"] == ticker) & (panel["date"] < t)].sort_values("date").tail(20)
    if len(df) < 20 or "volume" not in df.columns: return np.nan
    return float((df["close"] * df["volume"]).mean() / 1e7)  # Rs Cr


def adv_percentile_252d(panel, ticker, t):
    df = panel[(panel["ticker"] == ticker) & (panel["date"] < t)].sort_values("date").tail(252)
    if len(df) < 252 or "volume" not in df.columns: return np.nan
    dv = (df["close"] * df["volume"]).rolling(20).mean().dropna() / 1e7
    if dv.empty: return np.nan
    return float((dv.iloc[-1] <= dv).mean())


def turnover_ratio_20d(panel, ticker, t):
    # Requires market_cap column on panel rows. Returns NaN if absent.
    df = panel[(panel["ticker"] == ticker) & (panel["date"] < t)].sort_values("date").tail(20)
    if len(df) < 20 or "market_cap" not in df.columns: return np.nan
    adv = (df["close"] * df["volume"]).mean()
    mcap = df["market_cap"].iloc[-1]
    if mcap == 0 or pd.isna(mcap): return np.nan
    return float(adv / mcap)


def trust_score(panel, ticker, t):
    # Runner injects trust_score column on panel rows (per ticker, constant over dates).
    df = panel[(panel["ticker"] == ticker) & (panel["date"] < t)]
    if df.empty or "trust_score" not in df.columns: return np.nan
    val = df["trust_score"].dropna()
    return float(val.iloc[-1]) if not val.empty else np.nan


def trust_sector_rank(panel, ticker, t):
    if "trust_score" not in panel.columns or "sector" not in panel.columns: return np.nan
    last = panel[panel["date"] < t].sort_values("date").groupby("ticker").tail(1)
    if ticker not in last["ticker"].values: return np.nan
    my_sector = last[last["ticker"] == ticker]["sector"].iloc[0]
    peers = last[last["sector"] == my_sector].dropna(subset=["trust_score"])
    if peers.empty: return np.nan
    my_ts = peers[peers["ticker"] == ticker]["trust_score"]
    if my_ts.empty: return np.nan
    return float((peers["trust_score"] <= my_ts.iloc[0]).mean())


FEATURE_FUNCS: dict[str, Callable] = {
    "ret_1d": ret_1d, "ret_5d": ret_5d, "ret_20d": ret_20d, "ret_60d": ret_60d,
    "mom_ratio_20_60": mom_ratio_20_60,
    "vol_20d": vol_20d, "vol_percentile_252d": vol_percentile_252d,
    "vol_of_vol_60d": vol_of_vol_60d,
    "resid_vs_sector_1d": resid_vs_sector_1d,
    "z_resid_vs_sector_20d": z_resid_vs_sector_20d,
    "beta_nifty_60d": beta_nifty_60d,
    "days_from_52w_high": days_from_52w_high,
    "dist_from_52w_high_pct": dist_from_52w_high_pct,
    "beta_vix_60d": beta_vix_60d,
    "macro_composite_60d_corr": macro_composite_60d_corr,
    "adv_20d": adv_20d, "adv_percentile_252d": adv_percentile_252d,
    "turnover_ratio_20d": turnover_ratio_20d,
    "trust_score": trust_score, "trust_sector_rank": trust_sector_rank,
}
assert set(FEATURE_FUNCS) == set(FEATURES), "FEATURE_FUNCS / FEATURES out of sync"


def build_feature_matrix(panel: pd.DataFrame, eval_date: pd.Timestamp,
                          tickers: list[str]) -> pd.DataFrame:
    rows = []
    for t in tickers:
        row = {"ticker": t}
        for name, fn in FEATURE_FUNCS.items():
            row[name] = fn(panel, t, eval_date)
        rows.append(row)
    return pd.DataFrame(rows).set_index("ticker")
