"""NEUTRAL-day NIFR dispersion explorer (Track 1, exploratory only).

Forensic 5y replay of the spec §6 fair-value dislocation trigger across all
NEUTRAL trading days 2021-05 → 2024-04. Walks every (date, ticker, snap_t)
in the frozen 100-ticker universe at every 15-min snap from 10:00 → 14:00,
computes VWAP-dev z + hour-balance-dev z + range_spike_pctile, applies the
trigger gate per spec §6, simulates forward to ATR(14)×1.75 stop or 14:30
TIME_STOP, and writes:

  - explorer_trades.csv     -- one row per fired trigger candidate
  - explorer_universe.csv   -- one row per evaluated (date, ticker, snap_t),
                               regardless of trigger -- for distributional
                               plots of |vwap_dev_z| and friends.
  - explorer_summary.json   -- aggregate stats (trigger rate, hit, mean P&L,
                               Sharpe, per-sector breakdown).

THIS DOES NOT REGISTER OR CONSUME THE NIFR SINGLE-TOUCH HOLDOUT.
This is data exploration to inform whether NIFR registration is worth
spending the slot. No claim of edge is made by this module.

Usage on VPS:
  ~/askanka.com/.venv/bin/python -m \
      pipeline.research.h_2026_05_01_neutral_fair_value_reversion.dispersion_explorer
"""
from __future__ import annotations

import bisect
import csv
import json
import logging
import math
import statistics
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from pipeline.research.h_2026_04_27_secrsi.historical_replay import (
    INTRADAY_5M_DIR, _load_daily_ohlc,
)

log = logging.getLogger("anka.h_2026_05_01.nifr.dispersion")

REPO = Path(__file__).resolve().parents[3]
PKG = Path(__file__).resolve().parent
PHASE_C_PKG = REPO / "pipeline" / "research" / "h_2026_05_01_phase_c_mr_karpathy"

REGIME_TAPE = REPO / "pipeline" / "data" / "research" / "etf_v3" / "regime_tape_5y_pit.csv"
UNIVERSE_FROZEN = PHASE_C_PKG / "universe_frozen.json"  # reuse 100-ticker list
SECTOR_MAP_FROZEN = PHASE_C_PKG / "sector_map_frozen.json"
EVENT_CALENDAR = PHASE_C_PKG / "event_calendar.json"

OUT_TRADES = PKG / "explorer_trades.csv"
OUT_UNIVERSE = PKG / "explorer_universe.csv"
OUT_SUMMARY = PKG / "explorer_summary.json"

# Spec section 6 trigger thresholds (frozen)
VWAP_DEV_Z_MIN = 1.75
HOUR_BALANCE_Z_MIN = 1.25
RANGE_PCTILE_MAX = 90.0

# Spec section 9 trade rules
ATR_STOP_MULT = 1.75
TIME_STOP_HHMM = "14:30:00"
NO_NEW_OPEN_AFTER = "14:00:00"
COST_BPS_ROUND_TRIP_S1 = 30.0  # 15 bps/side per spec §9

TRAINING_OPEN = "2021-05-01"
TRAINING_CLOSE = "2024-04-30"

SNAP_GRID = [
    "10:00:00", "10:15:00", "10:30:00", "10:45:00",
    "11:00:00", "11:15:00", "11:30:00", "11:45:00",
    "12:00:00", "12:15:00", "12:30:00", "12:45:00",
    "13:00:00", "13:15:00", "13:30:00", "13:45:00",
    "14:00:00",
]


# ----------------------- helpers ------------------------------------------

def _load_neutral_dates() -> list[str]:
    """Return sorted list of NEUTRAL trading days inside the training window."""
    out: list[str] = []
    with REGIME_TAPE.open(encoding="utf-8", newline="") as fp:
        reader = csv.DictReader(fp)
        for row in reader:
            d = row["date"]
            if not (TRAINING_OPEN <= d <= TRAINING_CLOSE):
                continue
            if row["regime"] == "NEUTRAL":
                out.append(d)
    return sorted(out)


def _load_event_days() -> set[str]:
    """Pull ±1 day around any event from the frozen event calendar."""
    if not EVENT_CALENDAR.is_file():
        return set()
    payload = json.loads(EVENT_CALENDAR.read_text(encoding="utf-8"))
    skip_window = int(payload.get("skip_window_days", 1))
    out: set[str] = set()
    from datetime import date, timedelta
    for ev in payload.get("events", []):
        d_str = ev.get("date")
        if not d_str:
            continue
        try:
            y, m, d = d_str.split("-")
            base = date(int(y), int(m), int(d))
        except Exception:
            continue
        for offset in range(-skip_window, skip_window + 1):
            out.add((base + timedelta(days=offset)).isoformat())
    return out


