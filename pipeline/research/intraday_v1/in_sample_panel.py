"""In-sample panel assembler for the intraday-v1 kickoff weight fit.

Reads ONLY persisted artifacts (1-min cache parquets, OI archive JSONs, daily
F&O history) and emits a tidy DataFrame ready for Karpathy random search.

Hard contract (per ``feedback_no_hallucination_mandate.md``):
- Every ``(date, instrument)`` row must trace to real bars + a real PCR
  snapshot pair + real volume history.
- NaN feature values cause the row to be dropped, NOT imputed.
- Missing entry/exit prices (e.g., trading halt) cause the row to be dropped.
- No synthetic feature values, no fabricated labels, no defaults.

Usage::

    from datetime import date
    from pipeline.research.intraday_v1 import in_sample_panel
    df = in_sample_panel.assemble_for_pool("stocks")
    # df columns: date, instrument, f1..f6, next_return_pct
    fit = karpathy_fit.run(df, seed=42, n_iters=2000, rolling_window_days=N)

The ``assemble_for_pool`` wrapper resolves the V1 universe and the candidate
in-sample dates from the cache file contents, then calls ``assemble_panel``.
"""
from __future__ import annotations

import json
import logging
import math
import tempfile
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

from pipeline.research.intraday_v1 import features, pcr_producer, universe, volume_aggregator

PIPELINE_ROOT = Path(__file__).resolve().parents[2]
CACHE_DIR = PIPELINE_ROOT / "data" / "research" / "h_2026_04_29_intraday_v1" / "cache_1min"
OI_ARCHIVE_DIR = PIPELINE_ROOT / "data" / "oi_history_stocks"
IST = timezone(timedelta(hours=5, minutes=30))

log = logging.getLogger("intraday_v1.in_sample_panel")

# Stock symbol -> Kite-naming sector index (matches actual on-disk cache files,
# which use the space-separated Kite convention "NIFTY ENERGY", not "NIFTYENERGY").
# Mirrors runner.SECTOR_INDEX_MAP semantically; the value differs because the
# in-sample panel reads the cache directly, where filenames use the Kite form.
SECTOR_INDEX_MAP_KITE: Dict[str, str] = {
    "HDFCBANK": "NIFTY BANK", "ICICIBANK": "NIFTY BANK", "AXISBANK": "NIFTY BANK",
    "KOTAKBANK": "NIFTY BANK", "SBIN": "NIFTY BANK", "INDUSINDBK": "NIFTY BANK",
    "INFY": "NIFTY IT", "TCS": "NIFTY IT", "HCLTECH": "NIFTY IT",
    "TECHM": "NIFTY IT", "WIPRO": "NIFTY IT",
    "RELIANCE": "NIFTY ENERGY", "ONGC": "NIFTY ENERGY", "BPCL": "NIFTY ENERGY",
    "GAIL": "NIFTY ENERGY", "COALINDIA": "NIFTY ENERGY", "NTPC": "NIFTY ENERGY",
    "POWERGRID": "NIFTY ENERGY",
    "SUNPHARMA": "NIFTY PHARMA", "CIPLA": "NIFTY PHARMA", "DRREDDY": "NIFTY PHARMA",
    "DIVISLAB": "NIFTY PHARMA", "APOLLOHOSP": "NIFTY PHARMA",
    "MARUTI": "NIFTY AUTO", "TMPV": "NIFTY AUTO", "BAJAJ-AUTO": "NIFTY AUTO",
    "EICHERMOT": "NIFTY AUTO", "HEROMOTOCO": "NIFTY AUTO", "M&M": "NIFTY AUTO",
    "HINDUNILVR": "NIFTY FMCG", "ITC": "NIFTY FMCG", "NESTLEIND": "NIFTY FMCG",
    "BRITANNIA": "NIFTY FMCG", "TATACONSUM": "NIFTY FMCG",
    "TATASTEEL": "NIFTY METAL", "JSWSTEEL": "NIFTY METAL", "HINDALCO": "NIFTY METAL",
    "BAJFINANCE": "NIFTY FIN SERVICE", "BAJAJFINSV": "NIFTY FIN SERVICE",
    "HDFCLIFE": "NIFTY FIN SERVICE", "SBILIFE": "NIFTY FIN SERVICE",
    "JIOFIN": "NIFTY FIN SERVICE", "SHRIRAMFIN": "NIFTY FIN SERVICE",
    # Stocks not mapped fall back to NIFTY 50 (broad market) for RS computation.
}
DEFAULT_SECTOR_FALLBACK = "NIFTY 50"

EVAL_TIME = time(9, 30)
EXIT_TIME = time(14, 30)


