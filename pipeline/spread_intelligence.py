"""
Anka Research Pipeline — Spread Intelligence Orchestrator
Reads 5 signal-layer JSON artifacts, applies gate + modifier scoring,
and outputs ranked spread recommendations with Telegram delivery.

Entry point:  python spread_intelligence.py --morning --no-telegram
Output:       data/recommendations.json

Functions
---------
apply_gates(spread_name, regime_data, spread_stats, today_spread_return, regime)
    Two-gate filter: regime eligibility + divergence check.

apply_modifiers(base, technicals, positioning, news)
    Score adjustments from technicals, OI/PCR, and news signals.

score_spread(score)
    Map numeric score to (conviction, action) label.

run_scan(send_telegram, morning)
    Full pipeline: load artifacts, price, gate, score, rank, deliver.
"""

import argparse
import json
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import mean, NormalDist
from typing import Any, Dict, List, Optional, Tuple

# Ensure pipeline/ is importable
_root = str(Path(__file__).parent)
if _root not in sys.path:
    sys.path.insert(0, _root)

_lib = str(Path(__file__).parent / "lib")
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from config import INDIA_SPREAD_PAIRS

log = logging.getLogger("anka.spread_intelligence")

IST = timezone(timedelta(hours=5, minutes=30))
DATA_DIR = Path(__file__).parent / "data"

# Normal distribution for percentile calculation
_NORM = NormalDist(0, 1)


# =============================================================================
# Gate logic
# =============================================================================


def apply_gates(
    spread_name: str,
    regime_data: dict,
    spread_stats: dict,
    today_spread_return: float,
    regime: str,
) -> dict:
    """
    Two gates that must BOTH pass before a spread is scored.

    Gate 1 — Regime Active: spread_name must be in regime_data["eligible_spreads"].
    Gate 2 — Spread Diverging: z-score of today's return vs regime distribution.

    Returns dict with 'status' and supporting fields.
    """
    # Gate 1: regime eligibility
    eligible = regime_data.get("eligible_spreads", {})
    if spread_name not in eligible and regime in ("UNKNOWN", ""):
        return {"status": "INACTIVE", "reason": "unknown regime"}
    # If ETF engine has eligible spreads and this spread isn't listed,
    # still let it through if we have z-score data — Gate 2 is the real filter
    # This handles name mismatches between trade_map and config

    # Gate 2: divergence check
    spread_entry = spread_stats.get(spread_name)
    if not spread_entry:
        # No stats AND regime explicitly excluded this spread → INACTIVE
        # (distinct from INSUFFICIENT_DATA, which is for stats-fetch failure on
        # a spread the regime DOES allow). UI renders the two differently:
        # INACTIVE is expected/muted; INSUFFICIENT_DATA is a warning.
        if spread_name not in eligible:
            return {"status": "INACTIVE", "reason": "not in eligible spreads"}
        return {"status": "INSUFFICIENT_DATA"}

    regimes = spread_entry.get("regimes", spread_entry)
    # Bridge ETF names (NEUTRAL) to MSI names (MACRO_NEUTRAL) in spread stats
    ETF_TO_MSI = {"RISK-OFF": "MACRO_STRESS", "CAUTION": "MACRO_STRESS",
                  "NEUTRAL": "MACRO_NEUTRAL", "RISK-ON": "MACRO_EASY", "EUPHORIA": "MACRO_EASY"}
    regime_stats = regimes.get(regime) or regimes.get(ETF_TO_MSI.get(regime, ""))
    if not regime_stats:
        return {"status": "INSUFFICIENT_DATA"}

    # Correlation warning
    if regime_stats.get("correlated_warning", False):
        return {
            "status": "CORRELATED",
            "reason": "leg correlation > 0.8",
        }

    regime_mean = regime_stats.get("mean", 0)
    regime_std = regime_stats.get("std", 0)

    if regime_std <= 0:
        return {"status": "INSUFFICIENT_DATA"}

    z_score = (today_spread_return - regime_mean) / regime_std

    if abs(z_score) <= 1.0:
        return {"status": "AT_MEAN", "z_score": z_score}

    # Percentile from standard normal CDF
    percentile = round(_NORM.cdf(abs(z_score)) * 100, 1)

    return {
        "status": "ACTIVE",
        "z_score": z_score,
        "percentile": percentile,
    }


# =============================================================================
# Modifier logic
# =============================================================================


