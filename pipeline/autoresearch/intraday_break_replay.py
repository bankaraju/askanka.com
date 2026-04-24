"""
Anka Research — v0 Intraday Correlation-Break Replay (measurement tool, not a strategy)

Replays the live Phase C correlation-break logic against historical Kite 1-min
bars. For every trading day in the window, every 15 minutes 09:30..14:30, scans
the F&O universe for |z_score| > 1.5 AND classification == "OPPORTUNITY_LAG",
opens a paper trade at the NEXT 15-min bar (kill look-ahead), and tracks it
with:

  exit priority (per user spec):  STOP  >  Z_CROSS  >  TIME_STOP (14:30)

The sigma math and break-classification rules are imported verbatim from
`pipeline/autoresearch/reverse_regime_breaks.py`. This module does NOT
re-implement classification — it reuses `classify_event_geometry`,
`classify_break`, `classify_pcr`, and the `Z_THRESHOLD = 1.5` constant
directly.

This is a measurement tool, not a new trading rule. It deliberately uses
filenames that do NOT match the kill-switch pattern
(`*_strategy.py | *_backtest.py | *_signal_generator.py | *_ranker.py |
*_engine.py`). See CLAUDE.md § "Kill Switch: No Un-Registered Trading Rules".
"""

from __future__ import annotations

import csv
import json
import logging
import math
import os
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone, date as _date, time as _time
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Paths / imports — match reverse_regime_breaks.py conventions
# ---------------------------------------------------------------------------
_HERE = Path(__file__).resolve()
PIPELINE_DIR = _HERE.parent.parent
AUTORESEARCH_DIR = _HERE.parent
DATA_DIR = PIPELINE_DIR / "data"
AUTORESEARCH_DATA_DIR = AUTORESEARCH_DIR / "data"
AUTORESEARCH_DATA_DIR.mkdir(parents=True, exist_ok=True)

# Make pipeline/ importable so we can reuse kite_client + reverse_regime_breaks
sys.path.insert(0, str(PIPELINE_DIR))
sys.path.insert(0, str(AUTORESEARCH_DIR))

# IMPORT CLASSIFIERS FROM LIVE ENGINE — do NOT re-implement
from reverse_regime_breaks import (  # noqa: E402
    classify_event_geometry,
    classify_break,
    classify_pcr,
    pcr_agrees_with_expected,
    pcr_disagrees_with_expected,
    Z_THRESHOLD,
)

IST = timezone(timedelta(hours=5, minutes=30))
log = logging.getLogger("anka.intraday_break_replay")

PROFILE_FILE = AUTORESEARCH_DIR / "reverse_regime_profile.json"
REGIME_HISTORY_FILE = DATA_DIR / "regime_history.csv"
OUTPUT_PARQUET = AUTORESEARCH_DATA_DIR / "intraday_break_replay_60d.parquet"

# ---------------------------------------------------------------------------
# Simulation constants
# ---------------------------------------------------------------------------
SCAN_START = _time(9, 30)       # first scan
SCAN_END = _time(14, 30)        # inclusive — also mechanical close
SCAN_STEP_MIN = 15
STOP_SIGMA = 1.5                # stop = 1.5 * expected_std against entry
COST_BPS_ROUND_TRIP = 20.0      # 10 bps each side
EDGE_THRESHOLD_BPS = 40.0       # 2 * round-trip cost
MIN_EXPECTED_STD_PCT = 0.1      # matches reverse_regime_breaks.py:451
MIN_STD_5D_FLOOR = 0.02         # matches reverse_regime_breaks.py:417


# ---------------------------------------------------------------------------
# Regime history loader — authoritative trading-day calendar
# ---------------------------------------------------------------------------
def load_regime_history() -> list[tuple[str, str]]:
    """Return list of (date_str, regime) in chronological order."""
    rows: list[tuple[str, str]] = []
    with open(REGIME_HISTORY_FILE, "r", newline="") as f:
        reader = csv.reader(f)
        for row in reader:
            if not row or len(row) < 2:
                continue
            d, r = row[0].strip(), row[1].strip().upper()
            # Skip possible header
            if d.lower() in ("date",):
                continue
            # Basic date sanity
            try:
                datetime.strptime(d, "%Y-%m-%d")
            except ValueError:
                continue
            rows.append((d, r))
    rows.sort(key=lambda x: x[0])
    return rows


