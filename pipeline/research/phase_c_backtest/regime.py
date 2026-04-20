"""Historical ETF regime backfill.

Applies the current optimal weights (from etf_optimal_weights.json) to
historical ETF returns to label every historical date with a regime zone.

Mirrors the threshold ladder in pipeline/autoresearch/etf_daily_signal.py.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import pandas as pd

log = logging.getLogger(__name__)

# Default threshold ladder (override via weights file's "thresholds" key)
DEFAULT_THRESHOLDS = {
    "EUPHORIA":  0.015,
    "RISK-ON":   0.005,
    "NEUTRAL":   -0.005,
    "CAUTION":   -0.015,
    "RISK-OFF":  -1.0,
}
# Order matters: highest signal first, fall through to next.
ZONE_ORDER = ["EUPHORIA", "RISK-ON", "NEUTRAL", "CAUTION", "RISK-OFF"]


def _zone_from_signal(signal: float, thresholds: dict[str, float]) -> str:
    for zone in ZONE_ORDER:
        if signal >= thresholds[zone]:
            return zone
    return "RISK-OFF"


def _daily_return_at(bars: pd.DataFrame, date_str: str) -> float | None:
    """Return the close-to-close % return ending on date_str (or nearest prior bar).

    Financial markets are closed on weekends/holidays; when the target date has
    no bar we fall back to the most recent prior bar to compute the last
    available daily return.  Returns None if fewer than two bars exist at or
    before the target date.
    """
    target = pd.Timestamp(date_str)
    df = bars.sort_values("date").reset_index(drop=True)
    # Keep only bars on or before the target date
    df = df[df["date"] <= target].reset_index(drop=True)
    if len(df) < 2:
        return None
    prev = df.loc[len(df) - 2, "close"]
    cur = df.loc[len(df) - 1, "close"]
    if prev == 0:
        return None
    return (cur - prev) / prev


def compute_regime_for_date(
    date_str: str,
    weights_path: Path,
    etf_bars: dict[str, pd.DataFrame],
) -> str:
    """Compute the regime zone for a single historical date."""
    cfg = json.loads(Path(weights_path).read_text(encoding="utf-8"))
    weights: dict = cfg.get("optimal_weights", {})
    thresholds: dict = cfg.get("thresholds", DEFAULT_THRESHOLDS)
    if not weights:
        raise ValueError(f"weights file has no optimal_weights: {weights_path}")
    signal = 0.0
    for sym, w in weights.items():
        bars = etf_bars.get(sym)
        if bars is None or bars.empty:
            log.warning("no bars for ETF %s on %s — skipping", sym, date_str)
            continue
        ret = _daily_return_at(bars, date_str)
        if ret is None:
            continue
        signal += w * ret
    return _zone_from_signal(signal, thresholds)


def backfill_regime(
    dates: list[str],
    weights_path: Path,
    etf_bars: dict[str, pd.DataFrame],
    out_path: Path,
) -> dict[str, str]:
    """Compute regime for every date and write to out_path. Returns the dict."""
    result = {d: compute_regime_for_date(d, weights_path, etf_bars) for d in dates}
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text(json.dumps(result, indent=2), encoding="utf-8")
    log.info("regime backfill: %d dates written to %s", len(result), out_path)
    return result
