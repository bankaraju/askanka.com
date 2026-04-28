"""V1 universe loader: NIFTY-50 stock pool + options-liquid index pool.

Frozen at kickoff (2026-04-29 09:30 IST). Per spec §2 single-touch holdout
discipline — universe membership is locked for the 44-day window; mid-flight
NSE F&O additions/removals are NOT applied.
"""
from __future__ import annotations

import json
import statistics
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List

PIPELINE_ROOT = Path(__file__).resolve().parents[2]
NIFTY50_FILE = PIPELINE_ROOT.parent / "opus" / "config" / "nifty50.json"
OI_SNAPSHOT_DIR = PIPELINE_ROOT / "data" / "oi"

IST = timezone(timedelta(hours=5, minutes=30))

# Candidate index futures with options. Final V1 list = those clearing the
# §2 options-liquidity gate at kickoff.
INDEX_CANDIDATES: List[str] = [
    "NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "NIFTYNXT50",
    "NIFTYIT", "NIFTYAUTO", "NIFTYPHARMA", "NIFTYFMCG", "NIFTYBANK",
    "NIFTYMETAL", "NIFTYENERGY", "NIFTYREALTY", "NIFTYMEDIA", "NIFTYPSUBANK",
]

# Per spec §2 (locked thresholds for single-touch holdout)
LIQ_GATE_ATM_VOL_MIN = 5_000     # contracts/day median over prior 20d
LIQ_GATE_NEAR_OI_MIN = 50_000    # contracts
LIQ_GATE_SPREAD_MAX_PCT = 1.5    # ATM bid-ask spread as % of premium
LIQ_GATE_STRIKES_MIN = 5         # active strikes per side


def load_stocks_universe() -> List[str]:
    """Return the 50 NIFTY-50 constituents frozen for V1 holdout."""
    if not NIFTY50_FILE.exists():
        raise FileNotFoundError(
            f"NIFTY-50 reference list missing at {NIFTY50_FILE}. "
            "Create per spec §2: 50 NSE symbols, JSON list of upper-case strings."
        )
    data = json.loads(NIFTY50_FILE.read_text(encoding="utf-8"))
    if isinstance(data, dict) and "symbols" in data:
        symbols = data["symbols"]
    else:
        symbols = data
    if len(symbols) != 50:
        raise ValueError(f"NIFTY-50 list has {len(symbols)} symbols, expected 50")
    return [s.upper() for s in symbols]


def passes_options_liquidity_gate(snapshot: Dict) -> bool:
    """Apply §2 four-pronged gate to a per-instrument options snapshot.

    `snapshot` keys: atm_call_volume_median_20d, atm_put_volume_median_20d,
    near_month_total_oi, atm_bid_ask_spread_pct_median, active_strikes_count.

    All four conditions must hold.
    """
    atm_vol = (
        snapshot.get("atm_call_volume_median_20d", 0)
        + snapshot.get("atm_put_volume_median_20d", 0)
    )
    if atm_vol < LIQ_GATE_ATM_VOL_MIN:
        return False
    if snapshot.get("near_month_total_oi", 0) < LIQ_GATE_NEAR_OI_MIN:
        return False
    if snapshot.get("atm_bid_ask_spread_pct_median", 99.0) > LIQ_GATE_SPREAD_MAX_PCT:
        return False
    if snapshot.get("active_strikes_count", 0) < LIQ_GATE_STRIKES_MIN:
        return False
    return True


def _median_or_zero(xs):
    return statistics.median(xs) if xs else 0


def _build_options_snapshot(symbol: str) -> Dict:
    """Build a 20-day-rolling options-liquidity snapshot from oi_scanner archive.

    Reads the most-recent 20 daily snapshots under OI_SNAPSHOT_DIR/<symbol>/<date>_near_chain.json.
    If insufficient history, returns a snapshot that fails the gate (defensive default).
    """
    sym_dir = OI_SNAPSHOT_DIR / symbol
    if not sym_dir.exists():
        return {
            "atm_call_volume_median_20d": 0,
            "atm_put_volume_median_20d": 0,
            "near_month_total_oi": 0,
            "atm_bid_ask_spread_pct_median": 99.0,
            "active_strikes_count": 0,
        }
    daily_files = sorted(sym_dir.glob("*_near_chain.json"))[-20:]
    if not daily_files:
        return {
            "atm_call_volume_median_20d": 0,
            "atm_put_volume_median_20d": 0,
            "near_month_total_oi": 0,
            "atm_bid_ask_spread_pct_median": 99.0,
            "active_strikes_count": 0,
        }
    atm_call_vols, atm_put_vols, total_ois, spreads, strike_counts = [], [], [], [], []
    for f in daily_files:
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        atm_call_vols.append(d.get("atm_call_volume", 0))
        atm_put_vols.append(d.get("atm_put_volume", 0))
        total_ois.append(d.get("total_oi", 0))
        if d.get("atm_bid_ask_spread_pct") is not None:
            spreads.append(d["atm_bid_ask_spread_pct"])
        strike_counts.append(d.get("active_strikes_count", 0))
    return {
        "atm_call_volume_median_20d": _median_or_zero(atm_call_vols),
        "atm_put_volume_median_20d": _median_or_zero(atm_put_vols),
        "near_month_total_oi": _median_or_zero(total_ois),
        "atm_bid_ask_spread_pct_median": (
            statistics.median(spreads) if spreads else 99.0
        ),
        "active_strikes_count": int(_median_or_zero(strike_counts)),
    }


def load_v1_universe() -> Dict:
    """Resolve the V1 universe at kickoff.

    Returns: {"stocks": [...], "indices": [...], "frozen_at": iso_ts}
    """
    stocks = load_stocks_universe()
    indices = [
        sym for sym in INDEX_CANDIDATES
        if passes_options_liquidity_gate(_build_options_snapshot(sym))
    ]
    return {
        "stocks": stocks,
        "indices": indices,
        "frozen_at": datetime.now(IST).isoformat(),
    }