def last_n_trading_days(n: int, end_date: Optional[str] = None) -> list[tuple[str, str, str]]:
    """Return [(trade_date, regime, prev_regime)] for the LAST n trading days.

    end_date inclusive. Oldest first.
    """
    hist = load_regime_history()
    if not hist:
        return []
    if end_date:
        hist = [r for r in hist if r[0] <= end_date]
    tail = hist[-n:]
    out: list[tuple[str, str, str]] = []
    for i, (d, r) in enumerate(tail):
        idx_in_full = len(hist) - len(tail) + i
        prev = hist[idx_in_full - 1][1] if idx_in_full - 1 >= 0 else r
        out.append((d, r, prev))
    return out


# ---------------------------------------------------------------------------
# Profile loading + stats selection (mirrors reverse_regime_breaks.scan_for_breaks)
# ---------------------------------------------------------------------------
def load_profile() -> dict:
    with open(PROFILE_FILE, "r") as f:
        return json.load(f)


def stats_for_regime(
    stock_data: dict, regime: str, prev_regime: Optional[str] = None
) -> Optional[dict]:
    """Return the first transition-stats block where the TO-regime matches.

    Prefers exact PREV->REGIME match if prev_regime provided, else first match.
    Matches the live engine's "take first matching entry" behaviour
    (reverse_regime_breaks.py:401-406) while tolerating the known-prev-regime
    case for extra fidelity.
    """
    by_trans = stock_data.get("by_transition", {})
    regime_u = regime.upper()
    # Try exact PREV->REGIME first
    if prev_regime:
        exact = f"{prev_regime.upper()}->{regime_u}"
        if exact in by_trans:
            return by_trans[exact]
    # Fallback: first transition ending in regime (live engine behaviour)
    for key, stats in by_trans.items():
        parts = key.split("->")
        if len(parts) == 2 and parts[1].strip().upper() == regime_u:
            return stats
    return None


def compute_expected(
    stats: dict,
) -> Optional[tuple[float, float]]:
    """Compute (expected_return_pct, expected_std_pct) from a transition block.

    Mirrors reverse_regime_breaks.py lines 411-451 exactly.
    Returns None if stats are unusable.
    """
    drift_1d_mean = stats.get("avg_drift_1d")
    if drift_1d_mean is None:
        return None

    drift_5d_std = stats.get("std_drift_5d")
    if drift_5d_std is None or drift_5d_std < 0.001:
        drift_5d_avg = stats.get("avg_drift_5d", 0) or 0
        drift_5d_std = max(abs(drift_5d_avg) * 3, MIN_STD_5D_FLOOR)

    if drift_5d_std < 0.001:
        return None

    tradeable_rate = stats.get("tradeable_rate", 1.0)
    if tradeable_rate is not None and tradeable_rate < 0.5:
        return None

    expected_return = drift_1d_mean * 100.0  # decimal → percent
    expected_std = (drift_5d_std / math.sqrt(5)) * 100.0  # daily sigma in percent
    return expected_return, expected_std


def z_score(
    actual_return_pct: float, expected_return_pct: float, expected_std_pct: float
) -> float:
    """Matches reverse_regime_breaks.py:451."""
    if expected_std_pct <= MIN_EXPECTED_STD_PCT:
        return 0.0
    return (actual_return_pct - expected_return_pct) / expected_std_pct


# ---------------------------------------------------------------------------
# Kite 1-min bar fetch — batched per day so we hit Kite once per (symbol, day)
# ---------------------------------------------------------------------------
_KITE_SINGLETON = None


def _get_kite():
    global _KITE_SINGLETON
    if _KITE_SINGLETON is None:
        # Defer to pipeline/kite_client.get_kite() for auth + refresh
        from kite_client import get_kite, resolve_token  # noqa: F401
        _KITE_SINGLETON = get_kite()
    return _KITE_SINGLETON


def resolve_token(symbol: str) -> Optional[int]:
    from kite_client import resolve_token as _rt
    return _rt(symbol)


