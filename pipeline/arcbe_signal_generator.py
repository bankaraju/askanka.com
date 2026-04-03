"""
Anka ARCBE — Signal Generator

Converts ARCBE scan results into concrete BUY/SELL trade signals
using the same format as war signals (open_signals.json).

Called by run_correlation_scan.py after the nightly scan completes.
Signals are then monitored every 30 minutes by the existing schtasks.

Two signal sources:
  1. Hypothesis spreads that reach CONFIRMED status (Tier 1)
  2. Data-discovered linkages with strong correlation shift (Tier 2, regime-confirmed)

Stop logic:
  - Intraday: same daily/2-day price stops as war signals (run_signal_monitor)
  - Overnight: ARCBE structural stops checked at 23:00 (beta reversion, Z→0)
"""

import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

log = logging.getLogger("anka.arcbe.signals")

IST = timezone(timedelta(hours=5, minutes=30))


def _next_signal_id() -> str:
    """Generate ARCBE signal ID: ARCBE-YYYY-MM-DD-NNN."""
    today = datetime.now(IST).strftime("%Y-%m-%d")
    signals_dir = Path(__file__).parent / "data" / "signals"
    open_file = signals_dir / "open_signals.json"
    closed_file = signals_dir / "closed_signals.json"

    count = 0
    for fp in (open_file, closed_file):
        if fp.exists():
            try:
                sigs = json.loads(fp.read_text(encoding="utf-8"))
                count += sum(1 for s in sigs if s.get("signal_id", "").startswith(f"ARCBE-{today}"))
            except Exception:
                pass
    return f"ARCBE-{today}-{count + 1:03d}"


def _fetch_entry_prices(tickers: list[str]) -> dict[str, float]:
    """Fetch current prices for signal entry. Uses Kite → EODHD → yfinance."""
    from signal_tracker import fetch_current_prices
    prices = fetch_current_prices(tickers)
    return {t: p for t, p in prices.items() if p is not None}


def generate_arcbe_signals(
    report: dict,
    regime: dict,
    hypothesis_spreads: list[dict],
) -> list[dict]:
    """Generate trade signals from a completed ARCBE scan report.

    Returns list of signal dicts ready for signal_tracker.save_signal().

    Entry rules:
      Tier 1 (structural break): CONFIRMED hypothesis + Z persistence >= 3
      Tier 2 (regime-confirmed): WATCH hypothesis + regime score confirms direction
      Data discovery: top linkage with |delta| > 0.35 + regime confirms

    Signals include ARCBE-specific metadata for overnight structural stop checks.
    """
    from config import INDIA_SIGNAL_STOCKS

    signals: list[dict] = []
    regime_score = regime.get("score", 0)
    regime_label = regime.get("label", "TRANSITIONING")

    # ── 1. Hypothesis-driven signals (Tier 1 + Tier 2) ────────────────────

    for h in report.get("hypothesis_validation", []):
        status = h.get("validation_status")
        z = h.get("z_score", 0)
        persistence = h.get("persistence", 0)
        beta_conf = h.get("beta_confirmation", False)
        spread_name = h.get("spread_name", "")

        # Find matching spread config for tickers
        matching = [s for s in hypothesis_spreads if s["name"] == spread_name]
        if not matching:
            continue
        spread_cfg = matching[0]

        # ── Tier 1: Structural Break ──
        # All three required: beta shift ALERT, dispersion rising, Z persistence >= 3
        if status == "CONFIRMED" and persistence >= 3:
            tier = "TIER_1"
            position_note = "Half size (structural break, new linkage forming)"
        # ── Tier 2: Regime-Confirmed ──
        # WATCH or CONFIRMED + regime confirms direction + no need for full persistence
        elif (status in ("CONFIRMED", "WATCH") and abs(z) >= 1.5
              and regime_score <= -3 and z > 0):
            # Risk-off regime + long domestic/short Gulf spread is positive Z
            tier = "TIER_2"
            position_note = "Full size (regime-confirmed)"
        elif (status in ("CONFIRMED", "WATCH") and abs(z) >= 1.5
              and regime_score >= 3 and z < 0):
            # Risk-on regime + reverse direction
            tier = "TIER_2"
            position_note = "Full size (regime-confirmed)"
        else:
            continue  # No signal — thresholds not met

        # Direction: positive Z = long leg outperforming → BUY long, SELL short
        # Negative Z = short leg outperforming → reverse the trade
        if z > 0:
            long_tickers = spread_cfg["long"]
            short_tickers = spread_cfg["short"]
        else:
            long_tickers = spread_cfg["short"]
            short_tickers = spread_cfg["long"]

        all_tickers = long_tickers + short_tickers
        prices = _fetch_entry_prices(all_tickers)

        # Skip if we can't price all legs
        missing = [t for t in all_tickers if t not in prices]
        if missing:
            log.warning("ARCBE: skipping %s — missing prices for %s", spread_name, missing)
            continue

        weight = round(1.0 / max(len(long_tickers), 1), 4)
        long_legs = [
            {"ticker": t, "yf": INDIA_SIGNAL_STOCKS.get(t, {}).get("yf", f"{t}.NS"),
             "price": prices[t], "weight": weight}
            for t in long_tickers
        ]
        short_weight = round(1.0 / max(len(short_tickers), 1), 4)
        short_legs = [
            {"ticker": t, "yf": INDIA_SIGNAL_STOCKS.get(t, {}).get("yf", f"{t}.NS"),
             "price": prices[t], "weight": short_weight}
            for t in short_tickers
        ]

        signal = {
            "signal_id": _next_signal_id(),
            "open_timestamp": datetime.now(IST).isoformat(),
            "status": "OPEN",
            "spread_name": spread_name,
            "category": "arcbe",
            "tier": tier,
            "event_headline": f"ARCBE {tier}: {spread_cfg.get('theme', spread_name)}",
            "hit_rate": 0.0,  # no historical hit rate yet — data-driven entry
            "expected_1d_spread": abs(z) * 0.5,  # rough estimate from Z magnitude

            "long_legs": long_legs,
            "short_legs": short_legs,

            "peak_spread_pnl_pct": 0.0,
            "days_open": 0,
            "entry_snapped": False,  # will snap to market open tomorrow

            # ARCBE-specific metadata for structural stop checks
            "_arcbe": {
                "tier": tier,
                "entry_z": round(z, 3),
                "entry_persistence": persistence,
                "entry_beta_confirmed": beta_conf,
                "expected_driver": spread_cfg.get("expected_driver", "brent"),
                "entry_regime_score": regime_score,
                "position_note": position_note,
                "stop_rule": (
                    "beta_reversion" if tier == "TIER_1"
                    else "z_zero_cross"
                ),
            },
        }
        signals.append(signal)
        log.info("ARCBE signal generated: %s [%s] Z=%+.2f", spread_name, tier, z)

    # ── 2. Data-discovery signals (strong new linkages) ────────────────────

    # Only generate if regime is clear (not transitioning) and linkage is very strong
    if abs(regime_score) >= 3:
        for lnk in report.get("linkage_discoveries", [])[:3]:  # top 3 only
            delta = lnk.get("delta", 0)
            if abs(delta) < 0.35:
                continue  # not strong enough for a standalone trade

            ticker = lnk.get("ticker", "")
            driver = lnk.get("driver", "")

            if ticker not in INDIA_SIGNAL_STOCKS:
                continue

            # Discovery trade: if new positive correlation with driver and
            # regime is risk-off, the stock may be newly vulnerable
            # This is exploratory — half size, tight stop
            stock_info = INDIA_SIGNAL_STOCKS[ticker]
            prices = _fetch_entry_prices([ticker])
            if ticker not in prices:
                continue

            # For now, flag as an alert rather than auto-entering
            # Data discoveries need analyst review before entry
            log.info(
                "ARCBE discovery: %s developing %s linkage (delta=%+.3f) — flagged for review",
                ticker, driver, delta,
            )

    return signals


