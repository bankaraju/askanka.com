"""Backtest + holdout orchestrator for H-2026-05-01-phase-c-mr-karpathy-v1.

Strategy-gate-tracked filename per pipeline/scripts/hooks/strategy_patterns.txt
(*_engine.py). Registered in docs/superpowers/hypothesis-registry.jsonl
under hypothesis_id H-2026-05-01-phase-c-mr-karpathy-v1.

Spec: docs/superpowers/specs/2026-05-01-phase-c-mr-karpathy-v1-design.md (sections 6-7)

The engine:
  1. Iterates the trading-day window provided by caller.
  2. For each (date, snap_t in 09:30..14:00 step 15min, ticker in frozen universe):
     - Build SnapContext from intraday cache + daily history + sector indices + news.
     - Compute z-score against the (ticker, regime) PIT profile.
     - Call mr_signal_generator.generate_signal(...).
     - On Signal: open at 5m bar close; track ATR(14)*2.0 stop; close at first of
       {stop hit, 14:30 IST mechanical, end-of-day}.
  3. First-touch dedup per (date, ticker).
  4. Emit per-trade rows + per-day summary.

This is the SKELETON. Full integration with the corp-action adjuster + intraday
cache is wired by ``holdout_runner.py`` for daily live operation and by
``karpathy_search.py`` for the in-sample grid search. Both consume this engine.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import HOLDOUT_OPEN, HOLDOUT_CLOSE, HYPOTHESIS_ID, MIN_HOLDOUT_N
from .mr_signal_generator import KarpathyCell, Signal


SNAP_GRID_IST: tuple[str, ...] = (
    "09:30:00", "09:45:00", "10:00:00", "10:15:00", "10:30:00", "10:45:00",
    "11:00:00", "11:15:00", "11:30:00", "11:45:00", "12:00:00", "12:15:00",
    "12:30:00", "12:45:00", "13:00:00", "13:15:00", "13:30:00", "13:45:00",
    "14:00:00",
)
TIME_STOP_IST: str = "14:30:00"
ATR_MULTIPLIER: float = 2.0
NOTIONAL_INR_PER_LEG: int = 50_000
COST_BPS_S0: float = 10.0      # 5 + 5
COST_BPS_S1: float = 30.0      # 15 + 15
COST_BPS_S2: float = 50.0      # 25 + 25


@dataclass
class Trade:
    """One closed mean-revert trade."""
    hypothesis_id: str
    date: str
    snap_t: str
    ticker: str
    sector: str | None
    side: str
    regime: str
    entry_px: float
    exit_px: float
    exit_t: str
    exit_reason: str               # "STOP" | "TIME_STOP_1430" | "EOD"
    z_score: float
    intraday_ret_pct: float
    pnl_bps_S0: float
    pnl_bps_S1: float
    pnl_bps_S2: float
    notional_inr: int = NOTIONAL_INR_PER_LEG
    feature_values: dict[str, float] = field(default_factory=dict)
    qualifier_score: float = 0.0


def _gross_bps_long(entry: float, exit_: float) -> float:
    if entry <= 0:
        return 0.0
    return (exit_ - entry) / entry * 10000.0


def _gross_bps(side: str, entry: float, exit_: float) -> float:
    g = _gross_bps_long(entry, exit_)
    return g if side == "LONG" else -g


def trade_from_close(
    sig: Signal,
    *,
    exit_px: float,
    exit_t: str,
    exit_reason: str,
) -> Trade:
    """Compose a Trade from an open Signal + a close-price + reason."""
    g = _gross_bps(sig.side, sig.snap_px, exit_px)
    return Trade(
        hypothesis_id=sig.hypothesis_id,
        date=sig.date,
        snap_t=sig.snap_t,
        ticker=sig.ticker,
        sector=sig.sector,
        side=sig.side,
        regime=sig.regime,
        entry_px=sig.snap_px,
        exit_px=exit_px,
        exit_t=exit_t,
        exit_reason=exit_reason,
        z_score=sig.z_score,
        intraday_ret_pct=sig.intraday_ret_pct,
        pnl_bps_S0=g - COST_BPS_S0,
        pnl_bps_S1=g - COST_BPS_S1,
        pnl_bps_S2=g - COST_BPS_S2,
        feature_values=dict(sig.feature_values),
        qualifier_score=sig.qualifier_score,
    )


def write_trades(trades: list[Trade], out_path: Path) -> None:
    """Write trades to JSONL — one row per trade."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as fp:
        for t in trades:
            fp.write(json.dumps(asdict(t), ensure_ascii=False) + "\n")


# ---- Verdict helpers (consumed by verdict_writer) ---------------------------

def summarize(trades: list[Trade], cost_grid: str = "S1") -> dict[str, float]:
    """Aggregate stats per spec section 9."""
    if not trades:
        return {"n": 0, "mean_bps": 0.0, "hit_pct": 0.0, "sharpe": 0.0}
    field_name = {"S0": "pnl_bps_S0", "S1": "pnl_bps_S1", "S2": "pnl_bps_S2"}[cost_grid]
    pnls = [getattr(t, field_name) for t in trades]
    n = len(pnls)
    mean = sum(pnls) / n
    var = sum((p - mean) ** 2 for p in pnls) / max(n - 1, 1)
    sd = var ** 0.5
    sharpe_per_trade = mean / sd if sd > 0 else 0.0
    annualised = sharpe_per_trade * (252 ** 0.5)
    hit = sum(1 for p in pnls if p > 0) / n * 100.0
    return {
        "n": n,
        "mean_bps": round(mean, 2),
        "hit_pct": round(hit, 2),
        "sharpe_annualized": round(annualised, 3),
        "cost_grid": cost_grid,
    }


def holdout_meta() -> dict[str, str | int]:
    """Constants for the verdict writer."""
    return {
        "hypothesis_id": HYPOTHESIS_ID,
        "holdout_open": HOLDOUT_OPEN,
        "holdout_close": HOLDOUT_CLOSE,
        "min_n": MIN_HOLDOUT_N,
    }


# ---- Cell load (delegates to the signal generator) -------------------------

def load_chosen_cell() -> KarpathyCell | None:
    """Read karpathy_chosen_cell.json from disk; return None if missing."""
    return KarpathyCell.load()
