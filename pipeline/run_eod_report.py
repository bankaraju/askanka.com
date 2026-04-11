"""
Anka Research Pipeline — Daily EOD Track Record
Sends a full P&L report to Telegram every trading day at 16:30 IST.

Foolproof requirements:
  - Wraps execution in try/except — sends error notice if it fails
  - Lockfile prevents duplicate sends
  - If Telegram send fails, writes to logs/eod_report_YYYY-MM-DD.txt as fallback
  - Runs even on flat days, even if no positions are open

Run at 16:30 IST via schtasks (eod_track_record.bat).
"""

import json
import logging
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

_lib = str(Path(__file__).parent / "lib")
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(
            Path(__file__).parent / "logs" / "eod_report.log",
            encoding="utf-8",
            delay=True,
        ),
    ],
)
log = logging.getLogger("anka.eod_report")

IST = timezone(timedelta(hours=5, minutes=30))
DATA_DIR = Path(__file__).parent / "data"
LOGS_DIR = Path(__file__).parent / "logs"
LOCK_FILE = DATA_DIR / ".eod_report.lock"
LOCK_MAX_AGE_MINUTES = 60  # generous — EOD report only runs once per day


def _acquire_lock() -> bool:
    """Create lockfile. Returns True if acquired, False if already running."""
    if LOCK_FILE.exists():
        age_minutes = (time.time() - LOCK_FILE.stat().st_mtime) / 60
        if age_minutes < LOCK_MAX_AGE_MINUTES:
            log.warning("Lock held (%.0f min old) — another instance running, skipping", age_minutes)
            return False
        log.info("Stale lock (%.0f min old) — removing", age_minutes)
        LOCK_FILE.unlink()
    LOCK_FILE.write_text(str(os.getpid()), encoding="utf-8")
    return True


def _release_lock() -> None:
    try:
        if LOCK_FILE.exists():
            LOCK_FILE.unlink()
    except Exception:
        pass


def _fallback_log(message: str) -> None:
    """Write report to file when Telegram send fails."""
    LOGS_DIR.mkdir(exist_ok=True)
    today = datetime.now(IST).strftime("%Y-%m-%d")
    fallback_file = LOGS_DIR / f"eod_report_{today}.txt"
    try:
        fallback_file.write_text(message, encoding="utf-8")
        log.info("EOD report saved to fallback file: %s", fallback_file)
    except Exception as exc:
        log.error("Fallback file write failed: %s", exc)


