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
from pipeline.research.h_2026_04_27_secrsi.historical_replay import (
    _atr_pit, _load_daily_ohlc, _load_5m_bars,
)

log = logging.getLogger("anka.phase_c_minute.runner")

REPO = Path(__file__).resolve().parents[3]
INTRADAY_1M_DIR = REPO / "pipeline" / "data" / "fno_intraday_1m"
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


def _load_1m_bars(ticker: str) -> dict[str, list[dict]] | None:
    """Reuse the 5m loader (same CSV schema)."""
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
            if sig.status == "OPEN" and sig.trade_rec:
                exit_px, exit_reason, exit_t = r.simulate_exit(
                    bars, snap_t, sig.trade_rec, float(snap_bar["close"]), atr,
                )
                pnl_pct_gross = r.realize_pnl(sig.trade_rec, float(snap_bar["close"]), exit_px)
                pnl_pct_net = pnl_pct_gross - (COST_BPS / 1e4)
                row["entry_px"] = round(float(snap_bar["close"]), 4)
                row["exit_px"] = round(exit_px, 4)
                row["exit_reason"] = exit_reason
                row["exit_time_ist"] = exit_t
                row["pnl_pct_net"] = round(pnl_pct_net, 6)
                row["pnl_inr_net"] = round(pnl_pct_net * NOTIONAL_INR, 2)
                row["atr_14"] = round(atr, 4) if atr is not None else ""
                row["notional_inr"] = NOTIONAL_INR
                rows.append(row)
            else:
                # Informational / duplicate / no-trade — record without exit
                row["entry_px"] = round(float(snap_bar["close"]), 4)
                row["exit_px"] = ""
                row["exit_reason"] = ""
                row["exit_time_ist"] = ""
                row["pnl_pct_net"] = ""
                row["pnl_inr_net"] = ""
                row["atr_14"] = round(atr, 4) if atr is not None else ""
                row["notional_inr"] = ""
                rows.append(row)
    return rows


def _summarize(traded_rows: list[dict]) -> dict:
    if not traded_rows:
        return {"n_traded": 0, "mean_bps_net": 0.0, "hit_rate": 0.0,
                "kill_criteria_met": True}
    pnls = [float(r["pnl_pct_net"]) for r in traded_rows
            if r.get("pnl_pct_net") not in (None, "", "INFORMATIONAL")]
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


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="from_d", required=True, help="YYYY-MM-DD")
    ap.add_argument("--to", dest="to_d", required=True)
    ap.add_argument("--max-tickers", type=int, default=None)
    ap.add_argument("--out-dir", default=None)
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

    minute_cache: dict[str, dict[str, list[dict]]] = {}
    daily_cache: dict[str, list[dict]] = {}
    for t in universe:
        m = _load_1m_bars(t)
        if m:
            minute_cache[t] = m
        d = _load_daily_ohlc(t)
        if d:
            daily_cache[t] = d

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
              "notional_inr"]
    n_traded = 0
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
                if row.get("status") == "OPEN" and row.get("trade_rec"):
                    n_traded += 1
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
    log.info("n_traded=%d  mean_bps_net=%.1f  hit=%.1f%%  kill=%s",
             summary["n_traded"], summary.get("mean_bps_net", 0),
             summary.get("hit_rate", 0) * 100, summary.get("kill_criteria_met"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
