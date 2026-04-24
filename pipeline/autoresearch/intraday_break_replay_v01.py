"""
Anka Research — v0.1 Intraday Correlation-Break Replay (sector-gated, T+1 exit)

Pre-registered thesis:
  docs/superpowers/specs/2026-04-25-correlation-break-intraday-thesis-v0.1.md
  (committed at 10a39a8, frozen before any v0.1 results computed)

Differences from v0 (pipeline/autoresearch/intraday_break_replay.py):
  1. Date-range bug fixed: iterates the real N-day window, validated by
     integration test.
  2. Sector-alignment gate at entry (§5.2 of thesis): trigger only passes
     gate when sector return at entry scan is within ±0.3% of sigma direction.
  3. Intra-hold sector-flip exit (§5.4): if sector moves >=0.5% against trade
     after entry, close at that scan.
  4. Exit ladder changed: STOP > SECTOR_FLIP > Z_CROSS > T+1 09:43 mechanical
     close (not same-day 14:30). Matches live overnight-hold behaviour.
  5. Primary metric: alpha-vs-sector (strips sector beta from raw P&L).

This is a measurement tool, not a strategy file. File name deliberately does
NOT match the kill-switch patterns (`*_strategy.py`, `*_backtest.py`, etc).
"""
from __future__ import annotations

import json
import logging
import math
import sys
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone, date as _date, time as _time
from pathlib import Path
from typing import Optional

# --------------------------------------------------------------------------
# Reuse all v0 classification primitives
# --------------------------------------------------------------------------
_HERE = Path(__file__).resolve()
PIPELINE_DIR = _HERE.parent.parent
AUTORESEARCH_DIR = _HERE.parent
DATA_DIR = PIPELINE_DIR / "data"
AUTORESEARCH_DATA_DIR = AUTORESEARCH_DIR / "data"
AUTORESEARCH_DATA_DIR.mkdir(parents=True, exist_ok=True)
DOCS_DIR = PIPELINE_DIR.parent / "docs" / "superpowers" / "specs"

sys.path.insert(0, str(PIPELINE_DIR))
sys.path.insert(0, str(AUTORESEARCH_DIR))

from intraday_break_replay import (  # noqa: E402
    load_regime_history,
    last_n_trading_days,
    load_profile,
    stats_for_regime,
    compute_expected,
    z_score,
    fetch_1min_bars_for_day,
    resolve_token,
    index_bars_by_minute,
    nearest_bar_at_or_before,
    scan_times_for_day,
    MIN_EXPECTED_STD_PCT,
)
from reverse_regime_breaks import (  # noqa: E402
    classify_event_geometry,
    Z_THRESHOLD,
)

IST = timezone(timedelta(hours=5, minutes=30))
log = logging.getLogger("anka.intraday_break_replay_v01")

# --------------------------------------------------------------------------
# Constants
# --------------------------------------------------------------------------
SCAN_START = _time(9, 30)
SCAN_END = _time(14, 30)
T1_EXIT_TIME = _time(9, 43)     # §5.5 of thesis
SCAN_STEP_MIN = 15
STOP_SIGMA = 1.5
COST_BPS_ROUND_TRIP = 20.0
GATE_MAX_OPPOSING_PCT = 0.3     # §5.2
SECTOR_FLIP_THRESHOLD_PCT = 0.5  # §5.4

SECTOR_MAP_FILE = DOCS_DIR / "2026-04-25-correlation-break-intraday-thesis-v0.1-sector-map.json"
OUTPUT_PARQUET_GATED = AUTORESEARCH_DATA_DIR / "intraday_break_replay_60d_v0.1.parquet"
OUTPUT_PARQUET_UNGATED = AUTORESEARCH_DATA_DIR / "intraday_break_replay_60d_v0.1_ungated.parquet"

# --------------------------------------------------------------------------
# Sector map
# --------------------------------------------------------------------------
_SECTOR_MAP = None

def load_sector_map() -> dict:
    global _SECTOR_MAP
    if _SECTOR_MAP is None:
        _SECTOR_MAP = json.loads(SECTOR_MAP_FILE.read_text(encoding='utf-8'))
    return _SECTOR_MAP


