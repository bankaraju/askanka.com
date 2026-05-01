"""Per-event feature computation for the Karpathy search.

Walks every Candidate, assembles the universe-wide context at its (date, snap_t),
and computes the 8 features defined in feature_library. Caches results to JSON
so the 448-cell search doesn't re-compute features per cell.

Strategy: load each universe ticker's full 5y CSV ONCE into an in-memory
date->bars map, then slice for any (date, snap_t) needed by the candidate
itself or by its 5-day / 20-day sector history. ~50 s preload + sub-second
per-candidate compute on VPS.
"""
from __future__ import annotations

import bisect
import csv
import json
import logging
import statistics
from collections import defaultdict
from pathlib import Path

from pipeline.research.h_2026_04_27_secrsi.historical_replay import (
    INTRADAY_5M_DIR, _load_daily_ohlc,
)

from .candidate_loader import Candidate
from .feature_library import FEATURE_NAMES, SnapContext, compute_features

log = logging.getLogger("anka.h_2026_05_01.feature_builder")

REPO = Path(__file__).resolve().parents[3]
INTRADAY_5M_DIR_LOCAL = INTRADAY_5M_DIR
DAILY_DIR = REPO / "pipeline" / "data" / "fno_historical"
VIX_PATH = REPO / "pipeline" / "data" / "india_historical" / "indices" / "INDIAVIX.csv"

CACHE_PATH = Path(__file__).resolve().parent / "feature_cache.json"


# ------------------ universe bar cache (lazy, in-memory) ------------------

class UniverseCache:
    """Loads full 5m CSVs for the frozen universe ONCE, slices them per query.

    Memory: ~100 tickers × ~6 MB CSV each ≈ 600 MB — fine on VPS (4-8 GB RAM).
    """

    def __init__(self, universe: list[str], sector_map: dict[str, str] | None = None):
        self.universe = universe
        self.sector_map = sector_map or {}
        self._by_ticker: dict[str, dict[str, list[dict]]] = {}
        self._sorted_dates: dict[str, list[str]] = {}
        self._all_dates_sorted: list[str] | None = None
        self._univ_cache: dict[tuple[str, str], dict[str, float]] = {}
        self._sec_cache: dict[tuple[str, str], dict[str, float]] = {}

    def _read_ticker(self, ticker: str) -> dict[str, list[dict]]:
        """Read a full ticker CSV and bucket by date."""
        p = INTRADAY_5M_DIR_LOCAL / f"{ticker}.csv"
        out: dict[str, list[dict]] = defaultdict(list)
        if not p.is_file():
            return {}
        with p.open(encoding="utf-8", newline="") as fp:
            reader = csv.DictReader(fp)
            for row in reader:
                dt = row.get("datetime", "")
                if " " not in dt:
                    continue
                d, t = dt.split(" ", 1)
                try:
                    bar = {
                        "time": t,
                        "open": float(row["open"]) if row.get("open") else None,
                        "high": float(row["high"]) if row.get("high") else None,
                        "low": float(row["low"]) if row.get("low") else None,
                        "close": float(row["close"]) if row.get("close") else None,
                        "volume": float(row["volume"]) if row.get("volume") else None,
                    }
                except ValueError:
                    continue
                if bar["close"] is None:
                    continue
                out[d].append(bar)
        # already chronological in source files; keep as-is
        return dict(out)

    def preload(self) -> None:
        """Materialize the full universe in memory in one pass."""
        for i, t in enumerate(self.universe, 1):
            if t in self._by_ticker:
                continue
            data = self._read_ticker(t)
            self._by_ticker[t] = data
            self._sorted_dates[t] = sorted(data.keys())
            if i % 25 == 0:
                log.info("preloaded %d / %d tickers", i, len(self.universe))
        # union of dates across all tickers (sorted)
        all_dates: set[str] = set()
        for ds in self._sorted_dates.values():
            all_dates.update(ds)
        self._all_dates_sorted = sorted(all_dates)

    def bars_on(self, ticker: str, date: str) -> list[dict]:
        return self._by_ticker.get(ticker, {}).get(date, [])

    def universe_returns(self, date: str, snap_t: str) -> dict[str, float]:
        """Map ticker -> intraday %chg-from-open at snap_t (within 15-min).
        Memoized on (date, snap_t)."""
        key = (date, snap_t)
        cached = self._univ_cache.get(key)
        if cached is not None:
            return cached
        out: dict[str, float] = {}
        for t in self.universe:
            bars = self.bars_on(t, date)
            r = _intraday_ret_pct(bars, snap_t)
            if r is not None:
                out[t] = r
        self._univ_cache[key] = out
        return out

    def sector_returns(self, date: str, snap_t: str) -> dict[str, float]:
        """Sector -> mean of constituent intraday returns at (date, snap_t).
        Memoized on (date, snap_t)."""
        key = (date, snap_t)
        cached = self._sec_cache.get(key)
        if cached is not None:
            return cached
        univ = self.universe_returns(date, snap_t)
        bucket: dict[str, list[float]] = defaultdict(list)
        for ticker, ret in univ.items():
            sec = self.sector_map.get(ticker)
            if sec:
                bucket[sec].append(ret)
        out = {sec: sum(rs) / len(rs) for sec, rs in bucket.items() if rs}
        self._sec_cache[key] = out
        return out

    def trading_days_before(self, date: str, n: int) -> list[str]:
        """Return the n trading days strictly before `date`, ascending order."""
        if self._all_dates_sorted is None:
            return []
        # bisect_left gives index of `date`; we want last n before it
        idx = bisect.bisect_left(self._all_dates_sorted, date)
        start = max(0, idx - n)
        return self._all_dates_sorted[start:idx]


