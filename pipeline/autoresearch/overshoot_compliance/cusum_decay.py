"""CUSUM decay + recent-24m edge-ratio detector per §12 of backtesting-specs.txt v1.0.

§12.2 CUSUM control chart on rolling monthly mean P&L: flag triggers when
|cumulative deviation| exceeds 3σ_monthly × √N.

§12.3 recent-24m edge / full-history edge ratio: verdict DECAYING when
ratio < 0.5 (and historic edge is positive).
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def analyse(events: pd.DataFrame, recent_months: int = 24) -> dict:
    """events columns: date, trade_ret_pct (percent signed by strategy direction)."""
    df = events.copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)
    if df.empty:
        return {
            "cusum_triggers": 0,
            "recent_24m_mean_ret_pct": 0.0,
            "full_history_mean_ret_pct": 0.0,
            "recent_24m_ratio": 0.0,
            "verdict": "UNKNOWN",
        }

    monthly = df.set_index("date")["trade_ret_pct"].resample("ME").mean().fillna(0.0)
    sigma = float(monthly.std(ddof=1)) if len(monthly) > 1 else 0.0
    if sigma == 0.0:
        triggers = 0
    else:
        mu = float(monthly.mean())
        cs = np.cumsum(monthly.to_numpy() - mu)
        triggers = int(np.sum(np.abs(cs) > 3.0 * sigma * np.sqrt(len(monthly))))

    cutoff = df["date"].max() - pd.DateOffset(months=recent_months)
    recent = df.loc[df["date"] > cutoff, "trade_ret_pct"]
    full_mean = float(df["trade_ret_pct"].mean())
    recent_mean = float(recent.mean()) if len(recent) else 0.0
    ratio = (recent_mean / full_mean) if full_mean else 0.0

    if full_mean <= 0:
        verdict = "NO-HISTORIC-EDGE"
    elif ratio < 0.5:
        verdict = "DECAYING"
    else:
        verdict = "STABLE"

    return {
        "cusum_triggers": triggers,
        "recent_24m_mean_ret_pct": round(recent_mean, 4),
        "full_history_mean_ret_pct": round(full_mean, 4),
        "recent_24m_ratio": round(ratio, 4),
        "verdict": verdict,
    }
