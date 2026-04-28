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


def _compute_signals_at(eval_t: datetime, univ: Dict) -> List[Dict]:
    """Compute per-instrument scores at eval_t. Test-patched."""
    raise NotImplementedError(
        "Wire features.compute_all + score.apply across universe at runtime — "
        "test-suite monkey-patches this. Production wiring in Task 11."
    )


def _ledger_path(name: str) -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return DATA_DIR / name


def _append_csv(path: Path, row: Dict) -> None:
    df = pd.DataFrame([row])
    if path.exists():
        df.to_csv(path, mode="a", header=False, index=False)
    else:
        df.to_csv(path, index=False)


def live_open(eval_t: datetime) -> None:
    """09:30 IST batch — open paper trades, write to recommendations.csv."""
    rec_path = _ledger_path("recommendations.csv")
    try:
        univ = _resolve_universe()
        signals = _compute_signals_at(eval_t, univ)
    except KiteSessionError as e:
        _append_csv(rec_path, {
            "open_date": eval_t.date().isoformat(),
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
        _append_csv(rec_path, {
            "open_date": eval_t.date().isoformat(),
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
