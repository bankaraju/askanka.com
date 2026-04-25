"""Phase C signal roster for the mechanical replay.

Joins:
  - correlation_break_history.json (full OPPORTUNITY universe, both legacy and
    post-2026-04-23 LAG/OVERSHOOT/POSSIBLE labels)
  - closed_signals.json (phase_c category — marks rows as actual vs missed)

Filtered to:
  - rows in the (window_start, window_end) range
  - tickers in canonical_fno_research_v1 universe
  - actionable classifications (legacy OPPORTUNITY, post-relabel LAG,
    OVERSHOOT, POSSIBLE_OPPORTUNITY)
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from pipeline.autoresearch.mechanical_replay import canonical_loader, constants as C

logger = logging.getLogger(__name__)

ACTIONABLE_CLASSIFICATIONS = (
    "OPPORTUNITY_LAG",
    "OPPORTUNITY_OVERSHOOT",
    "POSSIBLE_OPPORTUNITY",
    "OPPORTUNITY",  # legacy label (pre-2026-04-23 split)
)


def _load_break_history(path: Path) -> pd.DataFrame:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not raw:
        return pd.DataFrame()
    df = pd.DataFrame(raw)
    df["date"] = pd.to_datetime(df["date"]).dt.normalize()
    return df


def _load_closed_phase_c(path: Path) -> pd.DataFrame:
    raw = json.loads(path.read_text(encoding="utf-8"))
    rows: list[dict] = []
    for s in raw:
        if s.get("category") != "phase_c":
            continue
        meta = s.get("_break_metadata") or {}
        ticker = meta.get("symbol")
        ts = s.get("open_timestamp")
        if not ticker or not ts:
            continue
        # Mixed tz formats in the live ledger — strip to naive.
        open_dt = pd.to_datetime(ts)
        if open_dt.tz is not None:
            open_dt = open_dt.tz_localize(None)
        fp = s.get("final_pnl") or {}
        side = "SHORT" if fp.get("short_legs") else ("LONG" if fp.get("long_legs") else None)
        rows.append({
            "signal_id": s.get("signal_id"),
            "ticker": ticker,
            "date": open_dt.normalize(),
            "actual_pnl_pct": fp.get("spread_pnl_pct"),
            "actual_open_time_ist": ts,
            "actual_close_time_ist": s.get("close_timestamp"),
            "actual_side": side,
        })
    return pd.DataFrame(rows)


def _derive_side(row: pd.Series) -> Optional[str]:
    """Trade rec wins; fall back to direction_tested for legacy rows."""
    rec = row.get("trade_rec")
    if rec in ("LONG", "SHORT"):
        return rec
    return None


def build_phase_c_roster(
    *,
    loader: canonical_loader.CanonicalLoader,
    window_start: pd.Timestamp,
    window_end: pd.Timestamp,
    break_history_path: Path = C.BREAK_HISTORY_JSON,
    closed_path: Path = C.CLOSED_SIGNALS_JSON,
) -> pd.DataFrame:
    """Return the Phase C signal roster for the window."""
    hist = _load_break_history(break_history_path)
    if hist.empty:
        return pd.DataFrame()

    in_window = hist["date"].between(window_start.normalize(), window_end.normalize())
    is_actionable = hist["classification"].isin(ACTIONABLE_CLASSIFICATIONS)
    hist = hist[in_window & is_actionable].copy()

    # Filter to canonical universe with point-in-time check.
    universe = loader.universe
    hist = hist[hist["symbol"].isin(universe)].copy()
    pit_mask = hist.apply(
        lambda r: loader.is_in_universe(r["symbol"], r["date"].date()),
        axis=1,
    )
    hist = hist[pit_mask].copy()

    if hist.empty:
        return pd.DataFrame()

    # Collapse to one row per (ticker, date, classification), keeping max |z|.
    hist["abs_z"] = hist.get("z_score", pd.Series(np.nan, index=hist.index)).abs()
    hist = (
        hist.sort_values("abs_z", ascending=False, na_position="last")
            .drop_duplicates(subset=["symbol", "date", "classification"])
            .rename(columns={"symbol": "ticker"})
            .drop(columns=["abs_z"])
    )

    closed = _load_closed_phase_c(closed_path)
    if not closed.empty:
        closed = closed[closed["date"].between(window_start.normalize(), window_end.normalize())]

    if closed.empty:
        merged = hist.assign(
            source="missed",
            actual_pnl_pct=np.nan,
            actual_open_time_ist=pd.NaT,
            actual_close_time_ist=pd.NaT,
            actual_side=None,
            signal_id=lambda df: "MISSED-" + df["date"].dt.strftime("%Y-%m-%d") + "-" + df["ticker"] + "-" + df["classification"],
        )
    else:
        merged = hist.merge(
            closed,
            on=["ticker", "date"],
            how="left",
            suffixes=("", "_closed"),
        )
        is_actual = merged["actual_pnl_pct"].notna()
        merged["source"] = np.where(is_actual, "actual", "missed")
        synth_id = (
            "MISSED-" + merged["date"].dt.strftime("%Y-%m-%d")
            + "-" + merged["ticker"] + "-" + merged["classification"]
        )
        merged["signal_id"] = merged["signal_id"].where(is_actual, synth_id)

    # Side: trade_rec wins; fall back to actual_side from closed ledger.
    merged["side"] = merged.apply(_derive_side, axis=1)
    fallback_side = merged.get("actual_side")
    if fallback_side is not None:
        merged["side"] = merged["side"].fillna(fallback_side)

    return merged.reset_index(drop=True)
