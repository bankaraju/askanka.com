"""Per-ticker stock context features (6 dims), causal."""
from __future__ import annotations

import numpy as np
import pandas as pd

from pipeline.autoresearch.etf_stock_tail import constants as C


def stock_feature_names() -> tuple[str, ...]:
    return tuple(f"stock_{f}" for f in C.STOCK_CONTEXT_FEATURES)


def _trailing(bars: pd.DataFrame, eval_date: pd.Timestamp, n: int) -> pd.DataFrame:
    return bars[bars["date"] < eval_date].sort_values("date").tail(n)


def build_stock_features_row(
    bars: pd.DataFrame,
    eval_date: pd.Timestamp,
    sector_id: int,
) -> pd.Series:
    """Compute 6 stock-context features for one (ticker, eval_date)."""
    eval_date = pd.Timestamp(eval_date)
    out: dict[str, float] = {}

    # ret_5d: log return over trailing 6 closes (T-6 → T-1)
    last6 = _trailing(bars, eval_date, 6)["close"]
    if len(last6) >= 6 and last6.iloc[0] > 0:
        out["stock_ret_5d"] = float(np.log(last6.iloc[-1] / last6.iloc[0]))
    else:
        out["stock_ret_5d"] = float("nan")

    # vol_z_60d: z-score of trailing-20d realized vol against trailing-60d distribution of 20d vols
    returns_60 = _trailing(bars, eval_date, 61)["close"].pct_change().dropna()
    if len(returns_60) >= 60:
        vol20_series = returns_60.rolling(20).std().dropna()
        if len(vol20_series) >= 2 and vol20_series.std() > 0:
            out["stock_vol_z_60d"] = float((vol20_series.iloc[-1] - vol20_series.mean()) / vol20_series.std())
        else:
            out["stock_vol_z_60d"] = float("nan")
    else:
        out["stock_vol_z_60d"] = float("nan")

    # volume_z_20d
    last20 = _trailing(bars, eval_date, 20)["volume"]
    if len(last20) >= 20 and last20.std() > 0:
        out["stock_volume_z_20d"] = float((last20.iloc[-1] - last20.mean()) / last20.std())
    else:
        out["stock_volume_z_20d"] = float("nan")

    # adv_percentile_252d: rank of T-1 ADV in trailing 252d distribution
    last252 = _trailing(bars, eval_date, 252)
    if len(last252) >= 252:
        adv = (last252["close"] * last252["volume"])
        out["stock_adv_percentile_252d"] = float((adv.rank(pct=True)).iloc[-1])
    else:
        out["stock_adv_percentile_252d"] = float("nan")

    # sector_id pass-through
    out["stock_sector_id"] = float(sector_id)

    # dist_from_52w_high_pct: (T-1 close / 252d trailing peak) - 1; negative means below 52w high; NaN if fewer than 252 days available
    if len(last252) >= 252:
        peak = float(last252["close"].max())
        latest = float(last252["close"].iloc[-1])
        out["stock_dist_from_52w_high_pct"] = float(latest / peak - 1.0) if peak > 0 else float("nan")
    else:
        out["stock_dist_from_52w_high_pct"] = float("nan")

    result = pd.Series(out)
    return result[list(stock_feature_names())]