def _run_eod_report() -> None:
    """Core EOD report logic. Called inside try/except wrapper."""
    from signal_tracker import (
        load_open_signals, load_closed_signals, fetch_current_prices,
        compute_signal_pnl,
    )
    from telegram_bot import format_eod_track_record, send_message

    today_str = datetime.now(IST).strftime("%Y-%m-%d")

    # ── Open positions ────────────────────────────────────────────────────
    open_sigs = load_open_signals()
    open_positions = []

    if open_sigs:
        all_tickers = list({
            t for sig in open_sigs
            for leg in sig.get("long_legs", []) + sig.get("short_legs", [])
            for t in [leg["ticker"]]
        })
        current_prices = fetch_current_prices(all_tickers)
    else:
        current_prices = {}

    for sig in open_sigs:
        pnl = compute_signal_pnl(sig, current_prices)
        levels = sig.get("_data_levels", {})

        # P&L colour
        sp = pnl["spread_pnl_pct"]
        daily_stop = levels.get("daily_stop", None)
        if sp > 0:
            pnl_emoji = "🟢"
        elif daily_stop and sp < 0 and sp > daily_stop * 0.8:
            pnl_emoji = "🟠"  # within 20% of stop
        elif daily_stop and sp <= daily_stop:
            pnl_emoji = "🔴"
        else:
            pnl_emoji = "⚪" if abs(sp) < 0.1 else "🟠"

        # Days held
        entry_ts = sig.get("open_timestamp") or sig.get("timestamp", "")
        try:
            entry_date = datetime.fromisoformat(entry_ts).date()
            days_held = (datetime.now(IST).date() - entry_date).days + 1
        except Exception:
            days_held = 1

        tier = sig.get("tier", "SIGNAL")
        tier_badge = "🔵" if tier == "SIGNAL" else "🟡"

        open_positions.append({
            "spread_name":    sig.get("spread_name", sig.get("trade", {}).get("spread_name", "?")),
            "tier_badge":     tier_badge,
            "entry_date":     entry_date.isoformat() if "entry_date" in dir() else "?",
            "days_held":      days_held,
            "spread_pnl_pct": sp,
            "pnl_emoji":      pnl_emoji,
            "daily_stop":     daily_stop,
            "long_legs":      pnl["long_legs"],
            "short_legs":     pnl["short_legs"],
            "corr_break":     levels.get("corr_break", False),
        })

    # ── Closed this week ──────────────────────────────────────────────────
    from signal_tracker import get_weekly_closed_signals
    closed_this_week = get_weekly_closed_signals(days=7)
    closed_summary = []
    for sig in closed_this_week:
        fp = sig.get("final_pnl", {})
        sp = fp.get("spread_pnl_pct", 0.0)
        result_badge = "🟩 WIN" if sp > 0 else "🟥 LOSS"

        entry_ts = sig.get("open_timestamp") or sig.get("timestamp", "")
        close_ts = sig.get("close_timestamp", "")
        try:
            entry_date = datetime.fromisoformat(entry_ts).date()
            close_date = datetime.fromisoformat(close_ts).date()
            days_held = (close_date - entry_date).days + 1
        except Exception:
            days_held = 1

        exit_reason = sig.get("status", "STOPPED")
        if exit_reason == "STOPPED_OUT":
            exit_label = "stopped"
        elif exit_reason == "STOPPED_OUT_2DAY":
            exit_label = "2-day stop"
        elif exit_reason == "TARGET_HIT":
            exit_label = "target"
        else:
            exit_label = exit_reason.lower()

        closed_summary.append({
            "spread_name":    sig.get("spread_name", "?"),
            "result_badge":   result_badge,
            "spread_pnl_pct": sp,
            "days_held":      days_held,
            "exit_label":     exit_label,
        })

    # ── Running scorecard ─────────────────────────────────────────────────
    all_closed = load_closed_signals()

    # Open signals contribute 🔷 to the strip (ongoing, outcome unknown)
    open_strip = "🔷" * len(open_sigs)
    recent_closed_20 = all_closed[-20:] if all_closed else []

    closed_strip = ""
    for sig in recent_closed_20:
        sp = sig.get("final_pnl", {}).get("spread_pnl_pct", 0.0)
        closed_strip += "🟩" if sp > 0 else "🟥"

    # Strip: open positions first (ongoing), then last closed ones
    strip = open_strip + closed_strip
    strip = strip[:20]  # cap at 20 blocks

    # Tier-split stats (closed only — can't count open as wins/losses yet)
    signal_closed    = [s for s in all_closed if s.get("tier") == "SIGNAL"]
    exploring_closed = [s for s in all_closed if s.get("tier") == "EXPLORING"]

    def _tier_stats(signals):
        if not signals:
            return {"wins": 0, "losses": 0, "avg_pnl": 0.0}
        wins = sum(1 for s in signals if s.get("final_pnl", {}).get("spread_pnl_pct", 0) > 0)
        pnls = [s.get("final_pnl", {}).get("spread_pnl_pct", 0.0) for s in signals]
        return {
            "wins":    wins,
            "losses":  len(signals) - wins,
            "avg_pnl": round(sum(pnls) / len(pnls), 2),
        }

    total_closed = len(all_closed)
    total_open = len(open_sigs)

    # Collect current P&L of open positions by tier for scorecard display
    open_signal_pnls    = [p["spread_pnl_pct"] for p in open_positions if "🔵" in p.get("tier_badge", "")]
    open_exploring_pnls = [p["spread_pnl_pct"] for p in open_positions if "🟡" in p.get("tier_badge", "")]

    scorecard = {
        "strip":               strip,
        "signal_stats":        _tier_stats(signal_closed),
        "exploring_stats":     _tier_stats(exploring_closed),
        "total_signals":       total_closed + total_open,
        "total_open":          total_open,
        "total_closed":        total_closed,
        "total_wins":          sum(1 for s in all_closed if s.get("final_pnl", {}).get("spread_pnl_pct", 0) > 0),
        "open_signal_pnls":    open_signal_pnls,
        "open_exploring_pnls": open_exploring_pnls,
    }
    if total_closed > 0:
        scorecard["win_rate_pct"] = round(
            scorecard["total_wins"] / total_closed * 100, 1  # win rate over closed only
        )
    else:
        scorecard["win_rate_pct"] = 0.0

    # ── Macro context (MSI if available) ─────────────────────────────────
    macro_line = ""
    institutional_data = None
    try:
        from macro_stress import compute_msi, msi_bar, append_msi_history
        msi = compute_msi()
        append_msi_history(msi)
        macro_line = msi_bar(msi["msi_score"], msi["regime"])
        # Extract institutional data for display
        fii_net = msi.get("fii_net")
        dii_net = msi.get("dii_net")
        if fii_net is not None:
            institutional_data = {
                "fii_net": fii_net,
                "dii_net": dii_net or 0.0,
            }
    except Exception as exc:
        log.warning("MSI computation failed (omitting from report): %s", exc)

    # FII flow line (legacy, kept as fallback if institutional_data is None)
    fii_line = ""
    if institutional_data:
        fii = institutional_data["fii_net"]
        emoji = "🟢" if fii > 0 else "🔴"
        fii_line = f"FII today: {emoji} ₹{abs(fii):,.0f} cr {'net buy' if fii > 0 else 'net sell'}"

    # ── Update drift tracker with outcomes ────────────────────────────────
    try:
        from model_drift import update_outcome
        for sig in open_sigs:
            pnl = compute_signal_pnl(sig, current_prices)
            update_outcome(today_str, sig.get("signal_id", ""), pnl["spread_pnl_pct"])
    except Exception as exc:
        log.debug("Drift tracker outcome update failed (non-fatal): %s", exc)

    # ── Format and send ───────────────────────────────────────────────────
    message = format_eod_track_record(
        date_str=today_str,
        open_positions=open_positions,
        closed_this_week=closed_summary,
        scorecard=scorecard,
        macro_line=macro_line,
        fii_line=fii_line,
        institutional_data=institutional_data,
    )

    try:
        send_message(message)
        log.info("EOD track record sent successfully")
    except Exception as exc:
        log.error("Telegram send failed: %s", exc)
        _fallback_log(message)


def main() -> None:
    """Entry point. Wraps _run_eod_report with error handler."""
    LOGS_DIR.mkdir(exist_ok=True)
    DATA_DIR.mkdir(exist_ok=True)

    if not _acquire_lock():
        sys.exit(0)

    try:
        _run_eod_report()
    except Exception as exc:
        error_msg = f"⚠️ EOD report failed — {exc}"
        log.error(error_msg, exc_info=True)
        # Best-effort Telegram error notice
        try:
            from telegram_bot import send_message
            send_message(error_msg)
        except Exception:
            _fallback_log(error_msg)
    finally:
        _release_lock()


if __name__ == "__main__":
    main()