def check_arcbe_structural_stops(
    report: dict,
    hypothesis_spreads: list[dict],
) -> list[dict]:
    """Check ARCBE-specific structural stop conditions for open ARCBE signals.

    Called at 23:00 during the nightly scan (not intraday — these are regime-level checks).

    Stop rules:
      Tier 1: beta shift has substantially reversed (|shift| < 0.25 for entry driver)
      Tier 2: Z-score has crossed zero against position

    Returns list of signal_ids that should be closed with reason.
    """
    from signal_tracker import load_open_signals

    open_sigs = load_open_signals()
    arcbe_sigs = [s for s in open_sigs if s.get("category") == "arcbe"]

    if not arcbe_sigs:
        return []

    closes: list[dict] = []

    for sig in arcbe_sigs:
        arcbe_meta = sig.get("_arcbe", {})
        tier = arcbe_meta.get("tier", "TIER_2")
        spread_name = sig.get("spread_name", "")
        stop_rule = arcbe_meta.get("stop_rule", "z_zero_cross")

        # Find current hypothesis validation for this spread
        current_h = None
        for h in report.get("hypothesis_validation", []):
            if h.get("spread_name") == spread_name:
                current_h = h
                break

        if current_h is None:
            continue  # spread not in tonight's scan — keep open

        current_z = current_h.get("z_score", 0)
        entry_z = arcbe_meta.get("entry_z", 0)

        # ── Tier 1 stop: beta reversion ──
        if stop_rule == "beta_reversion":
            # Check if any short-leg ticker's beta shift has reversed below 0.25
            beta_still_active = current_h.get("beta_confirmation", False)
            if not beta_still_active:
                closes.append({
                    "signal_id": sig["signal_id"],
                    "reason": "ARCBE_BETA_REVERSION",
                    "detail": f"Beta shift reversed — structural linkage no longer active",
                })
                log.info("ARCBE structural stop: %s — beta reverted", spread_name)
                continue

        # ── Tier 2 stop: Z crosses zero against position ──
        if stop_rule == "z_zero_cross":
            # Entry was positive Z → stop if Z crosses negative (or vice versa)
            if entry_z > 0 and current_z < 0:
                closes.append({
                    "signal_id": sig["signal_id"],
                    "reason": "ARCBE_Z_ZERO_CROSS",
                    "detail": f"Z-score crossed zero: entry Z={entry_z:+.2f} → now Z={current_z:+.2f}",
                })
                log.info("ARCBE structural stop: %s — Z crossed zero", spread_name)
            elif entry_z < 0 and current_z > 0:
                closes.append({
                    "signal_id": sig["signal_id"],
                    "reason": "ARCBE_Z_ZERO_CROSS",
                    "detail": f"Z-score crossed zero: entry Z={entry_z:+.2f} → now Z={current_z:+.2f}",
                })
                log.info("ARCBE structural stop: %s — Z crossed zero", spread_name)

        # ── Universal: 10-day time stop for Tier 1 ──
        if tier == "TIER_1":
            days = sig.get("days_open", 0)
            if days >= 10:
                closes.append({
                    "signal_id": sig["signal_id"],
                    "reason": "ARCBE_TIME_STOP",
                    "detail": f"Tier 1 time stop: {days} days open (max 10)",
                })
                log.info("ARCBE time stop: %s — %d days", spread_name, days)

    return closes
