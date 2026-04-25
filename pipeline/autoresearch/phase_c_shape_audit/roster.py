"""Build the SP1 trade-equivalent roster.

Joins:
  - closed_signals.json (actual-trade rows)
  - correlation_break_history.json (full OPPORTUNITY universe)
  - regime_history.csv (canonical daily regime tag)

Per spec §4. Output is a pandas DataFrame with one row per
(ticker, date, classification) and a `source` tag in {actual, missed}.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from pipeline.autoresearch.phase_c_shape_audit import constants as C

ACTIONABLE_CLASSIFICATIONS = (
    "OPPORTUNITY_LAG",
    "OPPORTUNITY_OVERSHOOT",
    "POSSIBLE_OPPORTUNITY",
)


def _load_history(path: Path) -> pd.DataFrame:
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
        open_dt = pd.to_datetime(ts)
        side = "SHORT" if s.get("short_legs") else ("LONG" if s.get("long_legs") else None)
        final_pnl = s.get("final_pnl") or {}
        rows.append({
            "signal_id": s.get("signal_id"),
            "ticker": ticker,
            "date": open_dt.normalize(),
            "classification": meta.get("classification"),
            "actual_pnl_pct": final_pnl.get("spread_pnl_pct"),
            "actual_open_time_ist": ts,
            "actual_close_time_ist": s.get("close_timestamp"),
            "actual_side": side,
        })
    return pd.DataFrame(rows)


def _load_regime(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["date"] = pd.to_datetime(df["date"]).dt.normalize()
    return df[["date", "regime_zone"]]


def build_roster(
    *,
    history_path: Path = C.BREAK_HISTORY_JSON,
    closed_path: Path = C.CLOSED_SIGNALS_JSON,
    regime_path: Path = C.REGIME_HISTORY_CSV,
    window_start: pd.Timestamp,
    window_end: pd.Timestamp,
) -> pd.DataFrame:
    """Return roster DataFrame for the (window_start, window_end) inclusive range."""
    hist = _load_history(history_path)
    if hist.empty:
        return pd.DataFrame()

    in_window = hist["date"].between(window_start.normalize(), window_end.normalize())
    is_actionable = hist["classification"].isin(ACTIONABLE_CLASSIFICATIONS)
    hist = hist[in_window & is_actionable].copy()

    # Collapse to one row per (ticker, date, classification) keeping max |z_score|
    hist["abs_z"] = hist["z_score"].abs()
    hist = (
        hist.sort_values("abs_z", ascending=False)
            .drop_duplicates(subset=["symbol", "date", "classification"])
            .rename(columns={"symbol": "ticker"})
            .drop(columns=["abs_z"])
    )

    closed = _load_closed_phase_c(closed_path)
    if not closed.empty:
        closed = closed[closed["date"].between(window_start.normalize(), window_end.normalize())]

    regime = _load_regime(regime_path)
    hist = hist.merge(regime, on="date", how="left")

    # Join closed onto roster on (ticker, date, classification).
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
            on=["ticker", "date", "classification"],
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

    # Promote regime_history regime over per-row history regime if mismatch
    merged["regime_history_value"] = merged["regime_zone"]
    merged["regime"] = merged["regime_zone"].fillna(merged.get("regime"))

    return merged.reset_index(drop=True)
