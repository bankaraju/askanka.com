"""Historical ETF regime backfill.

Applies the current optimal weights (from etf_optimal_weights.json) to
historical ETF returns to label every historical date with a regime zone.

Delegates to pipeline.autoresearch.etf_reoptimize._signal_to_zone (the
canonical zone-mapping function used by the live engine), so the backfill
and the live engine cannot drift.

Returns are scaled to PERCENT-space to match the live engine's signal scale
(see etf_daily_signal.py:203).
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import pandas as pd

from pipeline.autoresearch.etf_reoptimize import _signal_to_zone

log = logging.getLogger(__name__)

VALID_ZONES = {"EUPHORIA", "RISK-ON", "NEUTRAL", "CAUTION", "RISK-OFF"}


def _daily_return_at(bars: pd.DataFrame, date_str: str) -> float | None:
    """Close-to-close fractional return ending on date_str (or most recent
    trading day on or before date_str). Returns None if fewer than two valid
    bars are available, or if either close is NaN/zero.
    """
    target = pd.Timestamp(date_str)
    df = bars.sort_values("date").reset_index(drop=True)
    df = df[df["date"] <= target]
    if len(df) < 2:
        return None
    prev = df.iloc[-2]["close"]
    cur = df.iloc[-1]["close"]
    if pd.isna(prev) or pd.isna(cur) or prev == 0:
        return None
    return (cur - prev) / prev


def _compute_signal(
    date_str: str,
    weights: dict[str, float],
    etf_bars: dict[str, pd.DataFrame],
) -> float:
    """Sum of weight × percent-space return across the ETF basket."""
    signal = 0.0
    for sym, w in weights.items():
        bars = etf_bars.get(sym)
        if bars is None or bars.empty:
            log.warning("no bars for ETF %s on %s — skipping", sym, date_str)
            continue
        ret = _daily_return_at(bars, date_str)
        if ret is None:
            continue
        # Convert fractional → percent to match live engine's signal scale
        signal += w * ret * 100.0
    return signal


def compute_regime_for_date(
    date_str: str,
    weights_path: Path,
    etf_bars: dict[str, pd.DataFrame],
) -> str:
    """Compute the regime zone for a single historical date.

    Reads weights file on every call — for bulk use, prefer backfill_regime
    which parses the weights file once.
    """
    cfg = json.loads(Path(weights_path).read_text(encoding="utf-8"))
    weights = cfg.get("optimal_weights", {})
    if not weights:
        raise ValueError(f"weights file has no optimal_weights: {weights_path}")
    signal = _compute_signal(date_str, weights, etf_bars)
    return _signal_to_zone(signal)


def backfill_regime(
    dates: list[str],
    weights_path: Path,
    etf_bars: dict[str, pd.DataFrame],
    out_path: Path,
) -> dict[str, str]:
    """Compute regime for every date and write to out_path. Returns the dict.

    Parses weights file once. Output JSON has sorted keys for reproducibility.
    """
    cfg = json.loads(Path(weights_path).read_text(encoding="utf-8"))
    weights = cfg.get("optimal_weights", {})
    if not weights:
        raise ValueError(f"weights file has no optimal_weights: {weights_path}")
    result = {d: _signal_to_zone(_compute_signal(d, weights, etf_bars)) for d in dates}
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    log.info("regime backfill: %d dates written to %s", len(result), out_path)
    return result
