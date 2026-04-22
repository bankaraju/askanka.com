"""
Anka Research — Regime Playbook
Generates actionable trade recommendations based on current market regime.

Combines:
  - MSI score + regime (from macro_stress.py)
  - Options PCR + OI levels (from options_monitor.py)
  - Fragility score (from correlation_regime.py)
  - Backtest hit rates (from spread_universe.json)

Outputs a structured "what to do" for Telegram and website.
"""

import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

log = logging.getLogger("anka.playbook")

IST = timezone(timedelta(hours=5, minutes=30))
SPREAD_FILE = Path("C:/Users/Claude_Anka/askanka.com/data/spread_universe.json")


def generate_playbook(msi: dict, oi_data: dict = None, fragility: dict = None) -> dict:
    """Generate actionable regime playbook from current market state.

    Returns dict with regime_summary, action_level, recommended_spreads,
    sizing_guidance, and what_to_watch.
    """
    score = msi.get("msi_score", 50)
    regime = msi.get("regime", "MACRO_NEUTRAL")
    pcr = oi_data.get("pcr", 1.0) if oi_data else 1.0
    pcr_bias = oi_data.get("bias", "NEUTRAL") if oi_data else "NEUTRAL"
    frag_score = fragility.get("fragility_score", 0) if fragility else 0
    frag_label = fragility.get("regime_label", "STABLE") if fragility else "STABLE"
    support = oi_data.get("support", 0) if oi_data else 0
    resistance = oi_data.get("resistance", 0) if oi_data else 0
    nifty = oi_data.get("nifty", 0) if oi_data else 0

    # Determine action level
    if score >= 65 and pcr < 0.8:
        action_level = "HIGH_ALERT"
        action_color = "red"
        action_text = "High stress + weak options support — active defensive positioning required"
    elif score >= 65:
        action_level = "DEFENSIVE"
        action_color = "red"
        action_text = "Macro stress elevated — favour defensive spreads, reduce gross exposure"
    elif score >= 55 and pcr < 0.85:
        action_level = "CAUTIOUS"
        action_color = "amber"
        action_text = "Moderate stress, options leaning bearish — trade with smaller size, wider stops"
    elif score >= 55:
        action_level = "WATCHFUL"
        action_color = "amber"
        action_text = "Elevated stress but options support intact — normal trading with awareness"
    elif score >= 35:
        action_level = "NORMAL"
        action_color = "green"
        action_text = "Neutral regime — trade with full conviction on high-quality setups"
    else:
        action_level = "RISK_ON"
        action_color = "green"
        action_text = "Low stress — lean into momentum trades, full size"

    # Determine relevant event categories
    relevant_cats = _get_relevant_categories(score, pcr)

    # Get best spreads from backtest
    recommended = _get_best_spreads(relevant_cats, min_hit_rate=0.60, min_n=3)

    # Sizing guidance
    if frag_label == "FRAGILE":
        sizing = "0.5x position size — fragility HIGH, correlations unstable"
    elif frag_label == "CAUTION":
        sizing = "0.75x position size — fragility moderate"
    elif action_level in ("HIGH_ALERT", "DEFENSIVE"):
        sizing = "0.5x position size — macro stress elevated"
    elif action_level == "CAUTIOUS":
        sizing = "0.75x position size — moderate caution"
    else:
        sizing = "Full position size — conditions normal"

    # What to watch
    watch_items = _get_watch_items(score, pcr, frag_score, nifty, support, resistance)

    playbook = {
        "timestamp": datetime.now(IST).isoformat(),
        "regime_summary": {
            "msi_score": score,
            "msi_regime": regime,
            "pcr": round(pcr, 2),
            "pcr_bias": pcr_bias,
            "fragility": frag_label,
            "fragility_score": round(frag_score, 1),
            "nifty": nifty,
            "support": support,
            "resistance": resistance,
        },
        "action_level": action_level,
        "action_color": action_color,
        "action_text": action_text,
        "sizing_guidance": sizing,
        "recommended_spreads": recommended,
        "what_to_watch": watch_items,
    }

    return playbook


def _get_relevant_categories(msi_score: float, pcr: float) -> list:
    """Map current regime to relevant backtest categories."""
    cats = []
    if msi_score >= 65:
        cats.extend(["escalation", "hormuz", "sanctions", "india_stress", "fii_selling"])
    elif msi_score >= 50:
        cats.extend(["escalation", "india_stress", "fii_selling", "oil_negative"])
    elif msi_score >= 35:
        cats.extend(["fii_buying", "diplomacy", "oil_positive"])
    else:
        cats.extend(["ceasefire", "de_escalation", "diplomacy", "rbi_rate_cut"])

    # PCR overlay
    if pcr < 0.8:
        if "fii_selling" not in cats:
            cats.append("fii_selling")
        if "india_stress" not in cats:
            cats.append("india_stress")
    elif pcr > 1.3:
        if "fii_buying" not in cats:
            cats.append("fii_buying")

    return cats