def _list_cache_dates(cache_dir: Path, symbol: str) -> List[date]:
    """Return sorted list of distinct trading dates present in ``symbol``'s cache."""
    p = cache_dir / f"{symbol}.parquet"
    if not p.exists():
        return []
    df = pd.read_parquet(p, columns=["timestamp"])
    if df.empty:
        return []
    return sorted(df["timestamp"].dt.date.unique())


def _bar_at(df: pd.DataFrame, ts: datetime) -> Optional[pd.Series]:
    """Return the row with ``timestamp == ts``, or None if absent."""
    hits = df[df["timestamp"] == ts]
    if hits.empty:
        return None
    return hits.iloc[0]


def _resolve_pcr_for_date(
    eval_date: date, archive_dir: Path
) -> Optional[Tuple[Dict[str, Dict], Dict[str, Dict]]]:
    """Materialize per-date PCR snapshots in a temp dir, then load them in-memory.

    Returns ``(today_map, two_d_ago_map)`` where each is ``{symbol: pcr_blob}``,
    or ``None`` if anchors cannot be resolved (insufficient archives).
    """
    with tempfile.TemporaryDirectory() as td:
        out_dir = Path(td)
        summary = pcr_producer.produce_pcr_snapshots(
            eval_date=eval_date, output_dir=out_dir, archive_dir=archive_dir
        )
        if summary["symbols_written"] == 0:
            return None
        today_map: Dict[str, Dict] = {}
        two_d_map: Dict[str, Dict] = {}
        for f in out_dir.iterdir():
            if not f.is_file() or f.suffix != ".json":
                continue
            stem = f.stem  # e.g. "RELIANCE_today" or "RELIANCE_2d_ago"
            if stem.endswith("_today"):
                sym = stem[: -len("_today")]
                today_map[sym] = json.loads(f.read_text(encoding="utf-8"))
            elif stem.endswith("_2d_ago"):
                sym = stem[: -len("_2d_ago")]
                two_d_map[sym] = json.loads(f.read_text(encoding="utf-8"))
    return today_map, two_d_map


def _resolve_sector_symbol(instrument: str, pool: str) -> str:
    """Pick the sector reference for a (instrument, pool) pair.

    - stocks: per ``SECTOR_INDEX_MAP_KITE``, falling back to NIFTY 50.
    - indices: every index is benchmarked against NIFTY 50 (broad market).
      An index compared against itself yields rs_vs_sector == 0 every minute,
      which is informationless; benchmarking against NIFTY 50 captures the
      sector's relative strength vs the broad market and is the natural
      analogue of the stock-vs-sector spread.
    """
    if pool == "stocks":
        return SECTOR_INDEX_MAP_KITE.get(instrument, DEFAULT_SECTOR_FALLBACK)
    # indices pool
    if instrument == DEFAULT_SECTOR_FALLBACK:
        # NIFTY 50 vs itself is degenerate; benchmark against itself anyway.
        # rs_vs_sector will be 0 and the row drops naturally if other features
        # are NaN. If all 6 features are valid, this row contributes a signal
        # whose RS component is identically zero — informationless but
        # otherwise legitimate; the random-search optimizer will down-weight
        # the RS dim if NIFTY 50 dominates the pool.
        return DEFAULT_SECTOR_FALLBACK
    return DEFAULT_SECTOR_FALLBACK


def _eval_dates_for_pool(cache_dir: Path, pool_symbols: List[str]) -> List[date]:
    """Return the union of trading dates available across the pool's cache files."""
    all_dates: set = set()
    for sym in pool_symbols:
        all_dates.update(_list_cache_dates(cache_dir, sym))
    return sorted(all_dates)


