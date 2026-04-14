#!/usr/bin/env python3
"""
Phase B — Daily Regime Stock Ranker

On regime transition days, reads Phase A historical profile, ranks stocks
by tradeable drift, and outputs a morning recommendation.

Fires ONLY when today's regime != yesterday's regime.

Usage:
    python reverse_regime_ranker.py                          # normal run
    python reverse_regime_ranker.py --zone RISK-OFF          # force zone
    python reverse_regime_ranker.py --no-telegram            # skip telegram
    python reverse_regime_ranker.py --zone RISK-OFF --no-telegram
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
PIPELINE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PIPELINE_DIR / "lib"))

AUTORESEARCH_DIR = Path(__file__).resolve().parent
DATA_DIR = PIPELINE_DIR / "data"

PROFILE_PATH = AUTORESEARCH_DIR / "reverse_regime_profile.json"
STATE_PATH = DATA_DIR / "regime_ranker_state.json"
HISTORY_PATH = DATA_DIR / "regime_ranker_history.json"

# ---------------------------------------------------------------------------
# VIX regime thresholds (same as Phase A)
# ---------------------------------------------------------------------------
VIX_THRESHOLDS = [
    (11, "EUPHORIA"),
    (14, "RISK-ON"),
    (18, "NEUTRAL"),
    (24, "CAUTION"),
]
DEFAULT_ZONE = "RISK-OFF"  # VIX >= 24

TOP_N = 5  # max recommendations per side
HOLD_DAYS = 5  # trading days


def vix_to_zone(vix_value: float) -> str:
    """Map a VIX level to a regime zone."""
    for threshold, zone in VIX_THRESHOLDS:
        if vix_value < threshold:
            return zone
    return DEFAULT_ZONE


def fetch_vix() -> float:
    """Fetch latest India VIX close from yfinance."""
    try:
        import yfinance as yf
    except ImportError:
        print("ERROR: yfinance not installed. pip install yfinance")
        sys.exit(1)

    ticker = yf.Ticker("^INDIAVIX")
    hist = ticker.history(period="5d")
    if hist.empty:
        print("ERROR: Could not fetch India VIX data from yfinance.")
        sys.exit(1)
    return float(hist["Close"].iloc[-1])


def get_today_zone(forced_zone: str | None = None) -> tuple[str, float | None]:
    """Return (zone, vix_value). If forced, vix_value is None."""
    if forced_zone:
        return forced_zone.upper(), None
    vix = fetch_vix()
    return vix_to_zone(vix), vix


def load_state() -> dict:
    """Load state file, or create default if missing."""
    if STATE_PATH.exists():
        with open(STATE_PATH, "r") as f:
            return json.load(f)
    return {
        "last_zone": None,
        "last_date": None,
        "active_recommendations": [],
    }


def save_state(state: dict) -> None:
    """Persist state to disk."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(STATE_PATH, "w") as f:
        json.dump(state, f, indent=2)


def load_profile() -> dict:
    """Load Phase A profile. Exit if missing."""
    if not PROFILE_PATH.exists():
        print(f"Run Phase A first — profile not found at {PROFILE_PATH}")
        sys.exit(1)
    with open(PROFILE_PATH, "r") as f:
        return json.load(f)


def load_history() -> list[dict]:
    """Load recommendation history."""
    if HISTORY_PATH.exists():
        with open(HISTORY_PATH, "r") as f:
            return json.load(f)
    return []