def _get_best_spreads(categories: list, min_hit_rate: float = 0.60, min_n: int = 3) -> list:
    """Get top spreads from backtest for given categories."""
    if not SPREAD_FILE.exists():
        return []

    data = json.loads(SPREAD_FILE.read_text(encoding="utf-8"))
    results = []

    for sp in data.get("spreads", []):
        for cat in categories:
            c = sp["categories"].get(cat, {})
            hr = c.get("hit_rate", 0)
            n = c.get("n", 0)
            s5d = c.get("spread_5d", 0)
            if hr >= min_hit_rate and n >= min_n:
                results.append({
                    "spread_name": sp["name"],
                    "category": cat,
                    "hit_rate": round(hr * 100),
                    "avg_5d_spread": round(s5d, 2),
                    "n_precedents": n,
                    "long": sp.get("long", []),
                    "short": sp.get("short", []),
                })

    # Dedupe by spread name (keep highest hit rate)
    seen = {}
    for r in sorted(results, key=lambda x: -x["hit_rate"]):
        if r["spread_name"] not in seen:
            seen[r["spread_name"]] = r

    return list(seen.values())[:5]


def _get_watch_items(msi: float, pcr: float, frag: float,
                     nifty: float, support: float, resistance: float) -> list:
    """Generate watch items based on current state."""
    items = []

    if msi >= 60:
        items.append(f"MSI at {msi:.0f} — approaching STRESS threshold (65). FII flows and crude are key drivers.")
    if pcr < 0.85:
        items.append(f"PCR at {pcr:.2f} — options market leaning bearish. Watch for put unwinding as sign of support breaking.")
    if pcr > 1.2:
        items.append(f"PCR at {pcr:.2f} — heavy put writing = support. But if this unwinds suddenly, floor collapses fast.")
    if frag > 40:
        items.append(f"Fragility at {frag:.0f}/100 — correlations shifting. Spread behaviour may deviate from historical patterns.")
    if nifty and support and nifty < support + 200:
        items.append(f"Nifty ({nifty:.0f}) near OI support ({support}) — watch for a bounce or break.")
    if nifty and resistance and nifty > resistance - 200:
        items.append(f"Nifty ({nifty:.0f}) near OI resistance ({resistance}) — call writers may cap upside here.")

    if not items:
        items.append("No immediate concerns — trade with confidence on high-conviction setups.")

    return items


def format_playbook_telegram(playbook: dict) -> str:
    """Format playbook for Telegram."""
    rs = playbook["regime_summary"]
    action = playbook["action_level"]
    spreads = playbook["recommended_spreads"]
    watch = playbook["what_to_watch"]

    emoji_map = {
        "HIGH_ALERT": "🔴", "DEFENSIVE": "🔴", "CAUTIOUS": "🟡",
        "WATCHFUL": "🟡", "NORMAL": "🟢", "RISK_ON": "🟢",
    }
    emoji = emoji_map.get(action, "⚪")

    lines = [
        "━" * 22,
        f"📋 *REGIME PLAYBOOK* — {emoji} {action.replace('_', ' ')}",
        "━" * 22,
        "",
        f"*Market State:*",
        f"  MSI: {rs['msi_score']:.0f}/100 ({rs['msi_regime'].replace('MACRO_', '')})",
        f"  PCR: {rs['pcr']} ({rs['pcr_bias']})",
        f"  Fragility: {rs['fragility']} ({rs['fragility_score']:.0f}/100)",
        f"  Nifty: {rs['nifty']:.0f} | OI Support: {rs['support']} | Resistance: {rs['resistance']}",
        "",
        f"*Action:* {playbook['action_text']}",
        f"*Sizing:* {playbook['sizing_guidance']}",
    ]

    if spreads:
        lines.append("")
        lines.append("*Recommended Spreads (backtest-validated):*")
        for sp in spreads[:4]:
            n = sp['n_precedents']
            wins = round(sp['hit_rate'] * n / 100)
            lines.append(
                f"  📌 *{sp['spread_name']}* — worked {wins}/{n} times ({sp['hit_rate']}%)"
            )
            lines.append(
                f"      Long: {', '.join(sp['long'])} | Short: {', '.join(sp['short'])}"
            )

    if watch:
        lines.append("")
        lines.append("*Watch:*")
        for w in watch:
            lines.append(f"  👁 {w}")

    lines.extend([
        "",
        "_Anka Research · Not investment advice_",
        "━" * 22,
    ])

    return "\n".join(lines)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    from macro_stress import compute_msi
    from options_monitor import fetch_nifty_oi

    msi = compute_msi()
    oi = fetch_nifty_oi()

    # Get fragility score
    try:
        from correlation_regime import train_fragility_model, score_current_fragility
        train_fragility_model()
        scores = score_current_fragility()
        avg_frag = sum(s.get("fragility_score", 0) for s in scores.values()) / max(len(scores), 1)
        pairs_flagged = sum(1 for s in scores.values() if s.get("fragility_score", 0) > 70)
        frag_label = "FRAGILE" if avg_frag > 70 else "CAUTION" if avg_frag > 40 else "STABLE"
        fragility = {"fragility_score": avg_frag, "regime_label": frag_label, "pairs_flagged": pairs_flagged}
    except Exception as e:
        print(f"Fragility scoring failed: {e}")
        fragility = {"fragility_score": 0, "regime_label": "STABLE", "pairs_flagged": 0}

    playbook = generate_playbook(msi, oi_data=oi, fragility=fragility)
    print(format_playbook_telegram(playbook))
