"""Intraday 1-minute simulator with mechanical 14:30 IST exit.

For each OPPORTUNITY signal on date t, replay the day's 1-minute bars:
enter at the **next bar's open** after the signal time, walk forward
bar-by-bar, exit on the first of:

* stop-loss hit (intra-bar low for LONG, high for SHORT),
* target hit (intra-bar high for LONG, low for SHORT), or
* mechanical 14:30:00 IST exit at that bar's open.

The entry bar is excluded from the stop/target check to avoid same-bar
lookahead — entry happens at its open, so the same bar's high/low
cannot be used to fill an exit. Round-trip cost is applied via
:mod:`pipeline.research.phase_c_backtest.cost_model`.

This is the 60-day forward true-intraday simulator (T2 in the Phase C
spec). The 4-year EOD simulator lives in :mod:`simulator_eod`.
"""
from __future__ import annotations

import logging
from datetime import time as dtime

import pandas as pd

from .cost_model import apply_to_pnl

log = logging.getLogger(__name__)


# Canonical output column order for the intraday trade ledger.
_LEDGER_COLUMNS = [
    "entry_time",
    "exit_time",
    "symbol",
    "side",
    "entry_px",
    "exit_px",
    "exit_reason",
    "notional_inr",
    "pnl_gross_inr",
    "pnl_net_inr",
    "signal_time",
    "z_score",
]


def _parse_exit_time(exit_time: str) -> dtime:
    """Parse an ``HH:MM:SS`` string into a ``datetime.time``."""
    h, m, s = exit_time.split(":")
    return dtime(int(h), int(m), int(s))


def simulate_trade(
    bars: pd.DataFrame,
    signal_time: str,
    side: str,
    stop_pct: float,
    target_pct: float,
    notional_inr: float = 50_000,
    slippage_bps: float = 5.0,
    exit_time: str = "14:30:00",
) -> dict | None:
    """Simulate a single intraday trade.

    Args:
        bars: 1-min OHLCV DataFrame with ``date`` as a datetime column and
            ``open/high/low/close`` columns. Bars must be on a single
            trading day (the simulator does not span sessions).
        signal_time: ISO timestamp string when the signal was generated.
        side: ``"LONG"`` or ``"SHORT"``.
        stop_pct: Stop-loss as a positive fraction of entry price.
        target_pct: Profit target as a positive fraction of entry price.
        notional_inr: Position notional (INR).
        slippage_bps: Round-trip slippage assumption in basis points.
        exit_time: Mechanical exit time of day (``HH:MM:SS``).

    Returns:
        A trade dict with ``entry_time, entry_px, exit_time, exit_px,
        exit_reason, side, notional_inr, pnl_gross_inr, pnl_net_inr`` —
        or ``None`` when no entry is possible (e.g. signal at/after the
        last bar, or signal at/after ``exit_time``).
    """
    sig_ts = pd.Timestamp(signal_time)
    cutoff = _parse_exit_time(exit_time)

    df = bars.sort_values("date").reset_index(drop=True)
    after = df[df["date"] > sig_ts]
    if after.empty:
        return None

    entry_idx = int(after.index[0])
    entry_bar = df.iloc[entry_idx]
    if entry_bar["date"].time() >= cutoff:
        return None

    entry_px = float(entry_bar["open"])

    if side == "LONG":
        stop_px = entry_px * (1 - stop_pct)
        target_px = entry_px * (1 + target_pct)
    else:
        stop_px = entry_px * (1 + stop_pct)
        target_px = entry_px * (1 - target_pct)

    exit_reason: str | None = None
    exit_px: float | None = None
    exit_bar: pd.Series | None = None

    for i in range(entry_idx, len(df)):
        bar = df.iloc[i]
        bar_time = bar["date"].time()

        # Mechanical 14:30 exit fires at this bar's open. Evaluated for
        # every bar (including the entry bar) — entry bar is already
        # guarded above to be strictly pre-cutoff.
        if bar_time >= cutoff:
            exit_px = float(bar["open"])
            exit_reason = "TIME_STOP"
            exit_bar = bar
            break

        # Skip stop/target check on the entry bar — we entered at its
        # open, so its high/low can't be used to fill an exit without
        # introducing same-bar lookahead.
        if i == entry_idx:
            continue

        bar_hi = float(bar["high"])
        bar_lo = float(bar["low"])
        if side == "LONG":
            if bar_lo <= stop_px:
                exit_px = stop_px
                exit_reason = "STOP"
                exit_bar = bar
                break
            if bar_hi >= target_px:
                exit_px = target_px
                exit_reason = "TARGET"
                exit_bar = bar
                break
        else:  # SHORT
            if bar_hi >= stop_px:
                exit_px = stop_px
                exit_reason = "STOP"
                exit_bar = bar
                break
            if bar_lo <= target_px:
                exit_px = target_px
                exit_reason = "TARGET"
                exit_bar = bar
                break

    if exit_reason is None:
        # Day ran out without 14:30 hit (e.g. minute data truncated
        # mid-session) — fall back to the last close.
        last = df.iloc[-1]
        exit_px = float(last["close"])
        exit_reason = "EOD"
        exit_bar = last

    direction = 1 if side == "LONG" else -1
    signed_return = (exit_px - entry_px) / entry_px * direction
    pnl_gross = signed_return * notional_inr
    pnl_net = apply_to_pnl(pnl_gross, notional_inr, side, slippage_bps)

    return {
        "entry_time": entry_bar["date"].strftime("%Y-%m-%d %H:%M:%S"),
        "entry_px": entry_px,
        "exit_time": exit_bar["date"].strftime("%Y-%m-%d %H:%M:%S"),
        "exit_px": float(exit_px),
        "exit_reason": exit_reason,
        "side": side,
        "notional_inr": float(notional_inr),
        "pnl_gross_inr": float(pnl_gross),
        "pnl_net_inr": float(pnl_net),
    }


