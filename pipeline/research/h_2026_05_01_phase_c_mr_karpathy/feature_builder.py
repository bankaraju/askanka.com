"""Per-event feature computation for the Karpathy search.

Walks every Candidate, assembles the universe-wide context at its (date, snap_t),
and computes the 8 features defined in feature_library. Caches results to JSON
so the 448-cell search doesn't re-compute features per cell.

Only laptop-light I/O on the laptop side; the heavy run is intended for VPS.
"""
from __future__ import annotations

import csv
import json
import logging
import statistics
from dataclasses import asdict
from pathlib import Path

from pipeline.research.h_2026_04_27_secrsi.historical_replay import (
    INTRADAY_5M_DIR, _atr_pit, _load_daily_ohlc,
)

from .candidate_loader import Candidate
from .feature_library import FEATURE_NAMES, SnapContext, compute_features

log = logging.getLogger("anka.h_2026_05_01.feature_builder")

REPO = Path(__file__).resolve().parents[3]
INTRADAY_5M_DIR_LOCAL = INTRADAY_5M_DIR
DAILY_DIR = REPO / "pipeline" / "data" / "fno_historical"
SECTORAL_DIR = REPO / "pipeline" / "data" / "sectoral_indices"
VIX_PATH = REPO / "pipeline" / "data" / "india_historical" / "indices" / "INDIAVIX.csv"

CACHE_PATH = Path(__file__).resolve().parent / "feature_cache.json"


# ------------------ universe bar loaders ----------------------------------

def _load_5m_bars_for_date(ticker: str, date_str: str) -> list[dict]:
    """Single-date fast-path read; same shape as holdout_runner._load_5m_bars_for_date."""
    p = INTRADAY_5M_DIR_LOCAL / f"{ticker}.csv"
    if not p.is_file():
        return []
    out: list[dict] = []
    found = False
    with p.open(encoding="utf-8", newline="") as fp:
        reader = csv.DictReader(fp)
        for row in reader:
            dt = row.get("datetime", "")
            if " " not in dt:
                continue
            d, t = dt.split(" ", 1)
            if d != date_str:
                if found:
                    break
                continue
            found = True
            try:
                bar = {
                    "time": t,
                    "open": float(row["open"]) if row.get("open") else None,
                    "high": float(row["high"]) if row.get("high") else None,
                    "low": float(row["low"]) if row.get("low") else None,
                    "close": float(row["close"]) if row.get("close") else None,
                }
            except ValueError:
                continue
            if bar["close"] is None:
                continue
            out.append(bar)
    out.sort(key=lambda b: b["time"])
    return out


def _bar_at_snap(bars: list[dict], snap_t: str) -> dict | None:
    """Return the first bar with time >= snap_t and within 15 minutes."""
    for b in bars:
        if b.get("time", "") >= snap_t:
            sh, sm, _ = snap_t.split(":")
            bh, bm, _ = b["time"].split(":")
            if int(bh) * 60 + int(bm) - (int(sh) * 60 + int(sm)) <= 15:
                return b
            return None
    return None


# ------------------ universe-wide context per snap ------------------------

def _intraday_ret_pct(bars: list[dict], snap_t: str) -> float | None:
    """% change from day's open to snap_t close."""
    if not bars:
        return None
    open_px = bars[0].get("open") or bars[0].get("close")
    if open_px is None or open_px <= 0:
        return None
    snap_bar = _bar_at_snap(bars, snap_t)
    if snap_bar is None or snap_bar.get("close") is None:
        return None
    return (snap_bar["close"] - open_px) / open_px * 100.0


def _build_universe_returns(universe: list[str], date_str: str, snap_t: str) -> dict[str, float]:
    """Map each ticker -> %chg-from-open at snap_t. Excludes missing tickers."""
    out: dict[str, float] = {}
    for t in universe:
        bars = _load_5m_bars_for_date(t, date_str)
        ret = _intraday_ret_pct(bars, snap_t)
        if ret is not None:
            out[t] = ret
    return out


def _read_index_csv(path: Path) -> list[dict]:
    """Read a sectoral / VIX CSV (Date, Open, High, Low, Close)."""
    if not path.is_file():
        return []
    rows: list[dict] = []
    with path.open(encoding="utf-8", newline="") as fp:
        reader = csv.DictReader(fp)
        for row in reader:
            try:
                rows.append({
                    "date": row.get("Date") or row.get("date"),
                    "open": float(row.get("Open") or row.get("open") or 0),
                    "close": float(row.get("Close") or row.get("close") or 0),
                })
            except (TypeError, ValueError):
                continue
    rows.sort(key=lambda r: r["date"])
    return rows