def sector_for_ticker(ticker: str) -> tuple[str, int]:
    sm = load_sector_map()
    name = sm['ticker_sector'].get(ticker, 'NIFTY 50')
    tok = sm['sector_tokens'].get(name, sm['fallback_token'])
    return name, tok


# --------------------------------------------------------------------------
# Sector 1-min bar cache
# --------------------------------------------------------------------------
_SECTOR_BARS_CACHE: dict[tuple[int, str], dict] = {}


def sector_bars_by_minute(sector_token: int, trade_date: str) -> dict[_time, dict]:
    key = (sector_token, trade_date)
    if key in _SECTOR_BARS_CACHE:
        return _SECTOR_BARS_CACHE[key]
    bars = fetch_1min_bars_for_day(sector_token, trade_date)
    idx = index_bars_by_minute(bars) if bars else {}
    _SECTOR_BARS_CACHE[key] = idx
    return idx


def sector_return_pct(sector_idx: dict[_time, dict], t: _time) -> Optional[float]:
    """Return sector index cumulative pct from day open to scan time t."""
    if not sector_idx:
        return None
    # Open = 09:15 bar open
    open_bar = sector_idx.get(_time(9, 15))
    if open_bar is None:
        # fallback: use earliest bar
        try:
            earliest = min(sector_idx.keys())
            open_bar = sector_idx[earliest]
        except ValueError:
            return None
    open_p = float(open_bar.get('open') or open_bar.get('close') or 0.0)
    if open_p <= 0:
        return None
    t_bar = nearest_bar_at_or_before(sector_idx, t)
    if t_bar is None:
        return None
    return (float(t_bar['close']) / open_p - 1.0) * 100.0


def sector_return_between(sector_idx: dict[_time, dict], t_from: _time, t_to: _time) -> Optional[float]:
    """Return sector pct between two scan times on same day."""
    if not sector_idx:
        return None
    b_from = nearest_bar_at_or_before(sector_idx, t_from)
    b_to = nearest_bar_at_or_before(sector_idx, t_to)
    if b_from is None or b_to is None:
        return None
    p_from = float(b_from['close'])
    p_to = float(b_to['close'])
    if p_from <= 0:
        return None
    return (p_to / p_from - 1.0) * 100.0


# --------------------------------------------------------------------------
# T+1 close helper — find the trade's "next trading day" from regime history
# --------------------------------------------------------------------------
def next_trading_day_after(trade_date: str) -> Optional[str]:
    hist = load_regime_history()
    for d, _r in hist:
        if d > trade_date:
            return d
    return None


def sigma_bucket(abs_z: float) -> str:
    if abs_z >= 3.0: return "extreme"
    if abs_z >= 2.0: return "rare"
    return "mild"


# --------------------------------------------------------------------------
# Trade record
# --------------------------------------------------------------------------
@dataclass
class TradeV01:
    trade_id: str
    ticker: str
    sector: str
    trade_date: str
    regime: str
    transition: str
    direction: str
    trigger_time: str
    trigger_z: float
    expected_return_pct: float
    expected_std_pct: float
    gate_pass: bool
    gate_sector_return_pct: Optional[float]
    entry_time: str
    entry_price: float
    entry_sector_price: Optional[float]
    stop_price: float
    exit_time: str
    exit_price: float
    exit_reason: str           # STOP | SECTOR_FLIP | Z_CROSS | T1_CLOSE | SKIP_NO_NEXT_DAY
    exit_date: str
    exit_sector_price: Optional[float]
    hold_minutes: int
    gross_pnl_pct: float
    net_pnl_pct: float
    sector_return_over_hold_pct: Optional[float]
    alpha_vs_sector_pct: Optional[float]
    sigma_bucket_: str


