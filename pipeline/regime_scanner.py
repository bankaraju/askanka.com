"""
Anka Research Pipeline — Regime Scanner (daily pre-market)

PRIMARY: ETF regime engine (20 ETFs, ML-optimized, 62.3% accuracy)
  → 5 zones: RISK-OFF / CAUTION / NEUTRAL / RISK-ON / EUPHORIA
  → Read from autoresearch/regime_trade_map.json (today_zone field)

SECONDARY: MSI (5-input heuristic) as additional context, NOT for regime classification.

Usage:
    python -X utf8 regime_scanner.py

Output files:
    data/today_regime.json  — today's full regime snapshot
    data/prev_regime.json   — rolling hysteresis state
"""

import json
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

_HERE = Path(__file__).parent
_DATA = _HERE / "data"
_TRADE_MAP = _HERE / "autoresearch" / "regime_trade_map.json"
_PREV_REGIME_FILE = _DATA / "prev_regime.json"
_TODAY_REGIME_FILE = _DATA / "today_regime.json"

IST = timezone(timedelta(hours=5, minutes=30))

log = logging.getLogger("anka.regime_scanner")

# ---------------------------------------------------------------------------
# Regime name mapping
# MSI returns: MACRO_STRESS | MACRO_NEUTRAL | MACRO_EASY
# regime_trade_map keys: RISK-OFF | CAUTION | NEUTRAL | RISK-ON | EUPHORIA
# We map MSI names → trade map names, with MACRO_ prefix strip as fallback.
# ---------------------------------------------------------------------------
MSI_TO_TRADE_MAP = {
    "MACRO_STRESS":  "RISK-OFF",
    "MACRO_NEUTRAL": "NEUTRAL",
    "MACRO_EASY":    "RISK-ON",
}


def _resolve_regime_key(regime: str, trade_map: dict) -> str | None:
    """Return the key into trade_map that best matches this MSI regime.

    Strategy:
      1. Direct lookup in MSI_TO_TRADE_MAP
      2. Exact key match in trade_map
      3. Strip 'MACRO_' prefix and try again
      4. Return None if no match found
    """
    # 1. Canonical mapping
    mapped = MSI_TO_TRADE_MAP.get(regime)
    if mapped and mapped in trade_map:
        return mapped

    # 2. Exact key match (regime might already match a trade_map key)
    if regime in trade_map:
        return regime

    # 3. Strip MACRO_ prefix
    stripped = regime.replace("MACRO_", "")
    if stripped in trade_map:
        return stripped

    # 4. Case-insensitive search as last resort
    regime_lower = regime.lower()
    for key in trade_map:
        if key.lower() == regime_lower or key.lower() == regime_lower.replace("macro_", ""):
            return key

    return None


# ---------------------------------------------------------------------------
# Hysteresis helpers
# ---------------------------------------------------------------------------

def _load_prev_regime() -> dict:
    """Load prev_regime.json or return empty dict if missing/corrupt."""
    if _PREV_REGIME_FILE.exists():
        try:
            return json.loads(_PREV_REGIME_FILE.read_text(encoding="utf-8"))
        except Exception as exc:
            log.warning("Could not read prev_regime.json: %s — starting fresh", exc)
    return {}


def _save_prev_regime(state: dict) -> None:
    _DATA.mkdir(exist_ok=True)
    _PREV_REGIME_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _compute_hysteresis(current_regime: str, prev_state: dict) -> tuple[dict, bool]:
    """Update hysteresis state and return (new_state, regime_stable).

    regime_stable=True when consecutive_days >= 2 in the same regime.

    Args:
        current_regime: MSI regime string for today
        prev_state: loaded from prev_regime.json

    Returns:
        (updated_state dict, regime_stable bool)
    """
    today = datetime.now(IST).strftime("%Y-%m-%d")
    prev_regime = prev_state.get("regime")
    prev_consecutive = prev_state.get("consecutive_days", 0)

    if prev_regime == current_regime:
        # Same regime — increment streak
        consecutive_days = prev_consecutive + 1
        changed_date = prev_state.get("changed_date", today)
    else:
        # Regime changed — reset streak
        consecutive_days = 1
        changed_date = today
        if prev_regime:
            log.info("Regime change detected: %s -> %s (need 2 consecutive days to confirm)",
                     prev_regime, current_regime)

    regime_stable = consecutive_days >= 2

    new_state = {
        "regime": current_regime,
        "changed_date": changed_date,
        "consecutive_days": consecutive_days,
    }
    return new_state, regime_stable


# ---------------------------------------------------------------------------
# Main scan function
# ---------------------------------------------------------------------------

