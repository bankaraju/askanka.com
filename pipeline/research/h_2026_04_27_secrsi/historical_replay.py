"""SECRSI 5y historical backtest on 5m bar cache.

Replays the H-2026-04-27-003 SECRSI mechanical rules against the
``pipeline/data/fno_intraday_5m/<TICKER>.csv`` cache produced by
``pipeline.intraday_backfill_eodhd``.

Replay rules (must match forward shadow exactly)
-----------------------------------------------
- 09:15 IST: snapshot per-ticker open prices (open of 09:15 bar).
- 11:00 IST: snapshot per-ticker LTP (close of 11:00 bar).
- Sector aggregation: median of per-stock %chg-from-open (pure
  ``sector_snapshot.take_snapshot`` reuse).
- Basket selection: ``basket_builder.build_basket`` reused; 8 legs
  (top-2 sectors x top-2 stocks long, bottom-2 sectors x bottom-2 stocks
  short, equal weight 1/8 each).
- Per-leg ATR(14) computed on the prior 14 daily bars from
  ``pipeline/data/fno_historical/<TICKER>.csv`` (PIT, no leakage).
- Stop-out check: walk forward 5m bars from 11:00; LONG stops if intraday
  low <= entry - 2*ATR; SHORT stops if intraday high >= entry + 2*ATR.
- TIME_STOP: 14:30 close-of-bar if no stop hit.

Scope notes
-----------
- This is a research-only sanity check. The H-2026-04-27-003 single-touch
  holdout (2026-04-28 -> 2026-07-31) is independent and unaffected.
- Tickers without 5m or daily history on a given date are skipped silently.
  The number-skipped is logged per day to ``skipped`` field.
- Universe: ``canonical_fno_research_v3.json`` (current, not PIT). Tickers
  added to F&O after the replay date show up as silent skips.

Output
------
``pipeline/data/research/h_2026_04_27_secrsi/historical_backtest_<from>_<to>.csv``
columns: date, basket_id, leg_id, ticker, sector, side, entry_px,
exit_px, exit_reason, atr_14, stop_px, pnl_pct, regime_label,
n_qualified_sectors

``pipeline/data/research/h_2026_04_27_secrsi/historical_summary_<from>_<to>.json``
year-by-year + full-period stats (mean bps, hit rate, sharpe, MaxDD,
n_baskets, n_skipped_days).

CLI
---
    python -m pipeline.research.h_2026_04_27_secrsi.historical_backtest \
           --from 2021-05-01 --to 2026-04-30
    python -m pipeline.research.h_2026_04_27_secrsi.historical_backtest \
           --from 2024-01-01 --to 2024-12-31 --max-tickers 30
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import statistics
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Mapping

from pipeline.research.h_2026_04_27_secrsi.basket_builder import build_basket
from pipeline.research.h_2026_04_27_secrsi.sector_snapshot import take_snapshot

log = logging.getLogger("anka.secrsi.historical_backtest")

REPO = Path(__file__).resolve().parents[3]
INTRADAY_5M_DIR = REPO / "pipeline" / "data" / "fno_intraday_5m"
DAILY_DIR = REPO / "pipeline" / "data" / "fno_historical"
CANONICAL = REPO / "pipeline" / "data" / "canonical_fno_research_v3.json"
OUT_DIR = REPO / "pipeline" / "data" / "research" / "h_2026_04_27_secrsi"

ATR_WINDOW = 14
ATR_MULT = 2.0
MIN_STOCKS_PER_SECTOR = 4
SNAPSHOT_TIME = "11:00:00"
EXIT_TIME = "14:30:00"
OPEN_TIME = "09:15:00"


# ---- Daily OHLC + ATR (PIT) -----------------------------------------------

def _load_daily_ohlc(ticker: str) -> list[dict] | None:
    """Return list of {date, open, high, low, close, volume} dicts, sorted asc."""
    p = DAILY_DIR / f"{ticker}.csv"
    if not p.is_file():
        return None
    rows: list[dict] = []
    with p.open(encoding="utf-8", newline="") as fp:
        reader = csv.DictReader(fp)
        for r in reader:
            try:
                rows.append({
                    "date": r["Date"],
                    "high": float(r["High"]),
                    "low": float(r["Low"]),
                    "close": float(r["Close"]),
                })
            except (KeyError, ValueError):
                continue
    rows.sort(key=lambda x: x["date"])
    return rows


def _atr_pit(daily: list[dict], up_to: str, window: int = ATR_WINDOW) -> float | None:
    """ATR(window) computed strictly from bars BEFORE `up_to` (exclusive)."""
    prior = [d for d in daily if d["date"] < up_to]
    if len(prior) < window + 1:
        return None
    trs: list[float] = []
    for i in range(len(prior) - window, len(prior)):
        if i == 0:
            continue
        h = prior[i]["high"]
        lo = prior[i]["low"]
        prev_c = prior[i - 1]["close"]
        tr = max(h - lo, abs(h - prev_c), abs(lo - prev_c))
        trs.append(tr)
    if not trs:
        return None
    return sum(trs) / len(trs)


# ---- 5m bars -----------------------------------------------------------------

def _load_5m_bars(ticker: str) -> dict[str, list[dict]] | None:
    """Return {YYYY-MM-DD: [bar dicts ordered by time]}.

    Returns None if file missing.
    """
    p = INTRADAY_5M_DIR / f"{ticker}.csv"
    if not p.is_file():
        return None
    by_day: dict[str, list[dict]] = {}
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
                    "open": float(row["open"]) if row["open"] else None,
                    "high": float(row["high"]) if row["high"] else None,
                    "low": float(row["low"]) if row["low"] else None,
                    "close": float(row["close"]) if row["close"] else None,
                }
            except (ValueError, KeyError):
                continue
            if bar["close"] is None:
                continue
            by_day.setdefault(d, []).append(bar)
    for d in by_day:
        by_day[d].sort(key=lambda b: b["time"])
    return by_day


def _bar_at(bars: list[dict], hhmmss: str) -> dict | None:
    """Find first bar with time == hhmmss; if not present, the closest bar
    AFTER (since 5m bars are aligned to :00, :05, :10 ...)."""
    for b in bars:
        if b["time"] >= hhmmss:
            return b
    return None


def _exit_for_leg(
    bars: list[dict], side: str, entry_px: float, atr: float | None,
) -> tuple[float, str]:
    """Walk 5m bars from 11:00 (inclusive) to 14:30 (inclusive).

    Returns (exit_px, exit_reason). exit_reason in
    {ATR_STOP, TIME_STOP, NO_DATA}.
    """
    snap_bars = [b for b in bars if SNAPSHOT_TIME <= b["time"] <= EXIT_TIME]
    if not snap_bars:
        return entry_px, "NO_DATA"

    if atr is not None and atr > 0:
        stop_distance = ATR_MULT * atr
        if side == "LONG":
            stop_px = entry_px - stop_distance
            for b in snap_bars[1:]:
                if b["low"] is not None and b["low"] <= stop_px:
                    return stop_px, "ATR_STOP"
        else:
            stop_px = entry_px + stop_distance
            for b in snap_bars[1:]:
                if b["high"] is not None and b["high"] >= stop_px:
                    return stop_px, "ATR_STOP"

    last_bar = snap_bars[-1]
    return float(last_bar["close"]), "TIME_STOP"


# ---- Sector map -------------------------------------------------------------

def _load_sector_map() -> dict[str, str]:
    try:
        from pipeline.scorecard_v2.sector_mapper import SectorMapper
        sm = SectorMapper()
        full = sm.map_all()
    except Exception as exc:
        log.warning("SectorMapper failed: %s — backtest cannot run without sectors", exc)
        return {}
    return {sym: meta.get("sector", "") for sym, meta in full.items()}


def _load_universe() -> list[str]:
    if not CANONICAL.is_file():
        raise SystemExit(f"canonical FNO file missing: {CANONICAL}")
    doc = json.loads(CANONICAL.read_text(encoding="utf-8"))
    valid_from = doc.get("per_ticker_valid_from", {}) or doc.get("tickers", {})
    if isinstance(valid_from, dict):
        return list(valid_from.keys())
    return list(valid_from)


# ---- Replay loop ------------------------------------------------------------

def _trading_days(intraday_cache: Mapping[str, dict[str, list[dict]]]) -> list[str]:
    """Union of dates seen across all tickers in cache."""
    days: set[str] = set()
    for d_map in intraday_cache.values():
        days.update(d_map.keys())
    return sorted(days)


def _replay_one_day(
    day: str,
    universe: list[str],
    sector_map: dict[str, str],
    intraday_cache: dict[str, dict[str, list[dict]]],
    daily_cache: dict[str, list[dict]],
) -> list[dict]:
    """Replay SECRSI rules for a single trading day. Returns leg-rows or []."""
    prices_open: dict[str, float] = {}
    prices_now: dict[str, float] = {}

    for t in universe:
        d_map = intraday_cache.get(t)
        if not d_map:
            continue
        bars = d_map.get(day)
        if not bars:
            continue
        open_bar = _bar_at(bars, OPEN_TIME)
        snap_bar = _bar_at(bars, SNAPSHOT_TIME)
        if open_bar is None or snap_bar is None:
            continue
        if open_bar["open"] is None or snap_bar["close"] is None:
            continue
        prices_open[t] = float(open_bar["open"])
        prices_now[t] = float(snap_bar["close"])

    if len(prices_open) < 4 * MIN_STOCKS_PER_SECTOR:
        return []

    snapshot = take_snapshot(
        prices_open, prices_now, sector_map,
        min_stocks_per_sector=MIN_STOCKS_PER_SECTOR,
    )
    qualified = [s for s in snapshot if s.get("qualified")]
    basket = build_basket(snapshot)
    if not basket:
        return []

    rows: list[dict] = []
    for leg in basket:
        t = leg["ticker"]
        bars = intraday_cache[t][day]
        entry_bar = _bar_at(bars, SNAPSHOT_TIME)
        if entry_bar is None or entry_bar["close"] is None:
            continue
        entry_px = float(entry_bar["close"])
        atr = _atr_pit(daily_cache.get(t, []), day, ATR_WINDOW)
        exit_px, exit_reason = _exit_for_leg(bars, leg["side"], entry_px, atr)

        if leg["side"] == "LONG":
            pnl_pct = (exit_px - entry_px) / entry_px
        else:
            pnl_pct = (entry_px - exit_px) / entry_px

        rows.append({
            "date": day,
            "basket_id": f"SECRSI-HIST-{day}",
            "leg_id": f"SECRSI-HIST-{day}-{t}-{leg['side']}",
            "ticker": t,
            "sector": leg["sector"],
            "side": leg["side"],
            "weight": leg["weight"],
            "entry_px": round(entry_px, 4),
            "exit_px": round(exit_px, 4),
            "exit_reason": exit_reason,
            "atr_14": round(atr, 4) if atr is not None else "",
            "pnl_pct": round(pnl_pct, 6),
            "n_qualified_sectors": len(qualified),
        })
    return rows


# ---- Aggregation ------------------------------------------------------------

def _basket_pnl(leg_rows: list[dict]) -> float:
    if not leg_rows:
        return 0.0
    return sum(float(r["weight"]) * float(r["pnl_pct"]) for r in leg_rows)


def _max_drawdown(returns: list[float]) -> float:
    """Daily return series → MaxDD (most negative cumulative drawdown)."""
    if not returns:
        return 0.0
    cum = 0.0
    peak = 0.0
    mdd = 0.0
    for r in returns:
        cum += r
        if cum > peak:
            peak = cum
        dd = cum - peak
        if dd < mdd:
            mdd = dd
    return mdd


def _sharpe(daily_returns: list[float]) -> float:
    if len(daily_returns) < 2:
        return 0.0
    mu = statistics.mean(daily_returns)
    sd = statistics.pstdev(daily_returns)
    if sd == 0:
        return 0.0
    return (mu / sd) * (252 ** 0.5)


def _summarize(daily_returns: dict[str, float]) -> dict:
    if not daily_returns:
        return {"n": 0, "mean_bps": 0.0, "hit_rate": 0.0, "sharpe": 0.0, "max_dd_bps": 0.0}
    by_year: dict[str, list[float]] = {}
    for d, r in daily_returns.items():
        y = d[:4]
        by_year.setdefault(y, []).append(r)

    full = list(daily_returns.values())
    full_summary = {
        "n": len(full),
        "mean_bps": round(statistics.mean(full) * 1e4, 2),
        "hit_rate": round(sum(1 for r in full if r > 0) / len(full), 4),
        "sharpe": round(_sharpe(full), 3),
        "max_dd_bps": round(_max_drawdown(full) * 1e4, 2),
    }

    per_year = {}
    for y, rs in sorted(by_year.items()):
        per_year[y] = {
            "n": len(rs),
            "mean_bps": round(statistics.mean(rs) * 1e4, 2) if rs else 0.0,
            "hit_rate": round(sum(1 for r in rs if r > 0) / len(rs), 4) if rs else 0.0,
            "sharpe": round(_sharpe(rs), 3),
            "max_dd_bps": round(_max_drawdown(rs) * 1e4, 2),
        }

    return {"full": full_summary, "per_year": per_year}


# ---- Main -------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="from_d", required=True, help="YYYY-MM-DD")
    ap.add_argument("--to", dest="to_d", required=True, help="YYYY-MM-DD")
    ap.add_argument("--max-tickers", type=int, default=None,
                    help="cap universe (debug)")
    ap.add_argument("--out-dir", default=None)
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")

    from_d = date.fromisoformat(args.from_d)
    to_d = date.fromisoformat(args.to_d)
    out_dir = Path(args.out_dir) if args.out_dir else OUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    sector_map = _load_sector_map()
    if not sector_map:
        log.error("empty sector map — cannot proceed")
        return 1

    universe = _load_universe()
    if args.max_tickers:
        universe = universe[: args.max_tickers]
    log.info("universe: %d tickers", len(universe))

    log.info("loading 5m intraday cache + daily ATR cache…")
    intraday_cache: dict[str, dict[str, list[dict]]] = {}
    daily_cache: dict[str, list[dict]] = {}
    n_5m_loaded = 0
    n_daily_loaded = 0
    for t in universe:
        bars = _load_5m_bars(t)
        if bars:
            intraday_cache[t] = bars
            n_5m_loaded += 1
        d = _load_daily_ohlc(t)
        if d:
            daily_cache[t] = d
            n_daily_loaded += 1
    log.info("5m loaded: %d / %d  daily loaded: %d / %d",
             n_5m_loaded, len(universe), n_daily_loaded, len(universe))

    if n_5m_loaded < 4 * MIN_STOCKS_PER_SECTOR:
        log.error("only %d tickers have 5m data — too sparse for backtest", n_5m_loaded)
        return 1

    all_days = _trading_days(intraday_cache)
    days = [d for d in all_days if from_d.isoformat() <= d <= to_d.isoformat()]
    log.info("replaying %d trading days (%s -> %s)", len(days),
             days[0] if days else "n/a", days[-1] if days else "n/a")

    leg_rows_path = out_dir / f"historical_backtest_{from_d}_{to_d}.csv"
    daily_returns: dict[str, float] = {}
    n_baskets = 0
    n_no_basket = 0

    fields = ["date", "basket_id", "leg_id", "ticker", "sector", "side",
              "weight", "entry_px", "exit_px", "exit_reason", "atr_14",
              "pnl_pct", "n_qualified_sectors"]
    with leg_rows_path.open("w", encoding="utf-8", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=fields)
        writer.writeheader()
        for d in days:
            rows = _replay_one_day(d, universe, sector_map,
                                   intraday_cache, daily_cache)
            if not rows:
                n_no_basket += 1
                continue
            for r in rows:
                writer.writerow(r)
            daily_returns[d] = _basket_pnl(rows)
            n_baskets += 1

    summary = _summarize(daily_returns)
    summary["meta"] = {
        "from": from_d.isoformat(),
        "to": to_d.isoformat(),
        "n_universe": len(universe),
        "n_5m_loaded": n_5m_loaded,
        "n_daily_loaded": n_daily_loaded,
        "n_trading_days": len(days),
        "n_baskets": n_baskets,
        "n_no_basket_days": n_no_basket,
        "atr_window": ATR_WINDOW,
        "atr_mult": ATR_MULT,
        "min_stocks_per_sector": MIN_STOCKS_PER_SECTOR,
    }

    summary_path = out_dir / f"historical_summary_{from_d}_{to_d}.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    log.info("leg-rows: %s", leg_rows_path)
    log.info("summary:  %s", summary_path)
    if "full" in summary:
        f = summary["full"]
        log.info("full-period: n=%d  mean=%.2f bps  hit=%.1f%%  sharpe=%.2f  MaxDD=%.0f bps",
                 f["n"], f["mean_bps"], f["hit_rate"] * 100, f["sharpe"], f["max_dd_bps"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
