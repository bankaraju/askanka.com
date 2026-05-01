"""Daily holdout runner for H-2026-05-01-phase-c-mr-karpathy-v1.

Spec section 11 + section 17. Single-touch locked: no parameter mutation
between 2026-05-04 and verdict date.

Operation
---------
For each trading day in the holdout window, ``run_for_date(date_str)``:
  1. Loads frozen universe + frozen profile + frozen sector map.
  2. Loads adjusted 5m bars + daily OHLC for every frozen-universe ticker.
  3. Resolves the V3 CURATED-30 regime label for `date_str` (PIT tape or live tape).
  4. Iterates the 19-step snap grid 09:30 -> 14:00 IST, computes z-score vs
     profile, classifies via phase_c_minute.replay._classify.
  5. For each POSSIBLE_OPPORTUNITY candidate, applies the 3 layered gates:
     - regime in {RISK-ON, CAUTION}
     - not within +/- 1 day of any registered event (RBI/FOMC/Election/Budget/GST)
     - Karpathy 6-of-8 qualifier score >= threshold (if karpathy_chosen_cell.json
       exists; otherwise we run the regime-gated baseline = §9B.1 margin baseline).
  6. Simulates exit at ATR(14)*2 stop or 14:30 IST mechanical close.
  7. Writes one row per surviving candidate to recommendations.csv.
  8. Appends a run summary to run_log.jsonl.

CLI:
    python -m pipeline.research.h_2026_05_01_phase_c_mr_karpathy.holdout_runner \
           --date 2026-05-04 --phase open

For the 14:30 close-of-day operation, OPEN already simulates the exit out to
14:30 because we run on full-day 5m bars. The two scheduled tasks
(AnkaPhaseCMRKarpathyOpen at 09:30 IST and AnkaPhaseCMRKarpathyClose at 14:30
IST) both invoke this runner; the close phase verifies + idempotently re-runs
to capture any partial-OPEN day. See spec section 11.
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from pipeline.research.phase_c_minute import corp_action_adjuster as ca
from pipeline.research.phase_c_minute import replay as r_lib
from pipeline.research.phase_c_minute import replay_runner as rr
from pipeline.research.h_2026_04_27_secrsi.historical_replay import (
    _atr_pit, _load_5m_bars, _load_daily_ohlc, INTRADAY_5M_DIR,
)

from . import (
    HOLDOUT_CLOSE,
    HOLDOUT_EXTEND_TO,
    HOLDOUT_OPEN,
    HYPOTHESIS_ID,
    MIN_HOLDOUT_N,
)
from .event_day_skip import is_event_day
from .feature_library import SnapContext, compute_features
from .mr_engine import (
    COST_BPS_S0,
    COST_BPS_S1,
    COST_BPS_S2,
    NOTIONAL_INR_PER_LEG,
    holdout_meta,
)
from .mr_signal_generator import KarpathyCell, _qualifier_score
from .regime_gate import is_allowed as regime_allowed, regime_for_date

log = logging.getLogger("anka.h_2026_05_01_phase_c_mr_karpathy.holdout")

PKG_DIR = Path(__file__).resolve().parent
UNIVERSE_PATH = PKG_DIR / "universe_frozen.json"
PROFILE_PATH = PKG_DIR / "profile_frozen.json"
SECTOR_MAP_PATH = PKG_DIR / "sector_map_frozen.json"
CHOSEN_CELL_PATH = PKG_DIR / "karpathy_chosen_cell.json"

REPO = PKG_DIR.parents[2]
LEDGER_DIR = REPO / "pipeline" / "data" / "research" / "h_2026_05_01_phase_c_mr_karpathy"
LEDGER_PATH = LEDGER_DIR / "recommendations.csv"
RUN_LOG_PATH = LEDGER_DIR / "run_log.jsonl"

LEDGER_FIELDS: tuple[str, ...] = (
    "hypothesis_id", "date", "snap_t", "ticker", "sector", "regime",
    "side", "z_score", "intraday_ret_pct", "expected_ret_pct",
    "entry_px", "exit_px", "exit_reason", "exit_t", "atr_14",
    "pnl_bps_S0", "pnl_bps_S1", "pnl_bps_S2",
    "qualifier_score", "qualifier_threshold",
    "notional_inr", "ledger_written_at_utc",
)


# ---------------- frozen artefact loaders ----------------------------------

def _load_universe() -> list[str]:
    payload = json.loads(UNIVERSE_PATH.read_text(encoding="utf-8"))
    return list(payload["tickers"])


def _load_profile() -> dict:
    payload = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    return payload["profile"]


def _load_sector_map() -> dict[str, str]:
    payload = json.loads(SECTOR_MAP_PATH.read_text(encoding="utf-8"))
    return payload["sector_map"]


# ---------------- engine ----------------------------------------------------

def _gross_bps_long(entry: float, exit_: float) -> float:
    if entry <= 0:
        return 0.0
    return (exit_ - entry) / entry * 10000.0


def _gross_bps(side: str, entry: float, exit_: float) -> float:
    g = _gross_bps_long(entry, exit_)
    return g if side == "LONG" else -g


def _direction_for_mean_revert(z: float) -> str | None:
    """Mean-revert: z>0 (overshoot up) -> SHORT, z<0 (overshoot down) -> LONG."""
    if z != z:
        return None
    if z > 0:
        return "SHORT"
    if z < 0:
        return "LONG"
    return None


def _build_snap_ctx(*, date: str, snap_t: str, ticker: str, sector: str | None,
                    snap_px: float, prev_close: float, atr_14: float | None,
                    is_event: bool) -> SnapContext:
    """Build a SnapContext for feature computation.

    For v1 we hand a *minimal* context — most macro features (universe returns,
    sector returns, breadth, VIX, news) are NaN at the snap level for the per-ticker
    inner loop. The Karpathy search will only have selected features that actually
    populate; if all 6 chosen features are NaN, _qualifier_score returns None and
    the trade is skipped. This is the correct behaviour and the reason we keep the
    feature library NaN-tolerant.
    """
    ret_pct = (snap_px - prev_close) / prev_close * 100.0 if prev_close > 0 else float("nan")
    return SnapContext(
        date=date,
        snap_t=snap_t,
        ticker=ticker,
        sector=sector,
        snap_px=snap_px,
        intraday_ret_pct=ret_pct,
        atr_14_pit=atr_14,
        is_event_day=is_event,
    )


def _run_one_day(
    *,
    date_str: str,
    minute_cache: dict[str, dict[str, list[dict]]],
    daily_cache: dict[str, list[dict]],
    profile: dict,
    sector_map: dict[str, str],
    regime: str,
    cell: KarpathyCell | None,
) -> list[dict]:
    """Replay one trading day through the full 4-stage gate.

    Returns: list of ledger rows for every surviving signal (CLOSED or NO_DATA).
    """
    rows: list[dict] = []
    snap_times = r_lib.snapshot_times()
    seen_today: set[str] = set()
    is_event = is_event_day(date_str)
    written_at_utc = datetime.now(timezone.utc).isoformat()

    for ticker, day_bars in minute_cache.items():
        bars = day_bars.get(date_str)
        if not bars:
            continue
        prev_close = rr._prev_close(daily_cache.get(ticker, []), date_str)
        if prev_close is None or prev_close <= 0:
            continue
        sym_prof = profile.get(ticker, {}).get(regime)
        if sym_prof is None:
            continue
        atr = _atr_pit(daily_cache.get(ticker, []), date_str, 14)

        for snap_t in snap_times:
            if ticker in seen_today:
                break
            snap_bar = next((b for b in bars if b["time"] >= snap_t), None)
            if snap_bar is None or snap_bar.get("close") is None:
                continue
            sh, sm, _ = snap_t.split(":")
            bh, bm, _ = snap_bar["time"].split(":")
            snap_minutes = int(sh) * 60 + int(sm)
            bar_minutes = int(bh) * 60 + int(bm)
            if bar_minutes - snap_minutes > 15:
                continue

            snap_px = float(snap_bar["close"])
            intraday_ret = (snap_px - float(prev_close)) / float(prev_close)
            expected = float(sym_prof.get("expected_return", 0.0))
            std = float(sym_prof.get("std_return", 0.0))
            if std <= 0.001:
                continue
            z = (intraday_ret - expected) / std

            classification = r_lib._classify(z, expected, intraday_ret)
            if classification != "POSSIBLE_OPPORTUNITY":
                continue

            # Gate 1: regime
            if regime not in {"RISK-ON", "CAUTION"}:
                # Single regime per day; if regime fails once, fails for all snaps.
                # Break to next ticker for clarity.
                break

            # Gate 2: event-day skip
            if is_event:
                break

            # Gate 3: direction
            side = _direction_for_mean_revert(z)
            if side is None:
                continue

            # Gate 4: Karpathy qualifier (if cell is loaded)
            ctx = _build_snap_ctx(
                date=date_str, snap_t=snap_t, ticker=ticker,
                sector=sector_map.get(ticker), snap_px=snap_px,
                prev_close=float(prev_close), atr_14=atr, is_event=is_event,
            )
            features = compute_features(ctx)
            qualifier_score = 0.0
            qualifier_threshold = 0.0
            if cell is not None:
                score = _qualifier_score(features, cell)
                if score is None:
                    continue
                if score < cell.threshold:
                    continue
                qualifier_score = score
                qualifier_threshold = cell.threshold

            # Simulate exit using the rest of the day's bars
            exit_px, exit_reason, exit_t = r_lib.simulate_exit(
                bars, snap_t, side, snap_px, atr,
            )
            if exit_reason == "NO_DATA":
                continue

            gross = _gross_bps(side, snap_px, exit_px)
            seen_today.add(ticker)
            rows.append({
                "hypothesis_id": HYPOTHESIS_ID,
                "date": date_str,
                "snap_t": snap_t,
                "ticker": ticker,
                "sector": sector_map.get(ticker, ""),
                "regime": regime,
                "side": side,
                "z_score": round(z, 4),
                "intraday_ret_pct": round(intraday_ret * 100, 4),
                "expected_ret_pct": round(expected * 100, 4),
                "entry_px": round(snap_px, 4),
                "exit_px": round(exit_px, 4),
                "exit_reason": exit_reason,
                "exit_t": exit_t,
                "atr_14": round(atr, 4) if atr else "",
                "pnl_bps_S0": round(gross - COST_BPS_S0, 2),
                "pnl_bps_S1": round(gross - COST_BPS_S1, 2),
                "pnl_bps_S2": round(gross - COST_BPS_S2, 2),
                "qualifier_score": round(qualifier_score, 6),
                "qualifier_threshold": qualifier_threshold,
                "notional_inr": NOTIONAL_INR_PER_LEG,
                "ledger_written_at_utc": written_at_utc,
            })
            break  # first-touch dedup per (date, ticker)

    return rows


# ---------------- I/O wrappers --------------------------------------------

def _load_5m_bars_for_date(ticker: str, date_str: str) -> list[dict]:
    """Fast-path: read only the rows for `date_str` from the 5m CSV.

    The full-history loader reads ~200K rows per ticker (5y of 5m bars). For
    live operation we only need a single day's bars (~75 rows) -- this scan
    short-circuits as soon as we move past `date_str`.

    Returns: ordered list[bar] for that day, or [] if absent.
    """
    p = INTRADAY_5M_DIR / f"{ticker}.csv"
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
                    break  # past target date, sorted file -> stop scanning
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


def _empirical_factor_for_date(ticker: str, date_str: str,
                               daily: list[dict]) -> float:
    """Return the corp-action adjustment factor for one (ticker, date).

    factor = adjusted_daily_close(D) / raw_5m_last_close(D). 1.0 if either is missing.
    """
    bars = _load_5m_bars_for_date(ticker, date_str)
    if not bars:
        return 1.0
    raw_close = bars[-1].get("close")
    if raw_close is None or raw_close <= 0:
        return 1.0
    daily_close: float | None = None
    for d in daily:
        if d.get("date") == date_str:
            daily_close = d.get("close")
            break
    if daily_close is None or daily_close <= 0:
        return 1.0
    return float(daily_close) / float(raw_close)


def _adjust_bars_inplace(bars: list[dict], factor: float) -> list[dict]:
    if abs(factor - 1.0) < 1e-6:
        return bars
    out: list[dict] = []
    for b in bars:
        nb = dict(b)
        for k in ("open", "high", "low", "close"):
            v = nb.get(k)
            if v is not None:
                nb[k] = v * factor
        out.append(nb)
    return out


def _load_today_minute_and_daily(universe: list[str], *,
                                 date_str: str | None = None) -> tuple[dict, dict, int]:
    """Load 5m + daily caches; apply empirical corp adjustment.

    If `date_str` is provided, uses the fast-path single-date loader (live).
    If None, falls back to full-history load (Karpathy / backtest path).

    Returns: (minute_cache, daily_cache, n_adjusted)
    """
    minute_cache: dict[str, dict[str, list[dict]]] = {}
    daily_cache: dict[str, list[dict]] = {}
    n_adjusted = 0

    if date_str is not None:
        # Live fast-path: only load `date_str` bars; ATR PIT only needs daily.
        for t in universe:
            d = _load_daily_ohlc(t)
            if d:
                daily_cache[t] = d
        for t in universe:
            bars = _load_5m_bars_for_date(t, date_str)
            if not bars:
                continue
            if t in daily_cache:
                factor = _empirical_factor_for_date(t, date_str, daily_cache[t])
                if abs(factor - 1.0) > 0.02:
                    bars = _adjust_bars_inplace(bars, factor)
                    n_adjusted += 1
            minute_cache[t] = {date_str: bars}
        return minute_cache, daily_cache, n_adjusted

    # Full-history path (Karpathy / multi-day backtest)
    for t in universe:
        m = _load_5m_bars(t)
        if m:
            minute_cache[t] = m
        d = _load_daily_ohlc(t)
        if d:
            daily_cache[t] = d

    for t in list(minute_cache.keys()):
        if t not in daily_cache:
            continue
        ftable = ca.empirical_factor_table(minute_cache[t], daily_cache[t])
        if not ftable:
            continue
        non_unity = sum(1 for f in ftable.values() if abs(f - 1.0) > 0.02)
        if non_unity > 0:
            minute_cache[t] = ca.adjust_bars_empirical(minute_cache[t], ftable)
            n_adjusted += 1
    return minute_cache, daily_cache, n_adjusted


def _append_rows_to_ledger(rows: list[dict]) -> None:
    LEDGER_DIR.mkdir(parents=True, exist_ok=True)
    is_new = not LEDGER_PATH.is_file()
    with LEDGER_PATH.open("a", encoding="utf-8", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=list(LEDGER_FIELDS), extrasaction="ignore")
        if is_new:
            writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _ledger_dates() -> set[str]:
    """Set of dates already present in the ledger (for idempotency)."""
    if not LEDGER_PATH.is_file():
        return set()
    out: set[str] = set()
    with LEDGER_PATH.open(encoding="utf-8", newline="") as fp:
        reader = csv.DictReader(fp)
        for row in reader:
            d = row.get("date")
            if d:
                out.add(d)
    return out


def append_run_log(summary: dict) -> None:
    RUN_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with RUN_LOG_PATH.open("a", encoding="utf-8") as fp:
        fp.write(json.dumps(summary, ensure_ascii=False) + "\n")


# ---------------- public API -----------------------------------------------

def is_in_holdout(date_str: str) -> bool:
    return HOLDOUT_OPEN <= date_str <= HOLDOUT_EXTEND_TO


def is_in_extension(date_str: str) -> bool:
    return HOLDOUT_CLOSE < date_str <= HOLDOUT_EXTEND_TO


def run_for_date(date_str: str, *, dry_run: bool = False, force: bool = False) -> dict:
    """Run the engine for `date_str`. Idempotent: skips if already in ledger.

    `dry_run`: don't write CSV, just return the summary + rows.
    `force`: re-run even if `date_str` is already in the ledger.
    """
    universe = _load_universe()
    profile = _load_profile()
    sector_map = _load_sector_map()
    cell = KarpathyCell.load(CHOSEN_CELL_PATH)

    minute_cache, daily_cache, n_adjusted = _load_today_minute_and_daily(
        universe, date_str=date_str,
    )
    log.info("loaded 5m: %d / %d  daily: %d / %d  adjusted: %d",
             len(minute_cache), len(universe), len(daily_cache), len(universe), n_adjusted)

    regime = regime_for_date(date_str)
    skip_reason: str | None = None
    if regime is None:
        skip_reason = "regime_label_unavailable"
        rows: list[dict] = []
    elif not regime_allowed(date_str):
        skip_reason = f"regime_gate_blocked_{regime}"
        rows = []
    elif is_event_day(date_str):
        skip_reason = "event_day_skip"
        rows = []
    elif not force and date_str in _ledger_dates():
        skip_reason = "already_in_ledger"
        rows = []
    else:
        rows = _run_one_day(
            date_str=date_str,
            minute_cache=minute_cache,
            daily_cache=daily_cache,
            profile=profile,
            sector_map=sector_map,
            regime=regime,
            cell=cell,
        )

    if rows and not dry_run:
        _append_rows_to_ledger(rows)

    summary = {
        "hypothesis_id": HYPOTHESIS_ID,
        "date": date_str,
        "now_ist": datetime.now(timezone.utc).isoformat(),
        "regime": regime,
        "skip_reason": skip_reason,
        "n_rows": len(rows),
        "in_holdout": is_in_holdout(date_str),
        "in_extension": is_in_extension(date_str),
        "dry_run": dry_run,
        "karpathy_cell_loaded": cell is not None,
        "ledger_path": str(LEDGER_PATH),
    }
    if not dry_run:
        append_run_log(summary)
    return summary


def open_today(date_str: str) -> dict:
    """Compatibility shim — equivalent to ``run_for_date(date_str)``."""
    return run_for_date(date_str)


def close_today(date_str: str) -> dict:
    """Compatibility shim — equivalent to ``run_for_date(date_str)``.

    Because the v1 engine simulates exits at OPEN time (we have full-day 5m bars),
    the 14:30 close phase is idempotent: it runs the same logic and `_ledger_dates`
    short-circuits if the date already wrote rows. If the OPEN run was missed
    (e.g., scheduler skip), CLOSE will pick it up.
    """
    return run_for_date(date_str)


def meta_dump() -> dict:
    return {**holdout_meta(), "ledger_path": str(LEDGER_PATH)}


# ---------------- CLI ------------------------------------------------------

def _cli(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True, help="YYYY-MM-DD")
    ap.add_argument("--phase", choices=("open", "close"), default="open")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true",
                    help="Re-run even if date already in ledger.")
    args = ap.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    summary = run_for_date(args.date, dry_run=args.dry_run, force=args.force)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