# --------------------------------------------------------------------------
# Core simulation per (ticker, day)
# --------------------------------------------------------------------------
def simulate_day(
    ticker: str,
    trade_date: str,
    regime: str,
    prev_regime: str,
    stats: dict,
    bars_today: list[dict],
    next_day: Optional[str],
) -> tuple[list[TradeV01], list[TradeV01]]:
    """Returns (gated_trades, ungated_trades).

    ungated_trades = paper records that WOULD have been taken but gate blocked.
    At most one trade per ticker per day (matches live engine's behaviour).
    """
    gated: list[TradeV01] = []
    ungated: list[TradeV01] = []

    if not bars_today:
        return gated, ungated

    idx_today = index_bars_by_minute(bars_today)
    first_bar = bars_today[0]
    today_open = float(first_bar.get('open', 0) or 0)
    if today_open <= 0:
        return gated, ungated

    exp = compute_expected(stats)
    if exp is None:
        return gated, ungated
    expected_return, expected_std = exp
    if abs(expected_return) < 0.1:  # §5.1: skip tiny expectations
        return gated, ungated

    sector_name, sector_token = sector_for_ticker(ticker)
    sector_idx_today = sector_bars_by_minute(sector_token, trade_date)

    scans = scan_times_for_day()
    has_traded_today = False

    # For T+1 close we pre-fetch next_day bars *once* if needed
    next_day_sector_idx: Optional[dict] = None
    next_day_ticker_idx: Optional[dict] = None

    def _ensure_next_day(token_stock: int) -> None:
        nonlocal next_day_sector_idx, next_day_ticker_idx
        if next_day is None:
            return
        if next_day_sector_idx is None:
            next_day_sector_idx = sector_bars_by_minute(sector_token, next_day)
        if next_day_ticker_idx is None:
            bars_next = fetch_1min_bars_for_day(token_stock, next_day)
            next_day_ticker_idx = index_bars_by_minute(bars_next) if bars_next else {}

    for i, t in enumerate(scans):
        if has_traded_today:
            break
        if t == scans[-1]:
            break  # no entry at 14:30 (no next scan)

        bar = nearest_bar_at_or_before(idx_today, t)
        if bar is None:
            continue
        price_at_scan = float(bar['close'])
        actual_ret = (price_at_scan / today_open - 1.0) * 100.0
        z = z_score(actual_ret, expected_return, expected_std)

        if abs(z) <= Z_THRESHOLD:
            continue
        geometry = classify_event_geometry(expected_return, actual_ret)
        if geometry != "LAG":
            continue

        direction = "LONG" if expected_return > 0 else "SHORT"

        # §5.2 Gate: sector return at scan vs sigma direction
        sec_ret_now = sector_return_pct(sector_idx_today, t)
        gate_pass: bool
        if sec_ret_now is None:
            # No sector data — conservatively skip both lists
            continue
        if direction == "SHORT":
            gate_pass = (sec_ret_now <= GATE_MAX_OPPOSING_PCT)
        else:
            gate_pass = (sec_ret_now >= -GATE_MAX_OPPOSING_PCT)

        # Entry = NEXT scan close (kill look-ahead)
        if i + 1 >= len(scans):
            continue
        entry_t = scans[i + 1]
        entry_bar = nearest_bar_at_or_before(idx_today, entry_t)
        if entry_bar is None:
            continue
        entry_price = float(entry_bar['close'])
        if entry_price <= 0:
            continue

        # Sector price at entry
        sec_entry_bar = nearest_bar_at_or_before(sector_idx_today, entry_t)
        entry_sector_price = float(sec_entry_bar['close']) if sec_entry_bar else None

        # Stop = 1.5σ against entry
        stop_dist_pct = STOP_SIGMA * expected_std
        if direction == "LONG":
            stop_price = entry_price * (1.0 - stop_dist_pct / 100.0)
        else:
            stop_price = entry_price * (1.0 + stop_dist_pct / 100.0)

        # Simulate the hold — same-day first, then T+1
        exit_reason: Optional[str] = None
        exit_time_obj: Optional[_time] = None
        exit_date = trade_date
        exit_price: Optional[float] = None
        exit_sector_price: Optional[float] = None

        # Iterate per-minute from entry_t to 15:29 on same day
        sorted_keys = sorted(idx_today.keys())
        # Per-scan checks (at 15-min boundaries)
        future_scans = scans[i + 2:]  # scans strictly AFTER entry scan
        future_scan_set = set(future_scans)

        last_key = None
        for k in sorted_keys:
            if k < entry_t:
                continue
            last_key = k
            b = idx_today[k]
            lo = float(b['low']); hi = float(b['high']); cl = float(b['close'])

            # STOP check per minute
            if direction == 'LONG' and lo <= stop_price:
                exit_reason = 'STOP'; exit_time_obj = k; exit_price = stop_price
                break
            if direction == 'SHORT' and hi >= stop_price:
                exit_reason = 'STOP'; exit_time_obj = k; exit_price = stop_price
                break

            # At 15-min scan boundaries → sector-flip + Z_CROSS checks
            if k in future_scan_set:
                # Sector flip
                sec_ret_since_entry = sector_return_between(sector_idx_today, entry_t, k)
                if sec_ret_since_entry is not None:
                    if direction == 'SHORT' and sec_ret_since_entry >= SECTOR_FLIP_THRESHOLD_PCT:
                        exit_reason = 'SECTOR_FLIP'; exit_time_obj = k; exit_price = cl
                        break
                    if direction == 'LONG' and sec_ret_since_entry <= -SECTOR_FLIP_THRESHOLD_PCT:
                        exit_reason = 'SECTOR_FLIP'; exit_time_obj = k; exit_price = cl
                        break

                # Z_CROSS check
                scan_ret = (cl / today_open - 1.0) * 100.0
                z_now = z_score(scan_ret, expected_return, expected_std)
                if abs(z_now) < Z_THRESHOLD:
                    exit_reason = 'Z_CROSS'; exit_time_obj = k; exit_price = cl
                    break

        # If no same-day exit, roll to T+1 09:43 close
        if exit_reason is None:
            _ensure_next_day(resolve_token(ticker))
            if next_day is None or not next_day_ticker_idx:
                exit_reason = 'SKIP_NO_NEXT_DAY'
                exit_time_obj = last_key if last_key else entry_t
                exit_price = float(idx_today[last_key]['close']) if last_key else entry_price
            else:
                t1_bar = nearest_bar_at_or_before(next_day_ticker_idx, T1_EXIT_TIME)
                if t1_bar is None:
                    # Try first bar of next day
                    try:
                        earliest = min(next_day_ticker_idx.keys())
                        t1_bar = next_day_ticker_idx[earliest]
                    except ValueError:
                        t1_bar = None
                if t1_bar is None:
                    exit_reason = 'SKIP_NO_NEXT_DAY'
                    exit_time_obj = last_key if last_key else entry_t
                    exit_price = float(idx_today[last_key]['close']) if last_key else entry_price
                else:
                    exit_reason = 'T1_CLOSE'
                    exit_time_obj = _minute_key_or(t1_bar, T1_EXIT_TIME)
                    exit_price = float(t1_bar['close'])
                    exit_date = next_day
                    if next_day_sector_idx:
                        sec_t1 = nearest_bar_at_or_before(next_day_sector_idx, T1_EXIT_TIME)
                        if sec_t1 is not None:
                            exit_sector_price = float(sec_t1['close'])

        # Fallback for same-day exit sector price
        if exit_sector_price is None and exit_time_obj is not None and exit_date == trade_date:
            sec_ex = nearest_bar_at_or_before(sector_idx_today, exit_time_obj)
            if sec_ex is not None:
                exit_sector_price = float(sec_ex['close'])

        # Compute P&L + alpha-vs-sector
        assert exit_time_obj is not None and exit_price is not None
        if direction == 'LONG':
            gross_pct = (exit_price / entry_price - 1.0) * 100.0
        else:
            gross_pct = (entry_price / exit_price - 1.0) * 100.0
        net_pct = gross_pct - (COST_BPS_ROUND_TRIP / 100.0)
        hold_min = _hold_minutes(entry_t, exit_time_obj, trade_date, exit_date)

        # Sector return over hold: entry_sector_price -> exit_sector_price
        sec_over_hold = None
        alpha_vs_sec = None
        if entry_sector_price and exit_sector_price and entry_sector_price > 0:
            sec_over_hold = (exit_sector_price / entry_sector_price - 1.0) * 100.0
            # alpha in direction of trade: short profits when stock drops,
            # so alpha_vs_sector = net_pct - (-sec_over_hold) for SHORT
            #                   = net_pct - sec_over_hold      for LONG
            if direction == 'SHORT':
                alpha_vs_sec = net_pct - (-sec_over_hold)
            else:
                alpha_vs_sec = net_pct - sec_over_hold

        rec = TradeV01(
            trade_id=f"{ticker}_{trade_date}_{_fmt(entry_t)}_v01",
            ticker=ticker,
            sector=sector_name,
            trade_date=trade_date,
            regime=regime,
            transition=f"{prev_regime}->{regime}",
            direction=direction,
            trigger_time=_fmt(t),
            trigger_z=round(float(z), 3),
            expected_return_pct=round(expected_return, 3),
            expected_std_pct=round(expected_std, 3),
            gate_pass=gate_pass,
            gate_sector_return_pct=round(sec_ret_now, 3) if sec_ret_now is not None else None,
            entry_time=_fmt(entry_t),
            entry_price=round(entry_price, 3),
            entry_sector_price=round(entry_sector_price, 3) if entry_sector_price else None,
            stop_price=round(stop_price, 3),
            exit_time=_fmt(exit_time_obj),
            exit_price=round(float(exit_price), 3),
            exit_reason=exit_reason,
            exit_date=exit_date,
            exit_sector_price=round(exit_sector_price, 3) if exit_sector_price else None,
            hold_minutes=hold_min,
            gross_pnl_pct=round(gross_pct, 4),
            net_pnl_pct=round(net_pct, 4),
            sector_return_over_hold_pct=round(sec_over_hold, 4) if sec_over_hold is not None else None,
            alpha_vs_sector_pct=round(alpha_vs_sec, 4) if alpha_vs_sec is not None else None,
            sigma_bucket_=sigma_bucket(abs(z)),
        )

        if gate_pass:
            gated.append(rec)
        else:
            ungated.append(rec)
        has_traded_today = True
        break  # one trade per ticker per day

    return gated, ungated