def scan_regime() -> dict:
    """Run the daily pre-market regime scan.

    Steps:
      1. Read ETF engine regime from regime_trade_map.json (today_zone) — PRIMARY
      2. Call macro_stress.compute_msi() for secondary context (MSI score)
      3. Map ETF regime to eligible spreads from the same trade map
      4. Apply hysteresis: require 2 consecutive sessions to confirm a new regime
      5. Save data/today_regime.json and data/prev_regime.json

    Returns:
        Full regime snapshot dict (same content written to today_regime.json)
    """
    # ---- 1. Load ETF regime (PRIMARY) ----
    eligible_spreads: dict = {}
    trade_map_key: str | None = None
    etf_regime: str = "UNKNOWN"

    if _TRADE_MAP.exists():
        try:
            raw_map = json.loads(_TRADE_MAP.read_text(encoding="utf-8"))
            etf_regime = raw_map.get("today_zone", "UNKNOWN")
            trade_map = raw_map.get("results", raw_map)
            log.info("ETF engine regime: %s (from regime_trade_map.json)", etf_regime)

            if etf_regime in trade_map:
                trade_map_key = etf_regime
                eligible_spreads = trade_map[etf_regime]
                # Enrich each spread with its long/short leg constituents from
                # the static INDIA_SPREAD_PAIRS config so the dashboard can show
                # what tickers a spread actually trades, not just its win rate.
                try:
                    from config import INDIA_SPREAD_PAIRS
                    legs_by_name = {p["name"]: p for p in INDIA_SPREAD_PAIRS}
                    for name, stats in eligible_spreads.items():
                        cfg = legs_by_name.get(name)
                        if cfg and isinstance(stats, dict):
                            stats["long_legs"] = cfg.get("long", [])
                            stats["short_legs"] = cfg.get("short", [])
                except Exception as exc:
                    log.warning("Could not enrich eligible_spreads with legs: %s", exc)
                log.info("ETF regime '%s' → %d eligible spreads", etf_regime, len(eligible_spreads))
            else:
                log.warning("ETF regime '%s' not in trade map (keys: %s)", etf_regime, list(trade_map.keys()))
        except Exception as exc:
            log.error("Failed to load regime_trade_map.json: %s", exc)
    else:
        log.warning("regime_trade_map.json not found at %s", _TRADE_MAP)

    current_regime = etf_regime

    # ---- 2. Compute MSI (SECONDARY — context only, not for regime classification) ----
    msi_score = 0.0
    msi_regime = "UNAVAILABLE"
    msi = {}
    try:
        log.info("Computing MSI (secondary context)...")
        from macro_stress import compute_msi
        msi = compute_msi()
        msi_score = msi["msi_score"]
        msi_regime = msi["regime"]
        log.info("MSI: %.1f (%s) — ETF regime: %s", msi_score, msi_regime, current_regime)
    except Exception as exc:
        log.warning("MSI computation failed (non-fatal, ETF regime is primary): %s", exc)

    # ---- 3. Hysteresis ----
    prev_state = _load_prev_regime()
    new_prev_state, regime_stable = _compute_hysteresis(current_regime, prev_state)
    consecutive_days = new_prev_state["consecutive_days"]

    if regime_stable:
        log.info("Regime STABLE: %s (%d consecutive days)", current_regime, consecutive_days)
    else:
        log.info("Regime UNSTABLE: %s (only %d day — need 2 to confirm)",
                 current_regime, consecutive_days)

    # ---- 4. Build and save output ----
    timestamp = datetime.now(IST).isoformat()

    today_regime = {
        "timestamp": timestamp,
        "regime": current_regime,
        "regime_source": "etf_engine",
        "msi_score": msi_score,
        "msi_regime": msi_regime,
        "regime_stable": regime_stable,
        "consecutive_days": consecutive_days,
        "trade_map_key": trade_map_key,
        "eligible_spreads": eligible_spreads,
        "components": msi.get("components", {}),
    }

    _DATA.mkdir(exist_ok=True)
    _TODAY_REGIME_FILE.write_text(json.dumps(today_regime, indent=2), encoding="utf-8")
    log.info("Saved today_regime.json: regime=%s stable=%s msi=%.1f",
             current_regime, regime_stable, msi_score)

    _save_prev_regime(new_prev_state)
    log.info("Updated prev_regime.json: consecutive_days=%d", consecutive_days)

    return today_regime


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-7s  %(name)s — %(message)s",
        datefmt="%H:%M:%S",
    )

    result = scan_regime()

    print()
    print("=" * 60)
    print("REGIME SCAN COMPLETE")
    print("=" * 60)
    print(f"  Regime         : {result['regime']}")
    print(f"  MSI Score      : {result['msi_score']}")
    print(f"  Stable         : {result['regime_stable']}  ({result['consecutive_days']} consecutive days)")
    print(f"  Trade map key  : {result['trade_map_key']}")
    print(f"  Eligible spreads ({len(result['eligible_spreads'])}):")
    for spread_name, stats in result["eligible_spreads"].items():
        best_win = stats.get("best_win", "?")
        best_period = stats.get("best_period", "?")
        print(f"    - {spread_name:<30}  best_win={best_win}%  period={best_period}d")
    print(f"  Timestamp      : {result['timestamp']}")
    print(f"  Output         : {_TODAY_REGIME_FILE}")