def apply_modifiers(
    base: int,
    technicals: dict,
    positioning: dict,
    news: dict,
) -> int:
    """
    Apply score modifiers from technicals, OI/PCR positioning, and news.
    Returns clamped score in [0, 100].
    """
    score = base

    # --- Technicals ---
    if technicals.get("short_rsi_avg", 50) < 30:
        score += 15
    if technicals.get("long_rsi_avg", 50) > 70:
        score -= 15
    if technicals.get("trend_confirming", False):
        score += 15
    if technicals.get("trend_conflicting", False):
        score -= 15

    # --- OI / PCR positioning ---
    short_pcr = positioning.get("short_pcr_avg", 0.7)
    long_pcr = positioning.get("long_pcr_avg", 0.7)

    if short_pcr > 1.2:
        score += 15
    elif short_pcr < 0.5:
        score -= 15

    if long_pcr < 0.5:
        score += 15

    # --- News ---
    direction = news.get("direction", "NEUTRAL")
    if direction == "BOOST":
        score += 15
    elif direction == "CAUTION":
        score -= 15

    return max(0, min(100, score))


# =============================================================================
# Score classification
# =============================================================================


def score_spread(score: int) -> Tuple[str, str]:
    """Map numeric score to (conviction_level, action)."""
    if score >= 80:
        return ("HIGH", "ENTER")
    elif score >= 50:
        return ("MEDIUM", "WATCH")
    else:
        return ("LOW", "CAUTION")


# =============================================================================
# JSON artifact loaders
# =============================================================================


def _load_json(filename: str) -> dict:
    """Load a JSON file from data/, returning empty dict on failure."""
    path = DATA_DIR / filename
    if not path.exists():
        log.warning("Missing artifact: %s", path)
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        log.error("Failed to load %s: %s", path, e)
        return {}


# =============================================================================
# Telegram formatting
# =============================================================================


def _format_morning_scan(regime: str, msi: int, results: list) -> str:
    """Format morning scan as Telegram message."""
    now = datetime.now(IST)
    LINE = "\u2501" * 22

    lines = [
        LINE,
        f"\U0001f3af ANKA MORNING SCAN \u2014 {now.strftime('%d %b %Y')}",
        LINE,
    ]

    # Regime emoji
    regime_emoji = {
        "MACRO_STRESS": "\U0001f534",
        "RISK_ON": "\U0001f7e2",
        "NEUTRAL": "\U0001f7e1",
        "RISK_OFF": "\U0001f534",
    }.get(regime, "\u26aa")
    lines.append(f"REGIME: {regime_emoji} {regime} (MSI {msi})")
    lines.append("")

    # Group by action
    enter = [r for r in results if r.get("action") == "ENTER"]
    watch = [r for r in results if r.get("action") == "WATCH"]
    inactive_count = sum(
        1 for r in results if r.get("gate_status") in ("INACTIVE", "AT_MEAN", "CORRELATED", "INSUFFICIENT_DATA")
    )

    if enter:
        lines.append("ENTER \u2014 HIGH CONVICTION:")
        for r in enter:
            z = r.get("z_score", 0)
            pctl = r.get("percentile", 0)
            lines.append(f"  \U0001f7e2 {r['name']} [Score: {r['score']}]")
            lines.append(f"     Divergence: {z:+.1f}\u03c3 ({pctl:.0f}th pctl)")
            if r.get("anomaly_flags"):
                lines.append(f"     \u26a0\ufe0f {', '.join(r['anomaly_flags'])}")
        lines.append("")

    if watch:
        lines.append("WATCH \u2014 MEDIUM:")
        for r in watch:
            z = r.get("z_score", 0)
            lines.append(f"  \U0001f7e1 {r['name']} [Score: {r['score']}]")
            lines.append(f"     Divergence: {z:+.1f}\u03c3")
        lines.append("")

    if inactive_count:
        lines.append(f"INACTIVE: {inactive_count} spreads")

    lines.append(LINE)
    return "\n".join(lines)


def _format_state_change_alert(name: str, old_action: str, new_action: str,
                                z_score: float, score: int, conviction: str) -> str:
    """Format intraday state-change alert."""
    now = datetime.now(IST)
    return (
        f"\U0001f514 SPREAD ALERT \u2014 {now.strftime('%H:%M')} IST\n"
        f"{name}: {old_action} \u2192 {new_action}\n"
        f"  z-score: {z_score:+.1f}\u03c3\n"
        f"  Conviction: {score} ({conviction})"
    )


