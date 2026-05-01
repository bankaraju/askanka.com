"""Horizon extender — re-evaluate the 1,029 NIFR triggers from the Track-1
dispersion explorer at multiple holding horizons (D0..D5) using two exit
families: VWAP-touch (within window) and forced-close-at-end.

This answers the question "does extending holding period change anything?"
without re-running the trigger detection — same trigger rows, different exit
logic.

Design:
  - For each trigger row in explorer_trades.csv:
    - Load that ticker's 5m bars from entry_date through entry_date+5
      trading days.
    - For each holding window D in {0, 1, 2, 3, 4, 5}:
      - VWAP_TOUCH variant: walk forward from entry_t. Each session day has
        its own session VWAP (cumulative price*volume / cumulative volume,
        reset each session). Exit at the first 5m bar where price crosses
        that day's VWAP in the favorable reversion direction. If no touch
        within the window, force-close at close-of-day-D.
      - CLOSE_DN variant: forced exit at close-of-day-D, regardless of
        intraday VWAP behavior. Pure horizon test.
  - No ATR stop applied — the 47.6% knock-out at ATR*1.75 was killing the
    intraday math; this extension tests whether letting the trade breathe
    rescues the gross expectancy.
  - Cost layers: gross / net_s1 (30 bps round-trip) / net_s1_on (30 bps + 5
    bps per overnight hold, conservative borrow proxy).

Outputs:
  - horizon_trades.csv     — one row per (trigger, horizon, exit_family)
  - horizon_summary.json   — aggregated metrics

Usage:
  python -m pipeline.research.h_2026_05_01_neutral_fair_value_reversion.horizon_extender
"""
from __future__ import annotations

import csv
import json
import math
import statistics
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
TRADES_CSV = Path(__file__).resolve().parent / "explorer_trades.csv"
OUT_TRADES_CSV = Path(__file__).resolve().parent / "horizon_trades.csv"
OUT_SUMMARY_JSON = Path(__file__).resolve().parent / "horizon_summary.json"
BARS_5M_DIR = REPO_ROOT / "pipeline" / "data" / "fno_intraday_5m"
SECTOR_MAP_PATH = (
    REPO_ROOT
    / "pipeline"
    / "research"
    / "h_2026_05_01_phase_c_mr_karpathy"
    / "frozen"
    / "sector_map_frozen.json"
)

HOLDING_DAYS = (0, 1, 2, 3, 4, 5)
COST_BPS_S1 = 30.0
COST_BPS_OVERNIGHT_PER_DAY = 5.0
ANNUAL_TRADING_DAYS = 252


@dataclass
class Bar:
    dt: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