# ------------------ helpers ----------------------------------------------

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


# ------------------ singleton index reads --------------------------------

def _read_index_csv(path: Path) -> list[dict]:
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


_VIX_CACHE: list[dict] | None = None


def _vix_open_for_date(date_str: str) -> float | None:
    global _VIX_CACHE
    if _VIX_CACHE is None:
        _VIX_CACHE = _read_index_csv(VIX_PATH)
    for r in _VIX_CACHE:
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
            v = 1.0
        num += c * v
        den += v
    if den <= 0:
        return None
    return num / den


# ------------------ snap context builder --------------------------------

def build_snap_context(
    *,
    candidate: Candidate,
    universe_cache: UniverseCache,
) -> SnapContext:
    """Construct a fully-populated SnapContext using the in-memory cache."""
    bars = universe_cache.bars_on(candidate.ticker, candidate.date)

    # universe & sector returns at the candidate snap
    univ_ret = universe_cache.universe_returns(candidate.date, candidate.snap_t)
    sec_ret_today = universe_cache.sector_returns(candidate.date, candidate.snap_t)

    # 5-day history of sector returns (same snap_t)
    past_5d = universe_cache.trading_days_before(candidate.date, 5)
    sec_ret_5d = [universe_cache.sector_returns(d, candidate.snap_t) for d in past_5d]

    # 20-day history of THIS candidate's sector intraday return at the snap_t
    past_20d = universe_cache.trading_days_before(candidate.date, 20)
    sec_rs_20d: list[float] = []
    for d in past_20d:
        m = universe_cache.sector_returns(d, candidate.snap_t)
        if candidate.sector and candidate.sector in m:
            sec_rs_20d.append(m[candidate.sector])

    return SnapContext(
        date=candidate.date,
        snap_t=candidate.snap_t,
        ticker=candidate.ticker,
        sector=candidate.sector or None,
        snap_px=candidate.snap_px,
        intraday_ret_pct=candidate.intraday_ret_pct,
        universe_returns=univ_ret,
        sector_returns=sec_ret_today,
        sector_returns_5d=sec_ret_5d,
        sector_rs_history_20d=sec_rs_20d if sec_rs_20d else None,
        breadth_above_20dma_pct=_breadth_above_20dma_pct(universe_cache.universe, candidate.date),
        india_vix=_vix_open_for_date(candidate.date),
        realized_30min_atr_pct=_realized_30min_atr_pct(bars),
        cumulative_vwap_at_snap=_cumulative_vwap_at_snap(bars, candidate.snap_t),
        atr_14_pit=candidate.atr_14,
        news_count_24h=None,
        news_count_60d_history=None,
        is_event_day=False,
    )


# ------------------ cache I/O ---------------------------------------------

def build_feature_cache(
    candidates: list[Candidate],
    universe: list[str],
    sector_map: dict[str, str] | None = None,
) -> list[dict]:
    """Compute features for every candidate. Returns a list of cache rows."""
    cache = UniverseCache(universe, sector_map=sector_map or {})
    log.info("preloading %d ticker CSVs into memory…", len(universe))
    cache.preload()
    log.info("preload complete; computing features for %d candidates", len(candidates))

    out: list[dict] = []
    for i, c in enumerate(candidates, 1):
        ctx = build_snap_context(candidate=c, universe_cache=cache)
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
