"""Parameter robustness grid for the trade ledger.

Slippage and top-N can be applied post-hoc to a single ledger.
Exit-time variants require re-running ``simulator_intraday`` and are
wired in ``run_backtest.py`` via repeated calls.
"""
from __future__ import annotations

import pandas as pd

from .cost_model import round_trip_cost_inr


def _recost(row: pd.Series, slippage_bps: float) -> float:
    """Apply ``slippage_bps`` to a single ledger row, returning net P&L."""
    cost = round_trip_cost_inr(row["notional_inr"], row["side"], slippage_bps)
    return row["pnl_gross_inr"] - cost


def slippage_sweep(ledger: pd.DataFrame, bps_grid: list[float]) -> pd.DataFrame:
    """For each slippage value in ``bps_grid``, recompute net P&L and summary stats.

    Args:
        ledger: Trade ledger with at least ``notional_inr``, ``side`` and
            ``pnl_gross_inr`` columns.
        bps_grid: Iterable of slippage assumptions (round-trip basis points).

    Returns:
        DataFrame with one row per bps value and columns
        ``slippage_bps, n_trades, total_net_pnl_inr, avg_net_pnl_inr, win_rate``.
    """
    rows: list[dict] = []
    for bps in bps_grid:
        if len(ledger) == 0:
            total = 0.0
            avg = 0.0
            win = 0.0
        else:
            net = ledger.apply(lambda r, b=bps: _recost(r, b), axis=1)
            total = float(net.sum())
            avg = float(net.mean())
            win = float((net > 0).mean())
        rows.append({
            "slippage_bps": bps,
            "n_trades": int(len(ledger)),
            "total_net_pnl_inr": total,
            "avg_net_pnl_inr": avg,
            "win_rate": win,
        })
    return pd.DataFrame(rows)


def top_n_sweep(ledger: pd.DataFrame, n_grid: list[int]) -> pd.DataFrame:
    """For each N cap in ``n_grid``, keep top-N by ``abs(z_score)`` per ``entry_date``.

    Ties are broken deterministically by ``symbol`` (ascending), mirroring
    :mod:`simulator_eod`.

    Args:
        ledger: Trade ledger with at least ``entry_date``, ``symbol``,
            ``z_score`` and ``pnl_net_inr`` columns.
        n_grid: Iterable of per-day caps. ``n`` values that exceed the
            number of trades on a given date simply keep all of them.

    Returns:
        DataFrame with one row per N value and columns
        ``top_n, n_trades, total_net_pnl_inr, avg_net_pnl_inr, win_rate``.
    """
    rows: list[dict] = []
    for n in n_grid:
        if len(ledger) == 0:
            rows.append({
                "top_n": n,
                "n_trades": 0,
                "total_net_pnl_inr": 0.0,
                "avg_net_pnl_inr": 0.0,
                "win_rate": 0.0,
            })
            continue

        df = ledger.copy()
        df["_abs_z"] = df["z_score"].abs()
        df = df.sort_values(
            ["entry_date", "_abs_z", "symbol"],
            ascending=[True, False, True],
        )
        capped = df.groupby("entry_date", sort=False).head(n)
        rows.append({
            "top_n": n,
            "n_trades": int(len(capped)),
            "total_net_pnl_inr": float(capped["pnl_net_inr"].sum()),
            "avg_net_pnl_inr": float(capped["pnl_net_inr"].mean()) if len(capped) else 0.0,
            "win_rate": float((capped["pnl_net_inr"] > 0).mean()) if len(capped) else 0.0,
        })
    return pd.DataFrame(rows)