# ----------------------- bar loaders --------------------------------------

@dataclass
class Bar:
    time: str
    open_: float
    high: float
    low: float
    close: float
    volume: float | None


def _read_ticker_bars(ticker: str) -> dict[str, list[Bar]]:
    """Read full 5y CSV for `ticker`, bucket by date. ~75K rows × ~6 MB."""
    p = INTRADAY_5M_DIR / f"{ticker}.csv"
    if not p.is_file():
        return {}
    out: dict[str, list[Bar]] = defaultdict(list)
    with p.open(encoding="utf-8", newline="") as fp:
        reader = csv.DictReader(fp)
        for row in reader:
            dt = row.get("datetime", "")
            if " " not in dt:
                continue
            d, t = dt.split(" ", 1)
            try:
                bar = Bar(
                    time=t,
                    open_=float(row["open"]) if row.get("open") else float("nan"),
                    high=float(row["high"]) if row.get("high") else float("nan"),
                    low=float(row["low"]) if row.get("low") else float("nan"),
                    close=float(row["close"]) if row.get("close") else float("nan"),
                    volume=float(row["volume"]) if row.get("volume") else None,
                )
            except ValueError:
                continue
            if math.isnan(bar.close):
                continue
            out[d].append(bar)
    return dict(out)


def _atr_pit(daily_rows: list[dict], date_str: str, n: int = 14) -> float | None:
    """ATR(14) using only daily bars dated < date_str."""
    prior = [r for r in daily_rows if r.get("date") < date_str]
    if len(prior) < n + 1:
        return None
    trs: list[float] = []
    for i in range(len(prior) - n, len(prior)):
        h = prior[i].get("high")
        l = prior[i].get("low")
        prev_c = prior[i - 1].get("close") if i > 0 else None
        if h is None or l is None:
            return None
        tr = h - l
        if prev_c is not None:
            tr = max(tr, abs(h - prev_c), abs(l - prev_c))
        trs.append(tr)
    if not trs:
        return None
    return sum(trs) / len(trs)


# ----------------------- per-snap features --------------------------------

def _bar_at_snap(bars: list[Bar], snap_t: str) -> Bar | None:
    """First bar with time >= snap_t and within 15 minutes."""
    for b in bars:
        if b.time >= snap_t:
            sh, sm, _ = snap_t.split(":")
            bh, bm, _ = b.time.split(":")
            if int(bh) * 60 + int(bm) - (int(sh) * 60 + int(sm)) <= 15:
                return b
            return None
    return None


def _cumulative_vwap_through_snap(bars: list[Bar], snap_t: str) -> float | None:
    pre = [b for b in bars if b.time <= snap_t]
    if not pre:
        return None
    num = den = 0.0
    for b in pre:
        v = b.volume if (b.volume and b.volume > 0) else 1.0
        num += b.close * v
        den += v
    if den <= 0:
        return None
    return num / den


def _prior_60m_midpoint(bars: list[Bar], snap_t: str) -> float | None:
    """Midpoint of high/low over the 60 minutes ending at snap_t."""
    sh, sm, _ = snap_t.split(":")
    snap_min = int(sh) * 60 + int(sm)
    window_open_min = snap_min - 60
    sub: list[Bar] = []
    for b in bars:
        bh, bm, _ = b.time.split(":")
        bm_total = int(bh) * 60 + int(bm)
        if window_open_min <= bm_total < snap_min:
            sub.append(b)
    if not sub:
        return None
    return (max(b.high for b in sub) + min(b.low for b in sub)) / 2.0


def _today_realized_range_so_far(bars: list[Bar], snap_t: str) -> float | None:
    pre = [b for b in bars if b.time <= snap_t]
    if not pre:
        return None
    open_px = pre[0].open_
    if math.isnan(open_px) or open_px <= 0:
        return None
    return (max(b.high for b in pre) - min(b.low for b in pre)) / open_px


# ----------------------- core forensic loop -------------------------------

@dataclass
class TriggerRow:
    date: str
    snap_t: str
    ticker: str
    sector: str
    side: str  # LONG / SHORT
    entry_px: float
    vwap_dev_z: float
    hour_balance_dev_z: float
    range_pctile: float
    atr_14: float
    exit_px: float
    exit_reason: str  # STOP or TIME_STOP
    pnl_pct_gross: float
    pnl_pct_net_s1: float


@dataclass
class UniverseRow:
    date: str
    snap_t: str
    ticker: str
    vwap_dev_z: float | None
    hour_balance_dev_z: float | None
    range_pctile: float | None
    triggered: int