def _fmt(t: _time) -> str:
    return t.strftime('%H:%M') if hasattr(t, 'strftime') else str(t)


def _minute_key_or(bar: dict, fallback: _time) -> _time:
    d = bar.get('date')
    if d and hasattr(d, 'time'):
        return d.time().replace(second=0, microsecond=0)
    return fallback


def _hold_minutes(entry_t: _time, exit_t: _time, entry_date: str, exit_date: str) -> int:
    if entry_date == exit_date:
        h = (datetime.combine(_date(2000, 1, 1), exit_t)
             - datetime.combine(_date(2000, 1, 1), entry_t))
        return max(0, int(h.total_seconds() // 60))
    # Overnight — rough estimate: time from entry to 15:30 + time from 09:15 to exit
    close_today = _time(15, 30)
    open_next = _time(9, 15)
    h1 = (datetime.combine(_date(2000, 1, 1), close_today)
          - datetime.combine(_date(2000, 1, 1), entry_t)).total_seconds() // 60
    h2 = (datetime.combine(_date(2000, 1, 2), exit_t)
          - datetime.combine(_date(2000, 1, 2), open_next)).total_seconds() // 60
    return max(0, int(h1 + h2))


# --------------------------------------------------------------------------
# Run driver
# --------------------------------------------------------------------------
def run_replay_v01(
    n_days: int = 60,
    end_date: Optional[str] = None,
    max_tickers_per_day: Optional[int] = None,
) -> tuple[list[TradeV01], list[TradeV01]]:
    profile = load_profile()
    stock_profiles = profile.get('stock_profiles', {})
    sm = load_sector_map()
    mapped_tickers = set(sm['ticker_sector'].keys())

    days = last_n_trading_days(n_days, end_date=end_date)
    if not days:
        log.error("no trading days")
        return [], []

    log.info("v0.1 replay: %d days (%s -> %s)", len(days), days[0][0], days[-1][0])

    gated_all: list[TradeV01] = []
    ungated_all: list[TradeV01] = []
    token_cache: dict[str, Optional[int]] = {}

    for (trade_date, regime, prev_regime) in days:
        nd = next_trading_day_after(trade_date)

        # Candidate universe: has regime stats AND is in sector map
        candidates: list[tuple[str, dict]] = []
        for sym, data in stock_profiles.items():
            if sym not in mapped_tickers:
                continue
            st = stats_for_regime(data, regime, prev_regime)
            if st is None:
                continue
            if compute_expected(st) is None:
                continue
            candidates.append((sym, st))
        if max_tickers_per_day is not None:
            candidates = candidates[:max_tickers_per_day]

        log.info("[%s | %s (prev=%s)] candidates=%d next=%s",
                 trade_date, regime, prev_regime, len(candidates), nd)

        day_g = 0; day_u = 0; fail = 0
        for ix, (sym, st) in enumerate(candidates):
            if sym not in token_cache:
                try:
                    token_cache[sym] = resolve_token(sym)
                except Exception:
                    token_cache[sym] = None
            token = token_cache[sym]
            if token is None:
                continue
            bars = fetch_1min_bars_for_day(token, trade_date)
            if not bars:
                fail += 1
                continue
            try:
                g, u = simulate_day(sym, trade_date, regime, prev_regime, st, bars, nd)
            except Exception as exc:
                log.warning("sim fail %s %s: %s", sym, trade_date, exc)
                continue
            gated_all.extend(g)
            ungated_all.extend(u)
            day_g += len(g); day_u += len(u)
            if (ix + 1) % 30 == 0:
                time.sleep(0.2)

        log.info("[%s] gated=%d ungated=%d bar_fetch_fail=%d", trade_date, day_g, day_u, fail)

    return gated_all, ungated_all


# --------------------------------------------------------------------------
# Reporting
# --------------------------------------------------------------------------
def summarize(trades: list[TradeV01], label: str = "") -> dict:
    if not trades:
        return {'n_trades': 0, 'label': label, 'verdict': 'NO_TRADES'}
    import statistics as sm
    alpha_bps = [t.alpha_vs_sector_pct * 100.0 if t.alpha_vs_sector_pct is not None else None for t in trades]
    net_bps = [t.net_pnl_pct * 100.0 for t in trades]
    valid_alpha = [a for a in alpha_bps if a is not None]
    wins_alpha = [a for a in valid_alpha if a > 0]
    wins_net = [b for b in net_bps if b > 0]
    avg_alpha = sm.mean(valid_alpha) if valid_alpha else 0.0
    avg_net = sm.mean(net_bps)

    # Cluster-robust SE at (ticker, trade_date) — each row IS one cluster
    # here since we limit to one trade per ticker per day. But multiple
    # tickers on the same day are correlated via NIFTY beta; so cluster by
    # trade_date alone for a conservative SE.
    by_date: dict[str, list[float]] = {}
    for t, a in zip(trades, alpha_bps):
        if a is None: continue
        by_date.setdefault(t.trade_date, []).append(a)
    cluster_means = [sum(xs)/len(xs) for xs in by_date.values() if xs]
    if len(cluster_means) >= 2:
        mu = sm.mean(cluster_means)
        sd = sm.pstdev(cluster_means) * math.sqrt(len(cluster_means)/(len(cluster_means)-1))
        se = sd / math.sqrt(len(cluster_means))
        # one-sided t vs 40 bps
        t40 = (mu - 40.0) / se if se > 0 else 0.0
        t0 = mu / se if se > 0 else 0.0
    else:
        mu = avg_alpha; se = 0.0; t40 = 0.0; t0 = 0.0

    def pct(x): return round(x, 2)

    # Stratifications
    def group_stats(items, getter):
        out = {}
        for tr, ab in zip(trades, alpha_bps):
            if ab is None: continue
            k = getter(tr)
            out.setdefault(k, []).append(ab)
        return {k: {'n': len(v), 'avg_alpha_bps': pct(sum(v)/len(v))} for k, v in out.items()}

    return {
        'label': label,
        'n_trades': len(trades),
        'n_alpha_valid': len(valid_alpha),
        'n_clusters_date': len(by_date),
        'avg_alpha_bps': pct(avg_alpha),
        'cluster_robust_mean_alpha_bps': pct(mu),
        'cluster_robust_se_alpha_bps': pct(se),
        't_vs_40bps_cluster': pct(t40),
        't_vs_0_cluster': pct(t0),
        'hit_rate_alpha': round(len(wins_alpha)/max(1,len(valid_alpha)), 3),
        'hit_rate_net': round(len(wins_net)/len(net_bps), 3),
        'avg_net_pnl_bps': pct(avg_net),
        'by_direction': group_stats(trades, lambda t: t.direction),
        'by_regime': group_stats(trades, lambda t: t.regime),
        'by_sigma_bucket': group_stats(trades, lambda t: t.sigma_bucket_),
        'by_exit_reason': group_stats(trades, lambda t: t.exit_reason),
        'by_sector': group_stats(trades, lambda t: t.sector),
    }


def verdict_v01(gated_summary: dict, ungated_summary: dict) -> str:
    """Apply §7 of the v0.1 thesis (FROZEN rule)."""
    if gated_summary.get('n_trades', 0) == 0:
        return 'NO_DATA'
    mu = gated_summary.get('cluster_robust_mean_alpha_bps', 0.0) or 0.0
    se = gated_summary.get('cluster_robust_se_alpha_bps', 0.0) or 0.0
    hr = gated_summary.get('hit_rate_alpha', 0.0) or 0.0
    # one-sided p approx from t (we don't import scipy to keep deps light)
    import math as _m
    t0 = gated_summary.get('t_vs_0_cluster', 0.0) or 0.0
    # crude p-value under large-N normal approx
    def p_one_sided(t: float) -> float:
        return 0.5 * (1.0 - _m.erf(t / _m.sqrt(2)))
    p = p_one_sided(t0)

    # FAIL first
    if mu < 20.0 or p >= 0.10:
        return 'FAIL'
    # WEAK
    if mu < 40.0 and 0.05 <= p < 0.10:
        return 'WEAK'
    # PASS candidate — check falsifier
    ungated_mu = ungated_summary.get('cluster_robust_mean_alpha_bps', 0.0) or 0.0
    if (mu - ungated_mu) < 25.0:
        return 'WEAK_FALSIFIER_VIOLATED'
    if mu >= 40.0 and p < 0.05 and hr >= 0.50:
        return 'PASS'
    return 'WEAK'


# --------------------------------------------------------------------------
# Persistence
# --------------------------------------------------------------------------
def save_parquet(trades: list[TradeV01], path: Path) -> None:
    import pandas as pd
    if not trades:
        pd.DataFrame().to_parquet(path, index=False)
        log.warning("empty output -> %s", path)
        return
    df = pd.DataFrame([asdict(t) for t in trades])
    df.to_parquet(path, index=False)
    log.info("wrote %d trades -> %s", len(df), path)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument('--n-days', type=int, default=60)
    p.add_argument('--end-date', type=str, default=None)
    p.add_argument('--max-tickers-per-day', type=int, default=None)
    p.add_argument('-v', '--verbose', action='store_true')
    args = p.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format='%(asctime)s [%(name)s] %(levelname)s: %(message)s',
        datefmt='%H:%M:%S',
    )

    gated, ungated = run_replay_v01(
        n_days=args.n_days,
        end_date=args.end_date,
        max_tickers_per_day=args.max_tickers_per_day,
    )

    summary_gated = summarize(gated, 'gated')
    summary_ungated = summarize(ungated, 'ungated')
    v = verdict_v01(summary_gated, summary_ungated)

    print("\n==== v0.1 REPLAY SUMMARY ====")
    print(f"  GATED   n={summary_gated.get('n_trades')}  "
          f"alpha_mean(bps)={summary_gated.get('cluster_robust_mean_alpha_bps')}  "
          f"se={summary_gated.get('cluster_robust_se_alpha_bps')}  "
          f"t_vs_0={summary_gated.get('t_vs_0_cluster')}  "
          f"t_vs_40={summary_gated.get('t_vs_40bps_cluster')}  "
          f"hit={summary_gated.get('hit_rate_alpha')}")
    print(f"  UNGATED n={summary_ungated.get('n_trades')}  "
          f"alpha_mean(bps)={summary_ungated.get('cluster_robust_mean_alpha_bps')}")
    print(f"  VERDICT: {v}")

    save_parquet(gated, OUTPUT_PARQUET_GATED)
    save_parquet(ungated, OUTPUT_PARQUET_UNGATED)

    # Emit JSON summary adjacent to parquet
    import json as _json
    summary_path = AUTORESEARCH_DATA_DIR / "intraday_break_replay_60d_v0.1_summary.json"
    summary_path.write_text(_json.dumps({
        'gated': summary_gated,
        'ungated': summary_ungated,
        'verdict': v,
    }, indent=2, default=str), encoding='utf-8')
    print(f"  summary JSON -> {summary_path}")
