"""Real volume_history aggregator for intraday_v1 framework, feature 3 (``volume_z``).

Reads ONLY persisted 1-min OHLCV parquets at
``pipeline/data/research/h_2026_04_29_intraday_v1/cache_1min/<SYM>.parquet``
and emits per-symbol ``volume_history_<SYM>.parquet`` files containing
the 20-day rolling mean and population std of intraday cumulative-from-09:15
volume, indexed by ``minute_of_day_idx`` (0 = 09:15:00 ... 374 = 15:29:00).

Hard contract (per ``feedback_no_hallucination_mandate.md``):

- If a symbol's cache parquet is missing or empty, no file is written and
  the runtime SKIPs that instrument.
- If the cache has fewer than ``lookback_days`` distinct prior trading
  days (strict PIT — ``eval_date`` itself is excluded), no file is written.
- No defaults, no extrapolation, no zero-fallbacks. Real data or no data.

Wired into ``runner.loader_refresh()`` so the 04:30 IST nightly job
produces fresh ``volume_history_<sym>.parquet`` after refreshing the
1-min cache and the PCR snapshots.

This module replaces the synthetic stub in ``runner._compute_signals_at``
that previously hard-coded ``mean_cum_volume_20d = [1000*(i+1)]`` and
``std = 200`` — fake numbers that fed feature 3 in production.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd

PIPELINE_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CACHE_DIR = (
    PIPELINE_ROOT / "data" / "research" / "h_2026_04_29_intraday_v1" / "cache_1min"
)
DEFAULT_OUTPUT_DIR = (
    PIPELINE_ROOT / "data" / "research" / "h_2026_04_29_intraday_v1" / "volume_history"
)
IST = timezone(timedelta(hours=5, minutes=30))

# Trading session length in minutes: 09:15:00 ... 15:29:00 inclusive = 375 minutes.
SESSION_MINUTES = 375

log = logging.getLogger("intraday_v1.volume_aggregator")


class VolumeAggregatorError(RuntimeError):
    """Raised when input cache is missing or insufficient for aggregation."""


def _minute_of_day_idx(ts: pd.Series) -> pd.Series:
    """Compute integer offset from 09:15 IST for each timestamp.

    0 = 09:15:00, 1 = 09:16:00, ..., 374 = 15:29:00.
    """
    return (ts.dt.hour - 9) * 60 + (ts.dt.minute - 15)


def build_volume_history(
    symbol: str,
    cache_dir: Path,
    eval_date: date,
    lookback_days: int = 20,
) -> pd.DataFrame:
    """Aggregate per-(minute_of_day) cumulative volume mean+std over prior 20 trading days.

    Parameters
    ----------
    symbol
        Instrument symbol (e.g. ``"RELIANCE"``). The cache parquet is
        ``cache_dir / f"{symbol}.parquet"``.
    cache_dir
        Directory containing per-symbol 1-min OHLCV parquets.
    eval_date
        Runtime date — strictly excluded from the aggregation (PIT-correct).
        Only bars with ``timestamp.date() < eval_date`` contribute.
    lookback_days
        Number of distinct prior trading days required (default 20).

    Returns
    -------
    pd.DataFrame
        Columns: ``minute_of_day_idx`` (0..374), ``mean_cum_volume_20d``,
        ``std_cum_volume_20d`` (population std, ``ddof=0``). 375 rows.

    Raises
    ------
    VolumeAggregatorError
        If the cache file is missing, empty, or has fewer than
        ``lookback_days`` distinct prior trading days.
    """
    cache_path = cache_dir / f"{symbol}.parquet"
    if not cache_path.exists():
        raise VolumeAggregatorError(f"no cache for {symbol}")
    df = pd.read_parquet(cache_path)
    if df.empty:
        raise VolumeAggregatorError(f"empty cache for {symbol}")

    # Strict PIT filter — drop eval_date itself and anything later.
    ts = df["timestamp"]
    df = df.assign(_trading_date=ts.dt.date)
    df = df[df["_trading_date"] < eval_date]
    if df.empty:
        raise VolumeAggregatorError(
            f"insufficient history for {symbol}: 0/{lookback_days}"
        )

    # Take the most recent `lookback_days` distinct trading dates.
    distinct_dates = sorted(df["_trading_date"].unique())
    if len(distinct_dates) < lookback_days:
        raise VolumeAggregatorError(
            f"insufficient history for {symbol}: {len(distinct_dates)}/{lookback_days}"
        )
    recent_dates = distinct_dates[-lookback_days:]
    df = df[df["_trading_date"].isin(recent_dates)].copy()

    # Per-day cumulative volume from 09:15.
    df = df.sort_values(["_trading_date", "timestamp"]).reset_index(drop=True)
    df["minute_of_day_idx"] = _minute_of_day_idx(df["timestamp"]).astype(int)
    df["cumulative_volume"] = (
        df.groupby("_trading_date")["volume"].cumsum().astype(float)
    )

    # Aggregate across days, per minute-of-day.
    grouped = df.groupby("minute_of_day_idx")["cumulative_volume"]
    agg = pd.DataFrame({
        "mean_cum_volume_20d": grouped.mean(),
        "std_cum_volume_20d": grouped.std(ddof=0),
    }).reset_index()

    # Reindex to the full 0..374 grid; rows absent in cache become NaN.
    full_idx = pd.DataFrame({"minute_of_day_idx": list(range(SESSION_MINUTES))})
    out = full_idx.merge(agg, on="minute_of_day_idx", how="left")
    return out[["minute_of_day_idx", "mean_cum_volume_20d", "std_cum_volume_20d"]]


def produce_all(
    cache_dir: Path,
    output_dir: Path,
    eval_date: date,
    lookback_days: int = 20,
) -> Dict:
    """Iterate every ``<SYM>.parquet`` in ``cache_dir`` and emit volume_history files.

    On per-symbol failure (missing file, insufficient history, empty cache),
    record the reason and continue. Never raises globally.

    Returns
    -------
    dict
        ``{"date", "lookback_days", "written", "skipped"}`` where
        ``skipped`` is a list of ``[symbol, reason]`` pairs.
    """
    summary: Dict = {
        "date": eval_date.isoformat(),
        "lookback_days": lookback_days,
        "written": 0,
        "skipped": [],
    }
    if not cache_dir.exists():
        summary["skipped"].append(["_GLOBAL_", f"cache_dir missing: {cache_dir}"])
        return summary

    output_dir.mkdir(parents=True, exist_ok=True)

    parquets = sorted(p for p in cache_dir.iterdir() if p.suffix == ".parquet")
    written = 0
    skipped: List[Tuple[str, str]] = []
    for p in parquets:
        sym = p.stem
        try:
            hist = build_volume_history(sym, cache_dir, eval_date, lookback_days)
        except VolumeAggregatorError as e:
            skipped.append((sym, str(e)))
            continue
        out_path = output_dir / f"volume_history_{sym}.parquet"
        hist.to_parquet(out_path, index=False)
        written += 1

    summary["written"] = written
    summary["skipped"] = [list(t) for t in skipped]
    log.info(
        f"volume_aggregator: wrote {written} files to {output_dir}, "
        f"skipped {len(skipped)} (eval_date={eval_date}, lookback={lookback_days})"
    )
    return summary


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    today = datetime.now(IST).date()
    result = produce_all(DEFAULT_CACHE_DIR, DEFAULT_OUTPUT_DIR, today)
    print(json.dumps(result, indent=2, default=str))
