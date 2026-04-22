"""
Anka Research — Regime-Based Signal Generator
Generates spread trade ideas based on CURRENT market regime, not just headline events.

The existing signal pipeline waits for a news event → fires matching spreads.
This module looks at the regime itself (MSI + PCR + fragility) and says:
"Given where we are RIGHT NOW, these are the highest-probability spreads."

Runs every signal cycle alongside event-based signals.
Generates NEW trade ideas even when no fresh headlines exist.
"""

import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

log = logging.getLogger("anka.regime_signals")

IST = timezone(timedelta(hours=5, minutes=30))
SPREAD_FILE = Path("C:/Users/Claude_Anka/askanka.com/data/spread_universe.json")


def _map_regime_to_categories(msi_score: float, pcr: float, vix: float = 0) -> list:
    """Map current regime state to relevant backtest categories.
    Returns list of (category, relevance_weight) tuples."""
    cats = []

    # MSI-driven categories
    if msi_score >= 70:
        cats.extend([("escalation", 1.0), ("hormuz", 0.9), ("sanctions", 0.8),
                     ("india_stress", 1.0), ("fii_selling", 0.9)])
    elif msi_score >= 55:
        cats.extend([("escalation", 0.7), ("india_stress", 0.8),
                     ("fii_selling", 0.7), ("oil_negative", 0.6)])
    elif msi_score >= 35:
        cats.extend([("diplomacy", 0.5), ("fii_buying", 0.5),
                     ("oil_positive", 0.5)])
    else:
        cats.extend([("ceasefire", 0.8), ("de_escalation", 0.8),
                     ("diplomacy", 0.7), ("rbi_rate_cut", 0.6),
                     ("fii_buying", 0.7)])

    # PCR overlay
    if pcr < 0.7:
        cats.extend([("fii_selling", 0.9), ("india_stress", 0.8)])
    elif pcr > 1.3:
        cats.extend([("fii_buying", 0.7)])

    # VIX overlay
    if vix > 28:
        cats.extend([("india_stress", 0.8)])
    elif vix < 15:
        cats.extend([("de_escalation", 0.5)])

    # Dedupe — keep highest weight per category
    best = {}
    for cat, weight in cats:
        if cat not in best or weight > best[cat]:
            best[cat] = weight
    return [(c, w) for c, w in sorted(best.items(), key=lambda x: -x[1])]


def generate_regime_signals(
    msi_score: float,
    pcr: float = 1.0,
    vix: float = 0,
    fragility_score: float = 0,
    existing_spreads: set = None,
    min_hit_rate: float = 0.60,
    min_n: int = 3,
    max_signals: int = 5,
) -> list:
    """Generate spread trade ideas based on current regime.

    Args:
        msi_score: Current MSI (0-100)
        pcr: Current put/call ratio
        vix: Current India VIX
        fragility_score: Current fragility (0-100)
        existing_spreads: Set of spread names already in open positions (skip these)
        min_hit_rate: Minimum backtest hit rate to qualify
        min_n: Minimum sample size
        max_signals: Maximum signals to generate

    Returns list of signal dicts, each with spread details and regime context.
    """
    if not SPREAD_FILE.exists():
        log.warning("Spread universe file not found")
        return []

    data = json.loads(SPREAD_FILE.read_text(encoding="utf-8"))
    spreads = data.get("spreads", [])

    if existing_spreads is None:
        existing_spreads = set()

    # Map regime to categories with relevance weights
    regime_cats = _map_regime_to_categories(msi_score, pcr, vix)
    if not regime_cats:
        return []

    # Score each spread across all relevant categories
    scored = []
    for sp in spreads:
        name = sp["name"]
        if name in existing_spreads:
            continue  # Skip spreads already in portfolio

        best_cat = None
        best_score = 0
        best_hr = 0
        best_n = 0
        best_s5d = 0

        for cat, cat_weight in regime_cats:
            c = sp["categories"].get(cat, {})
            hr = c.get("hit_rate", 0)
            n = c.get("n", 0)
            s5d = c.get("spread_5d", 0)

            if hr < min_hit_rate or n < min_n:
                continue

            # Composite score: hit_rate × category_relevance × sample_confidence
            sample_conf = min(n / 10, 1.0)  # Caps at n=10
            composite = hr * cat_weight * sample_conf

            if composite > best_score:
                best_score = composite
                best_cat = cat
                best_hr = hr
                best_n = n
                best_s5d = s5d

        if best_cat and best_score > 0:
            # Apply fragility discount
            frag_discount = max(0.3, 1 - fragility_score / 100)
            adjusted_score = best_score * frag_discount

            scored.append({
                "spread_name": name,
                "category": best_cat,
                "hit_rate": round(best_hr * 100),
                "n_precedents": best_n,
                "avg_5d_spread": round(best_s5d, 2),
                "regime_score": round(adjusted_score, 3),
                "long": sp.get("long", []),
                "short": sp.get("short", []),
                "signal_type": "regime",
                "reason": _build_reason(name, best_cat, best_hr, msi_score, pcr, vix),
            })

    # Sort by composite score and take top N
    scored.sort(key=lambda x: -x["regime_score"])
    return scored[:max_signals]