# =============================================================================
# Main scan
# =============================================================================


def run_scan(send_telegram: bool = True, morning: bool = True) -> dict:
    """
    Full spread intelligence scan.

    1. Load all JSON artifacts
    2. Fetch live prices via kite_client
    3. For each spread: compute return, gate, score
    4. Rank, save, deliver via Telegram
    """
    from spread_statistics import compute_spread_return

    # Load artifacts
    regime_data = _load_json("today_regime.json")
    raw_stats = _load_json("spread_stats.json")
    spread_stats = raw_stats.get("spreads", raw_stats)  # handle nested or flat
    technicals_data = _load_json("technicals.json")
    positioning_data = _load_json("positioning.json")
    news_data = _load_json("news.json")
    prev_prices = _load_json("prev_prices.json")

    regime = regime_data.get("regime", "NEUTRAL")
    msi = regime_data.get("msi_score", 50)

    # Collect all symbols needed
    all_symbols = set()
    for pair in INDIA_SPREAD_PAIRS:
        all_symbols.update(pair["long"])
        all_symbols.update(pair["short"])

    # Fetch live prices
    try:
        from kite_client import fetch_ltp
        current_prices = fetch_ltp(list(all_symbols))
    except Exception as e:
        log.error("Failed to fetch live prices: %s", e)
        current_prices = {}

    # Process each spread
    results = []
    for pair in INDIA_SPREAD_PAIRS:
        name = pair["name"]
        long_syms = pair["long"]
        short_syms = pair["short"]

        # Build price dicts for spread return computation
        long_prev = {s: prev_prices.get(s, 0) for s in long_syms}
        long_curr = {s: current_prices.get(s, 0) for s in long_syms}
        short_prev = {s: prev_prices.get(s, 0) for s in short_syms}
        short_curr = {s: current_prices.get(s, 0) for s in short_syms}

        # Compute today's spread return
        if any(v > 0 for v in long_prev.values()) and any(v > 0 for v in short_prev.values()):
            today_return = compute_spread_return(long_prev, long_curr, short_prev, short_curr)
        else:
            today_return = 0.0

        # Apply gates
        gate_result = apply_gates(name, regime_data, spread_stats, today_return, regime)

        rec = {
            "name": name,
            "gate_status": gate_result["status"],
            "spread_return": round(today_return, 6),
        }

        if gate_result["status"] == "ACTIVE":
            z_score = gate_result["z_score"]
            percentile = gate_result.get("percentile", 0)

            # Build technicals for this spread's legs
            stocks_tech = technicals_data.get("stocks", {})
            stocks_pos = positioning_data.get("stocks", {})
            spread_news_map = news_data.get("spread_news", {})

            # Aggregate RSI across legs
            long_rsis = [stocks_tech.get(s, {}).get("rsi_14", 50) for s in long_syms]
            short_rsis = [stocks_tech.get(s, {}).get("rsi_14", 50) for s in short_syms]

            # Trend confirmation: long legs above 20dma, short legs below
            long_above = all(
                stocks_tech.get(s, {}).get("vs_20dma_pct", 0) > 0 for s in long_syms
            )
            short_below = all(
                stocks_tech.get(s, {}).get("vs_20dma_pct", 0) < 0 for s in short_syms
            )
            trend_confirming = long_above and short_below
            trend_conflicting = not long_above and not short_below and (
                all(stocks_tech.get(s, {}).get("vs_20dma_pct", 0) < 0 for s in long_syms)
                and all(stocks_tech.get(s, {}).get("vs_20dma_pct", 0) > 0 for s in short_syms)
            )

            tech_agg = {
                "short_rsi_avg": mean(short_rsis) if short_rsis else 50,
                "long_rsi_avg": mean(long_rsis) if long_rsis else 50,
                "trend_confirming": trend_confirming,
                "trend_conflicting": trend_conflicting,
            }

            # Aggregate PCR across legs
            short_pcrs = [stocks_pos.get(s, {}).get("pcr", 0.7) for s in short_syms]
            long_pcrs = [stocks_pos.get(s, {}).get("pcr", 0.7) for s in long_syms]
            pos_agg = {
                "short_pcr_avg": mean(short_pcrs) if short_pcrs else 0.7,
                "long_pcr_avg": mean(long_pcrs) if long_pcrs else 0.7,
            }

            # News for this spread
            spread_news_items = spread_news_map.get(name, [])
            news_agg = {"direction": "NEUTRAL"}
            if spread_news_items:
                # Take the most recent / dominant direction
                directions = [n.get("direction", "NEUTRAL") for n in spread_news_items]
                if "BOOST" in directions:
                    news_agg["direction"] = "BOOST"
                elif "CAUTION" in directions:
                    news_agg["direction"] = "CAUTION"

            # Anomaly flags from positioning
            anomaly_flags = []
            for s in long_syms + short_syms:
                flags = stocks_pos.get(s, {}).get("anomaly_flags", [])
                if flags:
                    anomaly_flags.extend([f"{s}: {f}" for f in flags])

            # Apply modifiers
            score = apply_modifiers(50, tech_agg, pos_agg, news_agg)
            conviction, action = score_spread(score)

            rec.update({
                "z_score": round(z_score, 2),
                "percentile": percentile,
                "score": score,
                "conviction": conviction,
                "action": action,
                "anomaly_flags": anomaly_flags,
            })
        else:
            rec["reason"] = gate_result.get("reason", gate_result["status"])
            rec["score"] = 0
            rec["action"] = "INACTIVE"
            rec["conviction"] = "NONE"
            if "z_score" in gate_result:
                rec["z_score"] = round(gate_result["z_score"], 2)

        results.append(rec)

    # Sort by score descending
    results.sort(key=lambda r: r.get("score", 0), reverse=True)

    # Load previous recommendations for state change detection
    prev_recs = _load_json("recommendations.json")
    prev_by_name = {}
    for r in prev_recs.get("recommendations", []):
        prev_by_name[r["name"]] = r

    # Save recommendations
    output = {
        "timestamp": datetime.now(IST).isoformat(),
        "regime": regime,
        "msi_score": msi,
        "recommendations": results,
    }
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "recommendations.json").write_text(
        json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # Save current prices for next scan
    if current_prices:
        (DATA_DIR / "prev_prices.json").write_text(
            json.dumps(current_prices, indent=2), encoding="utf-8"
        )

    # Telegram delivery
    if send_telegram:
        try:
            from telegram_bot import send_message
        except ImportError:
            log.warning("telegram_bot not available, skipping delivery")
            send_telegram = False

        if send_telegram:
            if morning:
                msg = _format_morning_scan(regime, msi, results)
                send_message(msg, parse_mode="Markdown")
                log.info("Morning scan sent via Telegram")
            else:
                # Intraday: only send state change alerts
                for r in results:
                    old = prev_by_name.get(r["name"], {})
                    old_action = old.get("action", "INACTIVE")
                    new_action = r.get("action", "INACTIVE")
                    if old_action != new_action and new_action in ("ENTER", "WATCH"):
                        alert = _format_state_change_alert(
                            r["name"],
                            old_action,
                            new_action,
                            r.get("z_score", 0),
                            r.get("score", 0),
                            r.get("conviction", "LOW"),
                        )
                        send_message(alert, parse_mode="Markdown")
                        log.info("State change alert: %s %s->%s", r["name"], old_action, new_action)

    # Print summary
    active = [r for r in results if r.get("action") in ("ENTER", "WATCH")]
    log.info(
        "Scan complete: %d active, %d inactive",
        len(active),
        len(results) - len(active),
    )

    return output


# =============================================================================
# CLI
# =============================================================================


def main():
    parser = argparse.ArgumentParser(description="Anka Spread Intelligence Scan")
    parser.add_argument("--morning", action="store_true", help="Send full morning scan")
    parser.add_argument("--no-telegram", action="store_true", help="Skip Telegram delivery")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s  %(message)s",
    )

    result = run_scan(
        send_telegram=not args.no_telegram,
        morning=args.morning,
    )

    # Print results summary to stdout
    recs = result.get("recommendations", [])
    print(f"\nRegime: {result.get('regime')} (MSI {result.get('msi_score')})")
    print(f"{'─' * 60}")
    for r in recs:
        action = r.get("action", "?")
        score = r.get("score", 0)
        z = r.get("z_score", "")
        z_str = f"  z={z:+.2f}" if isinstance(z, (int, float)) else ""
        print(f"  {action:8s}  {r['name']:<30s}  score={score:3d}{z_str}")
    print(f"{'─' * 60}")
    print(f"Active: {sum(1 for r in recs if r.get('action') in ('ENTER','WATCH'))}/{len(recs)}")


if __name__ == "__main__":
    main()
