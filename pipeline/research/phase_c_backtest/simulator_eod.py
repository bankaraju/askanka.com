"""End-of-day directional simulator for the 4-year in-sample window.

For each OPPORTUNITY classification on date t, enter at ``open[t+1]``,
exit at ``close[t+1]``. ``side`` is derived from ``sign(expected_return)``
(LONG if >= 0, else SHORT). Round-trip cost is applied via
:mod:`pipeline.research.phase_c_backtest.cost_model`.

This is intentionally simple — we test directional edge, not intraday
microstructure, which requires minute bars unavailable for the 4yr
window. The 60-day intraday simulator (Task 10) fills that gap.
"""
from __future__ import annotations

import logging

import pandas as pd

from .cost_model import apply_to_pnl

log = logging.getLogger(__name__)


# Canonical output column order for the trade ledger.
_LEDGER_COLUMNS = [
    "entry_date",
    "exit_date",
    "symbol",
    "side",
    "entry_px",
    "exit_px",
    "notional_inr",
    "pnl_gross_inr",
    "pnl_net_inr",
    "label",
    "z_score",
    "expected_return",
]


def _next_bar(bars: pd.DataFrame, after_date: str | pd.Timestamp) -> pd.Series | None:
    """Return the first bar with ``date`` strictly greater than ``after_date``,
    or ``None`` if none exists.
    """
    after = pd.Timestamp(after_date)
    candidates = bars.loc[bars["date"] > after].sort_values("date")
    if candidates.empty:
        return None
    return candidates.iloc[0]


def run_simulation(
    classifications: pd.DataFrame,
    symbol_bars: dict[str, pd.DataFrame],
    notional_inr: float = 50_000,
    slippage_bps: float = 5.0,
    top_n: int | None = None,
    label_filter: str = "OPPORTUNITY_LAG",
) -> pd.DataFrame:
    """Run the end-of-day directional simulator.

    Args:
        classifications: Rows with columns ``{date, symbol, label, action,
            z_score, expected_return}``. Rows whose ``label`` does not match
            ``label_filter`` are ignored.
        symbol_bars: Mapping ``{symbol: DataFrame}`` with per-symbol OHLCV
            bars. Each frame must contain at least ``date``, ``open``, and
            ``close`` columns.
        notional_inr: Per-trade notional (INR).
        slippage_bps: Round-trip slippage assumption in basis points.
        top_n: If set, keep only the top-N classifications per ``date``
            ranked by ``abs(z_score)`` (descending). Ties are broken
            deterministically by ``symbol``.
        label_filter: Classification label that triggers entry (default
            ``"OPPORTUNITY_LAG"``, which is alert-only until H-2026-04-23-003 passes).

    Returns:
        Trade ledger DataFrame with columns in the canonical order:
        ``entry_date, exit_date, symbol, side, entry_px, exit_px,
        notional_inr, pnl_gross_inr, pnl_net_inr, label, z_score,
        expected_return``. Empty DataFrame (with the canonical columns)
        is returned when no trades result.
    """
    required_cols = {"date", "symbol", "label", "z_score", "expected_return"}
    missing = required_cols - set(classifications.columns)
    if missing:
        raise ValueError(
            f"classifications is missing required columns: {sorted(missing)}"
        )

    df = classifications[classifications["label"] == label_filter].copy()

    if top_n is not None:
        df["_abs_z"] = df["z_score"].abs()
        # Sort by date asc, then abs_z desc, with symbol as a deterministic
        # tiebreaker so ties don't depend on input row order.
        df = df.sort_values(
            ["date", "_abs_z", "symbol"],
            ascending=[True, False, True],
        )
        df = df.groupby("date", sort=False).head(top_n).drop(columns="_abs_z")

    rows: list[dict] = []
    for _, row in df.iterrows():
        sym = row["symbol"]
        if sym not in symbol_bars:
            continue
        bars = symbol_bars[sym]
        nxt = _next_bar(bars, row["date"])
        if nxt is None:
            continue

        entry_px = float(nxt["open"])
        exit_px = float(nxt["close"])
        if entry_px <= 0:
            continue

        side = "LONG" if float(row["expected_return"]) >= 0 else "SHORT"
        direction = 1 if side == "LONG" else -1
        signed_return = (exit_px - entry_px) / entry_px * direction
        pnl_gross = signed_return * notional_inr
        pnl_net = apply_to_pnl(pnl_gross, notional_inr, side, slippage_bps)

        entry_date_str = pd.Timestamp(row["date"]).strftime("%Y-%m-%d")
        exit_date_str = pd.Timestamp(nxt["date"]).strftime("%Y-%m-%d")

        rows.append({
            "entry_date": entry_date_str,
            "exit_date": exit_date_str,
            "symbol": sym,
            "side": side,
            "entry_px": entry_px,
            "exit_px": exit_px,
            "notional_inr": float(notional_inr),
            "pnl_gross_inr": float(pnl_gross),
            "pnl_net_inr": float(pnl_net),
            "label": row["label"],
            "z_score": float(row["z_score"]),
            "expected_return": float(row["expected_return"]),
        })

    if not rows:
        return pd.DataFrame(columns=_LEDGER_COLUMNS)
    return pd.DataFrame(rows, columns=_LEDGER_COLUMNS)