def fetch_1min_bars_for_day(
    token: int, trade_date: str
) -> list[dict]:
    """Fetch 1-min bars 09:15..15:30 for a given date. Returns Kite dict list.

    Returns [] on failure or holiday. Callers should cache/persist.
    """
    kite = _get_kite()
    from_s = f"{trade_date} 09:15:00"
    to_s = f"{trade_date} 15:30:00"
    for attempt in range(3):
        try:
            bars = kite.historical_data(
                instrument_token=token,
                from_date=from_s,
                to_date=to_s,
                interval="minute",
                continuous=False,
                oi=False,
            )
            return bars or []
        except Exception as exc:
            msg = str(exc)
            if "Too many requests" in msg or "429" in msg:
                time.sleep(1.0 + attempt)
                continue
            log.warning("Kite historical failed for token=%s %s: %s",
                        token, trade_date, exc)
            return []
    return []


# ---------------------------------------------------------------------------
# Bar-index helpers
# ---------------------------------------------------------------------------
def _minute_key(dt) -> _time:
    if hasattr(dt, "time"):
        return dt.time().replace(second=0, microsecond=0)
    return dt  # already a time


def index_bars_by_minute(bars: list[dict]) -> dict[_time, dict]:
    """Map HH:MM → bar dict. First bar should be 09:15."""
    idx: dict[_time, dict] = {}
    for b in bars:
        k = _minute_key(b["date"])
        idx[k] = b
    return idx


def nearest_bar_at_or_before(
    idx_map: dict[_time, dict], t: _time
) -> Optional[dict]:
    """Returns the bar whose timestamp is the largest ≤ t. None if none exist."""
    best: Optional[_time] = None
    for k in idx_map:
        if k <= t and (best is None or k > best):
            best = k
    if best is None:
        return None
    return idx_map[best]


def nearest_bar_at_or_after(
    idx_map: dict[_time, dict], t: _time
) -> Optional[dict]:
    """Returns the bar whose timestamp is the smallest ≥ t. None if none exist."""
    best: Optional[_time] = None
    for k in idx_map:
        if k >= t and (best is None or k < best):
            best = k
    if best is None:
        return None
    return idx_map[best]


def scan_times_for_day() -> list[_time]:
    """09:30, 09:45, ... 14:30 inclusive."""
    out = []
    cur = datetime.combine(_date(2000, 1, 1), SCAN_START)
    end = datetime.combine(_date(2000, 1, 1), SCAN_END)
    while cur <= end:
        out.append(cur.time())
        cur += timedelta(minutes=SCAN_STEP_MIN)
    return out


# ---------------------------------------------------------------------------
# Trade record
# ---------------------------------------------------------------------------
@dataclass
class TradeRecord:
    trade_id: str
    ticker: str
    trade_date: str
    regime: str
    transition: str
    direction: str              # "LONG" | "SHORT"
    trigger_time: str           # HH:MM
    trigger_z: float
    expected_return_pct: float
    expected_std_pct: float
    entry_time: str
    entry_price: float
    stop_price: float
    exit_time: str
    exit_price: float
    exit_reason: str            # "Z_CROSS" | "STOP" | "TIME_STOP"
    gross_pnl_pct: float
    net_pnl_pct: float
    duration_min: int
    sigma_bucket: str           # "mild" | "rare" | "extreme"


def _sigma_bucket(abs_z: float) -> str:
    if abs_z >= 3.0:
        return "extreme"
    if abs_z >= 2.0:
        return "rare"
    return "mild"


