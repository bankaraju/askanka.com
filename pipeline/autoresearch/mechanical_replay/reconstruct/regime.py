"""Deterministic regime regeneration for the v2 mechanical replay.

For each trading day D in the window, this module re-runs the live ETF
regime engine's signal formula against canonical ETF parquet bars, then
maps the signal to a zone using the FROZEN quintile cutpoints from
`pipeline/data/regime_cutpoints.json`.

The signal formula and cutpoint mapping are imported from the
backtest/build sources of truth so behaviour cannot drift:

- Signal: `pipeline.research.phase_c_backtest.regime._compute_signal`
- Zone mapping: mirrors `build_regime_history._signal_to_zone_quantile`

Frozen-input bias: the weights file is the CURRENT optimal weights, not
the weights as-of D. The v1 spec's §14 contamination map records this as
the dominant uncertainty source. A future v3 study would be to back-fill a
weekly-snapshot weight log and re-run.

This module does NOT touch `regime_history.csv` — its output should be
indistinguishable from the live file (≥98% zone agreement per §10).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

import pandas as pd

from pipeline.autoresearch.mechanical_replay import constants as C
from pipeline.research.phase_c_backtest.regime import _compute_signal as _phase_c_compute_signal


_DEFAULT_WEIGHTS_PATH = C._REPO / "pipeline" / "autoresearch" / "etf_optimal_weights.json"
_DEFAULT_CUTPOINTS_PATH = C._REPO / "pipeline" / "data" / "regime_cutpoints.json"
_DEFAULT_ETF_DIR = C._REPO / "pipeline" / "data" / "research" / "phase_c" / "daily_bars"

_CUTPOINT_KEYS = ("q20", "q40", "q60", "q80")


def compute_signal(
    date_str: str,
    weights: dict[str, float],
    etf_bars: dict[str, pd.DataFrame],
) -> float:
    """Sum-of-weighted-percent-returns. Thin wrapper over the phase-C-backtest
    canonical implementation so we cannot drift from the historical
    backfill that produced regime_history.csv.
    """
    return _phase_c_compute_signal(date_str, weights, etf_bars)


def signal_to_zone(signal: float, cutpoints: dict[str, float]) -> str:
    """Quintile-bucket a scalar signal using frozen cutpoints.

    Mirrors `build_regime_history._signal_to_zone_quantile` exactly:
      - signal < q20  → RISK-OFF
      - q20 ≤ signal < q40 → CAUTION
      - q40 ≤ signal < q60 → NEUTRAL
      - q60 ≤ signal < q80 → RISK-ON
      - signal ≥ q80 → EUPHORIA
    """
    for k in _CUTPOINT_KEYS:
        if k not in cutpoints:
            raise ValueError(f"cutpoints missing required key: {k}")
    if signal < cutpoints["q20"]:
        return "RISK-OFF"
    if signal < cutpoints["q40"]:
        return "CAUTION"
    if signal < cutpoints["q60"]:
        return "NEUTRAL"
    if signal < cutpoints["q80"]:
        return "RISK-ON"
    return "EUPHORIA"


def load_canonical_inputs(
    *,
    weights_path: Path = _DEFAULT_WEIGHTS_PATH,
    cutpoints_path: Path = _DEFAULT_CUTPOINTS_PATH,
) -> tuple[dict[str, float], dict[str, float]]:
    """Read frozen weights + cutpoints from disk."""
    weights_payload = json.loads(Path(weights_path).read_text(encoding="utf-8"))
    weights = weights_payload.get("optimal_weights")
    if not weights:
        raise ValueError(f"weights file has no 'optimal_weights' key: {weights_path}")
    cutpoints = json.loads(Path(cutpoints_path).read_text(encoding="utf-8"))
    cutpoints = {k: float(cutpoints[k]) for k in _CUTPOINT_KEYS if k in cutpoints}
    return weights, cutpoints


def load_canonical_etf_bars(
    *,
    weights: dict[str, float],
    etf_dir: Path = _DEFAULT_ETF_DIR,
) -> dict[str, pd.DataFrame]:
    """Load each ETF's parquet from the canonical phase_c daily_bars directory.

    Skips ETFs whose parquet is missing (logged in returned dict by absence).
    Each frame is normalised to columns [date, close] sorted ascending.
    """
    bars: dict[str, pd.DataFrame] = {}
    for sym in weights:
        path = Path(etf_dir) / f"{sym}.parquet"
        if not path.exists():
            continue
        try:
            df = pd.read_parquet(path)
        except Exception:
            continue
        if "date" not in df.columns or "close" not in df.columns:
            continue
        df = df.copy()
        df["date"] = pd.to_datetime(df["date"]).dt.normalize()
        df = df.sort_values("date").reset_index(drop=True)
        bars[sym] = df[["date", "close"]]
    return bars


def regenerate(
    *,
    window_start: pd.Timestamp,
    window_end: pd.Timestamp,
    weights: dict[str, float],
    cutpoints: dict[str, float],
    etf_bars: dict[str, pd.DataFrame],
) -> pd.DataFrame:
    """Emit one row per business day in [window_start, window_end].

    Date set is the union of trading days appearing in any provided ETF
    bars within the window — same convention as build_regime_history.
    """
    window_start = pd.Timestamp(window_start).normalize()
    window_end = pd.Timestamp(window_end).normalize()

    all_dates: set[pd.Timestamp] = set()
    for df in etf_bars.values():
        in_window = df[(df["date"] >= window_start) & (df["date"] <= window_end)]
        all_dates.update(pd.to_datetime(in_window["date"]).tolist())

    rows = []
    for d in sorted(all_dates):
        sig = compute_signal(d.strftime("%Y-%m-%d"), weights, etf_bars)
        zone = signal_to_zone(sig, cutpoints)
        rows.append({"date": d, "regime_zone": zone, "signal_score": round(sig, 4)})

    if not rows:
        return pd.DataFrame(columns=["date", "regime_zone", "signal_score"])
    return pd.DataFrame(rows)


def regenerate_for_dates(
    *,
    dates: Iterable[pd.Timestamp],
    weights: dict[str, float],
    cutpoints: dict[str, float],
    etf_bars: dict[str, pd.DataFrame],
) -> pd.DataFrame:
    """Variant: regenerate for an explicit list of dates instead of a window."""
    rows = []
    for d in sorted({pd.Timestamp(x).normalize() for x in dates}):
        sig = compute_signal(d.strftime("%Y-%m-%d"), weights, etf_bars)
        zone = signal_to_zone(sig, cutpoints)
        rows.append({"date": d, "regime_zone": zone, "signal_score": round(sig, 4)})
    if not rows:
        return pd.DataFrame(columns=["date", "regime_zone", "signal_score"])
    return pd.DataFrame(rows)