def _percentile_rank(values: list[float], target: float) -> float | None:
    """Rank of `target` within `values` as percentile [0, 100]."""
    if not values:
        return None
    less_or_equal = sum(1 for v in values if v <= target)
    return less_or_equal / len(values) * 100.0


def _simulate_forward(
    bars: list[Bar],
    snap_t: str,
    entry_px: float,
    side: str,
    stop_dist: float,
) -> tuple[float, str]:
    """Walk bars after snap; exit at stop or TIME_STOP, whichever first."""
    sign = 1.0 if side == "LONG" else -1.0
    stop_level = entry_px - sign * stop_dist
    after = [b for b in bars if b.time > snap_t]
    for b in after:
        if b.time > TIME_STOP_HHMM:
            break
        # adverse touch: LONG → low <= stop_level; SHORT → high >= stop_level
        if side == "LONG" and b.low <= stop_level:
            return stop_level, "STOP"
        if side == "SHORT" and b.high >= stop_level:
            return stop_level, "STOP"
    # no stop; exit at TIME_STOP bar close (or last available bar before)
    pre_stop = [b for b in after if b.time <= TIME_STOP_HHMM]
    if not pre_stop:
        return entry_px, "NO_BARS_AFTER"
    return pre_stop[-1].close, "TIME_STOP"


def _evaluate_day(
    date_str: str,
    universe: list[str],
    sector_map: dict[str, str],
    bars_cache: dict[str, dict[str, list[Bar]]],
    daily_cache: dict[str, list[dict]],
    range_history: dict[str, dict[str, list[float]]],
) -> tuple[list[TriggerRow], list[UniverseRow]]:
    """Process one NEUTRAL day across the universe, all snaps."""
    triggers: list[TriggerRow] = []
    universe_rows: list[UniverseRow] = []
    fired_today: set[str] = set()

    for ticker in universe:
        bars = bars_cache.get(ticker, {}).get(date_str, [])
        if not bars:
            continue
        atr = _atr_pit(daily_cache.get(ticker, []), date_str)
        if atr is None or atr <= 0:
            continue

        for snap_t in SNAP_GRID:
            snap_bar = _bar_at_snap(bars, snap_t)
            if snap_bar is None:
                continue
            snap_px = snap_bar.close

            vwap = _cumulative_vwap_through_snap(bars, snap_t)
            if vwap is None:
                universe_rows.append(UniverseRow(date_str, snap_t, ticker, None, None, None, 0))
                continue
            vwap_dev_z = (snap_px - vwap) / atr

            balance = _prior_60m_midpoint(bars, snap_t)
            hour_z: float | None = None
            if balance is not None:
                hour_z = (snap_px - balance) / atr

            r_today = _today_realized_range_so_far(bars, snap_t)
            r_pctile: float | None = None
            if r_today is not None:
                hist = range_history.get(ticker, {}).get(snap_t, [])
                if len(hist) >= 20:
                    r_pctile = _percentile_rank(hist, r_today)
                # always update history for forward dates (PIT-clean: we only
                # use entries from BEFORE date_str when computing percentile;
                # we append today's at end-of-day, never read it for today)
            if r_today is not None:
                range_history.setdefault(ticker, {}).setdefault(snap_t, []).append(r_today)

            # universe row regardless of trigger fire
            universe_rows.append(UniverseRow(
                date_str, snap_t, ticker, vwap_dev_z, hour_z, r_pctile, 0,
            ))

            # trigger gate per spec §6
            if ticker in fired_today:
                continue
            if hour_z is None or r_pctile is None:
                continue
            if abs(vwap_dev_z) < VWAP_DEV_Z_MIN:
                continue
            if abs(hour_z) < HOUR_BALANCE_Z_MIN:
                continue
            if r_pctile > RANGE_PCTILE_MAX:
                continue
            # signs aligned (both positive or both negative)
            if (vwap_dev_z > 0) != (hour_z > 0):
                continue
            if vwap_dev_z == 0 or hour_z == 0:
                continue
            if snap_t > NO_NEW_OPEN_AFTER:
                continue

            side = "SHORT" if vwap_dev_z > 0 else "LONG"
            stop_dist = ATR_STOP_MULT * atr
            exit_px, exit_reason = _simulate_forward(bars, snap_t, snap_px, side, stop_dist)
            sign = 1.0 if side == "LONG" else -1.0
            pnl_gross = sign * (exit_px - snap_px) / snap_px
            pnl_net = pnl_gross - COST_BPS_ROUND_TRIP_S1 / 1e4

            triggers.append(TriggerRow(
                date=date_str,
                snap_t=snap_t,
                ticker=ticker,
                sector=sector_map.get(ticker, ""),
                side=side,
                entry_px=snap_px,
                vwap_dev_z=vwap_dev_z,
                hour_balance_dev_z=hour_z,
                range_pctile=r_pctile,
                atr_14=atr,
                exit_px=exit_px,
                exit_reason=exit_reason,
                pnl_pct_gross=pnl_gross,
                pnl_pct_net_s1=pnl_net,
            ))
            fired_today.add(ticker)
            universe_rows[-1] = UniverseRow(
                date_str, snap_t, ticker, vwap_dev_z, hour_z, r_pctile, 1,
            )

    return triggers, universe_rows


