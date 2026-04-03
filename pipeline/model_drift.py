"""
Anka Research Pipeline — Model Drift Performance Tracker
Logs MSI/ARCBE predictions at fire time, updates with actual outcomes at EOD.
Builds labelled training dataset for future ML model (target: 2026-04-24).
"""

import json
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

log = logging.getLogger("anka.model_drift")

IST = timezone(timedelta(hours=5, minutes=30))
DATA_DIR = Path(__file__).parent / "data"
PERF_FILE = DATA_DIR / "ml_performance.json"
LOCK_FILE = Path(__file__).parent / "logs" / "drift.lock"
LOCK_MAX_AGE_MINUTES = 25


def _acquire_lock() -> bool:
    """Return True if lock acquired, False if another writer is active."""
    if LOCK_FILE.exists():
        age = time.time() - LOCK_FILE.stat().st_mtime
        if age < LOCK_MAX_AGE_MINUTES * 60:
            return False
        LOCK_FILE.unlink(missing_ok=True)
    try:
        LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
        LOCK_FILE.write_text(str(os.getpid()), encoding="utf-8")
        return True
    except Exception:
        return False


def _release_lock() -> None:
    LOCK_FILE.unlink(missing_ok=True)


def _load_entries() -> list:
    if PERF_FILE.exists():
        try:
            return json.loads(PERF_FILE.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def _save_entries(entries: list) -> None:
    DATA_DIR.mkdir(exist_ok=True)
    PERF_FILE.write_text(
        json.dumps(entries, indent=2, default=str), encoding="utf-8"
    )


def log_prediction(signal_data: dict) -> None:
    """Log a prediction at signal fire time.

    signal_data keys:
        date, signal_id, source ('msi' | 'arcbe' | 'inr' | 'fii'),
        msi_score, regime, spread_name, predicted_direction,
        fii_net, dii_net, combined_flow, vix, usdinr_change,
        nifty_return, crude_change, arbitration_result (optional)
    """
    if not _acquire_lock():
        log.warning("Drift lock held — skipping prediction log for %s", signal_data.get("signal_id"))
        return
    try:
        entries = _load_entries()
        entry = {
            "date":                 signal_data.get("date", datetime.now(IST).strftime("%Y-%m-%d")),
            "signal_id":            signal_data.get("signal_id", "unknown"),
            "source":               signal_data.get("source", "unknown"),
            "msi_score":            signal_data.get("msi_score"),
            "regime":               signal_data.get("regime"),
            "spread_name":          signal_data.get("spread_name"),
            "predicted_direction":  signal_data.get("predicted_direction"),
            "fii_net":              signal_data.get("fii_net"),
            "dii_net":              signal_data.get("dii_net"),
            "combined_flow":        signal_data.get("combined_flow"),
            "vix":                  signal_data.get("vix"),
            "usdinr_change":        signal_data.get("usdinr_change"),
            "nifty_return":         signal_data.get("nifty_return"),
            "crude_change":         signal_data.get("crude_change"),
            "arbitration_result":   signal_data.get("arbitration_result"),
            "actual_pnl_pct":       None,
            "result":               None,
            "status":               "pending",
        }
        entries.append(entry)
        _save_entries(entries)
        log.info("Drift: logged prediction %s (%s)", entry["signal_id"], entry["source"])
    finally:
        _release_lock()


def update_outcome(date_str: str, signal_id: str, pnl_pct: float) -> None:
    """Update a pending entry with actual outcome. Called by run_eod_report.py."""
    if not _acquire_lock():
        log.warning("Drift lock held — skipping outcome update for %s", signal_id)
        return
    try:
        entries = _load_entries()
        updated = False
        for entry in entries:
            if entry["signal_id"] == signal_id and entry["status"] == "pending":
                entry["actual_pnl_pct"] = round(pnl_pct, 4)
                entry["result"] = "WIN" if pnl_pct > 0 else "LOSS"
                entry["status"] = "resolved"
                updated = True
                break
        if updated:
            _save_entries(entries)
            log.info("Drift: updated outcome %s → %s (%.2f%%)", signal_id, entry["result"], pnl_pct)
        else:
            log.debug("Drift: no pending entry for %s on %s", signal_id, date_str)
    finally:
        _release_lock()


def get_drift_summary() -> dict:
    """Return predicted vs actual win rates over last 30 days.

    Returns:
        predicted_win_rate: float (from historical hit rates)
        actual_win_rate: float (from resolved outcomes)
        drift_pct: float (gap between predicted and actual)
        is_drifting: bool (True if gap > 15%)
        n_samples: int
    """
    entries = _load_entries()
    cutoff = (datetime.now(IST) - timedelta(days=30)).strftime("%Y-%m-%d")
    resolved = [e for e in entries if e["status"] == "resolved" and e.get("date", "") >= cutoff]

    if not resolved:
        return {"predicted_win_rate": 0, "actual_win_rate": 0, "drift_pct": 0, "is_drifting": False, "n_samples": 0}

    actual_wins = sum(1 for e in resolved if e["result"] == "WIN")
    actual_wr = actual_wins / len(resolved) * 100

    # Predicted win rate: use 65% (our SIGNAL threshold) as baseline
    predicted_wr = 65.0

    drift = abs(predicted_wr - actual_wr)
    return {
        "predicted_win_rate": predicted_wr,
        "actual_win_rate": round(actual_wr, 1),
        "drift_pct": round(drift, 1),
        "is_drifting": drift > 15,
        "n_samples": len(resolved),
    }
