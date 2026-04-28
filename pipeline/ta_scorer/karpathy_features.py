"""H-2026-04-29-ta-karpathy-v1 feature builder.

Vectorised ~60-feature daily TA vector per (ticker, date).
All features point-in-time — only data with `date <= as_of` enters each row.

Spec ref: docs/superpowers/specs/2026-04-29-ta-karpathy-v1-design.md §5.

Feature groups:
- 11 momentum oscillators (RSI 7/14/21, Stoch K/D, Williams %R, CCI, MFI, ROC 5/10/20)
- 4 trend strength (ADX, +DI, -DI, DMI signal)
- 10 moving-average geometry (5 EMA distances, 3 SMA distances, 2 MA slopes)
- 4 volatility (ATR%, BB %B, BB width, range%)
- 4 volume (OBV slope, vol z-score, vol spike flag, vol relative-60)
- 5 price action (gap%, body/range, upper wick%, lower wick%, intraday close pos)
- 10 candle patterns (LONG: hammer/engulfing/morning-star/piercing/macd-bull;
                     SHORT: shooting-star/engulfing/evening-star/dark-cloud/macd-bear)
- 8 macro context (NIFTY 5d ret, VIX level/zscore-60/5d-change, regime-3-onehot, sector 5d ret)
- 4 periodicity (Mon/Tue/Wed/Thu; Fri = reference)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# Public list — 60 features
FEATURE_COLUMNS: list[str] = [
    # Momentum oscillators (11)
    "rsi_7", "rsi_14", "rsi_21",
    "stoch_k_14", "stoch_d_3",
    "williams_r_14", "cci_20", "mfi_14",
    "roc_5", "roc_10", "roc_20",
    # Trend strength (4)
    "adx_14", "plus_di_14", "minus_di_14", "dmi_signal",
    # Moving-average geometry (10)
    "dist_8ema_pct", "dist_13ema_pct", "dist_21ema_pct", "dist_50ema_pct", "dist_200ema_pct",
    "dist_20sma_pct", "dist_50sma_pct", "dist_200sma_pct",
    "ma_slope_20", "ma_slope_50",
    # Volatility (4)
    "atr_14_pct", "bb_pct_b_20", "bb_width_pct", "range_pct_today",
    # Volume (4)
    "obv_slope_20", "vol_zscore_20", "vol_spike_2x", "vol_relative_60",
    # Price action (5)
    "gap_pct", "body_to_range", "upper_wick_pct", "lower_wick_pct", "intraday_close_pos",
    # Candle patterns (10)
    "bullish_hammer", "bullish_engulfing", "morning_star", "piercing_line", "macd_bull_cross",
    "shooting_star", "bearish_engulfing", "evening_star", "dark_cloud_cover", "macd_bear_cross",
    # Macro context (8)
    "nifty_ret_5d", "vix_level", "vix_zscore_60", "vix_change_5d",
    "regime_RISK_ON", "regime_NEUTRAL", "regime_RISK_OFF",
    "sector_ret_5d",
    # Periodicity (4)
    "dow_mon", "dow_tue", "dow_wed", "dow_thu",
]
assert len(FEATURE_COLUMNS) == 60, f"FEATURE_COLUMNS has {len(FEATURE_COLUMNS)}, expected 60"


# ---------------------------------------------------------------------------
# Vectorised primitive indicators
# ---------------------------------------------------------------------------

def _rsi(close: pd.Series, n: int) -> pd.Series:
    delta = close.diff()
    up = delta.clip(lower=0).ewm(alpha=1.0 / n, adjust=False, min_periods=n).mean()
    down = (-delta.clip(upper=0)).ewm(alpha=1.0 / n, adjust=False, min_periods=n).mean()
    rs = up / down.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


def _stoch(high: pd.Series, low: pd.Series, close: pd.Series, k: int, d: int) -> tuple[pd.Series, pd.Series]:
    ll = low.rolling(k).min()
    hh = high.rolling(k).max()
    pct_k = 100 * (close - ll) / (hh - ll).replace(0, np.nan)
    pct_d = pct_k.rolling(d).mean()
    return pct_k, pct_d


def _williams_r(high: pd.Series, low: pd.Series, close: pd.Series, n: int) -> pd.Series:
    hh = high.rolling(n).max()
    ll = low.rolling(n).min()
    return -100 * (hh - close) / (hh - ll).replace(0, np.nan)


def _cci(high: pd.Series, low: pd.Series, close: pd.Series, n: int) -> pd.Series:
    tp = (high + low + close) / 3.0
    sma = tp.rolling(n).mean()
    md = (tp - sma).abs().rolling(n).mean()
    return (tp - sma) / (0.015 * md.replace(0, np.nan))


def _mfi(high: pd.Series, low: pd.Series, close: pd.Series, vol: pd.Series, n: int) -> pd.Series:
    tp = (high + low + close) / 3.0
    rmf = tp * vol
    pos = rmf.where(tp > tp.shift(1), 0.0)
    neg = rmf.where(tp < tp.shift(1), 0.0)
    pos_n = pos.rolling(n).sum()
    neg_n = neg.rolling(n).sum().replace(0, np.nan)
    mfr = pos_n / neg_n
    return 100 - 100 / (1 + mfr)


def _roc(close: pd.Series, n: int) -> pd.Series:
    return (close - close.shift(n)) / close.shift(n)


def _atr(high: pd.Series, low: pd.Series, close: pd.Series, n: int) -> pd.Series:
    tr = pd.concat([
        high - low,
        (high - close.shift(1)).abs(),
        (low - close.shift(1)).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1.0 / n, adjust=False, min_periods=n).mean()


def _adx_di(high: pd.Series, low: pd.Series, close: pd.Series, n: int) -> tuple[pd.Series, pd.Series, pd.Series]:
    up = high.diff()
    dn = -low.diff()
    plus_dm = ((up > dn) & (up > 0)).astype(float) * up
    minus_dm = ((dn > up) & (dn > 0)).astype(float) * dn
    atr = _atr(high, low, close, n)
    plus_di = 100 * plus_dm.ewm(alpha=1.0 / n, adjust=False, min_periods=n).mean() / atr.replace(0, np.nan)
    minus_di = 100 * minus_dm.ewm(alpha=1.0 / n, adjust=False, min_periods=n).mean() / atr.replace(0, np.nan)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    adx = dx.ewm(alpha=1.0 / n, adjust=False, min_periods=n).mean()
    return adx, plus_di, minus_di


def _macd_cross(close: pd.Series) -> tuple[pd.Series, pd.Series]:
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    sig = macd.ewm(span=9, adjust=False).mean()
    diff = macd - sig
    bull = ((diff > 0) & (diff.shift(1) <= 0)).astype(int)
    bear = ((diff < 0) & (diff.shift(1) >= 0)).astype(int)
    return bull, bear


def _obv(close: pd.Series, vol: pd.Series) -> pd.Series:
    direction = np.sign(close.diff().fillna(0))
    return (direction * vol).cumsum()


# ---------------------------------------------------------------------------
# Candle patterns (vectorised)
# ---------------------------------------------------------------------------

def _candle_flags(o: pd.Series, h: pd.Series, l: pd.Series, c: pd.Series) -> dict[str, pd.Series]:
    body = (c - o).abs()
    upper = h - np.maximum(o, c)
    lower = np.minimum(o, c) - l
    rng = (h - l).replace(0, np.nan)
    is_bull = c > o
    is_bear = c < o
    body_pct = body / rng

    # Bullish hammer: small body in upper third, lower wick >= 2x body, in mild downtrend
    downtrend = c < c.rolling(5).mean()
    hammer = ((body_pct < 0.35) & (lower >= 2.0 * body) & (upper < body) & downtrend).astype(int)

    # Shooting star: small body in lower third, upper wick >= 2x body, in mild uptrend
    uptrend = c > c.rolling(5).mean()
    shoot = ((body_pct < 0.35) & (upper >= 2.0 * body) & (lower < body) & uptrend).astype(int)

    # Bullish engulfing: bear yesterday, bull today, body engulfs prior body
    prev_bear = (c.shift(1) < o.shift(1))
    prev_bull = (c.shift(1) > o.shift(1))
    bull_engulf = (prev_bear & is_bull & (o <= c.shift(1)) & (c >= o.shift(1))).astype(int)
    bear_engulf = (prev_bull & is_bear & (o >= c.shift(1)) & (c <= o.shift(1))).astype(int)

    # Morning star (3-bar): bear-doji-bull pattern
    bear_2 = (c.shift(2) < o.shift(2))
    star_body_small = ((c.shift(1) - o.shift(1)).abs() < body.shift(1).rolling(20).mean() * 0.5)
    bull_3 = (c > o) & ((c - o) > body.rolling(20).mean() * 0.5)
    morning = (bear_2 & star_body_small & bull_3 & (c > (o.shift(2) + c.shift(2)) / 2)).astype(int)

    # Evening star: mirror
    bull_2 = (c.shift(2) > o.shift(2))
    bear_3 = (c < o) & ((o - c) > body.rolling(20).mean() * 0.5)
    evening = (bull_2 & star_body_small & bear_3 & (c < (o.shift(2) + c.shift(2)) / 2)).astype(int)

    # Piercing line (2-bar bull): big bear yesterday, today opens below prior low and closes above midpoint
    big_bear = prev_bear & ((o.shift(1) - c.shift(1)) > body.rolling(20).mean() * 0.7)
    piercing = (big_bear & (o < l.shift(1)) & (c > (o.shift(1) + c.shift(1)) / 2) & (c < o.shift(1))).astype(int)

    # Dark cloud cover: mirror of piercing
    big_bull = prev_bull & ((c.shift(1) - o.shift(1)) > body.rolling(20).mean() * 0.7)
    dark_cloud = (big_bull & (o > h.shift(1)) & (c < (o.shift(1) + c.shift(1)) / 2) & (c > o.shift(1))).astype(int)

    return {
        "bullish_hammer": hammer.fillna(0).astype(int),
        "bullish_engulfing": bull_engulf.fillna(0).astype(int),
        "morning_star": morning.fillna(0).astype(int),
        "piercing_line": piercing.fillna(0).astype(int),
        "shooting_star": shoot.fillna(0).astype(int),
        "bearish_engulfing": bear_engulf.fillna(0).astype(int),
        "evening_star": evening.fillna(0).astype(int),
        "dark_cloud_cover": dark_cloud.fillna(0).astype(int),
    }


# ---------------------------------------------------------------------------
# Main builder
# ---------------------------------------------------------------------------

def build_feature_matrix(
    *,
    bars: pd.DataFrame,
    nifty: pd.DataFrame,
    vix: pd.DataFrame,
    sector: pd.DataFrame,
    regime: pd.DataFrame,
) -> pd.DataFrame:
    """Build the 60-feature daily TA matrix per the spec.

    All inputs must have a `date` column (datetime64[ns]) sorted ascending.
    `bars` must have open/high/low/close/volume.
    `nifty`, `sector` must have `close`. `vix` must have `close`.
    `regime` must have `regime` column (RISK_ON/NEUTRAL/RISK_OFF and any other labels;
    only the 3 above are one-hotted, anything else collapses to all-zeros).

    Returns a DataFrame indexed by `bars['date']` with columns FEATURE_COLUMNS plus 'date'.
    Rows where any required input has NaN warm-up values are KEPT but the model
    layer drops rows with NaN before fitting.
    """
    df = bars.sort_values("date").reset_index(drop=True).copy()
    o, h, l, c, v = df["open"], df["high"], df["low"], df["close"], df["volume"]

    # ----- momentum oscillators (11) -----
    df["rsi_7"] = _rsi(c, 7)
    df["rsi_14"] = _rsi(c, 14)
    df["rsi_21"] = _rsi(c, 21)
    df["stoch_k_14"], df["stoch_d_3"] = _stoch(h, l, c, 14, 3)
    df["williams_r_14"] = _williams_r(h, l, c, 14)
    df["cci_20"] = _cci(h, l, c, 20)
    df["mfi_14"] = _mfi(h, l, c, v, 14)
    df["roc_5"] = _roc(c, 5)
    df["roc_10"] = _roc(c, 10)
    df["roc_20"] = _roc(c, 20)

    # ----- trend strength (4) -----
    adx, p_di, m_di = _adx_di(h, l, c, 14)
    df["adx_14"] = adx
    df["plus_di_14"] = p_di
    df["minus_di_14"] = m_di
    df["dmi_signal"] = np.where(adx >= 25, np.sign(p_di - m_di), 0.0)

    # ----- moving-average geometry (10) -----
    for span, name in [(8, "8ema"), (13, "13ema"), (21, "21ema"), (50, "50ema"), (200, "200ema")]:
        ema = c.ewm(span=span, adjust=False, min_periods=span).mean()
        df[f"dist_{name}_pct"] = (c - ema) / c
    sma20 = c.rolling(20).mean()
    sma50 = c.rolling(50).mean()
    sma200 = c.rolling(200).mean()
    df["dist_20sma_pct"] = (c - sma20) / c
    df["dist_50sma_pct"] = (c - sma50) / c
    df["dist_200sma_pct"] = (c - sma200) / c
    df["ma_slope_20"] = (sma20 - sma20.shift(5)) / sma20.shift(5)
    df["ma_slope_50"] = (sma50 - sma50.shift(5)) / sma50.shift(5)

    # ----- volatility (4) -----
    atr14 = _atr(h, l, c, 14)
    df["atr_14_pct"] = atr14 / c
    bb_std = c.rolling(20).std()
    upper_bb = sma20 + 2 * bb_std
    lower_bb = sma20 - 2 * bb_std
    df["bb_pct_b_20"] = (c - lower_bb) / (upper_bb - lower_bb).replace(0, np.nan)
    df["bb_width_pct"] = (upper_bb - lower_bb) / sma20
    df["range_pct_today"] = (h - l) / c

    # ----- volume (4) -----
    obv = _obv(c, v.astype(float))
    df["obv_slope_20"] = (obv - obv.shift(20)) / obv.shift(20).abs().clip(lower=1)
    vol_mean20 = v.rolling(20).mean()
    vol_std20 = v.rolling(20).std()
    df["vol_zscore_20"] = (v - vol_mean20) / vol_std20.replace(0, np.nan)
    df["vol_spike_2x"] = (v >= 2 * vol_mean20).astype(int)
    df["vol_relative_60"] = v / v.rolling(60).mean()

    # ----- price action (5) -----
    df["gap_pct"] = (o - c.shift(1)) / c.shift(1)
    rng = (h - l).replace(0, np.nan)
    body = (c - o).abs()
    df["body_to_range"] = body / rng
    df["upper_wick_pct"] = (h - np.maximum(o, c)) / c
    df["lower_wick_pct"] = (np.minimum(o, c) - l) / c
    df["intraday_close_pos"] = (c - l) / rng

    # ----- candle patterns (10) -----
    flags = _candle_flags(o, h, l, c)
    for k, s in flags.items():
        df[k] = s
    bull_macd, bear_macd = _macd_cross(c)
    df["macd_bull_cross"] = bull_macd
    df["macd_bear_cross"] = bear_macd

    # ----- macro context (8) -----
    df["__date_key"] = df["date"]

    nifty_s = nifty.sort_values("date").set_index("date")["close"]
    nifty_5d = (nifty_s / nifty_s.shift(5) - 1).reindex(df["__date_key"]).ffill().reset_index(drop=True)
    df["nifty_ret_5d"] = nifty_5d.values

    vix_s = vix.sort_values("date").set_index("date")["close"]
    vix_aligned = vix_s.reindex(df["__date_key"]).ffill().reset_index(drop=True)
    df["vix_level"] = vix_aligned.values
    vix_mean60 = vix_aligned.rolling(60).mean()
    vix_std60 = vix_aligned.rolling(60).std()
    df["vix_zscore_60"] = ((vix_aligned - vix_mean60) / vix_std60.replace(0, np.nan)).values
    vix_chg = (vix_aligned / vix_aligned.shift(5) - 1)
    df["vix_change_5d"] = vix_chg.values

    sector_s = sector.sort_values("date").set_index("date")["close"]
    sector_5d = (sector_s / sector_s.shift(5) - 1).reindex(df["__date_key"]).ffill().reset_index(drop=True)
    df["sector_ret_5d"] = sector_5d.values

    if regime is not None and len(regime) > 0:
        regime_s = regime.sort_values("date").set_index("date")["regime"].astype(str).str.upper().str.replace("-", "_")
        regime_aligned = regime_s.reindex(df["__date_key"]).ffill().reset_index(drop=True)
        df["regime_RISK_ON"] = (regime_aligned == "RISK_ON").astype(int).values
        df["regime_NEUTRAL"] = (regime_aligned == "NEUTRAL").astype(int).values
        df["regime_RISK_OFF"] = (regime_aligned == "RISK_OFF").astype(int).values
    else:
        df["regime_RISK_ON"] = 0
        df["regime_NEUTRAL"] = 0
        df["regime_RISK_OFF"] = 0

    # ----- periodicity (4) -----
    dow = df["date"].dt.dayofweek
    df["dow_mon"] = (dow == 0).astype(int)
    df["dow_tue"] = (dow == 1).astype(int)
    df["dow_wed"] = (dow == 2).astype(int)
    df["dow_thu"] = (dow == 3).astype(int)

    df = df.drop(columns=["__date_key"])

    # Verify all 60 columns present
    missing = [c for c in FEATURE_COLUMNS if c not in df.columns]
    if missing:
        raise RuntimeError(f"missing features: {missing}")

    return df[["date", *FEATURE_COLUMNS]]


def make_labels(bars: pd.DataFrame, *, win_threshold_pct: float = 0.4) -> pd.DataFrame:
    """T+1 open-to-close binary labels for LONG and SHORT directions.

    y_long  = 1 if (close_t1 - open_t1) / open_t1 >= +win_threshold_pct/100
    y_short = 1 if (open_t1  - close_t1) / open_t1 >= +win_threshold_pct/100

    The label for date T uses bar T+1's open and close (forward-looking),
    so the last row will have NaN labels (no T+1 yet) and must be excluded
    from training.
    """
    df = bars.sort_values("date").reset_index(drop=True).copy()
    o_t1 = df["open"].shift(-1)
    c_t1 = df["close"].shift(-1)
    long_ret = (c_t1 - o_t1) / o_t1
    short_ret = (o_t1 - c_t1) / o_t1
    thresh = win_threshold_pct / 100.0
    return pd.DataFrame({
        "date": df["date"],
        "y_long": (long_ret >= thresh).astype(float).where(long_ret.notna(), other=np.nan),
        "y_short": (short_ret >= thresh).astype(float).where(short_ret.notna(), other=np.nan),
        "ret_t1": long_ret,  # signed t+1 return for downstream P&L
    })