def _build_reason(spread_name: str, category: str, hit_rate: float,
                  msi: float, pcr: float, vix: float) -> str:
    """Build a human-readable reason for why this spread is recommended now."""
    cat_label = category.replace("_", " ").title()

    parts = [f"{spread_name} historically performs well ({hit_rate*100:.0f}% hit rate) during {cat_label} events."]

    if msi >= 65:
        parts.append(f"MSI at {msi:.0f} indicates macro stress — defensive spreads favoured.")
    elif msi >= 50:
        parts.append(f"MSI at {msi:.0f} is elevated — stress-resilient spreads in focus.")

    if pcr < 0.8:
        parts.append(f"PCR at {pcr:.2f} suggests bearish options positioning — downside risk elevated.")
    elif pcr > 1.2:
        parts.append(f"PCR at {pcr:.2f} indicates heavy put support — floor likely holds.")

    if vix > 25:
        parts.append(f"VIX at {vix:.1f} reflects elevated uncertainty.")

    return " ".join(parts)


def format_regime_signals_telegram(signals: list, msi_score: float, pcr: float) -> str:
    """Format regime-based signals for Telegram."""
    if not signals:
        return ""

    lines = [
        "━" * 22,
        "🔍 *REGIME TRADE IDEAS* — New Opportunities",
        "━" * 22,
        f"_Based on MSI {msi_score:.0f} + PCR {pcr:.2f} regime analysis_",
        "",
    ]

    for i, sig in enumerate(signals, 1):
        hr = sig["hit_rate"]
        emoji = "🏆" if hr >= 75 else "📌" if hr >= 65 else "🔎"
        n = sig['n_precedents']
        wins = round(sig['hit_rate'] * n / 100)
        lines.append(f"{emoji} *#{i} {sig['spread_name']}*")
        lines.append(f"  Worked {wins} out of {n} times ({sig['hit_rate']}%) | avg {sig['avg_5d_spread']:+.1f}% over 5 days")
        lines.append(f"  Long: {', '.join(sig['long'])} | Short: {', '.join(sig['short'])}")
        lines.append(f"  _{sig['reason'][:120]}_")
        lines.append("")

    lines.extend([
        "💡 _These are regime-based ideas, not event-triggered signals._",
        "_Validate with your own analysis before entering._",
        "",
        "_Anka Research · Not investment advice_",
        "━" * 22,
    ])

    return "\n".join(lines)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    from macro_stress import compute_msi
    from options_monitor import fetch_nifty_oi
    from kite_client import fetch_ltp

    msi = compute_msi()
    oi = fetch_nifty_oi()
    prices = fetch_ltp(["INDIA VIX"])
    vix = prices.get("INDIA VIX", 0)

    # Current open spreads
    from signal_tracker import load_open_signals
    open_sigs = load_open_signals()
    existing = {s.get("spread_name", "") for s in open_sigs}

    signals = generate_regime_signals(
        msi_score=msi["msi_score"],
        pcr=oi.get("pcr", 1.0),
        vix=vix,
        existing_spreads=existing,
        max_signals=5,
    )

    msg = format_regime_signals_telegram(signals, msi["msi_score"], oi.get("pcr", 1.0))
    print(msg)

    if signals:
        from telegram_bot import send_message
        send_message(msg)
        print("\nSent to Telegram!")
