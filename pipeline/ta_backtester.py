"""
TA Backtest Engine — measure forward returns after pattern events.
"""
from __future__ import annotations

import pandas as pd
import numpy as np
from collections import defaultdict

HORIZONS = [1, 3, 5, 10]


def backtest_events(events: list[dict], df: pd.DataFrame) -> dict[str, dict]:
    """Compute forward return statistics for each pattern type."""
    if not events or df.empty:
        return {}

    close = df.set_index("Date")["Close"].astype(float)
    if not isinstance(close.index, pd.DatetimeIndex):
        close.index = pd.to_datetime(close.index)

    pattern_returns: dict[str, list[dict]] = defaultdict(list)

    for event in events:
        event_date = pd.Timestamp(event["date"])
        if event_date not in close.index:
            idx = close.index.searchsorted(event_date)
            if idx >= len(close.index):
                continue
            event_date = close.index[idx]

        pos = close.index.get_loc(event_date)
        if isinstance(pos, slice):
            pos = pos.start

        entry_price = close.iloc[pos]
        fwd = {}
        for h in HORIZONS:
            if pos + h < len(close):
                exit_price = close.iloc[pos + h]
                ret = (exit_price - entry_price) / entry_price * 100.0
                fwd[h] = ret

        if fwd:
            pattern_returns[event["pattern"]].append({
                "direction": event["direction"],
                "returns": fwd,
            })

    results = {}
    for pattern, trades in pattern_returns.items():
        n = len(trades)
        direction = trades[0]["direction"]
        stats: dict = {"occurrences": n, "direction": direction}

        for h in HORIZONS:
            rets = [t["returns"][h] for t in trades if h in t["returns"]]
            if not rets:
                continue
            if direction == "SHORT":
                rets = [-r for r in rets]
            wins = sum(1 for r in rets if r > 0)
            stats[f"win_rate_{h}d"] = round(wins / len(rets), 2)
            stats[f"avg_return_{h}d"] = round(np.mean(rets), 2)
            stats[f"max_return_{h}d"] = round(max(rets), 2)
            stats[f"min_return_{h}d"] = round(min(rets), 2)

        dates = [e["date"] for e in events if e["pattern"] == pattern]
        stats["last_occurrence"] = max(dates) if dates else ""
        stats["dates"] = sorted(dates)

        results[pattern] = stats

    return results
