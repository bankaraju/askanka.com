"""Spec-bound naive comparators for H-2026-04-24-003 Section 9B.1.

always_fade:   direction = -sign(today_resid), P&L = sign * next_ret
always_follow: direction = +sign(expected_return_pct), P&L = sign * next_ret
buy_and_hold:  direction = +1, P&L = next_ret
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from pipeline.autoresearch.overshoot_compliance import metrics as M


def _signed(ev: pd.DataFrame, sign: np.ndarray) -> pd.Series:
    return pd.Series(sign * ev["next_ret"].to_numpy(float), index=ev.index,
                     name="pnl_pct")


def always_fade(events: pd.DataFrame) -> pd.Series:
    sign = -np.sign(events["today_resid"].to_numpy(float))
    return _signed(events, sign)


def always_follow(events: pd.DataFrame) -> pd.Series:
    sign = np.sign(events["expected_return_pct"].to_numpy(float))
    return _signed(events, sign)


def buy_and_hold(events: pd.DataFrame) -> pd.Series:
    sign = np.ones(len(events), dtype=float)
    return _signed(events, sign)


def summarize_naive(events: pd.DataFrame) -> dict:
    rows = {
        "always_fade": always_fade(events),
        "always_follow": always_follow(events),
        "buy_and_hold": buy_and_hold(events),
    }
    out = {}
    for name, s in rows.items():
        core = M.per_bucket_metrics(s.to_numpy())
        out[name] = {
            "sharpe": core["sharpe"],
            "mean_ret_pct": core["mean_ret_pct"],
            "hit_rate": core["hit_rate"],
            "n_trades": core["n_trades"],
        }
    return out


def strongest_name(summary: dict, metric: str = "sharpe") -> str:
    return max(summary.keys(), key=lambda k: summary[k][metric])