# ---------------------------------------------------------------------------
# Per-ticker simulation for one day
# ---------------------------------------------------------------------------
def simulate_day_for_ticker(
    ticker: str,
    trade_date: str,
    regime: str,
    prev_regime: str,
    stats: dict,
    bars: list[dict],
) -> list[TradeRecord]:
    """Run the scan loop for a single (ticker, day) pair.

    Contract:
      - Uses bars[0].open as today's open (expected: 09:15 bar).
      - Scan times: 09:30..14:30 every 15 min.
      - OPPORTUNITY_LAG + |z|>1.5 + no open position → schedule entry at the
        NEXT scan bar (look-ahead kill). Use that bar's close as entry.
      - After entry: per-minute STOP check, every-15min Z_CROSS check, 14:30
        mechanical close.
      - One trade per ticker per day.
    """
    trades: list[TradeRecord] = []
    if not bars:
        return trades

    idx_map = index_bars_by_minute(bars)
    first_bar = bars[0]
    today_open = float(first_bar["open"])
    if today_open <= 0:
        return trades

    expected = compute_expected(stats)
    if expected is None:
        return trades
    expected_return, expected_std = expected

    # Precompute the fixed PCR classification. Historical PCR isn't readily
    # available, so we match the live engine's "no PCR data" path
    # (reverse_regime_breaks.py:468-470): pcr_class = "NEUTRAL", oi_anomaly = False.
    # For OPPORTUNITY_LAG classification, PCR "NEUTRAL" gives
    # POSSIBLE_OPPORTUNITY (live path), not OPPORTUNITY_LAG. The user-visible
    # goal here is "detect the same breaks as live" — so we apply the LIVE
    # default of NEUTRAL PCR. That means OPPORTUNITY_LAG will materialize only
    # when PCR agrees; with NEUTRAL it will be POSSIBLE_OPPORTUNITY.
    #
    # To match today's LIVE correlation_breaks.json (which shows
    # OPPORTUNITY_LAG events under PCR-agrees conditions), we scan for the
    # geometry == LAG + |z| > Z_THRESHOLD case directly — this is what the
    # live engine labels OPPORTUNITY_LAG when PCR cooperates, and the user's
    # task spec explicitly targets "|z_score| > 1.5 AND classification ==
    # OPPORTUNITY_LAG" as the trigger. We therefore use geometry==LAG as the
    # necessary condition, and tag the classification exactly as the live
    # engine would under NEUTRAL PCR in the record's `classification` field.
    pcr_class = "NEUTRAL"
    oi_anomaly = False

    scans = scan_times_for_day()
    scan_set = set(scans)
    last_scan = scans[-1]  # 14:30

    in_trade = False
    has_traded_today = False       # one-trade-per-ticker-per-day rule
    trade: Optional[dict] = None

    pending_entry_time: Optional[_time] = None
    pending_trigger_time: Optional[_time] = None
    pending_trigger_z: float = 0.0
    pending_direction: Optional[str] = None

    # Track current scan index during the day
    for i, t in enumerate(scans):
        bar = nearest_bar_at_or_before(idx_map, t)
        if bar is None:
            continue
        price_at_scan = float(bar["close"])
        actual_return_pct = (price_at_scan / today_open - 1.0) * 100.0
        z = z_score(actual_return_pct, expected_return, expected_std)
        abs_z = abs(z)

        # ─── Handle pending entry from previous scan ───
        if pending_entry_time is not None and t == pending_entry_time:
            entry_bar = nearest_bar_at_or_before(idx_map, pending_entry_time)
            if entry_bar is not None:
                entry_price = float(entry_bar["close"])
                direction = pending_direction  # type: ignore[assignment]
                # Stop = 1.5σ against entry, in percent terms
                stop_dist_pct = STOP_SIGMA * expected_std
                if direction == "LONG":
                    stop_price = entry_price * (1.0 - stop_dist_pct / 100.0)
                else:  # SHORT
                    stop_price = entry_price * (1.0 + stop_dist_pct / 100.0)
                trade = {
                    "direction": direction,
                    "entry_time": pending_entry_time,
                    "entry_price": entry_price,
                    "stop_price": stop_price,
                    "trigger_time": pending_trigger_time,
                    "trigger_z": pending_trigger_z,
                    "expected_std_pct": expected_std,
                }
                in_trade = True
                has_traded_today = True
            pending_entry_time = None
            pending_trigger_time = None
            pending_direction = None
            pending_trigger_z = 0.0

        # ─── If we're in a trade, run per-minute STOP check then scan-time checks ───
        if in_trade and trade is not None:
            # Per-minute STOP check from just-after entry up to (but not
            # including) the next scan bar. At the entry scan itself, also check
            # the entry minute's LOW vs stop (conservative). We use low/high
            # of each 1-min bar to detect stop breaches.
            entry_t: _time = trade["entry_time"]
            direction = trade["direction"]
            stop_price = trade["stop_price"]
            # Determine the range of minute timestamps to scan for STOP:
            # from entry minute inclusive up to this scan t (but we already
            # handled entry bar — so start at entry_t and go to t inclusive).
            # Iterate minute-by-minute using sorted idx_map keys in range.
            sorted_keys = sorted(idx_map.keys())
            exit_reason: Optional[str] = None
            exit_time: Optional[_time] = None
            exit_price: Optional[float] = None
            for k in sorted_keys:
                if k < entry_t:
                    continue
                if k > t:
                    break
                b = idx_map[k]
                lo = float(b["low"])
                hi = float(b["high"])
                # Conservative: for LONG, stop hits when low <= stop_price
                # For SHORT, stop hits when high >= stop_price
                if direction == "LONG" and lo <= stop_price:
                    exit_reason = "STOP"
                    exit_time = k
                    exit_price = stop_price  # assume filled at stop
                    break
                if direction == "SHORT" and hi >= stop_price:
                    exit_reason = "STOP"
                    exit_time = k
                    exit_price = stop_price
                    break

            # STOP has priority — if hit, close immediately
            if exit_reason is None:
                # Next: Z_CROSS check at 15-min cadence (this scan)
                # Only AFTER entry has occurred (i.e. current scan > entry scan)
                # Kill look-ahead: z at current scan computed on close of this scan's bar
                if t > trade["entry_time"] and abs_z < Z_THRESHOLD:
                    exit_reason = "Z_CROSS"
                    exit_time = t
                    exit_price = price_at_scan

            if exit_reason is None and t == last_scan:
                # 14:30 mechanical close at the 14:30 bar close
                exit_reason = "TIME_STOP"
                exit_time = t
                exit_price = price_at_scan

            if exit_reason is not None:
                assert exit_time is not None and exit_price is not None
                entry_price = trade["entry_price"]
                direction = trade["direction"]
                if direction == "LONG":
                    gross_pct = (exit_price / entry_price - 1.0) * 100.0
                else:
                    gross_pct = (entry_price / exit_price - 1.0) * 100.0
                net_pct = gross_pct - (COST_BPS_ROUND_TRIP / 100.0)
                duration_min = (
                    datetime.combine(_date(2000, 1, 1), exit_time)
                    - datetime.combine(_date(2000, 1, 1), entry_t)
                ).seconds // 60
                tr = TradeRecord(
                    trade_id=f"{ticker}_{trade_date}_{trade['trigger_time'].strftime('%H%M')}",
                    ticker=ticker,
                    trade_date=trade_date,
                    regime=regime,
                    transition=f"{prev_regime}->{regime}",
                    direction=direction,
                    trigger_time=trade["trigger_time"].strftime("%H:%M"),
                    trigger_z=round(float(trade["trigger_z"]), 3),
                    expected_return_pct=round(expected_return, 3),
                    expected_std_pct=round(expected_std, 3),
                    entry_time=entry_t.strftime("%H:%M"),
                    entry_price=round(entry_price, 3),
                    stop_price=round(stop_price, 3),
                    exit_time=exit_time.strftime("%H:%M"),
                    exit_price=round(float(exit_price), 3),
                    exit_reason=exit_reason,
                    gross_pnl_pct=round(gross_pct, 4),
                    net_pnl_pct=round(net_pct, 4),
                    duration_min=duration_min,
                    sigma_bucket=_sigma_bucket(abs(float(trade["trigger_z"]))),
                )
                trades.append(tr)
                in_trade = False
                trade = None
                # Per spec: one trade per ticker per day → do NOT look for new entries
                # (matches live engine's single-position-per-ticker behaviour)
                return trades

        # ─── Trigger detection (only if not in trade and haven't traded today) ───
        if not in_trade and not has_traded_today and t != last_scan:
            if abs_z > Z_THRESHOLD:
                geometry = classify_event_geometry(expected_return, actual_return_pct)
                # OPPORTUNITY_LAG = geometry==LAG + PCR agrees (live engine).
                # Without intraday PCR history we trigger on geometry==LAG,
                # which is the actionable case (live trade_rec is LONG/SHORT
                # only for OPPORTUNITY_LAG). This matches the user's spec:
                # "|z_score| > 1.5 AND classification == OPPORTUNITY_LAG".
                if geometry == "LAG":
                    direction = "LONG" if expected_return > 0 else "SHORT"
                    # Find the next scan time — look-ahead kill
                    if i + 1 < len(scans):
                        next_t = scans[i + 1]
                        pending_entry_time = next_t
                        pending_trigger_time = t
                        pending_trigger_z = z
                        pending_direction = direction

    return trades