def save_history(history: list[dict]) -> None:
    """Append-save recommendation history."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(HISTORY_PATH, "w") as f:
        json.dump(history, f, indent=2)


def add_trading_days(start_date: str, n_days: int) -> str:
    """Add n trading days (weekdays only) to a date string."""
    dt = datetime.strptime(start_date, "%Y-%m-%d")
    added = 0
    while added < n_days:
        dt += timedelta(days=1)
        if dt.weekday() < 5:  # Mon-Fri
            added += 1
    return dt.strftime("%Y-%m-%d")


def confidence_level(episodes: int, hit_rate: float) -> str:
    """Compute confidence tier from episode count and hit rate."""
    if episodes >= 20 and hit_rate >= 65:
        return "HIGH"
    if episodes >= 10 and hit_rate >= 55:
        return "MEDIUM"
    return "LOW"


def expire_old_recommendations(state: dict, today: str) -> list[dict]:
    """Remove expired recommendations. Return list of expired ones."""
    active = state.get("active_recommendations", [])
    still_active = []
    expired = []
    for rec in active:
        if rec.get("expiry_date", "2000-01-01") < today:
            expired.append(rec)
        else:
            still_active.append(rec)
    state["active_recommendations"] = still_active
    return expired


def rank_stocks(profile: dict, target_zone: str) -> tuple[list[dict], list[dict]]:
    """
    Filter profile for target regime, rank by abs(drift_5d_mean).
    Return (longs, shorts) — each sorted by magnitude descending.

    Profile structure: {stock_profiles: {SYMBOL: {summary, by_transition, episodes}}}
    by_transition keys are "FROM->TO" strings.
    We look for any transition ending in target_zone (e.g., "NEUTRAL->RISK-OFF").
    """
    stock_profiles = profile.get("stock_profiles", {})
    candidates = []

    for symbol, data in stock_profiles.items():
        by_transition = data.get("by_transition", {})
        # Find transitions ending in the target zone
        for transition_key, stats in by_transition.items():
            parts = transition_key.split("->")
            if len(parts) != 2:
                continue
            to_zone = parts[1].strip()
            if to_zone.upper() != target_zone.upper():
                continue

            drift = stats.get("avg_drift_5d")
            if drift is None:
                continue

            candidates.append({
                "symbol": symbol,
                "transition": transition_key,
                "drift_5d_mean": drift,
                "drift_1d_mean": stats.get("avg_drift_1d", 0),
                "avg_gap": stats.get("avg_gap", 0),
                "hit_rate": stats.get("hit_rate", 0),
                "episodes": stats.get("episode_count", 0),
                "tradeable_rate": stats.get("tradeable_rate", 0),
                "persistence_rate": stats.get("persistence_rate", 0),
            })

    # Separate longs (positive drift) and shorts (negative drift)
    longs = [c for c in candidates if c["drift_5d_mean"] > 0]
    shorts = [c for c in candidates if c["drift_5d_mean"] < 0]

    # Sort by absolute drift descending
    longs.sort(key=lambda x: abs(x["drift_5d_mean"]), reverse=True)
    shorts.sort(key=lambda x: abs(x["drift_5d_mean"]), reverse=True)

    return longs[:TOP_N], shorts[:TOP_N]


def format_recommendation(
    from_zone: str,
    to_zone: str,
    today: str,
    longs: list[dict],
    shorts: list[dict],
    expiry: str,
) -> str:
    """Build the console output string."""
    lines = []
    lines.append(f"REGIME TRANSITION: {from_zone} -> {to_zone} (detected {today})")
    lines.append("")

    if longs:
        lines.append("TOP LONGS (historical drift > gap, persistent):")
        for i, s in enumerate(longs, 1):
            symbol = s.get("symbol", s.get("stock", "???"))
            drift = s.get("drift_5d_mean", 0) * 100  # decimal → percent
            hit = s.get("hit_rate", 0) * 100 if s.get("hit_rate", 0) <= 1 else s.get("hit_rate", 0)
            eps = s.get("episodes", 0)
            lines.append(f"  {i}. {symbol:<12} +{drift:.2f}% drift 5d, {hit:.0f}% hit, {eps} episodes")
    else:
        lines.append("TOP LONGS: (none with positive drift)")

    lines.append("")

    if shorts:
        lines.append("TOP SHORTS:")
        for i, s in enumerate(shorts, 1):
            symbol = s.get("symbol", s.get("stock", "???"))
            drift = s.get("drift_5d_mean", 0) * 100  # decimal → percent
            hit = s.get("hit_rate", 0) * 100 if s.get("hit_rate", 0) <= 1 else s.get("hit_rate", 0)
            eps = s.get("episodes", 0)
            lines.append(f"  {i}. {symbol:<12} {drift:+.2f}% drift 5d, {hit:.0f}% hit, {eps} episodes")
    else:
        lines.append("TOP SHORTS: (none with negative drift)")

    # Overall confidence from the best candidates
    all_picks = longs + shorts
    if all_picks:
        min_episodes = min(p.get("episodes", 0) for p in all_picks)
        min_hit = min(p.get("hit_rate", 0) for p in all_picks)
        conf = confidence_level(min_episodes, min_hit)
        lines.append("")
        lines.append(f"Confidence: {conf} ({min_episodes} episodes)")
        lines.append(f"Hold period: {HOLD_DAYS} trading days | Expires: {expiry}")

    return "\n".join(lines)


def build_active_recs(
    longs: list[dict], shorts: list[dict], to_zone: str, today: str, expiry: str
) -> list[dict]:
    """Build active recommendation entries for state file."""
    recs = []
    for s in longs:
        symbol = s.get("symbol", s.get("stock", "???"))
        recs.append({
            "symbol": symbol,
            "direction": "LONG",
            "regime": to_zone,
            "drift_5d_mean": s.get("drift_5d_mean", 0),
            "hit_rate": s.get("hit_rate", 0),
            "episodes": s.get("episodes", 0),
            "entry_date": today,
            "expiry_date": expiry,
        })
    for s in shorts:
        symbol = s.get("symbol", s.get("stock", "???"))
        recs.append({
            "symbol": symbol,
            "direction": "SHORT",
            "regime": to_zone,
            "drift_5d_mean": s.get("drift_5d_mean", 0),
            "hit_rate": s.get("hit_rate", 0),
            "episodes": s.get("episodes", 0),
            "entry_date": today,
            "expiry_date": expiry,
        })
    return recs


def main():
    parser = argparse.ArgumentParser(description="Phase B — Daily Regime Stock Ranker")
    parser.add_argument("--zone", type=str, default=None, help="Force a regime zone (for testing)")
    parser.add_argument("--no-telegram", action="store_true", help="Skip Telegram (no-op in this version)")
    args = parser.parse_args()

    today = datetime.now().strftime("%Y-%m-%d")

    # 1. Get today's zone
    to_zone, vix_value = get_today_zone(args.zone)
    if vix_value is not None:
        print(f"India VIX: {vix_value:.2f} -> Zone: {to_zone}")
    else:
        print(f"Forced zone: {to_zone}")

    # 2. Load state, expire old recommendations
    state = load_state()
    expired = expire_old_recommendations(state, today)
    if expired:
        print(f"Expired {len(expired)} old recommendation(s)")

    from_zone = state.get("last_zone")

    # 3. Check for transition
    if from_zone is not None and from_zone == to_zone:
        # No transition — update state date and save
        state["last_date"] = today
        save_state(state)
        active = state.get("active_recommendations", [])
        if active:
            print(f"No transition (staying {to_zone}). {len(active)} active recommendation(s).")
        else:
            print(f"No transition (staying {to_zone}). No active recommendations.")
        return

    # 4. Transition detected — load profile and rank
    if from_zone is None:
        print(f"First run — initializing state with zone {to_zone}")
        state["last_zone"] = to_zone
        state["last_date"] = today
        save_state(state)
        print("State initialized. Run again tomorrow to detect transitions.")
        return

    print(f"\n*** TRANSITION DETECTED: {from_zone} -> {to_zone} ***\n")

    profile = load_profile()
    longs, shorts = rank_stocks(profile, to_zone)

    if not longs and not shorts:
        print(f"No tradeable signals found for regime {to_zone} in profile.")
        state["last_zone"] = to_zone
        state["last_date"] = today
        save_state(state)
        return

    expiry = add_trading_days(today, HOLD_DAYS)

    # 5. Format and print recommendation
    output = format_recommendation(from_zone, to_zone, today, longs, shorts, expiry)
    print(output)

    # 6. Build new active recommendations
    new_recs = build_active_recs(longs, shorts, to_zone, today, expiry)
    state["active_recommendations"].extend(new_recs)
    state["last_zone"] = to_zone
    state["last_date"] = today
    save_state(state)

    # 7. Append to history
    history = load_history()
    history_entry = {
        "date": today,
        "transition": f"{from_zone}->{to_zone}",
        "vix": vix_value,
        "recommendations": new_recs,
        "confidence": confidence_level(
            min((r["episodes"] for r in new_recs), default=0),
            min((r["hit_rate"] for r in new_recs), default=0),
        ),
        "expiry": expiry,
    }
    history.append(history_entry)
    save_history(history)

    print(f"\nState saved to {STATE_PATH}")
    print(f"History appended to {HISTORY_PATH}")


if __name__ == "__main__":
    main()
