"""regime_features_v1 — 20 causal features over the ticker x date panel.

Every feature at date t uses only rows with date < t (strict inequality).
Unit-test `test_features_causal.py` asserts this pointwise.

Public API — unchanged:
  fn(panel, ticker, t) -> float   # for all 20 features (slow-path reference)
  FEATURE_FUNCS: dict[str, Callable]
  build_feature_matrix(panel, eval_date, tickers) -> pd.DataFrame

Performance
-----------
The public per-ticker functions remain the semantic reference implementations
and are the ones hit by `test_features_smoke.py` (40 parametrised tests) and
`test_features_causal.py`. `build_feature_matrix`, however, is the hot path
that real autoresearch runs drive. Naive delegation (20 features x ~213
tickers = 4,260 full-panel boolean filters per eval_date; `resid_vs_sector_*`
O(T^2) inside that) is unusable at production scale.

Refactor: `build_feature_matrix` constructs a `_Context` once per eval_date
that pre-slices the panel per-ticker, pre-computes the universe-wide 1d
return dict, and pre-computes the 20-prior-day residual history matrix.
Feature evaluation in the hot loop reads from this shared Context via
`_fast_<feature>` helpers and is O(1) per (ticker, feature) cell for the
simple features and O(k) for the history-based ones. The slow public
functions are preserved verbatim as the parity-test reference.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import numpy as np
import pandas as pd

from pipeline.autoresearch.regime_autoresearch.dsl import FEATURES


# ---------------------------------------------------------------------------
# Public slow-path functions — the semantic reference implementations.
# `test_features_smoke.py` and `test_features_causal.py` hit these directly.
# DO NOT alter their semantics. The fast-path in `build_feature_matrix`
# below is held to byte-for-byte parity with these via test_features_parity.
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Fast-path infrastructure for build_feature_matrix.
#
# All functions below are private and consume a pre-built `_Context`. They
# hold byte-for-byte parity with the public slow-path functions (enforced
# by test_features_parity.py). Do NOT drift these without updating the
# slow path too.
# ---------------------------------------------------------------------------


_PSEUDO_TICKERS = ("NIFTY", "VIX", "REGIME")


@dataclass
class _Context:
    eval_date: pd.Timestamp
    # Per-ticker pre-sliced, date-sorted DataFrame for rows with date < eval_date.
    per_ticker: dict[str, pd.DataFrame] = field(default_factory=dict)
    # Per-ticker cached close-price ndarray (last ~300 values, sufficient for all features).
    per_ticker_close: dict[str, np.ndarray] = field(default_factory=dict)
    # Per-ticker cached volume ndarray.
    per_ticker_volume: dict[str, np.ndarray] = field(default_factory=dict)
    # Whether panel has these columns at all.
    has_volume: bool = False
    has_market_cap: bool = False
    has_trust_score: bool = False
    has_sector: bool = False
    # Universe-wide 1d return at eval_date (all tickers including pseudos).
    universe_r1: dict[str, float] = field(default_factory=dict)
    # Last-observed market_cap per ticker (scalar).
    market_cap_map: dict[str, float] = field(default_factory=dict)
    # Last-observed trust_score per ticker.
    trust_score_map: dict[str, float] = field(default_factory=dict)
    # Per-ticker sector string (last observed).
    sector_map: dict[str, str] = field(default_factory=dict)
    # Pseudo-ticker close-arrays (pct_change returns) for NIFTY/VIX/REGIME.
    nifty_close: np.ndarray | None = None
    vix_close: np.ndarray | None = None
    regime_close: np.ndarray | None = None
    # Prior 20 dates that each ticker has available (for z_resid_vs_sector_20d).
    # History matrix: for each ticker, list of (at most) 20 residuals at its
    # last 20 prior dates. Keyed by ticker.
    resid_history: dict[str, list[float]] = field(default_factory=dict)


def _build_context(panel: pd.DataFrame, eval_date: pd.Timestamp,
                    tickers: list[str]) -> _Context:
    """Pre-compute everything the fast-path features need for one eval_date.

    Called once per eval_date. All subsequent feature lookups are O(k) in
    the feature's own window size, not in the full panel.
    """
    ctx = _Context(eval_date=eval_date)
    if panel.empty:
        return ctx

    ctx.has_volume = "volume" in panel.columns
    ctx.has_market_cap = "market_cap" in panel.columns
    ctx.has_trust_score = "trust_score" in panel.columns
    ctx.has_sector = "sector" in panel.columns

    # Filter to causal slice ONCE — the single most important optimisation.
    past = panel[panel["date"] < eval_date]
    if past.empty:
        return ctx

    # Group by ticker, sort within each group, cache per-ticker frames and
    # their close/volume ndarrays. We cap the window at 300 rows per ticker
    # because the longest-window feature (vol_percentile_252d) needs 253
    # and `adv_percentile_252d` needs 252; 300 is a safe ceiling.
    CAP = 300

    # Ensure every requested ticker is in the map (possibly empty) so feature
    # code can lookup without KeyError.
    all_needed = set(tickers) | set(_PSEUDO_TICKERS)

    for ticker, g in past.groupby("ticker", sort=False):
        if ticker not in all_needed:
            # Universe tickers we don't need per-ticker frames for still need
            # to contribute to universe_r1 — handled below.
            pass
        g_sorted = g.sort_values("date")
        tail = g_sorted.tail(CAP)
        ctx.per_ticker[ticker] = tail
        ctx.per_ticker_close[ticker] = tail["close"].to_numpy(dtype=float, copy=False)
        if ctx.has_volume:
            ctx.per_ticker_volume[ticker] = tail["volume"].to_numpy(dtype=float, copy=False)
        if ctx.has_market_cap and not tail.empty:
            ctx.market_cap_map[ticker] = float(tail["market_cap"].iloc[-1])
        if ctx.has_trust_score and not tail.empty:
            ts_series = tail["trust_score"].dropna()
            if not ts_series.empty:
                ctx.trust_score_map[ticker] = float(ts_series.iloc[-1])
        if ctx.has_sector and not tail.empty:
            sec = tail["sector"].iloc[-1]
            if pd.notna(sec):
                ctx.sector_map[ticker] = str(sec)

    # Pseudo-ticker close arrays (longer cap — beta features need 61).
    for pseudo in _PSEUDO_TICKERS:
        tail = ctx.per_ticker.get(pseudo)
        if tail is not None and not tail.empty:
            arr = ctx.per_ticker_close[pseudo]
            if pseudo == "NIFTY":
                ctx.nifty_close = arr
            elif pseudo == "VIX":
                ctx.vix_close = arr
            elif pseudo == "REGIME":
                ctx.regime_close = arr

    # Universe-wide 1d return at eval_date: for every ticker in the panel,
    # compute last-two-rows return. This is the `others` loop inside
    # resid_vs_sector_1d, collapsed from O(T^2) to O(T).
    for t_name, arr in ctx.per_ticker_close.items():
        if len(arr) < 2 or arr[-2] == 0:
            ctx.universe_r1[t_name] = np.nan
        else:
            ctx.universe_r1[t_name] = float(arr[-1] / arr[-2] - 1.0)

    # Residual history for z_resid_vs_sector_20d. The slow path walks back
    # 20 distinct prior dates per ticker, then calls resid_vs_sector_1d at
    # each — each call is O(T^2). That's O(T * 20 * T^2) total. The fast
    # path collapses this to O(20 * T) by batching: for each of the 20
    # prior dates (union across all target tickers), compute a full
    # universe_r1_at_prior dict in a single pass, then derive per-ticker
    # residuals from it.
    #
    # Slow-path semantics (preserved bit-for-bit):
    #   prior_dates = [ticker's own last 20 dates strictly < eval_date]
    #   resid_vs_sector_1d(panel, ticker, prior_t) uses panel["ticker"].unique()
    #   as its "others" set — i.e., the ENTIRE panel (not just sector peers).
    #   That's how the production code runs today. We faithfully preserve it.

    # Collect per-ticker list of up to 20 prior dates. Skip tickers not in
    # our target set to save work.
    target_set = set(tickers)
    prior_dates_per_ticker: dict[str, list[pd.Timestamp]] = {}
    global_prior_dates: set[pd.Timestamp] = set()
    for ticker in target_set:
        tail = ctx.per_ticker.get(ticker)
        if tail is None or tail.empty:
            prior_dates_per_ticker[ticker] = []
            continue
        dates = tail["date"].tail(20).tolist()
        prior_dates_per_ticker[ticker] = dates
        global_prior_dates.update(dates)

    # For each prior date d in the union, compute universe_r1_at_d in one
    # shot by slicing each per-ticker frame to (date < d) and taking the
    # last two rows. This uses searchsorted on the cached per-ticker date
    # arrays — O(log n) per ticker, O(T log n) per prior date.
    # Cache per-ticker date arrays once.
    per_ticker_date_arr: dict[str, np.ndarray] = {}
    for t_name, tail in ctx.per_ticker.items():
        per_ticker_date_arr[t_name] = tail["date"].to_numpy(dtype="datetime64[ns]", copy=False)

    universe_r1_by_date: dict[pd.Timestamp, dict[str, float]] = {}
    for d in global_prior_dates:
        d64 = np.datetime64(d, "ns")
        day_map: dict[str, float] = {}
        for t_name, date_arr in per_ticker_date_arr.items():
            # Positions with date < d, in the already-sorted array.
            idx = int(np.searchsorted(date_arr, d64, side="left"))
            if idx < 2:
                day_map[t_name] = np.nan
                continue
            close_arr = ctx.per_ticker_close[t_name]
            prev = close_arr[idx - 2]
            last = close_arr[idx - 1]
            if prev == 0:
                day_map[t_name] = np.nan
            else:
                day_map[t_name] = float(last / prev - 1.0)
        universe_r1_by_date[d] = day_map

    # Now derive residual history per target ticker: resid = my_r1 - mean(others)
    # where others = every ticker in the panel with non-NaN r1 at that date
    # (that's panel["ticker"].unique() minus self, minus NaNs — exactly the
    # slow-path semantics).
    for ticker in target_set:
        dates = prior_dates_per_ticker[ticker]
        history: list[float] = []
        for d in dates:
            day_map = universe_r1_by_date.get(d, {})
            my = day_map.get(ticker, np.nan)
            if np.isnan(my):
                continue
            others = [r for tn, r in day_map.items() if tn != ticker and not np.isnan(r)]
            if not others:
                continue
            history.append(my - float(np.mean(others)))
        ctx.resid_history[ticker] = history

    return ctx


# --- Fast-path feature kernels. Each reads from ctx; returns float/NaN. ---


def _fast_ret_1d(ctx: _Context, ticker: str) -> float:
    arr = ctx.per_ticker_close.get(ticker)
    if arr is None or len(arr) < 2 or arr[-2] == 0:
        return np.nan
    return float(arr[-1] / arr[-2] - 1.0)


def _fast_return_n(ctx: _Context, ticker: str, n: int) -> float:
    arr = ctx.per_ticker_close.get(ticker)
    if arr is None or len(arr) < n + 1 or arr[-(n + 1)] == 0:
        return np.nan
    return float(arr[-1] / arr[-(n + 1)] - 1.0)


def _fast_ret_5d(ctx, ticker): return _fast_return_n(ctx, ticker, 5)
def _fast_ret_20d(ctx, ticker): return _fast_return_n(ctx, ticker, 20)
def _fast_ret_60d(ctx, ticker): return _fast_return_n(ctx, ticker, 60)


def _fast_mom_ratio_20_60(ctx, ticker):
    r20 = _fast_ret_20d(ctx, ticker)
    r60 = _fast_ret_60d(ctx, ticker)
    if pd.isna(r60) or r60 == 0:
        return np.nan
    return r20 / r60


def _fast_vol_20d(ctx, ticker):
    arr = ctx.per_ticker_close.get(ticker)
    if arr is None or len(arr) < 21:
        return np.nan
    # Match slow-path: pd.Series([...]).pct_change().dropna().std()
    # which is pandas' default ddof=1 std over the 20 pct-change samples.
    window = arr[-21:]
    rets = window[1:] / window[:-1] - 1.0
    rets = rets[~np.isnan(rets) & ~np.isinf(rets)]
    if len(rets) < 2:
        return np.nan
    return float(rets.std(ddof=1) * np.sqrt(252))


def _fast_vol_percentile_252d(ctx, ticker):
    arr = ctx.per_ticker_close.get(ticker)
    if arr is None or len(arr) < 253:
        return np.nan
    window = arr[-253:]
    rets = window[1:] / window[:-1] - 1.0
    # dropna: infs/nans excluded to match pandas pct_change+dropna
    rets_mask = ~np.isnan(rets) & ~np.isinf(rets)
    rets = rets[rets_mask]
    if len(rets) < 20:
        return np.nan
    # Match slow-path exactly: pd.Series(rets).rolling(20).std() * sqrt(252)
    # then dropna and percentile-rank the final element.
    rolling = pd.Series(rets).rolling(20).std() * np.sqrt(252)
    rolling = rolling.dropna()
    if rolling.empty:
        return np.nan
    return float((rolling.iloc[-1] <= rolling).mean())


def _fast_vol_of_vol_60d(ctx, ticker):
    arr = ctx.per_ticker_close.get(ticker)
    if arr is None or len(arr) < 81:
        return np.nan
    window = arr[-81:]
    rets = window[1:] / window[:-1] - 1.0
    rets_mask = ~np.isnan(rets) & ~np.isinf(rets)
    rets = rets[rets_mask]
    roll_vol = pd.Series(rets).rolling(20).std().dropna()
    if len(roll_vol) < 2:
        return np.nan
    return float(roll_vol.std())


def _fast_resid_vs_sector_1d(ctx, ticker):
    my = ctx.universe_r1.get(ticker, np.nan)
    if np.isnan(my):
        return np.nan
    others = [r for tn, r in ctx.universe_r1.items()
              if tn != ticker and not np.isnan(r)]
    if not others:
        return np.nan
    return float(my - np.mean(others))


def _fast_z_resid_vs_sector_20d(ctx, ticker):
    history = ctx.resid_history.get(ticker, [])
    if len(history) < 10:
        return np.nan
    sd = float(np.std(history))
    if sd == 0:
        return np.nan
    current = _fast_resid_vs_sector_1d(ctx, ticker)
    if pd.isna(current):
        return np.nan
    return float((current - float(np.mean(history))) / sd)


def _pair_beta(arr_a: np.ndarray, arr_b: np.ndarray) -> float:
    """Shared kernel for beta_nifty_60d / beta_vix_60d — exact slow-path match."""
    if arr_a is None or arr_b is None:
        return np.nan
    if len(arr_a) < 61 or len(arr_b) < 61:
        return np.nan
    a_win = arr_a[-61:]
    b_win = arr_b[-61:]
    r_t = a_win[1:] / a_win[:-1] - 1.0
    r_t = r_t[~np.isnan(r_t) & ~np.isinf(r_t)]
    r_b = b_win[1:] / b_win[:-1] - 1.0
    r_b = r_b[~np.isnan(r_b) & ~np.isinf(r_b)]
    n = min(len(r_t), len(r_b))
    if n < 30:
        return np.nan
    a_tail = r_t[-n:]
    b_tail = r_b[-n:]
    cov = np.cov(a_tail, b_tail)[0, 1]
    var_b = np.var(b_tail)
    if var_b == 0:
        return np.nan
    return float(cov / var_b)


def _fast_beta_nifty_60d(ctx, ticker):
    arr_t = ctx.per_ticker_close.get(ticker)
    return _pair_beta(arr_t, ctx.nifty_close)


def _fast_beta_vix_60d(ctx, ticker):
    arr_t = ctx.per_ticker_close.get(ticker)
    return _pair_beta(arr_t, ctx.vix_close)


def _fast_macro_composite_60d_corr(ctx, ticker):
    arr_t = ctx.per_ticker_close.get(ticker)
    arr_r = ctx.regime_close
    if arr_t is None or arr_r is None:
        return np.nan
    if len(arr_t) < 61 or len(arr_r) < 61:
        return np.nan
    t_win = arr_t[-61:]
    r_win = arr_r[-61:]
    r_t = t_win[1:] / t_win[:-1] - 1.0
    r_t = r_t[~np.isnan(r_t) & ~np.isinf(r_t)]
    r_r = r_win[1:] / r_win[:-1] - 1.0
    r_r = r_r[~np.isnan(r_r) & ~np.isinf(r_r)]
    n = min(len(r_t), len(r_r))
    if n < 30:
        return np.nan
    return float(np.corrcoef(r_t[-n:], r_r[-n:])[0, 1])


def _fast_days_from_52w_high(ctx, ticker):
    arr = ctx.per_ticker_close.get(ticker)
    if arr is None or len(arr) < 252:
        return np.nan
    window = arr[-252:]
    idx_max = int(np.argmax(window))
    return float(len(window) - 1 - idx_max)


def _fast_dist_from_52w_high_pct(ctx, ticker):
    arr = ctx.per_ticker_close.get(ticker)
    if arr is None or len(arr) < 252:
        return np.nan
    window = arr[-252:]
    peak = float(window.max())
    if peak == 0:
        return np.nan
    return float((window[-1] - peak) / peak)


def _fast_adv_20d(ctx, ticker):
    if not ctx.has_volume:
        return np.nan
    close = ctx.per_ticker_close.get(ticker)
    vol = ctx.per_ticker_volume.get(ticker)
    if close is None or vol is None or len(close) < 20:
        return np.nan
    c = close[-20:]
    v = vol[-20:]
    return float((c * v).mean() / 1e7)


def _fast_adv_percentile_252d(ctx, ticker):
    if not ctx.has_volume:
        return np.nan
    close = ctx.per_ticker_close.get(ticker)
    vol = ctx.per_ticker_volume.get(ticker)
    if close is None or vol is None or len(close) < 252:
        return np.nan
    c = close[-252:]
    v = vol[-252:]
    # Match slow-path: pd.Series(close*volume).rolling(20).mean().dropna() / 1e7
    dv_series = pd.Series(c * v).rolling(20).mean().dropna() / 1e7
    if dv_series.empty:
        return np.nan
    return float((dv_series.iloc[-1] <= dv_series).mean())


def _fast_turnover_ratio_20d(ctx, ticker):
    if not ctx.has_volume or not ctx.has_market_cap:
        return np.nan
    close = ctx.per_ticker_close.get(ticker)
    vol = ctx.per_ticker_volume.get(ticker)
    if close is None or vol is None or len(close) < 20:
        return np.nan
    c = close[-20:]
    v = vol[-20:]
    adv = float((c * v).mean())
    mcap = ctx.market_cap_map.get(ticker, np.nan)
    if mcap == 0 or pd.isna(mcap):
        return np.nan
    return float(adv / mcap)


def _fast_trust_score(ctx, ticker):
    if not ctx.has_trust_score:
        return np.nan
    val = ctx.trust_score_map.get(ticker)
    if val is None:
        return np.nan
    return float(val)


# --- trust_sector_rank: needs a global-per-eval_date rank table. ---


def _precompute_trust_sector_rank(ctx: _Context) -> dict[str, float]:
    """For each ticker-with-sector, percentile-rank its trust score among
    same-sector peers (inclusive). Matches slow-path semantics:
      (peers["trust_score"] <= my_ts).mean()
    """
    if not ctx.has_trust_score or not ctx.has_sector:
        return {}
    # Bucket tickers by sector, filtering to those with a non-NaN trust score
    # (dropna(subset=["trust_score"])) semantics.
    by_sector: dict[str, list[tuple[str, float]]] = {}
    for ticker, sector in ctx.sector_map.items():
        ts = ctx.trust_score_map.get(ticker)
        if ts is None or pd.isna(ts):
            continue
        by_sector.setdefault(sector, []).append((ticker, ts))
    ranks: dict[str, float] = {}
    for sector, members in by_sector.items():
        if not members:
            continue
        scores = np.array([m[1] for m in members], dtype=float)
        for ticker, ts in members:
            ranks[ticker] = float((scores <= ts).mean())
    return ranks


def _fast_trust_sector_rank(ctx, ticker, _rank_cache):
    if not ctx.has_trust_score or not ctx.has_sector:
        return np.nan
    return float(_rank_cache.get(ticker, np.nan))


# Fast-path dispatch table: same keys as FEATURE_FUNCS, different callables.
# Note `trust_sector_rank` needs the rank cache passed in — handled specially
# in the loop.
_FAST_FEATURE_FUNCS: dict[str, Callable] = {
    "ret_1d": _fast_ret_1d,
    "ret_5d": _fast_ret_5d,
    "ret_20d": _fast_ret_20d,
    "ret_60d": _fast_ret_60d,
    "mom_ratio_20_60": _fast_mom_ratio_20_60,
    "vol_20d": _fast_vol_20d,
    "vol_percentile_252d": _fast_vol_percentile_252d,
    "vol_of_vol_60d": _fast_vol_of_vol_60d,
    "resid_vs_sector_1d": _fast_resid_vs_sector_1d,
    "z_resid_vs_sector_20d": _fast_z_resid_vs_sector_20d,
    "beta_nifty_60d": _fast_beta_nifty_60d,
    "days_from_52w_high": _fast_days_from_52w_high,
    "dist_from_52w_high_pct": _fast_dist_from_52w_high_pct,
    "beta_vix_60d": _fast_beta_vix_60d,
    "macro_composite_60d_corr": _fast_macro_composite_60d_corr,
    "adv_20d": _fast_adv_20d,
    "adv_percentile_252d": _fast_adv_percentile_252d,
    "turnover_ratio_20d": _fast_turnover_ratio_20d,
    "trust_score": _fast_trust_score,
    # trust_sector_rank: handled specially in build_feature_matrix.
}


def build_feature_matrix(panel: pd.DataFrame, eval_date: pd.Timestamp,
                          tickers: list[str]) -> pd.DataFrame:
    """Fast-path matrix builder.

    Semantically identical to the slow-path composition (`fn(panel, t, eval_date)`
    for each feature x ticker). Enforced by `test_features_parity.py`.
    """
    ctx = _build_context(panel, eval_date, tickers)
    trust_rank_cache = _precompute_trust_sector_rank(ctx)
    feature_names = list(FEATURE_FUNCS.keys())

    rows = []
    for ticker in tickers:
        row: dict[str, object] = {"ticker": ticker}
        for name in feature_names:
            if name == "trust_sector_rank":
                row[name] = _fast_trust_sector_rank(ctx, ticker, trust_rank_cache)
            else:
                row[name] = _FAST_FEATURE_FUNCS[name](ctx, ticker)
        rows.append(row)
    return pd.DataFrame(rows).set_index("ticker")