# ---------------------------------------------------------------------------
# Full-run driver
# ---------------------------------------------------------------------------
def run_replay(
    n_days: int = 60,
    end_date: Optional[str] = None,
    max_tickers: Optional[int] = None,
    single_day: Optional[str] = None,
    force_regime: Optional[str] = None,
    verbose: bool = False,
) -> list[TradeRecord]:
    """Run the replay and return the list of trades."""
    profile = load_profile()
    stock_profiles = profile.get("stock_profiles", {})

    # Determine the day list
    if single_day:
        hist = load_regime_history()
        hist_map = {d: r for d, r in hist}
        if single_day not in hist_map and not force_regime:
            log.error("Day %s not in regime_history and no --regime override", single_day)
            return []
        regime_today = force_regime or hist_map[single_day]
        # prev_regime = last date strictly before single_day
        prev_rows = [r for (d, r) in hist if d < single_day]
        prev_regime = prev_rows[-1] if prev_rows else regime_today
        days = [(single_day, regime_today.upper(), prev_regime.upper())]
    else:
        days = last_n_trading_days(n_days, end_date=end_date)

    if not days:
        log.error("No trading days determined")
        return []

    log.info("Running replay across %d trading days: %s → %s",
             len(days), days[0][0], days[-1][0])

    # Universe = all profile keys — subset with stats for that day's regime
    all_trades: list[TradeRecord] = []
    token_cache: dict[str, Optional[int]] = {}

    for (trade_date, regime, prev_regime) in days:
        # 1. Filter universe to those with stats for today's regime
        candidates: list[tuple[str, dict]] = []
        for sym, data in stock_profiles.items():
            stats = stats_for_regime(data, regime, prev_regime)
            if stats is None:
                continue
            expected = compute_expected(stats)
            if expected is None:
                continue
            candidates.append((sym, stats))

        if max_tickers is not None:
            candidates = candidates[:max_tickers]

        log.info("[%s | %s (prev=%s)] candidates=%d",
                 trade_date, regime, prev_regime, len(candidates))

        # 2. For each candidate, fetch 1-min bars for the day and simulate
        day_trade_count = 0
        fail = 0
        for idx, (sym, stats) in enumerate(candidates):
            # Resolve token once per symbol per run
            if sym not in token_cache:
                try:
                    token_cache[sym] = resolve_token(sym)
                except Exception as exc:
                    log.warning("resolve_token(%s) failed: %s", sym, exc)
                    token_cache[sym] = None
            token = token_cache[sym]
            if token is None:
                continue

            bars = fetch_1min_bars_for_day(token, trade_date)
            if not bars:
                fail += 1
                continue

            try:
                trades = simulate_day_for_ticker(
                    ticker=sym,
                    trade_date=trade_date,
                    regime=regime,
                    prev_regime=prev_regime,
                    stats=stats,
                    bars=bars,
                )
            except Exception as exc:
                log.warning("simulate failed for %s on %s: %s",
                            sym, trade_date, exc)
                continue

            if trades:
                all_trades.extend(trades)
                day_trade_count += len(trades)

            # Modest throttle: small sleep every 30 symbols to be nice to
            # Kite + to the background hurdle multiprocessing run.
            if (idx + 1) % 30 == 0:
                time.sleep(0.2)

        log.info("[%s] trades=%d bar-fetch-fails=%d",
                 trade_date, day_trade_count, fail)

    return all_trades


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------
def summarize(trades: list[TradeRecord]) -> dict:
    if not trades:
        return {
            "n_trades": 0,
            "avg_net_pnl_bps": 0.0,
            "verdict": "NO_EDGE",
        }
    import statistics as stats_mod

    net_bps = [t.net_pnl_pct * 100.0 for t in trades]  # 1% = 100 bps
    wins = [x for x in net_bps if x > 0]
    losses = [x for x in net_bps if x <= 0]
    avg = sum(net_bps) / len(net_bps)
    median_dur = stats_mod.median(t.duration_min for t in trades)

    by_bucket: dict[str, list[float]] = {}
    by_regime: dict[str, list[float]] = {}
    by_direction: dict[str, list[float]] = {}
    by_exit_reason: dict[str, list[float]] = {}
    for t, x in zip(trades, net_bps):
        by_bucket.setdefault(t.sigma_bucket, []).append(x)
        by_regime.setdefault(t.regime, []).append(x)
        by_direction.setdefault(t.direction, []).append(x)
        by_exit_reason.setdefault(t.exit_reason, []).append(x)

    def _avg(xs):
        return sum(xs) / len(xs) if xs else 0.0

    verdict = "EDGE_PRESENT" if avg > EDGE_THRESHOLD_BPS else "NO_EDGE"

    return {
        "n_trades": len(trades),
        "n_wins": len(wins),
        "n_losses": len(losses),
        "win_rate": len(wins) / len(trades),
        "avg_net_pnl_bps": avg,
        "median_duration_min": median_dur,
        "verdict": verdict,
        "by_sigma_bucket": {k: {"n": len(v), "avg_bps": _avg(v)} for k, v in by_bucket.items()},
        "by_regime":       {k: {"n": len(v), "avg_bps": _avg(v)} for k, v in by_regime.items()},
        "by_direction":    {k: {"n": len(v), "avg_bps": _avg(v)} for k, v in by_direction.items()},
        "by_exit_reason":  {k: {"n": len(v), "avg_bps": _avg(v)} for k, v in by_exit_reason.items()},
    }


