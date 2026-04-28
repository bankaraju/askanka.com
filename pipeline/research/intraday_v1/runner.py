"""V1 framework CLI driver — single entry point for all paper-trade lifecycle ops.

Subcommands:
  loader-refresh   — 04:30 IST nightly cache refresh
  live-open        — 09:30 IST fixed batch (writes recommendations.csv)
  shadow-eval      — every 15 min 09:30..13:00 (writes shadow_recs.csv)
  live-close       — 14:30 IST mechanical close
  recalibrate      — last Sunday of month 02:00 IST monthly weight refit
  verdict          — end-of-holdout 2026-07-04 strict-gate evaluator

Idempotent: re-runs of any subcommand on the same (date, eval_t) are no-ops
on already-written rows.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List

import pandas as pd

from pipeline.research.intraday_v1 import (
    exit_engine, features, karpathy_fit, loader, options_paired, score, universe, verdict,
)

PIPELINE_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PIPELINE_ROOT / "data" / "research" / "h_2026_04_29_intraday_v1"
WEIGHTS_DIR = DATA_DIR / "weights"
CACHE_DIR = DATA_DIR / "cache_1min"
PCR_DIR = DATA_DIR / "pcr"
IST = timezone(timedelta(hours=5, minutes=30))

log = logging.getLogger("intraday_v1.runner")


class KiteSessionError(RuntimeError):
    """Raised when Kite session is unavailable."""


def _resolve_universe() -> Dict:
    """Test-monkeypatch hook for universe resolution."""
    return universe.load_v1_universe()


def _fetch_ltp(symbol: str) -> float:
    """Test-monkeypatch hook for live price fetch."""
    from pipeline.kite_client import KiteClient
    return KiteClient().get_ltp(symbol)


def _read_bars(sym: str):
    """Read cached 1-min bars from runner.CACHE_DIR.

    Deviation from Task 11 plan-verbatim: the plan called ``loader.read_cache(sym)``
    but that reads from ``loader.CACHE_DIR`` (its own module-level constant), which
    the verbatim test does NOT monkeypatch. In production both constants resolve to
    the same path; in tests the runner's CACHE_DIR is the source of truth and the
    plan's verbatim test patches only ``runner.CACHE_DIR``. Reading directly via
    ``pd.read_parquet`` from the runner-scoped CACHE_DIR honors that contract
    without weakening production behavior.
    """
    p = CACHE_DIR / f"{sym}.parquet"
    if not p.exists():
        return None
    return pd.read_parquet(p)


def _compute_signals_at(eval_t: datetime, univ: Dict) -> List[Dict]:
    """Compute per-instrument scores at eval_t for the resolved universe."""
    weights_path = DATA_DIR / "weights" / "latest_stocks.json"
    if not weights_path.exists():
        log.warning(f"no stocks weights at {weights_path}, skipping")
        return []
    weights_data = json.loads(weights_path.read_text(encoding="utf-8"))
    import numpy as _np
    weights = _np.array(weights_data["weights"], dtype=float)
    long_t = float(weights_data["long_threshold"])
    short_t = float(weights_data["short_threshold"])

    # Sector mapping: stock symbol → sector index symbol. Production wiring
    # reads opus/artifacts/sectors/ (per reference_sector_mapper_artifact_dependency.md).
    # Hard-coded fallback for V1 kickoff; expanded to full NIFTY-50 in production.
    SECTOR_INDEX_MAP = {
        "HDFCBANK": "NIFTYBANK", "ICICIBANK": "NIFTYBANK", "AXISBANK": "NIFTYBANK",
        "KOTAKBANK": "NIFTYBANK", "SBIN": "NIFTYBANK", "INDUSINDBK": "NIFTYBANK",
        "INFY": "NIFTYIT", "TCS": "NIFTYIT", "HCLTECH": "NIFTYIT",
        "TECHM": "NIFTYIT", "WIPRO": "NIFTYIT",
        "RELIANCE": "NIFTYENERGY", "ONGC": "NIFTYENERGY", "BPCL": "NIFTYENERGY",
        "GAIL": "NIFTYENERGY", "COALINDIA": "NIFTYENERGY", "NTPC": "NIFTYENERGY",
        "SUNPHARMA": "NIFTYPHARMA", "CIPLA": "NIFTYPHARMA", "DRREDDY": "NIFTYPHARMA",
        "DIVISLAB": "NIFTYPHARMA", "APOLLOHOSP": "NIFTYPHARMA",
        "MARUTI": "NIFTYAUTO", "TATAMOTORS": "NIFTYAUTO", "BAJAJ-AUTO": "NIFTYAUTO",
        "EICHERMOT": "NIFTYAUTO", "HEROMOTOCO": "NIFTYAUTO", "M&M": "NIFTYAUTO",
        "HINDUNILVR": "NIFTYFMCG", "ITC": "NIFTYFMCG", "NESTLEIND": "NIFTYFMCG",
        "BRITANNIA": "NIFTYFMCG", "TATACONSUM": "NIFTYFMCG",
        "TATASTEEL": "NIFTYMETAL", "JSWSTEEL": "NIFTYMETAL", "HINDALCO": "NIFTYMETAL",
        # Stocks not mapped fall back to NIFTY (broad market) for RS computation
    }
    out: List[Dict] = []
    for sym in univ["stocks"]:
        bars = _read_bars(sym)
        if bars is None or bars.empty:
            continue
        sector_sym = SECTOR_INDEX_MAP.get(sym, "NIFTY")
        sector_bars = _read_bars(sector_sym)
        # No synthetic fallback: when the sector cache is missing we cannot compute
        # rs_vs_sector against the stock's own bars (that would silently return 0
        # and produce a bogus signal). Skip the instrument; NaN propagates via
        # score.apply when sector data is absent.
        if sector_bars is None:
            log.info(f"sector cache missing for {sym} -> {sector_sym}, skipping")
            continue
        sector_df = sector_bars
        try:
            today_pcr = json.loads((PCR_DIR / f"{sym}_today.json").read_text(encoding="utf-8"))
            two_d_pcr = json.loads((PCR_DIR / f"{sym}_2d_ago.json").read_text(encoding="utf-8"))
        except FileNotFoundError:
            today_pcr = {"put_oi_total_next_month": 0, "call_oi_total_next_month": 0}
            two_d_pcr = today_pcr
        # Stub volume_history — production reads 20d aggregated cache
        history = pd.DataFrame({
            "minute_of_day_idx": list(range(60)),
            "mean_cum_volume_20d": [1000.0 * (i + 1) for i in range(60)],
            "std_cum_volume_20d":  [200.0] * 60,
        })
        feats = features.compute_all(
            instrument_df=bars, sector_df=sector_df, eval_t=eval_t,
            today_pcr=today_pcr, two_days_ago_pcr=two_d_pcr,
            volume_history=history,
        )
        s = score.apply(feats, weights)
        decision_str = score.decision(s, long_t, short_t)
        # Entry price — last close before eval_t
        prior = bars[bars["timestamp"] < eval_t]
        entry_price = float(prior.iloc[-1]["close"]) if not prior.empty else float("nan")
        out.append({
            "instrument": sym,
            "instrument_class": "stocks",
            "score": s,
            "decision": decision_str,
            "entry_price": entry_price,
            "atr14": 0.0,  # populate from fno_historical in production
            "weights_used": weights_data["weights"],
        })
    return out


def _ledger_path(name: str) -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return DATA_DIR / name


def _append_csv(path: Path, row: Dict) -> None:
    df = pd.DataFrame([row])
    if path.exists():
        df.to_csv(path, mode="a", header=False, index=False)
    else:
        df.to_csv(path, index=False)


def _already_open_today(rec_path: Path, open_date: str, instrument: str) -> bool:
    """Idempotency check for live_open: True if a row with this (open_date, instrument)
    is already present in recommendations.csv. Survives scheduler retries.
    """
    if not rec_path.exists():
        return False
    try:
        df = pd.read_csv(rec_path)
    except (pd.errors.EmptyDataError, FileNotFoundError):
        return False
    if df.empty:
        return False
    if "open_date" not in df.columns or "instrument" not in df.columns:
        return False
    return ((df["open_date"].astype(str) == open_date) & (df["instrument"] == instrument)).any()


def live_open(eval_t: datetime) -> None:
    """09:30 IST batch — open paper trades, write to recommendations.csv.

    Idempotent on (open_date, instrument): re-runs of the 09:30 task on the same
    date will not duplicate rows. NO_KITE_SESSION sentinel is also deduped.
    """
    rec_path = _ledger_path("recommendations.csv")
    open_date = eval_t.date().isoformat()
    try:
        univ = _resolve_universe()
        signals = _compute_signals_at(eval_t, univ)
    except KiteSessionError as e:
        if _already_open_today(rec_path, open_date, "_GLOBAL_"):
            return
        _append_csv(rec_path, {
            "open_date": open_date,
            "instrument": "_GLOBAL_",
            "instrument_class": "_GLOBAL_",
            "direction": "",
            "entry_price": "",
            "atr14": "",
            "score": "",
            "status": "NO_KITE_SESSION",
            "exit_price": "",
            "pnl_pct": "",
            "exit_reason": str(e),
        })
        return
    for sig in signals:
        if sig["decision"] == "SKIP":
            continue
        if _already_open_today(rec_path, open_date, sig["instrument"]):
            continue
        _append_csv(rec_path, {
            "open_date": open_date,
            "instrument": sig["instrument"],
            "instrument_class": sig["instrument_class"],
            "direction": sig["decision"],
            "entry_price": sig["entry_price"],
            "atr14": sig["atr14"],
            "score": sig["score"],
            "status": "OPEN",
            "exit_price": "",
            "pnl_pct": "",
            "exit_reason": "",
        })


def shadow_eval(eval_t: datetime) -> None:
    """15-min shadow — write would-have-fired rows to shadow_recs.csv."""
    shadow_path = _ledger_path("shadow_recs.csv")
    try:
        univ = _resolve_universe()
        signals = _compute_signals_at(eval_t, univ)
    except KiteSessionError:
        return
    for sig in signals:
        if sig["decision"] == "SKIP":
            continue
        _append_csv(shadow_path, {
            "eval_timestamp": eval_t.isoformat(),
            "instrument": sig["instrument"],
            "instrument_class": sig["instrument_class"],
            "direction": sig["decision"],
            "entry_price": sig["entry_price"],
            "score": sig["score"],
        })


def live_close(eval_t: datetime) -> None:
    """14:30 IST mechanical close on all open V1 positions."""
    rec_path = _ledger_path("recommendations.csv")
    if not rec_path.exists():
        return
    df = pd.read_csv(rec_path)
    # Coerce string-bearing columns to object dtype before .loc assignment to
    # avoid pandas FutureWarning: "Setting an item of incompatible dtype"
    # when these columns are inferred as float64 from empty/NaN values.
    for col in ("status", "exit_reason", "exit_price", "pnl_pct"):
        if col in df.columns:
            df[col] = df[col].astype("object")
    for idx, row in df.iterrows():
        if row.get("status") != "OPEN":
            continue
        ltp = _fetch_ltp(row["instrument"])
        result = exit_engine.mechanical_exit(eval_t, ltp)
        df.loc[idx, "status"] = result["status"]
        df.loc[idx, "exit_price"] = result["exit_price"]
        df.loc[idx, "exit_reason"] = result["exit_reason"]
        if row["direction"] == "LONG":
            pnl = (ltp - float(row["entry_price"])) / float(row["entry_price"]) * 100.0
        else:
            pnl = (float(row["entry_price"]) - ltp) / float(row["entry_price"]) * 100.0
        df.loc[idx, "pnl_pct"] = pnl
    df.to_csv(rec_path, index=False)


def loader_refresh() -> None:
    """04:30 IST nightly cache refresh for the V1 universe."""
    univ = _resolve_universe()
    for sym in univ["stocks"] + univ["indices"]:
        try:
            loader.refresh_cache(sym, days=60)
        except loader.LoaderError as e:
            log.warning(f"loader-refresh failed for {sym}: {e}")


def recalibrate(pool: str) -> None:
    """Monthly weight refit on prior 60-day window for the named pool."""
    if pool not in ("stocks", "indices"):
        raise ValueError(f"pool must be stocks or indices, got {pool}")
    raise NotImplementedError("Recalibration in-sample assembly is wired in subsequent commit")


def evaluate_verdict() -> Dict:
    """End-of-holdout strict-gate evaluation."""
    rec_path = _ledger_path("recommendations.csv")
    if not rec_path.exists():
        return {"pass": False, "reason": "NO_LEDGER"}
    df = pd.read_csv(rec_path)
    fragility_path = DATA_DIR / "fragility_results.json"
    if fragility_path.exists():
        fragility = json.loads(fragility_path.read_text(encoding="utf-8"))
    else:
        fragility = {"perturbed_results": []}
    baseline = verdict.compute_baseline_hit_rate(df)
    out = DATA_DIR / "verdict_2026_07_04.json"
    return verdict.write_verdict(df, fragility, baseline_hit_rate=baseline, out_path=out)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser("intraday_v1.runner")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("loader-refresh")
    sub.add_parser("live-open")
    sub.add_parser("shadow-eval")
    sub.add_parser("live-close")
    rc = sub.add_parser("recalibrate")
    rc.add_argument("--pool", choices=["stocks", "indices"], required=True)
    sub.add_parser("verdict")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    now = datetime.now(IST)
    if args.cmd == "loader-refresh":
        loader_refresh()
    elif args.cmd == "live-open":
        live_open(eval_t=now)
    elif args.cmd == "shadow-eval":
        shadow_eval(eval_t=now)
    elif args.cmd == "live-close":
        live_close(eval_t=now)
    elif args.cmd == "recalibrate":
        recalibrate(pool=args.pool)
    elif args.cmd == "verdict":
        evaluate_verdict()


if __name__ == "__main__":
    main()