# ----------------------- output writers ----------------------------------

def _write_trades_csv(rows: list[TriggerRow]) -> None:
    OUT_TRADES.parent.mkdir(parents=True, exist_ok=True)
    with OUT_TRADES.open("w", encoding="utf-8", newline="") as fp:
        w = csv.writer(fp)
        w.writerow([
            "date", "snap_t", "ticker", "sector", "side",
            "entry_px", "vwap_dev_z", "hour_balance_dev_z", "range_pctile",
            "atr_14", "exit_px", "exit_reason",
            "pnl_pct_gross", "pnl_pct_net_s1",
        ])
        for r in rows:
            w.writerow([
                r.date, r.snap_t, r.ticker, r.sector, r.side,
                f"{r.entry_px:.4f}", f"{r.vwap_dev_z:.4f}",
                f"{r.hour_balance_dev_z:.4f}", f"{r.range_pctile:.2f}",
                f"{r.atr_14:.4f}", f"{r.exit_px:.4f}", r.exit_reason,
                f"{r.pnl_pct_gross:.6f}", f"{r.pnl_pct_net_s1:.6f}",
            ])


def _write_universe_csv(rows: list[UniverseRow]) -> None:
    with OUT_UNIVERSE.open("w", encoding="utf-8", newline="") as fp:
        w = csv.writer(fp)
        w.writerow([
            "date", "snap_t", "ticker",
            "vwap_dev_z", "hour_balance_dev_z", "range_pctile", "triggered",
        ])
        for r in rows:
            w.writerow([
                r.date, r.snap_t, r.ticker,
                f"{r.vwap_dev_z:.4f}" if r.vwap_dev_z is not None else "",
                f"{r.hour_balance_dev_z:.4f}" if r.hour_balance_dev_z is not None else "",
                f"{r.range_pctile:.2f}" if r.range_pctile is not None else "",
                r.triggered,
            ])


