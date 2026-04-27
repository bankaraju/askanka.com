"""Scanner pattern signals endpoint.

Per spec section 6.7. Returns the full pattern_signals_today.json contents merged
with a cumulative_paired_shadow rollup computed from the close ledgers.
"""
import json
from pathlib import Path

from fastapi import APIRouter, HTTPException

router = APIRouter()

PATTERN_SIGNALS_PATH = Path("pipeline/data/scanner/pattern_signals_today.json")
PAIRED_LEDGER_PATH = Path(
    "pipeline/data/research/scanner/live_paper_scanner_options_ledger.json")


def _resolve_signals_path() -> Path:
    return PATTERN_SIGNALS_PATH


def _resolve_ledger_path() -> Path:
    return PAIRED_LEDGER_PATH


def _cumulative_rollup() -> dict:
    p = _resolve_ledger_path()
    if not p.exists():
        return {"n_closed": 0, "win_rate": None,
                "mean_options_pnl_pct": None, "mean_futures_pnl_pct": None,
                "mean_paired_diff": None}
    rows = json.loads(p.read_text())
    closed = [r for r in rows if r.get("status") == "CLOSED"]
    if not closed:
        return {"n_closed": 0, "win_rate": None,
                "mean_options_pnl_pct": None, "mean_futures_pnl_pct": None,
                "mean_paired_diff": None}
    n = len(closed)
    opt = [r["pnl_net_pct"] for r in closed if r.get("pnl_net_pct") is not None]
    fut = [r.get("futures_pnl_net_pct") for r in closed
           if r.get("futures_pnl_net_pct") is not None]
    wins = sum(1 for r in closed if (r.get("pnl_net_pct") or 0) > 0)
    return {
        "n_closed": n,
        "win_rate": wins / n if n else None,
        "mean_options_pnl_pct": sum(opt) / len(opt) if opt else None,
        "mean_futures_pnl_pct": sum(fut) / len(fut) if fut else None,
        "mean_paired_diff": (sum(opt) / len(opt) - sum(fut) / len(fut))
            if opt and fut else None,
    }


@router.get("/api/scanner/pattern-signals")
def get_pattern_signals():
    p = _resolve_signals_path()
    if not p.exists():
        raise HTTPException(status_code=404, detail="pattern_signals_today.json missing")
    payload = json.loads(p.read_text())
    payload["cumulative_paired_shadow"] = _cumulative_rollup()
    return payload
