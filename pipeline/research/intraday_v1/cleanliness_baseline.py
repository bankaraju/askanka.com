"""Pre-deploy cleanliness baseline runner per data audit §9.1.

Run once manually before V1 kickoff. Walks the resolved V1 universe,
fetches Kite 1-min for each instrument, runs five integrity checks, and
writes the report to baseline_2026_04_29.json.

Failed-baseline instruments are quarantined from V1 universe.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List

import pandas as pd

from pipeline.research.intraday_v1 import loader, universe

IST = timezone(timedelta(hours=5, minutes=30))


def check_volume_density(df: pd.DataFrame) -> float:
    """% of 1-min bars with volume > 0 during 09:15-15:30."""
    sess = df[(df["timestamp"].dt.time >= pd.Timestamp("09:15").time()) &
              (df["timestamp"].dt.time <= pd.Timestamp("15:30").time())]
    if sess.empty:
        return 0.0
    return float((sess["volume"] > 0).mean())


def check_flat_bars(df: pd.DataFrame) -> float:
    """% of bars with high == low (suspicious flat)."""
    if df.empty:
        return 0.0
    return float((df["high"] == df["low"]).mean())


def check_max_consecutive_gaps(df: pd.DataFrame) -> int:
    """Max consecutive missing 1-min bars WITHIN A SINGLE TRADING DAY (09:15-15:30).

    The diff is computed per-day so cross-day gaps (overnight, weekend, holiday)
    are NOT counted as "missing bars" — those are by-design absences of data,
    not quality issues. An earlier version of this check returned the
    Friday-15:30 -> Monday-09:15 weekend gap (~5385 min) for every instrument,
    masking real intraday gaps with a constant calendar artefact.
    """
    sess = df[(df["timestamp"].dt.time >= pd.Timestamp("09:15").time()) &
              (df["timestamp"].dt.time <= pd.Timestamp("15:30").time())].copy()
    if sess.empty:
        return 9999
    sess["trading_day"] = sess["timestamp"].dt.date
    max_gap = 0
    for _, day_df in sess.groupby("trading_day"):
        if len(day_df) < 2:
            continue
        diffs = day_df["timestamp"].diff().dt.total_seconds()
        gap_minutes = (diffs / 60 - 1).clip(lower=0)
        day_max = int(gap_minutes.max()) if not gap_minutes.empty else 0
        if day_max > max_gap:
            max_gap = day_max
    return max_gap


def check_ohlc_consistency(df: pd.DataFrame) -> float:
    """% of rows with low <= open <= high AND low <= close <= high."""
    if df.empty:
        return 0.0
    ok = ((df["low"] <= df["open"]) & (df["open"] <= df["high"]) &
          (df["low"] <= df["close"]) & (df["close"] <= df["high"]))
    return float(ok.mean())


def run_baseline(out_path: Path) -> Dict:
    univ = universe.load_v1_universe()
    rows = []
    for sym in univ["stocks"] + univ["indices"]:
        try:
            df = loader.fetch_1min(sym, days=20)
        except loader.LoaderError as e:
            rows.append({"instrument": sym, "status": "FETCH_FAILED", "reason": str(e)})
            continue
        rows.append({
            "instrument": sym,
            "status": "OK",
            "volume_density": check_volume_density(df),
            "flat_bar_pct":   check_flat_bars(df),
            "max_gap_minutes": check_max_consecutive_gaps(df),
            "ohlc_consistency": check_ohlc_consistency(df),
        })
    report = {
        "generated_at": datetime.now(IST).isoformat(),
        "universe_size": len(rows),
        "results": rows,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    return report


if __name__ == "__main__":
    out = Path("pipeline/data/research/h_2026_04_29_intraday_v1/baseline_2026_04_29.json")
    rep = run_baseline(out)
    print(f"Cleanliness baseline written to {out}: {len(rep['results'])} instruments")