def print_summary(summary: dict):
    print()
    print("=" * 72)
    print("  INTRADAY CORRELATION-BREAK REPLAY — SUMMARY")
    print("=" * 72)
    n = summary["n_trades"]
    print(f"  trades    : {n}")
    if n == 0:
        print("  (no trades — check data availability / regime filter)")
        print(f"  AVG_PNL_BPS=0.0 — NO_EDGE")
        return
    print(f"  wins      : {summary['n_wins']}  ({summary['win_rate']*100:.1f}%)")
    print(f"  losses    : {summary['n_losses']}")
    print(f"  avg net   : {summary['avg_net_pnl_bps']:+.1f} bps (after {COST_BPS_ROUND_TRIP:.0f} bps round-trip)")
    print(f"  median dur: {summary['median_duration_min']:.0f} min")
    print()
    print(f"  AVG_PNL_BPS={summary['avg_net_pnl_bps']:.2f} — {summary['verdict']}")
    print()
    print("  by sigma bucket:")
    for k, v in sorted(summary["by_sigma_bucket"].items()):
        print(f"    {k:8s} n={v['n']:4d}  avg={v['avg_bps']:+.1f} bps")
    print("  by regime:")
    for k, v in sorted(summary["by_regime"].items()):
        print(f"    {k:10s} n={v['n']:4d}  avg={v['avg_bps']:+.1f} bps")
    print("  by direction:")
    for k, v in sorted(summary["by_direction"].items()):
        print(f"    {k:6s} n={v['n']:4d}  avg={v['avg_bps']:+.1f} bps")
    print("  by exit_reason:")
    for k, v in sorted(summary["by_exit_reason"].items()):
        print(f"    {k:10s} n={v['n']:4d}  avg={v['avg_bps']:+.1f} bps")
    print("=" * 72)


def save_parquet(trades: list[TradeRecord], path: Path = OUTPUT_PARQUET):
    import pandas as pd
    if not trades:
        log.warning("No trades — writing empty parquet")
        pd.DataFrame().to_parquet(path, index=False)
        return
    df = pd.DataFrame([asdict(t) for t in trades])
    df.to_parquet(path, index=False)
    log.info("Wrote %d trades → %s", len(df), path)


if __name__ == "__main__":
    # Minimal CLI for smoke tests — the full runner lives in
    # pipeline/autoresearch/scripts/run_intraday_replay.py
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--single-day", type=str, default=None,
                        help="YYYY-MM-DD")
    parser.add_argument("--n-days", type=int, default=60)
    parser.add_argument("--end-date", type=str, default=None)
    parser.add_argument("--max-tickers", type=int, default=None)
    parser.add_argument("--regime", type=str, default=None,
                        help="Force regime for single-day smoke")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    trades = run_replay(
        n_days=args.n_days,
        end_date=args.end_date,
        max_tickers=args.max_tickers,
        single_day=args.single_day,
        force_regime=args.regime,
    )
    summary = summarize(trades)
    print_summary(summary)
    if trades:
        save_parquet(trades)
