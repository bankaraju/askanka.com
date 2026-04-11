"""
Anka ARCBE — Morning Brief Formatter + Telegram Sender
Scheduled: 07:30 IST daily via schtask AnkaMorningBrief0730

Loads latest correlation_report_YYYY-MM-DD.json and sends a formatted
Telegram brief to personal chat (TELEGRAM_CHAT_ID) for review before
the analyst decides what to forward to the subscriber channel.
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
        logging.FileHandler(LOG_DIR / "arcbe.log", delay=True, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("anka.arcbe.brief")

IST = timezone(timedelta(hours=5, minutes=30))
DATA_DIR = Path(__file__).parent / "data"


def _regime_line(regime: dict) -> str:
    score = regime.get("score", 0)
    label = regime.get("label", "TRANSITIONING")
    emoji = {"RISK-ON": "🟢", "TRANSITIONING": "🟡", "RISK-OFF": "🔴"}.get(label, "⚪")
    inp = regime.get("inputs", {})
    lines = [f"{emoji} REGIME: {label} ({score:+d}/6)"]
    driver_map = {
        "brent_trend":      "Brent",
        "usdinr_trend":     "USD/INR",
        "india_vix":        "VIX",
        "fii_5d_flow":      "FII 5d",
        "nifty_momentum":   "Nifty",
        "us10yr_direction": "US10yr",
    }
    parts = []
    for k, label_str in driver_map.items():
        v = inp.get(k, 0)
        arrow = "↑" if v > 0 else ("↓" if v < 0 else "→")
        parts.append(f"{label_str}{arrow}")
    lines.append("  " + "  ".join(parts))
    return "\n".join(lines)


def _hypothesis_lines(hypotheses: list[dict]) -> str:
    if not hypotheses:
        return "✅ HYPOTHESES: none tested"
    lines = ["✅ HYPOTHESIS VALIDATION"]
    for h in hypotheses:
        status = h["validation_status"]
        emoji = {"CONFIRMED": "✅", "WATCH": "👁", "REJECTED": "❌"}.get(status, "?")
        z = h.get("z_score", 0)
        p = h.get("persistence", 0)
        bc = "β✓" if h.get("beta_confirmation") else "β✗"
        lines.append(f"  {emoji} {h['spread_name']}: Z={z:+.2f} ({p}d) {bc}")
    return "\n".join(lines)


def _discovery_lines(linkages: list[dict], dispersion: dict) -> str:
    lines = ["🔍 DATA DISCOVERIES"]
    if not linkages and not dispersion:
        lines.append("  Nothing notable")
        return "\n".join(lines)
    for lnk in linkages[:5]:
        lines.append(
            f"  {lnk['ticker']} ↔ {lnk['driver']}: corr {lnk['corr_90d']:+.2f}→{lnk['corr_20d']:+.2f} "
            f"(Δ{lnk['delta']:+.2f})"
        )
    for sector, d in dispersion.items():
        if d["signal"] != "NORMAL":
            emoji = "📊↑" if d["signal"] == "HIGH_DISPERSION" else "📊↓"
            lines.append(
                f"  {emoji} {sector}: dispersion Z={d['dispersion_z']:+.2f} "
                f"→ {'intra-sector spreads LIVE' if d['signal'] == 'HIGH_DISPERSION' else 'trade as BLOC'}"
            )
    return "\n".join(lines)


def _trade_ideas_lines(hypotheses: list[dict]) -> str:
    confirmed = [h for h in hypotheses if h["validation_status"] == "CONFIRMED"]
    if not confirmed:
        return "💡 TRADE IDEAS: none data-confirmed today"
    lines = ["💡 TRADE IDEAS (data-confirmed)"]
    for h in confirmed:
        z = h["z_score"]
        p = h["persistence"]
        direction = "REGIME SHIFT" if p >= 3 else "MEAN REVERT"
        lines.append(f"  {h['spread_name']} [{direction}]")
        lines.append(f"  Z={z:+.2f}, {p}d persistent")
        lines.append(f"  Data: {h['theme']}")
        lines.append(f"  Stop: beta re-convergence or Z→0")
    return "\n".join(lines)


def _decay_lines(decay: list[dict]) -> str:
    if not decay:
        return ""
    lines = ["⚠️  DECAY WATCH"]
    for d in decay:
        emoji = "🔴" if d["signal"] == "CROWDED" else "🟠"
        lines.append(
            f"  {emoji} {d['spread_name']}: decay {d['decay_ratio']:.2f}× "
            f"→ {d['signal']}"
        )
    return "\n".join(lines)


def _open_positions_lines() -> str:
    """Show open ARCBE positions with P&L."""
    try:
        from signal_tracker import load_open_signals, fetch_current_prices, compute_signal_pnl
        open_sigs = load_open_signals()
        arcbe_sigs = [s for s in open_sigs if s.get("category") == "arcbe"]
        if not arcbe_sigs:
            return ""

        # Collect all tickers
        all_tickers = []
        for sig in arcbe_sigs:
            for leg in sig.get("long_legs", []) + sig.get("short_legs", []):
                all_tickers.append(leg["ticker"])

        try:
            prices = fetch_current_prices(list(set(all_tickers)))
        except Exception:
            prices = {}

        lines = ["📈 OPEN ARCBE POSITIONS"]
        for sig in arcbe_sigs:
            arcbe = sig.get("_arcbe", {})
            pnl = compute_signal_pnl(sig, prices)
            spread_pnl = pnl["spread_pnl_pct"]
            emoji = "🟢" if spread_pnl > 0 else ("🔴" if spread_pnl < 0 else "⚪")
            days = sig.get("days_open", 0)

            long_str = "/".join(l["ticker"] for l in sig.get("long_legs", []))
            short_str = "/".join(s["ticker"] for s in sig.get("short_legs", []))

            lines.append(
                f"  {emoji} {sig['spread_name']} [{arcbe.get('tier', '?')}]"
            )
            lines.append(
                f"    BUY {long_str} / SELL {short_str}"
            )
            lines.append(
                f"    P&L: {spread_pnl:+.2f}% | Day {days} | Stop: {arcbe.get('stop_rule', '?').replace('_', ' ')}"
            )

            # Per-leg detail
            for leg in pnl.get("long_legs", []):
                lines.append(f"      BUY  {leg['ticker']}: ₹{leg['entry']:.0f}→₹{leg['current']:.0f} ({leg['pnl_pct']:+.1f}%)")
            for leg in pnl.get("short_legs", []):
                lines.append(f"      SELL {leg['ticker']}: ₹{leg['entry']:.0f}→₹{leg['current']:.0f} ({leg['pnl_pct']:+.1f}%)")

        return "\n".join(lines)
    except Exception as exc:
        log.warning("Failed to load ARCBE positions: %s", exc)
        return ""


def format_brief(report: dict) -> str:
    """Format a correlation report dict into a Telegram-ready message string."""
    date_str = report.get("date", datetime.now(IST).strftime("%Y-%m-%d"))
    parts = [f"🧭 ANKA REGIME BRIEF — {date_str}\n"]
    parts.append(_regime_line(report.get("regime", {})))
    parts.append("")
    parts.append(_hypothesis_lines(report.get("hypothesis_validation", [])))
    parts.append("")
    parts.append(_discovery_lines(
        report.get("linkage_discoveries", []),
        report.get("sector_dispersion", {}),
    ))
    parts.append("")
    parts.append(_trade_ideas_lines(report.get("hypothesis_validation", [])))
    decay_text = _decay_lines(report.get("beta_decay", []))
    if decay_text:
        parts.append("")
        parts.append(decay_text)
    # Open ARCBE positions section
    positions_text = _open_positions_lines()
    if positions_text:
        parts.append("")
        parts.append(positions_text)

    parts.append("")
    parts.append("━━━━━━━━━━━━━━━━━━━━━━")
    parts.append("ℹ️ Review before forwarding to channel. Reply SEND to forward.")
    return "\n".join(parts)


def send_brief() -> bool:
    """Load latest report, format, send to personal Telegram chat."""
    import glob
    reports = sorted(glob.glob(str(DATA_DIR / "correlation_report_*.json")))
    if not reports:
        log.error("No correlation report found — run run_correlation_scan.py first")
        return False

    latest = reports[-1]
    report = json.loads(Path(latest).read_text())
    report_date = report.get("date", "unknown")

    # Only send today's or yesterday's report
    today = datetime.now(IST).strftime("%Y-%m-%d")
    yesterday = (datetime.now(IST) - timedelta(days=1)).strftime("%Y-%m-%d")
    if report_date not in (today, yesterday):
        log.warning("Latest report is from %s — stale, skipping send", report_date)
        return False

    message = format_brief(report)

    # Send to personal chat only (not channel) — analyst reviews before forwarding
    from telegram_bot import _send_to_chat_http, CHAT_ID
    if not CHAT_ID:
        log.error("TELEGRAM_CHAT_ID not set")
        return False

    ok = _send_to_chat_http(CHAT_ID, message)
    if ok:
        log.info("Morning brief sent to personal chat for %s", report_date)
    else:
        log.error("Failed to send morning brief")
    return ok


if __name__ == "__main__":
    ok = send_brief()
    sys.exit(0 if ok else 1)