def _parse_float(value: str) -> float | None:
    if value is None:
        return None
    s = value.strip()
    if s == "" or s.lower() == "nan":
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _load_bars(ticker: str) -> list[Bar]:
    """Load all 5m bars for a ticker, ordered by datetime."""
    path = BARS_5M_DIR / f"{ticker}.csv"
    if not path.is_file():
        return []
    bars: list[Bar] = []
    with path.open("r", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            try:
                dt = datetime.strptime(row["datetime"], "%Y-%m-%d %H:%M:%S")
            except (KeyError, ValueError):
                continue
            o = _parse_float(row.get("open", ""))
            h = _parse_float(row.get("high", ""))
            lo = _parse_float(row.get("low", ""))
            c = _parse_float(row.get("close", ""))
            v = _parse_float(row.get("volume", ""))
            if c is None or v is None or v <= 0:
                continue
            bars.append(
                Bar(
                    dt=dt,
                    open=o if o is not None else c,
                    high=h if h is not None else c,
                    low=lo if lo is not None else c,
                    close=c,
                    volume=v,
                )
            )
    bars.sort(key=lambda b: b.dt)
    return bars


def _trading_days_from(bars: list[Bar], entry_date: date, max_days: int) -> list[date]:
    """Return the next `max_days+1` distinct trading dates >= entry_date present
    in bars (entry_date itself if it has any bars, then each subsequent
    trading date up to max_days more)."""
    seen: list[date] = []
    for bar in bars:
        d = bar.dt.date()
        if d < entry_date:
            continue
        if not seen or seen[-1] != d:
            seen.append(d)
        if len(seen) > max_days + 1:
            break
    return seen[: max_days + 1]


def _bars_for_session(bars: list[Bar], session: date) -> list[Bar]:
    """Return all bars for the given trading session, sorted by datetime."""
    return [b for b in bars if b.dt.date() == session]


def _session_vwap_after(
    session_bars: list[Bar], from_dt: datetime | None
) -> list[tuple[Bar, float]]:
    """Return (bar, running_session_vwap_at_close_of_bar) for bars at or after
    from_dt. Session VWAP uses cumulative price*volume / cumulative volume
    starting from the session open (not from_dt) — that matches the
    definition the original trigger used.
    """
    if not session_bars:
        return []
    cum_pv = 0.0
    cum_v = 0.0
    out: list[tuple[Bar, float]] = []
    for bar in session_bars:
        typical = (bar.high + bar.low + bar.close) / 3.0
        cum_pv += typical * bar.volume
        cum_v += bar.volume
        vwap = (cum_pv / cum_v) if cum_v > 0 else bar.close
        if from_dt is None or bar.dt >= from_dt:
            out.append((bar, vwap))
    return out


def _favorable_touch(
    bars_with_vwap: list[tuple[Bar, float]], side: str
) -> tuple[Bar, float] | None:
    """First bar in the sequence where price crosses session VWAP in the
    favorable reversion direction.

    LONG  => entered because price was below VWAP; favorable touch = bar.high
             reaches VWAP from below.
    SHORT => entered because price was above VWAP; favorable touch = bar.low
             reaches VWAP from above.
    """
    for bar, vwap in bars_with_vwap:
        if side == "LONG":
            if bar.high >= vwap:
                return bar, vwap
        elif side == "SHORT":
            if bar.low <= vwap:
                return bar, vwap
    return None


def _ret_bps(side: str, entry_px: float, exit_px: float) -> float:
    """Return bps gross. LONG = (exit-entry)/entry; SHORT = (entry-exit)/entry."""
    if entry_px <= 0:
        return 0.0
    raw = (exit_px - entry_px) / entry_px if side == "LONG" else (entry_px - exit_px) / entry_px
    return raw * 1e4


def _hit_flag(bps_gross: float) -> int:
    return 1 if bps_gross > 0 else 0


def _sharpe(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mu = statistics.mean(values)
    sd = statistics.pstdev(values)
    if sd <= 0:
        return 0.0
    return mu / sd


def _ann_sharpe(per_trade_sharpe: float, trades_per_day: float) -> float:
    if per_trade_sharpe == 0.0 or trades_per_day <= 0:
        return 0.0
    return per_trade_sharpe * math.sqrt(trades_per_day * ANNUAL_TRADING_DAYS)


def _read_explorer_trades() -> list[dict]:
    rows: list[dict] = []
    with TRADES_CSV.open("r", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            rows.append(row)
    return rows


def _load_sector_map() -> dict[str, str]:
    if not SECTOR_MAP_PATH.is_file():
        return {}
    payload = json.loads(SECTOR_MAP_PATH.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        return {str(k): str(v) for k, v in payload.items()}
    return {}


def _evaluate_trigger(
    trigger: dict, bars: list[Bar]
) -> list[dict]:
    """Produce one output row per (horizon D, exit_family) for this trigger."""
    ticker = trigger["ticker"]
    side = trigger["side"].upper()
    try:
        entry_dt = datetime.strptime(
            f"{trigger['date']} {trigger['snap_t']}", "%Y-%m-%d %H:%M:%S"
        )
    except (KeyError, ValueError):
        return []
    entry_date = entry_dt.date()
    entry_px = _parse_float(trigger.get("entry_px", ""))
    if entry_px is None or entry_px <= 0:
        return []

    sessions = _trading_days_from(bars, entry_date, max(HOLDING_DAYS))
    if not sessions or sessions[0] != entry_date:
        return []

    out_rows: list[dict] = []

    for D in HOLDING_DAYS:
        if D >= len(sessions):
            continue
        target_sessions = sessions[: D + 1]

        # ---- VWAP_TOUCH within window ----
        touch_exit_px: float | None = None
        touch_exit_dt: datetime | None = None
        touch_session_idx: int | None = None
        for idx, sess in enumerate(target_sessions):
            session_bars = _bars_for_session(bars, sess)
            if not session_bars:
                continue
            from_dt = entry_dt if idx == 0 else None
            sequence = _session_vwap_after(session_bars, from_dt)
            if idx == 0:
                # skip the entry bar itself (avoid same-bar self-touch)
                sequence = [(b, v) for (b, v) in sequence if b.dt > entry_dt]
            touch = _favorable_touch(sequence, side)
            if touch is not None:
                touch_bar, touch_vwap = touch
                touch_exit_px = touch_vwap
                touch_exit_dt = touch_bar.dt
                touch_session_idx = idx
                break

        # If no touch within window, force-close at close of last session in window
        last_session = target_sessions[-1]
        last_session_bars = _bars_for_session(bars, last_session)
        if not last_session_bars:
            continue
        force_close_px = last_session_bars[-1].close
        force_close_dt = last_session_bars[-1].dt

        if touch_exit_px is None:
            vwap_exit_px = force_close_px
            vwap_exit_dt = force_close_dt
            vwap_holding_days = D
            vwap_outcome = "FORCE_CLOSE_NO_TOUCH"
        else:
            vwap_exit_px = touch_exit_px
            vwap_exit_dt = touch_exit_dt
            vwap_holding_days = touch_session_idx
            vwap_outcome = "VWAP_TOUCH"

        # ---- CLOSE_DN variant (pure horizon, force-close regardless) ----
        close_exit_px = force_close_px
        close_exit_dt = force_close_dt
        close_holding_days = D

        # bps + cost layers
        for variant, exit_px, exit_dt, holding_days, outcome in (
            ("VWAP_TOUCH", vwap_exit_px, vwap_exit_dt, vwap_holding_days, vwap_outcome),
            ("CLOSE", close_exit_px, close_exit_dt, close_holding_days, "FORCED_CLOSE"),
        ):
            bps_gross = _ret_bps(side, entry_px, exit_px)
            bps_net_s1 = bps_gross - COST_BPS_S1
            on_cost = COST_BPS_OVERNIGHT_PER_DAY * holding_days
            bps_net_s1_on = bps_net_s1 - on_cost

            out_rows.append(
                dict(
                    trigger_id=trigger.get("trigger_id", ""),
                    ticker=ticker,
                    sector=trigger.get("sector", ""),
                    side=side,
                    date=trigger.get("date", ""),
                    snap_t=trigger.get("snap_t", ""),
                    entry_px=f"{entry_px:.6f}",
                    horizon_D=D,
                    variant=variant,
                    exit_dt=exit_dt.strftime("%Y-%m-%d %H:%M:%S"),
                    exit_px=f"{exit_px:.6f}",
                    holding_days=holding_days,
                    outcome=outcome,
                    bps_gross=f"{bps_gross:.4f}",
                    bps_net_s1=f"{bps_net_s1:.4f}",
                    bps_net_s1_on=f"{bps_net_s1_on:.4f}",
                )
            )

    return out_rows


def _aggregate(rows: list[dict]) -> dict:
    """Aggregate by (variant, horizon_D), and provide side / sector splits."""

    def stats_for(slice_rows: list[dict]) -> dict:
        if not slice_rows:
            return dict(n=0)
        gross = [float(r["bps_gross"]) for r in slice_rows]
        net_s1 = [float(r["bps_net_s1"]) for r in slice_rows]
        net_s1_on = [float(r["bps_net_s1_on"]) for r in slice_rows]
        hits_gross = [_hit_flag(v) for v in gross]
        hits_net_s1_on = [_hit_flag(v) for v in net_s1_on]
        sharpe_pt_gross = _sharpe(gross)
        sharpe_pt_net_s1 = _sharpe(net_s1)
        sharpe_pt_net_s1_on = _sharpe(net_s1_on)
        return dict(
            n=len(slice_rows),
            mean_bps_gross=round(statistics.mean(gross), 3),
            mean_bps_net_s1=round(statistics.mean(net_s1), 3),
            mean_bps_net_s1_on=round(statistics.mean(net_s1_on), 3),
            hit_rate_gross=round(sum(hits_gross) / len(hits_gross), 4),
            hit_rate_net_s1_on=round(sum(hits_net_s1_on) / len(hits_net_s1_on), 4),
            sharpe_per_trade_gross=round(sharpe_pt_gross, 4),
            sharpe_per_trade_net_s1=round(sharpe_pt_net_s1, 4),
            sharpe_per_trade_net_s1_on=round(sharpe_pt_net_s1_on, 4),
        )

    by_horizon = {}
    for variant in ("VWAP_TOUCH", "CLOSE"):
        for D in HOLDING_DAYS:
            slice_rows = [r for r in rows if r["variant"] == variant and r["horizon_D"] == D]
            key = f"{variant}_D{D}"
            by_horizon[key] = stats_for(slice_rows)

    by_side = {}
    for variant in ("VWAP_TOUCH", "CLOSE"):
        for D in (0, 1, 3, 5):
            for side in ("LONG", "SHORT"):
                key = f"{variant}_D{D}_{side}"
                slice_rows = [
                    r
                    for r in rows
                    if r["variant"] == variant and r["horizon_D"] == D and r["side"] == side
                ]
                by_side[key] = stats_for(slice_rows)

    by_sector_d3_vwap = {}
    sectors = sorted({r.get("sector", "") for r in rows if r.get("sector")})
    for sector in sectors:
        slice_rows = [
            r
            for r in rows
            if r["variant"] == "VWAP_TOUCH" and r["horizon_D"] == 3 and r.get("sector") == sector
        ]
        by_sector_d3_vwap[sector] = stats_for(slice_rows)

    by_outcome_vwap = {}
    for D in HOLDING_DAYS:
        for outcome in ("VWAP_TOUCH", "FORCE_CLOSE_NO_TOUCH"):
            slice_rows = [
                r
                for r in rows
                if r["variant"] == "VWAP_TOUCH"
                and r["horizon_D"] == D
                and r["outcome"] == outcome
            ]
            key = f"D{D}_{outcome}"
            by_outcome_vwap[key] = stats_for(slice_rows)

    holding_dist_vwap = {}
    for D in HOLDING_DAYS:
        slice_rows = [r for r in rows if r["variant"] == "VWAP_TOUCH" and r["horizon_D"] == D]
        if not slice_rows:
            holding_dist_vwap[f"D{D}"] = {}
            continue
        days = [int(r["holding_days"]) for r in slice_rows]
        dist = {}
        for d in range(D + 1):
            count = sum(1 for x in days if x == d)
            dist[f"hold_{d}d"] = round(count / len(days), 4)
        holding_dist_vwap[f"D{D}"] = dist

    return dict(
        by_horizon=by_horizon,
        by_side=by_side,
        by_sector_d3_vwap=by_sector_d3_vwap,
        by_outcome_vwap=by_outcome_vwap,
        holding_dist_vwap=holding_dist_vwap,
    )


def main() -> None:
    triggers = _read_explorer_trades()
    print(f"loaded {len(triggers)} trigger rows from {TRADES_CSV.name}")

    sector_map = _load_sector_map()
    if sector_map:
        for t in triggers:
            if not t.get("sector") and t.get("ticker") in sector_map:
                t["sector"] = sector_map[t["ticker"]]

    by_ticker: dict[str, list[dict]] = {}
    for t in triggers:
        by_ticker.setdefault(t["ticker"], []).append(t)
    print(f"unique tickers: {len(by_ticker)}")

    out_rows: list[dict] = []
    for i, (ticker, ticker_triggers) in enumerate(sorted(by_ticker.items()), start=1):
        bars = _load_bars(ticker)
        if not bars:
            print(f"  [{i}/{len(by_ticker)}] {ticker}: no bars, skipping {len(ticker_triggers)} triggers")
            continue
        for trig in ticker_triggers:
            out_rows.extend(_evaluate_trigger(trig, bars))
        if i % 10 == 0 or i == len(by_ticker):
            print(f"  [{i}/{len(by_ticker)}] processed (rows so far: {len(out_rows)})")

    print(f"writing {len(out_rows)} horizon rows -> {OUT_TRADES_CSV.name}")
    if out_rows:
        fields = list(out_rows[0].keys())
        with OUT_TRADES_CSV.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=fields)
            writer.writeheader()
            writer.writerows(out_rows)

    summary = _aggregate(out_rows)
    summary["meta"] = dict(
        n_input_triggers=len(triggers),
        n_horizon_rows=len(out_rows),
        cost_bps_s1=COST_BPS_S1,
        cost_bps_overnight_per_day=COST_BPS_OVERNIGHT_PER_DAY,
        holding_days_tested=list(HOLDING_DAYS),
    )
    print(f"writing summary -> {OUT_SUMMARY_JSON.name}")
    OUT_SUMMARY_JSON.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print("done.")


if __name__ == "__main__":
    main()