def _summarise(trades: list[TriggerRow], n_neutral_days: int) -> dict:
    """Headline stats + per-sector breakdown."""
    if not trades:
        return {
            "n_neutral_days": n_neutral_days,
            "n_triggers": 0,
            "trigger_rate_per_day": 0.0,
            "headline": "no triggers fired — setup may be too narrow for NEUTRAL",
        }
    pnls_net = [t.pnl_pct_net_s1 for t in trades]
    pnls_gross = [t.pnl_pct_gross for t in trades]
    hits = sum(1 for p in pnls_net if p > 0)
    mean_net = statistics.fmean(pnls_net)
    sd_net = statistics.pstdev(pnls_net) if len(pnls_net) > 1 else 0.0
    sharpe_per_trade = mean_net / sd_net if sd_net > 0 else 0.0
    trades_per_year = len(trades) / (n_neutral_days / 252.0) if n_neutral_days else 0.0
    sharpe_annual = sharpe_per_trade * (trades_per_year ** 0.5) if trades_per_year > 0 else 0.0

    by_sector: dict[str, dict] = {}
    sec_groups: dict[str, list[float]] = defaultdict(list)
    for t in trades:
        sec_groups[t.sector or "UNKNOWN"].append(t.pnl_pct_net_s1)
    for sec, ps in sec_groups.items():
        if len(ps) >= 5:
            by_sector[sec] = {
                "n": len(ps),
                "mean_bps": statistics.fmean(ps) * 1e4,
                "hit_rate": sum(1 for p in ps if p > 0) / len(ps),
            }

    by_side = {
        "LONG": [t.pnl_pct_net_s1 for t in trades if t.side == "LONG"],
        "SHORT": [t.pnl_pct_net_s1 for t in trades if t.side == "SHORT"],
    }
    side_summary = {
        side: {
            "n": len(ps),
            "mean_bps": statistics.fmean(ps) * 1e4 if ps else 0.0,
            "hit_rate": (sum(1 for p in ps if p > 0) / len(ps)) if ps else 0.0,
        }
        for side, ps in by_side.items()
    }

    by_exit = defaultdict(list)
    for t in trades:
        by_exit[t.exit_reason].append(t.pnl_pct_net_s1)
    exit_summary = {
        reason: {
            "n": len(ps),
            "mean_bps": statistics.fmean(ps) * 1e4,
            "hit_rate": sum(1 for p in ps if p > 0) / len(ps),
        }
        for reason, ps in by_exit.items() if len(ps) >= 5
    }

    z_buckets = [(1.75, 2.0), (2.0, 2.5), (2.5, 3.0), (3.0, 4.0), (4.0, 99.0)]
    by_zbucket = {}
    for lo, hi in z_buckets:
        ps = [t.pnl_pct_net_s1 for t in trades if lo <= abs(t.vwap_dev_z) < hi]
        if len(ps) >= 5:
            by_zbucket[f"|vwap_z|_{lo:.2f}-{hi:.2f}"] = {
                "n": len(ps),
                "mean_bps": statistics.fmean(ps) * 1e4,
                "hit_rate": sum(1 for p in ps if p > 0) / len(ps),
            }

    return {
        "n_neutral_days": n_neutral_days,
        "n_triggers": len(trades),
        "trigger_rate_per_day": len(trades) / n_neutral_days if n_neutral_days else 0.0,
        "n_unique_tickers_fired": len({t.ticker for t in trades}),
        "headline": {
            "mean_bps_gross": statistics.fmean(pnls_gross) * 1e4,
            "mean_bps_net_s1": mean_net * 1e4,
            "hit_rate": hits / len(trades),
            "sharpe_per_trade_net_s1": sharpe_per_trade,
            "sharpe_annual_net_s1": sharpe_annual,
        },
        "by_side": side_summary,
        "by_sector": by_sector,
        "by_exit_reason": exit_summary,
        "by_vwap_z_bucket": by_zbucket,
        "spec_thresholds": {
            "vwap_dev_z_min": VWAP_DEV_Z_MIN,
            "hour_balance_z_min": HOUR_BALANCE_Z_MIN,
            "range_pctile_max": RANGE_PCTILE_MAX,
            "atr_stop_mult": ATR_STOP_MULT,
            "cost_bps_round_trip_s1": COST_BPS_ROUND_TRIP_S1,
        },
        "training_window": [TRAINING_OPEN, TRAINING_CLOSE],
    }


# ----------------------- public runner -----------------------------------

def run() -> dict:
    log.info("loading universe...")
    universe = list(json.loads(UNIVERSE_FROZEN.read_text(encoding="utf-8"))["tickers"])
    sector_map = dict(json.loads(SECTOR_MAP_FROZEN.read_text(encoding="utf-8"))["sector_map"])

    log.info("loading NEUTRAL day list + event days...")
    neutral_dates = _load_neutral_dates()
    event_days = _load_event_days()
    eligible_dates = [d for d in neutral_dates if d not in event_days]
    log.info(
        "training window NEUTRAL days: %d (after event-skip: %d)",
        len(neutral_dates), len(eligible_dates),
    )

    log.info("preloading 5m bars for %d tickers...", len(universe))
    bars_cache: dict[str, dict[str, list[Bar]]] = {}
    daily_cache: dict[str, list[dict]] = {}
    for i, t in enumerate(universe, 1):
        bars_cache[t] = _read_ticker_bars(t)
        daily_cache[t] = _load_daily_ohlc(t)
        if i % 25 == 0:
            log.info("  preloaded %d / %d", i, len(universe))

    log.info("evaluating %d NEUTRAL days...", len(eligible_dates))
    range_history: dict[str, dict[str, list[float]]] = {}
    all_trades: list[TriggerRow] = []
    all_universe: list[UniverseRow] = []

    for i, date_str in enumerate(eligible_dates, 1):
        triggers, universe_rows = _evaluate_day(
            date_str, universe, sector_map,
            bars_cache, daily_cache, range_history,
        )
        all_trades.extend(triggers)
        all_universe.extend(universe_rows)
        if i % 25 == 0:
            log.info(
                "  day %d / %d -- triggers so far: %d",
                i, len(eligible_dates), len(all_trades),
            )

    log.info("writing outputs (%d triggers, %d universe rows)",
             len(all_trades), len(all_universe))
    _write_trades_csv(all_trades)
    _write_universe_csv(all_universe)
    summary = _summarise(all_trades, len(eligible_dates))
    OUT_SUMMARY.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    log.info("done. summary -> %s", OUT_SUMMARY)
    return summary


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    summary = run()
    print(json.dumps(summary["headline"], indent=2))