def run_simulation(
    signals: pd.DataFrame,
    minute_bars_loader,
    notional_inr: float = 50_000,
    slippage_bps: float = 5.0,
    exit_time: str = "14:30:00",
    top_n: int | None = 5,
) -> pd.DataFrame:
    """Run the intraday simulator over a stream of OPPORTUNITY signals.

    Args:
        signals: DataFrame with columns ``{date, signal_time, symbol,
            side, stop_pct, target_pct, z_score}``.
        minute_bars_loader: Callable ``(symbol, date) -> DataFrame`` of
            1-min bars for that symbol on that date. May raise; the
            simulator logs and skips on exception or empty result.
        notional_inr: Per-trade notional (INR).
        slippage_bps: Round-trip slippage assumption in basis points.
        exit_time: Mechanical exit time of day (``HH:MM:SS``).
        top_n: If set, keep only the top-N signals per ``date`` ranked by
            ``abs(z_score)`` (descending). Ties are broken
            deterministically by ``symbol``.

    Returns:
        Trade ledger DataFrame with columns in the canonical order:
        ``entry_time, exit_time, symbol, side, entry_px, exit_px,
        exit_reason, notional_inr, pnl_gross_inr, pnl_net_inr,
        signal_time, z_score``. Empty DataFrame (with the canonical
        columns) is returned when no trades result.
    """
    df = signals.copy()
    if top_n is not None:
        df["_abs_z"] = df["z_score"].abs()
        # Sort by date asc, abs_z desc, symbol asc — deterministic tie-break.
        df = df.sort_values(
            ["date", "_abs_z", "symbol"],
            ascending=[True, False, True],
        )
        df = df.groupby("date", sort=False).head(top_n).drop(columns="_abs_z")

    rows: list[dict] = []
    for _, sig in df.iterrows():
        try:
            bars = minute_bars_loader(sig["symbol"], sig["date"])
        except Exception as exc:
            log.warning(
                "minute bars unavailable: %s %s — %s",
                sig["symbol"], sig["date"], exc,
            )
            continue
        if bars is None or bars.empty:
            continue

        trade = simulate_trade(
            bars=bars,
            signal_time=sig["signal_time"],
            side=sig["side"],
            stop_pct=float(sig["stop_pct"]),
            target_pct=float(sig["target_pct"]),
            notional_inr=notional_inr,
            slippage_bps=slippage_bps,
            exit_time=exit_time,
        )
        if trade is None:
            continue

        trade["symbol"] = sig["symbol"]
        trade["signal_time"] = sig["signal_time"]
        trade["z_score"] = float(sig["z_score"])
        rows.append(trade)

    if not rows:
        return pd.DataFrame(columns=_LEDGER_COLUMNS)
    return pd.DataFrame(rows, columns=_LEDGER_COLUMNS)
