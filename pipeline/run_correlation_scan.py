"""
Anka ARCBE — Overnight Correlation Scan Orchestrator
Scheduled: 23:00 IST daily via schtask AnkaARCBE2300

Fetches price + driver data, runs all 5 methods, writes:
  data/correlation_report_YYYY-MM-DD.json
"""

import json
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

_lib = str(Path(__file__).parent / "lib")
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "arcbe.log"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("anka.arcbe.scan")

IST = timezone(timedelta(hours=5, minutes=30))
DATA_DIR = Path(__file__).parent / "data"


def run_scan() -> dict:
    """Run full ARCBE scan. Returns the report dict."""
    from config import INDIA_SIGNAL_STOCKS, ARCBE_SECTOR_GROUPS, ARCBE_HYPOTHESIS_SPREADS, INDIA_SPREAD_PAIRS
    from correlation_monitor import (
        fetch_price_matrix,
        fetch_driver_matrix,
        beta_shift_detector,
        linkage_scanner,
        sector_dispersion,
        beta_decay_detector,
        regime_score,
        validate_hypotheses,
    )

    today = datetime.now(IST).strftime("%Y-%m-%d")
    log.info("ARCBE scan started for %s", today)

    # ── 1. Fetch data ──────────────────────────────────────────────────────
    all_tickers = list(INDIA_SIGNAL_STOCKS.keys())
    log.info("Fetching price matrix for %d tickers...", len(all_tickers))
    price_df = fetch_price_matrix(all_tickers, days=400)
    log.info("Price matrix: %s", price_df.shape)

    log.info("Fetching driver matrix...")
    driver_df = fetch_driver_matrix(days=400)
    log.info("Driver matrix: %s", driver_df.shape)

    if price_df.empty:
        log.error("Price matrix empty — aborting scan")
        return {}

    # ── 2. Regime score ────────────────────────────────────────────────────
    log.info("Computing regime score...")
    regime = regime_score(driver_df)
    log.info("Regime: %s (score %d)", regime["label"], regime["score"])

    # ── 3. Method 1: Beta shift ────────────────────────────────────────────
    log.info("Running Method 1: beta shift detector...")
    beta_shifts = beta_shift_detector(price_df, driver_df)
    log.info("Beta shifts: %d non-normal results", len(beta_shifts))

    # ── 4. Method 3: Linkage scanner (bottom-up discovery) ────────────────
    log.info("Running Method 3: linkage scanner...")
    linkages = linkage_scanner(price_df, driver_df, top_n=10)
    log.info("Linkage discoveries: %d", len(linkages))

    # ── 5. Method 4: Sector dispersion ────────────────────────────────────
    log.info("Running Method 4: sector dispersion...")
    dispersion = sector_dispersion(price_df, ARCBE_SECTOR_GROUPS)
    log.info("Dispersion: %d sectors analysed", len(dispersion))

    # ── 6. Method 5: Beta decay ────────────────────────────────────────────
    log.info("Running Method 5: beta decay detector...")
    events_file = DATA_DIR / "historical_events.json"
    pattern_file = DATA_DIR / "pattern_lookup.json"
    historical_events = json.loads(events_file.read_text()) if events_file.exists() else []
    pattern_lookup = json.loads(pattern_file.read_text()) if pattern_file.exists() else {}
    decay = beta_decay_detector(historical_events, pattern_lookup, INDIA_SPREAD_PAIRS)
    log.info("Beta decay warnings: %d", len(decay))

    # ── 7. Method 2 + hypothesis validation ───────────────────────────────
    log.info("Validating %d hypothesis spreads...", len(ARCBE_HYPOTHESIS_SPREADS))
    hypotheses = validate_hypotheses(price_df, driver_df, ARCBE_HYPOTHESIS_SPREADS)
    confirmed = sum(1 for h in hypotheses if h["validation_status"] == "CONFIRMED")
    log.info("Hypotheses: %d confirmed, %d watch, %d rejected",
             confirmed,
             sum(1 for h in hypotheses if h["validation_status"] == "WATCH"),
             sum(1 for h in hypotheses if h["validation_status"] == "REJECTED"))

    # ── 8. Build report ────────────────────────────────────────────────────
    report = {
        "date": today,
        "generated_at": datetime.now(IST).isoformat(),
        "regime": regime,
        "hypothesis_validation": hypotheses,
        "beta_shifts": beta_shifts[:20],    # top 20
        "linkage_discoveries": linkages,
        "sector_dispersion": dispersion,
        "beta_decay": decay,
    }

    # ── 9. Write report ────────────────────────────────────────────────────
    report_path = DATA_DIR / f"correlation_report_{today}.json"
    report_path.write_text(json.dumps(report, indent=2, default=str))
    log.info("Report written to %s", report_path)

    # ── 10. Generate BUY/SELL signals ─────────────────────────────────────
    from arcbe_signal_generator import generate_arcbe_signals, check_arcbe_structural_stops
    from signal_tracker import save_signal, load_open_signals, close_signal, compute_signal_pnl, fetch_current_prices

    # First: check structural stops on any existing ARCBE positions
    structural_closes = check_arcbe_structural_stops(report, ARCBE_HYPOTHESIS_SPREADS)
    if structural_closes:
        open_sigs = load_open_signals()
        close_ids = {c["signal_id"] for c in structural_closes}
        for sig in open_sigs:
            if sig["signal_id"] in close_ids:
                close_info = next(c for c in structural_closes if c["signal_id"] == sig["signal_id"])
                all_tickers = (
                    [l["ticker"] for l in sig.get("long_legs", [])]
                    + [s["ticker"] for s in sig.get("short_legs", [])]
                )
                try:
                    prices = fetch_current_prices(all_tickers)
                    pnl = compute_signal_pnl(sig, prices)
                except Exception:
                    pnl = {"spread_pnl_pct": 0.0, "long_pnl_pct": 0.0, "short_pnl_pct": 0.0,
                           "long_legs": [], "short_legs": []}
                closed = close_signal(sig, close_info["reason"], pnl)
                log.info("ARCBE structural close: %s → %s (%s)",
                         sig["signal_id"], close_info["reason"], close_info["detail"])
                # Send Telegram notification
                try:
                    from telegram_bot import send_message
                    msg = (
                        f"🛑 ARCBE STOP — {sig['spread_name']}\n"
                        f"Reason: {close_info['detail']}\n"
                        f"P&L: {pnl['spread_pnl_pct']:+.2f}%"
                    )
                    send_message(msg)
                except Exception:
                    pass

    # Second: check if any existing ARCBE signals are still open for same spread
    open_sigs = load_open_signals()
    open_arcbe_spreads = {s["spread_name"] for s in open_sigs if s.get("category") == "arcbe"}

    # Generate new signals (skip spreads that already have an open position)
    new_signals = generate_arcbe_signals(report, regime, ARCBE_HYPOTHESIS_SPREADS)
    entered = []
    for sig in new_signals:
        if sig["spread_name"] in open_arcbe_spreads:
            log.info("ARCBE: skipping %s — already have open position", sig["spread_name"])
            continue
        save_signal(sig)
        open_arcbe_spreads.add(sig["spread_name"])
        entered.append(sig)
        log.info("ARCBE signal saved: %s [%s]", sig["signal_id"], sig["_arcbe"]["tier"])

        # Send Telegram entry notification
        try:
            from telegram_bot import send_message
            arcbe = sig["_arcbe"]
            long_str = ", ".join(l["ticker"] for l in sig["long_legs"])
            short_str = ", ".join(s["ticker"] for s in sig["short_legs"])
            msg = (
                f"📊 ARCBE {arcbe['tier']} — {sig['spread_name']}\n\n"
                f"BUY:  {long_str}\n"
                f"SELL: {short_str}\n\n"
                f"Z-score: {arcbe['entry_z']:+.2f} ({arcbe['entry_persistence']}d persistent)\n"
                f"Regime: {regime['label']} ({regime['score']:+d})\n"
                f"Beta confirmed: {'Yes' if arcbe['entry_beta_confirmed'] else 'No'}\n"
                f"Stop: {arcbe['stop_rule'].replace('_', ' ')}\n"
                f"{arcbe['position_note']}\n\n"
                f"Entry prices:\n"
            )
            for leg in sig["long_legs"]:
                msg += f"  BUY  {leg['ticker']}: ₹{leg['price']:.2f}\n"
            for leg in sig["short_legs"]:
                msg += f"  SELL {leg['ticker']}: ₹{leg['price']:.2f}\n"
            msg += f"\n30-min P&L tracking active. Stops monitored intraday + overnight."
            send_message(msg)
        except Exception as exc:
            log.warning("ARCBE Telegram entry notification failed: %s", exc)

    report["signals_generated"] = len(entered)
    report["structural_closes"] = len(structural_closes)

    return report


if __name__ == "__main__":
    report = run_scan()
    if report:
        print(f"\nScan complete. Regime: {report['regime']['label']} ({report['regime']['score']})")
        print(f"Beta shifts: {len(report['beta_shifts'])}")
        print(f"Linkage discoveries: {len(report['linkage_discoveries'])}")
        confirmed = sum(1 for h in report['hypothesis_validation'] if h['validation_status'] == 'CONFIRMED')
        print(f"Hypothesis confirmations: {confirmed}/{len(report['hypothesis_validation'])}")
        print(f"New ARCBE signals: {report.get('signals_generated', 0)}")
        print(f"Structural closes: {report.get('structural_closes', 0)}")
    else:
        print("Scan failed — check logs/arcbe.log")
        sys.exit(1)
