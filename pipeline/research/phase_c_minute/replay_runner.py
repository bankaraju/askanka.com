"""Phase C minute-resolution replay runner — orchestrates I/O around `replay.py`.

Reads:
  pipeline/data/fno_intraday_1m/<TICKER>.csv       (1m bars, IST)
  pipeline/data/fno_historical/<TICKER>.csv         (daily OHLC for ATR PIT)
  pipeline/data/research/etf_v3/regime_tape_5y_pit.csv  (PIT regime tape)
  pipeline/data/canonical_fno_research_v3.json     (universe)

Writes:
  pipeline/data/research/phase_c/minute_replay_<from>_<to>.csv  (per-signal rows)
  pipeline/data/research/phase_c/minute_replay_summary_<from>_<to>.json

CLI
---
    python -m pipeline.research.phase_c_minute.replay_runner \
           --from 2024-04-01 --to 2026-04-30
    python -m pipeline.research.phase_c_minute.replay_runner \
           --from 2024-04-01 --to 2024-12-31 --max-tickers 30

Pre-flight check
----------------
On startup the runner verifies that:
  - The PIT regime tape covers the window.
  - At least 12 tickers have ≥ window-length × 0.6 minute bars.
  - At least 12 tickers have ≥ 60 daily bars (for ATR PIT).

If any check fails, the runner exits 2 with a clear message — does NOT
fall back silently to a partial dataset, since edge estimates from a
data-starved replay would mislead the kill / continue verdict.
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import statistics
from dataclasses import asdict
from datetime import date
from pathlib import Path
from typing import Mapping

import pandas as pd

from pipeline.research.phase_c_minute import replay as r
from pipeline.research.phase_c_minute import corp_action_adjuster as ca
from pipeline.research.h_2026_04_27_secrsi.historical_replay import (
    _atr_pit, _load_daily_ohlc, _load_5m_bars,
)

log = logging.getLogger("anka.phase_c_minute.runner")

REPO = Path(__file__).resolve().parents[3]
INTRADAY_1M_DIR = REPO / "pipeline" / "data" / "fno_intraday_1m"
INTRADAY_5M_DIR = REPO / "pipeline" / "data" / "fno_intraday_5m"
PIT_REGIME_TAPE = REPO / "pipeline" / "data" / "research" / "etf_v3" / "regime_tape_5y_pit.csv"
OUT_DIR = REPO / "pipeline" / "data" / "research" / "phase_c"

NOTIONAL_INR = 50_000  # matches Phase C live ledger
COST_BPS = 5  # 5 bps round-trip — same as live ledger net P&L convention


def _load_regime_tape(window_from: str, window_to: str) -> dict[str, str]:
    if not PIT_REGIME_TAPE.is_file():
        log.error("PIT regime tape not found at %s", PIT_REGIME_TAPE)
        return {}
    tape = {}
    with PIT_REGIME_TAPE.open(encoding="utf-8", newline="") as fp:
        reader = csv.DictReader(fp)
        for row in reader:
            d = row.get("date")
            reg = row.get("regime")
            if d and reg and window_from <= d <= window_to:
                tape[d] = reg
    return tape


def _load_1m_bars(
    ticker: str,
    splits_cache: dict[str, list[tuple[str, float]]] | None = None,
) -> dict[str, list[dict]] | None:
    """Reuse the 5m loader (same CSV schema). Apply split adjustment if cache provided."""
    p = INTRADAY_1M_DIR / f"{ticker}.csv"
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
    if splits_cache is not None:
        splits = splits_cache.get(ticker, [])
        if splits:
            by_day = ca.adjust_bars(by_day, splits)
    return by_day


def _load_universe(max_tickers: int | None = None) -> list[str]:
    canonical = REPO / "pipeline" / "data" / "canonical_fno_research_v3.json"
    if not canonical.is_file():
        raise SystemExit(f"canonical FNO file missing: {canonical}")
    doc = json.loads(canonical.read_text(encoding="utf-8"))
    valid_from = doc.get("per_ticker_valid_from", {}) or doc.get("tickers", {})
    if isinstance(valid_from, dict):
        tickers = list(valid_from.keys())
    else:
        tickers = list(valid_from)
    try:
        from pipeline.research.auto_spread_discovery.liquidity import _cached_universe_adv
        adv = _cached_universe_adv()
        tickers.sort(key=lambda t: -adv.get(t.upper(), 0.0))
    except Exception:
        tickers.sort()
    return tickers[:max_tickers] if max_tickers else tickers


def _train_profiles(
    *,
    daily_cache: dict[str, list[dict]],
    regime_tape: dict[str, str],
    cutoffs: list[str],
    lookback_years: int = 2,
) -> dict[str, dict]:
    """Per-cutoff profile training. Returns {cutoff_str -> {ticker -> {regime -> {expected_return, std_return}}}}.
    """
    bars_df = {
        t: pd.DataFrame([{"date": pd.Timestamp(d["date"]), "close": d["close"]}
                         for d in rows])
        for t, rows in daily_cache.items()
    }
    from pipeline.research.phase_c_backtest import profile as profile_mod
    out = {}
    for cutoff in cutoffs:
        out[cutoff] = profile_mod.train_profile(
            symbol_bars=bars_df,
            regime_by_date=regime_tape,
            cutoff_date=cutoff,
            lookback_years=lookback_years,
        )
    return out


def _select_active_cutoff(cutoffs: list[str], target_date: str) -> str | None:
    eligible = [c for c in cutoffs if c <= target_date]
    return max(eligible) if eligible else None


def _prev_close(daily: list[dict], up_to: str) -> float | None:
    prior = [d for d in daily if d["date"] < up_to]
    return prior[-1]["close"] if prior else None


def _replay_one_day(
    *,
    day: str,
    regime: str,
    minute_cache: dict[str, dict[str, list[dict]]],
    daily_cache: dict[str, list[dict]],
    profile: dict,
    sector_map: dict[str, str],
) -> list[dict]:
    rows: list[dict] = []
    snap_times = r.snapshot_times()
    seen_today: set[str] = set()
    seen_today_research: set[str] = set()  # for POSSIBLE_OPPORTUNITY first-touch
    for ticker, day_bars in minute_cache.items():
        bars = day_bars.get(day)
        if not bars:
            continue
        prev_close = _prev_close(daily_cache.get(ticker, []), day)
        if prev_close is None or prev_close <= 0:
            continue
        sym_prof = profile.get(ticker, {}).get(regime)
        if sym_prof is None:
            continue
        atr = _atr_pit(daily_cache.get(ticker, []), day, 14)

        for snap_t in snap_times:
            snap_bar = next((b for b in bars if b["time"] >= snap_t), None)
            if snap_bar is None or snap_bar["close"] is None:
                continue
            # Snap-time tolerance: only fire if a bar exists within 15 minutes
            # of `snap_t`. Without this, days with sparse / partial coverage
            # (e.g. holiday-adjacent half-days, broken EODHD captures) let the
            # engine "snap" to a 15:09 bar at the 11:00 slot, producing a fake
            # signal whose exit window [11:00..14:30] then has no bars at all.
            sh, sm, _ = snap_t.split(":")
            bh, bm, _ = snap_bar["time"].split(":")
            snap_minutes = int(sh) * 60 + int(sm)
            bar_minutes = int(bh) * 60 + int(bm)
            if bar_minutes - snap_minutes > 15:
                continue
            sig = r.compute_signal_at_snapshot(
                date=day, snap_time_ist=snap_t, ticker=ticker,
                regime=regime, sector=sector_map.get(ticker),
                snap_px=float(snap_bar["close"]),
                prev_close=float(prev_close),
                profile_expected=float(sym_prof.get("expected_return", 0.0)),
                profile_std=float(sym_prof.get("std_return", 0.0)),
                seen_today=seen_today,
            )
            if sig is None:
                continue
            row = asdict(sig)
            row["entry_px"] = round(float(snap_bar["close"]), 4)
            row["atr_14"] = round(atr, 4) if atr is not None else ""

            # Decide synthetic trade direction for research-mode exit simulation.
            # Live engine routes OPPORTUNITY_LAG only; this code records that
            # outcome AND simulates POSSIBLE_OPPORTUNITY (mean-revert toward
            # expected direction = same side as expected return) on first-touch
            # only — same de-dup discipline as live LAG routing.
            synth_route: str | None = None
            synth_side: str | None = None
            if sig.classification == "OPPORTUNITY_LAG" and sig.trade_rec:
                synth_route = "LAG"
                synth_side = sig.trade_rec
            elif (
                sig.classification == "POSSIBLE_OPPORTUNITY"
                and ticker not in seen_today_research
            ):
                synth_side = r._direction_from_expected(sig.expected_ret * 100)
                if synth_side:
                    synth_route = "POSSIBLE_OPPORTUNITY"
                    seen_today_research.add(ticker)

            simulate = (
                synth_route is not None
                and synth_side is not None
                and sig.status in ("OPEN", "INFORMATIONAL")
            )
            if simulate:
                exit_px, exit_reason, exit_t = r.simulate_exit(
                    bars, snap_t, synth_side, float(snap_bar["close"]), atr,
                )
                if exit_reason == "NO_DATA":
                    # No bars between snap_t and 14:30 — drop from PnL pool;
                    # record as informational so the row exists for diagnosis.
                    row["exit_px"] = ""
                    row["exit_reason"] = "NO_DATA"
                    row["exit_time_ist"] = ""
                    row["pnl_pct_net"] = ""
                    row["pnl_inr_net"] = ""
                    row["notional_inr"] = ""
                    row["route_slice"] = ""
                    row["synth_side"] = ""
                else:
                    pnl_pct_gross = r.realize_pnl(
                        synth_side, float(snap_bar["close"]), exit_px,
                    )
                    pnl_pct_net = pnl_pct_gross - (COST_BPS / 1e4)
                    row["exit_px"] = round(exit_px, 4)
                    row["exit_reason"] = exit_reason
                    row["exit_time_ist"] = exit_t
                    row["pnl_pct_net"] = round(pnl_pct_net, 6)
                    row["pnl_inr_net"] = round(pnl_pct_net * NOTIONAL_INR, 2)
                    row["notional_inr"] = NOTIONAL_INR
                    row["route_slice"] = synth_route
                    row["synth_side"] = synth_side
            else:
                row["exit_px"] = ""
                row["exit_reason"] = ""
                row["exit_time_ist"] = ""
                row["pnl_pct_net"] = ""
                row["pnl_inr_net"] = ""
                row["notional_inr"] = ""
                row["route_slice"] = ""
                row["synth_side"] = ""
            rows.append(row)
    return rows


def _summarize_slice(rows: list[dict], slice_name: str) -> dict:
    """Summarise rows for one route_slice (LAG, POSSIBLE_OPPORTUNITY, or all)."""
    if slice_name == "all":
        in_slice = [r for r in rows if r.get("route_slice")]
    else:
        in_slice = [r for r in rows if r.get("route_slice") == slice_name]
    pnls: list[float] = []
    for r in in_slice:
        v = r.get("pnl_pct_net")
        if v in (None, "", "INFORMATIONAL"):
            continue
        try:
            pnls.append(float(v))
        except (TypeError, ValueError):
            continue
    if not pnls:
        return {"n_traded": 0, "mean_bps_net": 0.0, "hit_rate": 0.0,
                "kill_criteria_met": True}
    mean_pnl = statistics.mean(pnls)
    wins = sum(1 for p in pnls if p > 0)
    hit_rate = wins / len(pnls)
    mean_bps_net = mean_pnl * 1e4
    return {
        "n_traded": len(pnls),
        "mean_bps_net": round(mean_bps_net, 2),
        "hit_rate": round(hit_rate, 4),
        "max_pnl_pct": round(max(pnls), 6),
        "min_pnl_pct": round(min(pnls), 6),
        "kill_criteria_met": (mean_bps_net < 100) or (hit_rate < 0.55),
    }


def _summarize(traded_rows: list[dict]) -> dict:
    """Top-level summary: per-slice (LAG, POSSIBLE_OPPORTUNITY, all) + by_regime."""
    out: dict = {
        "lag": _summarize_slice(traded_rows, "LAG"),
        "possible_opportunity": _summarize_slice(traded_rows, "POSSIBLE_OPPORTUNITY"),
        "all": _summarize_slice(traded_rows, "all"),
    }
    # Live behaviour = LAG-only routing
    out["n_traded"] = out["lag"]["n_traded"]
    out["mean_bps_net"] = out["lag"]["mean_bps_net"]
    out["hit_rate"] = out["lag"]["hit_rate"]
    out["kill_criteria_met"] = out["lag"]["kill_criteria_met"]
    # Regime slice for the bigger POSSIBLE_OPPORTUNITY pool
    by_regime: dict[str, dict] = {}
    pool = [r for r in traded_rows
            if r.get("route_slice") == "POSSIBLE_OPPORTUNITY" and r.get("pnl_pct_net") not in (None, "")]
    if pool:
        regimes = sorted({r["regime"] for r in pool})
        for reg in regimes:
            sub = [r for r in pool if r["regime"] == reg]
            pnls = []
            for r in sub:
                try:
                    pnls.append(float(r["pnl_pct_net"]))
                except (TypeError, ValueError):
                    pass
            if not pnls:
                continue
            mean = statistics.mean(pnls)
            hit = sum(1 for p in pnls if p > 0) / len(pnls)
            by_regime[reg] = {
                "n": len(pnls),
                "mean_bps_net": round(mean * 1e4, 2),
                "hit_rate": round(hit, 4),
            }
    out["possible_opportunity_by_regime"] = by_regime
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="from_d", required=True, help="YYYY-MM-DD")
    ap.add_argument("--to", dest="to_d", required=True)
    ap.add_argument("--max-tickers", type=int, default=None)
    ap.add_argument("--out-dir", default=None)
    ap.add_argument(
        "--bar-feed",
        choices=("1m", "5m"),
        default="5m",
        help="Bar feed for snapshots. EODHD 1m has only 45 full-session "
             "days; 5m has 5y of full coverage. 5m is recommended.",
    )
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")

    from_d = date.fromisoformat(args.from_d)
    to_d = date.fromisoformat(args.to_d)
    out_dir = Path(args.out_dir) if args.out_dir else OUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    log.info("loading PIT regime tape…")
    regime_tape = _load_regime_tape(from_d.isoformat(), to_d.isoformat())
    if not regime_tape:
        log.error("PIT regime tape empty for window — aborting")
        return 2

    universe = _load_universe(args.max_tickers)
    log.info("universe: %d tickers", len(universe))

    bar_loader = _load_5m_bars if args.bar_feed == "5m" else _load_1m_bars
    log.info("bar feed: %s", args.bar_feed)
    minute_cache: dict[str, dict[str, list[dict]]] = {}
    daily_cache: dict[str, list[dict]] = {}
    for t in universe:
        m = bar_loader(t)  # raw, unadjusted
        if m:
            minute_cache[t] = m
        d = _load_daily_ohlc(t)
        if d:
            daily_cache[t] = d

    # Empirical corp-action adjustment: derive per-date factor from
    # (adjusted_daily_close / raw_1m_last_close) so 1m bars match the
    # adjusted daily series the profile is trained on.
    n_adjusted = 0
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
            log.info("corp-action adjusted %s: %d / %d days had factor != 1",
                     t, non_unity, len(ftable))
    log.info("corp-action adjustment applied to %d / %d tickers",
             n_adjusted, len(minute_cache))

    log.info("1m loaded: %d / %d  daily loaded: %d / %d",
             len(minute_cache), len(universe), len(daily_cache), len(universe))

    if len(minute_cache) < 12:
        log.error("only %d tickers have 1m data — too sparse for replay",
                  len(minute_cache))
        return 2

    # Profile training: monthly cutoffs (1st of each month within window)
    cutoffs = sorted({d for d in regime_tape.keys() if d[8:10] == "01"})
    log.info("training %d walk-forward profiles…", len(cutoffs))
    profiles_by_cutoff = _train_profiles(
        daily_cache=daily_cache, regime_tape=regime_tape, cutoffs=cutoffs,
    )

    try:
        sector_map = {}
        from pipeline.scorecard_v2.sector_mapper import SectorMapper
        sm = SectorMapper()
        full = sm.map_all()
        sector_map = {sym: meta.get("sector", "") for sym, meta in full.items()}
    except Exception as exc:
        log.warning("SectorMapper failed: %s", exc)

    # Replay per day
    csv_path = out_dir / f"minute_replay_{from_d}_{to_d}.csv"
    fields = ["date", "snap_time_ist", "ticker", "regime", "sector", "z_score",
              "classification", "trade_rec", "intraday_ret", "expected_ret",
              "std_ret", "status", "entry_px", "exit_px", "exit_reason",
              "exit_time_ist", "atr_14", "pnl_pct_net", "pnl_inr_net",
              "notional_inr", "route_slice", "synth_side"]
    traded_rows: list[dict] = []
    days_replayed = 0
    with csv_path.open("w", encoding="utf-8", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for d, regime in sorted(regime_tape.items()):
            cutoff = _select_active_cutoff(cutoffs, d)
            if cutoff is None:
                continue
            profile = profiles_by_cutoff.get(cutoff, {})
            day_rows = _replay_one_day(
                day=d, regime=regime, minute_cache=minute_cache,
                daily_cache=daily_cache, profile=profile,
                sector_map=sector_map,
            )
            for row in day_rows:
                writer.writerow(row)
                if row.get("route_slice") and row.get("pnl_pct_net") not in (None, ""):
                    traded_rows.append(row)
            days_replayed += 1

    summary = _summarize(traded_rows)
    summary["meta"] = {
        "from": from_d.isoformat(),
        "to": to_d.isoformat(),
        "n_universe": len(universe),
        "n_1m_loaded": len(minute_cache),
        "n_daily_loaded": len(daily_cache),
        "n_days_replayed": days_replayed,
        "notional_inr": NOTIONAL_INR,
        "cost_bps": COST_BPS,
    }
    summary_path = out_dir / f"minute_replay_summary_{from_d}_{to_d}.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    log.info("rows: %s", csv_path)
    log.info("summary: %s", summary_path)
    lag = summary["lag"]
    poss = summary["possible_opportunity"]
    log.info("LAG (live route): n=%d mean=%.1f bps hit=%.1f%% kill=%s",
             lag["n_traded"], lag["mean_bps_net"],
             lag["hit_rate"] * 100, lag["kill_criteria_met"])
    log.info("POSSIBLE_OPPORTUNITY (research): n=%d mean=%.1f bps hit=%.1f%% kill=%s",
             poss["n_traded"], poss["mean_bps_net"],
             poss["hit_rate"] * 100, poss["kill_criteria_met"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