def assemble_panel(
    eval_dates: List[date],
    universe_symbols: List[str],
    pool: str,
    cache_dir: Path = CACHE_DIR,
    archive_dir: Path = OI_ARCHIVE_DIR,
) -> pd.DataFrame:
    """Assemble the in-sample panel for the named pool.

    Parameters
    ----------
    eval_dates
        Trading dates over which to compute features at 09:30 IST.
    universe_symbols
        Instruments in this pool (Kite naming convention; indices contain
        spaces, e.g. ``"NIFTY 50"``).
    pool
        Either ``"stocks"`` or ``"indices"``. Drives sector-reference choice.
    cache_dir
        Where the 1-min cache parquets live. Defaults to
        ``pipeline/data/research/h_2026_04_29_intraday_v1/cache_1min``.
    archive_dir
        Where the EOD OI archive JSONs live. Defaults to
        ``pipeline/data/oi_history_stocks``.

    Returns
    -------
    pd.DataFrame
        Columns ``date``, ``instrument``, ``f1``, ``f2``, ``f3``, ``f4``, ``f5``,
        ``f6``, ``next_return_pct``. NaN-feature rows and missing-label rows
        are dropped (never imputed).
    """
    if pool not in ("stocks", "indices"):
        raise ValueError(f"pool must be 'stocks' or 'indices', got {pool!r}")

    # Cache 1-min reads to avoid re-reading per date.
    bar_cache: Dict[str, pd.DataFrame] = {}

    def _load_bars(sym: str) -> Optional[pd.DataFrame]:
        if sym in bar_cache:
            return bar_cache[sym]
        p = cache_dir / f"{sym}.parquet"
        if not p.exists():
            bar_cache[sym] = None  # type: ignore[assignment]
            return None
        bar_cache[sym] = pd.read_parquet(p)
        return bar_cache[sym]

    rows: List[Dict] = []
    for eval_d in eval_dates:
        pcr_pair = _resolve_pcr_for_date(eval_d, archive_dir)
        if pcr_pair is None:
            log.debug(f"date={eval_d} skipped: PCR anchors unresolvable")
            continue
        today_pcr_map, two_d_pcr_map = pcr_pair

        eval_t = datetime.combine(eval_d, EVAL_TIME).replace(tzinfo=IST)
        exit_t = datetime.combine(eval_d, EXIT_TIME).replace(tzinfo=IST)

        for sym in universe_symbols:
            bars = _load_bars(sym)
            if bars is None or bars.empty:
                continue
            sector_sym = _resolve_sector_symbol(sym, pool)
            sector_bars = _load_bars(sector_sym)
            if sector_bars is None:
                continue

            # Volume history for THIS eval_date — strict PIT (eval_date excluded).
            try:
                vol_hist = volume_aggregator.build_volume_history(
                    sym, cache_dir, eval_d, lookback_days=20
                )
            except volume_aggregator.VolumeAggregatorError:
                continue

            today_pcr = today_pcr_map.get(sym)
            two_d_pcr = two_d_pcr_map.get(sym)
            if today_pcr is None or two_d_pcr is None:
                continue

            feats = features.compute_all(
                instrument_df=bars,
                sector_df=sector_bars,
                eval_t=eval_t,
                today_pcr=today_pcr,
                two_days_ago_pcr=two_d_pcr,
                volume_history=vol_hist,
            )

            # Drop rows with any NaN feature — DO NOT impute.
            if any(
                (v is None) or (isinstance(v, float) and not math.isfinite(v))
                for v in feats.values()
            ):
                continue

            entry_bar = _bar_at(bars, eval_t)
            exit_bar = _bar_at(bars, exit_t)
            if entry_bar is None or exit_bar is None:
                continue
            entry_close = float(entry_bar["close"])
            exit_close = float(exit_bar["close"])
            if not math.isfinite(entry_close) or entry_close == 0:
                continue
            if not math.isfinite(exit_close):
                continue
            label = (exit_close - entry_close) / entry_close * 100.0

            rows.append({
                "date": eval_d.isoformat(),
                "instrument": sym,
                "f1": feats["delta_pcr_2d"],
                "f2": feats["orb_15min"],
                "f3": feats["volume_z"],
                "f4": feats["vwap_dev"],
                "f5": feats["rs_vs_sector"],
                "f6": feats["trend_slope_15min"],
                "next_return_pct": label,
            })

    df = pd.DataFrame(rows)
    if df.empty:
        log.warning(f"in_sample_panel for pool={pool} is EMPTY")
    else:
        log.info(
            f"in_sample_panel for pool={pool}: {df['date'].nunique()} days, "
            f"{len(df)} rows, {df['instrument'].nunique()} instruments"
        )
    return df


def assemble_for_pool(pool: str) -> pd.DataFrame:
    """Wrapper: resolve V1 universe + candidate dates from cache, return the panel."""
    if pool not in ("stocks", "indices"):
        raise ValueError(f"pool must be 'stocks' or 'indices', got {pool!r}")
    univ = universe.load_v1_universe()
    if pool == "stocks":
        symbols = univ["stocks"]
    else:
        # Indices pool: pass-through. universe.INDEX_CANDIDATES uses no-space
        # form ("NIFTYBANK") but the cache uses Kite convention ("NIFTY BANK").
        # Resolution is left to the caller / liquidity gate — at V1 kickoff
        # the gate returns an EMPTY indices list (no oi_scanner archive for
        # indices), so this branch yields an empty panel and the recalibrate
        # driver raises a clear RuntimeError. When the gate eventually returns
        # indices, supply them in cache-on-disk form (with spaces).
        symbols = univ["indices"]
    eval_dates = _eval_dates_for_pool(CACHE_DIR, symbols)
    return assemble_panel(eval_dates, symbols, pool)