def _vix_open_for_date(date_str: str) -> float | None:
    rows = _read_index_csv(VIX_PATH)
    for r in rows:
        if r["date"] == date_str:
            return r.get("open") or None
    return None


def _breadth_above_20dma_pct(universe: list[str], date_str: str) -> float | None:
    """% of universe with previous-close > 20-DMA on the snap day's prev close."""
    above = 0
    counted = 0
    for t in universe:
        rows = _load_daily_ohlc(t)
        if not rows:
            continue
        prior = [r for r in rows if r.get("date") < date_str]
        if len(prior) < 21:
            continue
        last_close = prior[-1].get("close")
        ma20 = statistics.fmean(r["close"] for r in prior[-20:])
        if last_close is None or ma20 == 0:
            continue
        counted += 1
        if last_close > ma20:
            above += 1
    if counted == 0:
        return None
    return above / counted * 100.0


def _realized_30min_atr_pct(bars: list[dict]) -> float | None:
    """First 30-min ATR % from open. Uses bars within 09:15..09:45."""
    early = [b for b in bars if "09:15:00" <= b.get("time", "") <= "09:45:00"]
    if len(early) < 2:
        return None
    open_px = early[0].get("open") or early[0].get("close")
    if not open_px or open_px <= 0:
        return None
    highs = [b.get("high") for b in early if b.get("high") is not None]
    lows = [b.get("low") for b in early if b.get("low") is not None]
    if not highs or not lows:
        return None
    hi = max(highs)
    lo = min(lows)
    return (hi - lo) / open_px * 100.0


def _cumulative_vwap_at_snap(bars: list[dict], snap_t: str) -> float | None:
    """Cumulative VWAP from day open through the snap bar (inclusive)."""
    pre = [b for b in bars if b.get("time", "") <= snap_t]
    if not pre:
        return None
    num = 0.0
    den = 0.0
    for b in pre:
        c = b.get("close")
        v = b.get("volume")
        if c is None:
            continue
        if v is None or v <= 0:
            v = 1.0  # equal-weight fallback if volume missing
        num += c * v
        den += v
    if den <= 0:
        return None
    return num / den


# ------------------ snap context builder ----------------------------------

def build_snap_context(*, candidate: Candidate, universe: list[str]) -> SnapContext:
    """Construct a SnapContext fully populated with universe-wide data.

    Falls back to None for fields whose source data is missing — the feature
    computers downstream return NaN, which causes those Karpathy cells (whose
    chosen subset includes that feature) to gracefully skip the candidate.
    """
    bars = _load_5m_bars_for_date(candidate.ticker, candidate.date)

    return SnapContext(
        date=candidate.date,
        snap_t=candidate.snap_t,
        ticker=candidate.ticker,
        sector=candidate.sector or None,
        snap_px=candidate.snap_px,
        intraday_ret_pct=candidate.intraday_ret_pct,
        universe_returns=_build_universe_returns(universe, candidate.date, candidate.snap_t),
        sector_returns=None,        # sector intraday computed later if budget allows
        sector_returns_5d=None,
        sector_rs_history_20d=None,
        breadth_above_20dma_pct=_breadth_above_20dma_pct(universe, candidate.date),
        india_vix=_vix_open_for_date(candidate.date),
        realized_30min_atr_pct=_realized_30min_atr_pct(bars),
        cumulative_vwap_at_snap=_cumulative_vwap_at_snap(bars, candidate.snap_t),
        atr_14_pit=candidate.atr_14,
        news_count_24h=None,
        news_count_60d_history=None,
        is_event_day=False,         # already filtered by candidate_loader
    )


# ------------------ cache I/O ---------------------------------------------

def build_feature_cache(candidates: list[Candidate], universe: list[str]) -> list[dict]:
    """Compute features for every candidate. Returns a list of cache rows."""
    out: list[dict] = []
    for i, c in enumerate(candidates, 1):
        ctx = build_snap_context(candidate=c, universe=universe)
        feats = compute_features(ctx)
        row = {
            "date": c.date,
            "snap_t": c.snap_t,
            "ticker": c.ticker,
            "regime": c.regime,
            "sector": c.sector,
            "pnl_pct_net": c.pnl_pct_net,
            **{k: (None if v != v else float(v)) for k, v in feats.items()},
        }
        out.append(row)
        if i % 10 == 0:
            log.info("features computed: %d / %d", i, len(candidates))
    return out


def save_feature_cache(rows: list[dict], path: Path = CACHE_PATH) -> None:
    payload = {
        "hypothesis_id": "H-2026-05-01-phase-c-mr-karpathy-v1",
        "n_events": len(rows),
        "feature_names": list(FEATURE_NAMES),
        "rows": rows,
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def load_feature_cache(path: Path = CACHE_PATH) -> list[dict] | None:
    if not path.is_file():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload.get("rows", [])
