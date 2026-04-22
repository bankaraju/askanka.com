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

# ETF zone → MSI name mapping used when looking up regime buckets in spread_stats
_ETF_TO_MSI = {
    "RISK-OFF": "MACRO_STRESS",
    "CAUTION":  "MACRO_STRESS",
    "NEUTRAL":  "MACRO_NEUTRAL",
    "RISK-ON":  "MACRO_EASY",
    "EUPHORIA": "MACRO_EASY",
}


def _classify_conviction(entry: dict, gate_result: dict, tier: str) -> str:
    """Map gate output + tier to a human-readable conviction label.

    Thresholds (applied in priority order):
      1. tier == "PROVISIONAL"     → "PROVISIONAL"  (< 15 samples, label honestly)
      2. gate status INSUFFICIENT_DATA or INACTIVE → "NONE"  (no data or not in regime)
      3. |z_score| >= 2.0 AND best_win >= 65        → "HIGH"
      4. |z_score| >= 1.5 AND best_win >= 55        → "MEDIUM"
      5. gate status ACTIVE or AT_MEAN              → "LOW"   (in-gate but below thresholds)
      6. fallback                                   → "NONE"

    Note: 'ACTIVE' is the spread_intelligence gate status meaning the spread IS
    diverging (z > 1.0). 'AT_MEAN' means z <= 1.0 but still within regime gate.
    The spec's 'DIVERGENT' label maps to 'ACTIVE' in the actual implementation.
    """
    if tier == "PROVISIONAL":
        return "PROVISIONAL"

    status = gate_result.get("status", "")
    if status in ("INSUFFICIENT_DATA", "INACTIVE"):
        return "NONE"

    z = abs(gate_result.get("z_score") or 0)
    best_win = float(entry.get("best_win") or 0)

    if z >= 2.0 and best_win >= 65:
        return "HIGH"
    if z >= 1.5 and best_win >= 55:
        return "MEDIUM"
    if status in ("ACTIVE", "AT_MEAN"):
        return "LOW"   # in-gate but below threshold
    return "NONE"


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

    # ---- 3b. Bootstrap any eligible spread missing from spread_stats ----
    # Import lazily to keep the import graph clean (spread_bootstrap depends on
    # spread_statistics which depends on EODHD; we don't want that at module load).
    if eligible_spreads:
        try:
            import spread_bootstrap as _sb  # lazy import — keeps module load fast
        except ImportError:
            _sb = None  # type: ignore
            log.warning("spread_bootstrap not importable — skipping same-day bootstrap")

        if _sb is not None:
            for spread_name, spread_info in eligible_spreads.items():
                long_legs  = spread_info.get("long_legs",  []) if isinstance(spread_info, dict) else []
                short_legs = spread_info.get("short_legs", []) if isinstance(spread_info, dict) else []
                if not long_legs or not short_legs:
                    log.debug("Bootstrap: no leg data for %r — skipping", spread_name)
                    continue
                try:
                    bootstrap_result = _sb.ensure(spread_name, long_legs, short_legs)
                    if isinstance(spread_info, dict):
                        spread_info["_bootstrap_result"] = bootstrap_result
                    log.info("Bootstrap %r: %s", spread_name, bootstrap_result.get("status"))
                except Exception as _be:
                    log.warning("Bootstrap failed for %r: %s", spread_name, _be)

    # ---- 3c. Annotate each eligible spread with gate output ----
    # Load spread_stats once; annotation uses apply_gates from spread_intelligence.
    if eligible_spreads:
        try:
            from spread_intelligence import apply_gates as _apply_gates
            from spread_bootstrap import tier_from_n as _tier_from_n

            # Load spread_stats.json for gate computation
            _stats_file = _DATA / "spread_stats.json"
            try:
                _spread_stats: dict = json.loads(_stats_file.read_text(encoding="utf-8"))
            except Exception as _se:
                log.warning("Could not load spread_stats.json for gate annotation: %s", _se)
                _spread_stats = {}

            # Build a minimal regime_data dict for Gate 1 check
            _regime_data_for_gate = {"eligible_spreads": dict(eligible_spreads)}

            for _sname, _sinfo in eligible_spreads.items():
                if not isinstance(_sinfo, dict):
                    continue

                # --- Determine tier from spread_stats bucket sample count ---
                _bucket_count = 0
                _stats_entry = _spread_stats.get(_sname, {})
                # Try ETF zone name first, then MSI-mapped name
                _msi_key = _ETF_TO_MSI.get(current_regime, "")
                _regime_bucket = (
                    _stats_entry.get(current_regime)
                    or _stats_entry.get(_msi_key)
                    or {}
                )
                _bucket_count = int(_regime_bucket.get("count") or 0)

                # Fall back to bootstrap result if spread_stats has no data
                _bootstrap = _sinfo.get("_bootstrap_result", {})
                if _bucket_count == 0 and isinstance(_bootstrap, dict):
                    _bucket_count = int(_bootstrap.get("n") or 0)

                _tier = _tier_from_n(_bucket_count)
                # DROPPED tier (< 15 samples) → treat as PROVISIONAL for UI purposes
                if _tier == "DROPPED":
                    _tier = "PROVISIONAL"

                # --- Call apply_gates; pass None for today's return (pre-close) ---
                # today_spread_return=None signals "no live price yet".
                # We catch any failure so annotation never breaks the regime scan.
                try:
                    _gate = _apply_gates(
                        _sname,
                        _regime_data_for_gate,
                        _spread_stats,
                        None,          # today_spread_return — unavailable pre-market
                        current_regime,
                    )
                except Exception as _ge:
                    log.warning("apply_gates failed for %r: %s — using NO_TODAY_RETURN", _sname, _ge)
                    _gate = {"status": "NO_TODAY_RETURN", "z_score": None}

                _conviction = _classify_conviction(_sinfo, _gate, _tier)

                # Persist annotation fields into the entry dict (mutates in-place)
                _sinfo["conviction"]   = _conviction
                _sinfo["z_score"]      = _gate.get("z_score")
                _sinfo["gate_status"]  = _gate.get("status", "UNKNOWN")
                _sinfo["tier"]         = _tier

                log.debug(
                    "Annotate %r: conviction=%s z=%.2f gate=%s tier=%s",
                    _sname,
                    _conviction,
                    _gate.get("z_score") or 0.0,
                    _gate.get("status"),
                    _tier,
                )

        except Exception as _ae:
            log.error("Spread annotation block failed: %s — eligible_spreads will lack conviction fields", _ae)

    # ---- 4. Build and save output ----
    timestamp = datetime.now(IST).isoformat()

    today_regime = {
        "timestamp": timestamp,
        "zone": current_regime,       # canonical key — all UI/API consumers read this
        "regime": current_regime,     # legacy alias — kept for one release cycle (backward compat)
        "regime_source": "etf_engine",
        "msi_score": msi_score,
        "msi_regime": msi_regime,
        "msi_updated_at": msi.get("timestamp") if msi else None,
        "msi_cached_inputs": {
            "fii_net":       msi.get("fii_net") if msi else None,
            "dii_net":       msi.get("dii_net") if msi else None,
            "combined_flow": msi.get("combined_flow") if msi else None,
        } if msi else None,
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
