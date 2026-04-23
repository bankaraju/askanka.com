"""
Anka Research — Reverse Regime Correlation Break Detector (Phase C)

Intraday scanner (designed for 15-min intervals) that detects stocks
deviating from their expected regime behavior, cross-references with
OI/PCR data from positioning.json, and classifies each break as
OPPORTUNITY, WARNING, CONFIRMED_WARNING, POSSIBLE_OPPORTUNITY, or UNCERTAIN.

Reads:
  - autoresearch/reverse_regime_profile.json  (Phase A output)
  - data/regime_ranker_state.json             (Phase B regime state)
  - data/positioning.json                     (OI scanner output, optional)

Writes:
  - data/correlation_breaks.json              (today's breaks, overwritten daily)
  - data/correlation_break_history.json       (append-only log)

Usage:
    python reverse_regime_breaks.py                                   # normal scan
    python reverse_regime_breaks.py --regime RISK-OFF                 # force regime
    python reverse_regime_breaks.py --transition "NEUTRAL->RISK-OFF" --regime RISK-OFF
    python reverse_regime_breaks.py --dry-run                         # no state writes
"""

import argparse
import json
import logging
import math
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PIPELINE_DIR = Path(__file__).resolve().parent.parent
AUTORESEARCH_DIR = PIPELINE_DIR / "autoresearch"
DATA_DIR = PIPELINE_DIR / "data"
LIB_DIR = PIPELINE_DIR / "lib"

sys.path.insert(0, str(PIPELINE_DIR))
sys.path.insert(0, str(LIB_DIR))

IST = timezone(timedelta(hours=5, minutes=30))

log = logging.getLogger("anka.reverse_regime_breaks")

# ---------------------------------------------------------------------------
# File paths
# ---------------------------------------------------------------------------
PROFILE_FILE = AUTORESEARCH_DIR / "reverse_regime_profile.json"
REGIME_STATE_FILE = DATA_DIR / "regime_ranker_state.json"
POSITIONING_FILE = DATA_DIR / "positioning.json"
BREAKS_FILE = DATA_DIR / "correlation_breaks.json"
BREAK_HISTORY_FILE = DATA_DIR / "correlation_break_history.json"

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
Z_THRESHOLD = 1.5          # sigma threshold for break detection
VALID_REGIMES = {"RISK-OFF", "CAUTION", "NEUTRAL", "RISK-ON", "EUPHORIA"}

# NSE suffix for yfinance
NSE_SUFFIX = ".NS"


# ===================================================================
# PCR classification
# ===================================================================
def classify_pcr(pcr: float) -> str:
    """Classify put-call ratio into a directional bucket."""
    if pcr > 1.3:
        return "BULLISH"
    elif pcr > 1.1:
        return "MILD_BULL"
    elif pcr > 0.9:
        return "NEUTRAL"
    elif pcr > 0.7:
        return "MILD_BEAR"
    else:
        return "BEARISH"


def pcr_agrees_with_expected(pcr_class: str, expected_return: float) -> bool:
    """Check if PCR direction agrees with the expected return direction."""
    bullish_classes = {"BULLISH", "MILD_BULL"}
    bearish_classes = {"BEARISH", "MILD_BEAR"}
    if expected_return > 0:
        return pcr_class in bullish_classes
    elif expected_return < 0:
        return pcr_class in bearish_classes
    return False


def pcr_disagrees_with_expected(pcr_class: str, expected_return: float) -> bool:
    """Check if PCR direction actively disagrees with expected return."""
    bullish_classes = {"BULLISH", "MILD_BULL"}
    bearish_classes = {"BEARISH", "MILD_BEAR"}
    if expected_return > 0:
        return pcr_class in bearish_classes
    elif expected_return < 0:
        return pcr_class in bullish_classes
    return False


# ===================================================================
# Geometric classifier (spec §3)
# ===================================================================
# Inputs are in PERCENT (e.g. 2.0 means 2%). Matches scan_for_breaks line 365.
_DEGENERATE_THRESHOLD_PCT = 0.1  # absolute percent


def classify_event_geometry(expected_return: float, actual_return: float) -> str:
    """
    Classify a Phase C event by its geometric geometry per spec §3:

      LAG         — sign(expected_return) != sign(residual)
                    Peers moved; stock lagged or went opposite.
                    Backtest FADE and live engine FOLLOW agree on trade side.
      OVERSHOOT   — sign(expected_return) == sign(residual)
                    Peers moved; stock moved further on the same side.
                    Backtest FADE and live engine FOLLOW are opposite.
      DEGENERATE  — |expected_return| < 0.1% or |residual| < 0.1%
                    Classification ambiguous; excluded from sub-bucket tests.

    residual = actual_return - expected_return (matches line 369).
    """
    residual = actual_return - expected_return
    if abs(expected_return) < _DEGENERATE_THRESHOLD_PCT or abs(residual) < _DEGENERATE_THRESHOLD_PCT:
        return "DEGENERATE"
    same_sign = (expected_return > 0 and residual > 0) or (expected_return < 0 and residual < 0)
    return "OVERSHOOT" if same_sign else "LAG"


# ===================================================================
# Break classification
# ===================================================================
def classify_break(
    expected_return: float,
    actual_return: float,
    z_score: float,
    pcr_class: str,
    oi_anomaly: bool,
) -> tuple:
    """
    Classify a correlation break according to the decision matrix.

    Returns (classification, action) tuple.

    Matrix (post-§3.1 geometric split):
      LAG-geometry + PCR agrees + no anomaly      -> OPPORTUNITY_LAG, ADD
      OVERSHOOT-geometry + PCR agrees + no anom   -> OPPORTUNITY_OVERSHOOT, ALERT
      Either geometry + PCR neutral + no anomaly  -> POSSIBLE_OPPORTUNITY, HOLD
      Either geometry + PCR disagrees or anomaly  -> WARNING, REDUCE
      Opposite + PCR agrees w/ break + anomaly    -> CONFIRMED_WARNING, EXIT
      Opposite + PCR disagrees + no anomaly       -> UNCERTAIN, HOLD
      Degenerate geometry                         -> UNCERTAIN, HOLD

    OPPORTUNITY_OVERSHOOT carries action=ALERT (not ADD): it is an alert-only
    classification until H-2026-04-23-003 (FADE hypothesis) passes. See
    docs/superpowers/specs/2026-04-23-phase-c-follow-vs-fade-audit-design.md §3.1.
    """
    # Degenerate geometry is uncertain — too small to classify
    geometry = classify_event_geometry(expected_return, actual_return)
    if geometry == "DEGENERATE":
        return "UNCERTAIN", "HOLD"

    # Determine if price is lagging or moving opposite (legacy decision matrix)
    same_direction = (expected_return >= 0 and actual_return >= 0) or \
                     (expected_return < 0 and actual_return < 0)

    is_lagging = same_direction or abs(actual_return) < abs(expected_return) * 0.3
    is_opposite = not same_direction and abs(actual_return) > abs(expected_return) * 0.3

    if is_lagging and not is_opposite:
        # Price is lagging expected move OR overshooting same-direction
        if pcr_agrees_with_expected(pcr_class, expected_return) and not oi_anomaly:
            # Split OPPORTUNITY by geometry — spec §3.1
            if geometry == "LAG":
                return "OPPORTUNITY_LAG", "ADD"
            # geometry == "OVERSHOOT": alert-only until H-2026-04-23-003 passes
            return "OPPORTUNITY_OVERSHOOT", "ALERT"
        elif pcr_class == "NEUTRAL" and not oi_anomaly:
            return "POSSIBLE_OPPORTUNITY", "HOLD"
        elif pcr_disagrees_with_expected(pcr_class, expected_return) or oi_anomaly:
            return "WARNING", "REDUCE"
        else:
            return "POSSIBLE_OPPORTUNITY", "HOLD"
    elif is_opposite:
        pcr_agrees_with_break = pcr_agrees_with_expected(pcr_class, actual_return)
        if pcr_agrees_with_break and oi_anomaly:
            return "CONFIRMED_WARNING", "EXIT"
        elif not pcr_agrees_with_break and not oi_anomaly:
            return "UNCERTAIN", "HOLD"
        elif oi_anomaly:
            return "WARNING", "REDUCE"
        else:
            return "UNCERTAIN", "HOLD"
    else:
        return "UNCERTAIN", "HOLD"


# ===================================================================
# Direction enrichment (spec §3 + §4.1)
# ===================================================================
def enrich_break_with_direction(brk: dict) -> dict:
    """
    Add direction-audit fields to a break record (spec §3 + §4.1).

    Mutates and returns the input dict. Computes:
      - event_geometry (LAG/OVERSHOOT/DEGENERATE)
      - direction_intended (FOLLOW/NEUTRAL — FADE is currently never intended)
      - direction_tested (FADE — hard-coded per spec for correlation-breaks v1)
      - direction_consistent (bool/None) — True iff geometry==LAG (backtest FADE
        and live FOLLOW agree on LAG by construction). None for non-actionable
        classifications.
      - trade_rec (LONG/SHORT/None) — None for overshoots and non-actionable labels.

    Uses expected_return and actual_return in PERCENT (matches classify_break).
    """
    expected = brk.get("expected_return", 0.0)
    actual = brk.get("actual_return", 0.0)
    classification = brk.get("classification", "")

    geometry = classify_event_geometry(expected, actual)
    brk["event_geometry"] = geometry
    brk["direction_tested"] = "FADE"

    if classification == "OPPORTUNITY_LAG":
        brk["direction_intended"] = "FOLLOW"
        brk["direction_consistent"] = True
        brk["trade_rec"] = "LONG" if expected > 0 else "SHORT"
    elif classification == "OPPORTUNITY_OVERSHOOT":
        brk["direction_intended"] = "NEUTRAL"
        brk["direction_consistent"] = False
        brk["trade_rec"] = None
    else:
        brk["direction_intended"] = "NEUTRAL"
        brk["direction_consistent"] = None
        brk["trade_rec"] = None

    return brk


# ===================================================================
# Data loaders
# ===================================================================
def load_profile() -> dict:
    """Load Phase A reverse regime profile."""
    if not PROFILE_FILE.exists():
        log.error("Phase A profile not found: %s", PROFILE_FILE)
        return {}
    with open(PROFILE_FILE, "r") as f:
        return json.load(f)


def load_regime_state() -> dict:
    """Load current regime from Phase B state file."""
    if not REGIME_STATE_FILE.exists():
        log.warning("Regime state file not found: %s — will try VIX fallback",
                     REGIME_STATE_FILE)
        return {}
    with open(REGIME_STATE_FILE, "r") as f:
        return json.load(f)


def load_positioning() -> dict:
    """Load OI/PCR positioning data (optional)."""
    if not POSITIONING_FILE.exists():
        log.info("positioning.json not found — skipping OI cross-reference")
        return {}
    try:
        with open(POSITIONING_FILE, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        log.warning("Failed to read positioning.json: %s", e)
        return {}


def determine_regime_from_vix() -> tuple:
    """
    Fallback: determine regime from VIX level when state file is missing.
    Returns (regime_name, days_in_regime).
    """
    try:
        import yfinance as yf
        vix = yf.Ticker("^INDIAVIX")
        hist = vix.history(period="5d")
        if hist.empty:
            # Try regular VIX as fallback
            vix = yf.Ticker("^VIX")
            hist = vix.history(period="5d")
        if hist.empty:
            log.warning("Could not fetch VIX data — defaulting to NEUTRAL")
            return "NEUTRAL", 1

        current_vix = hist["Close"].iloc[-1]
        if current_vix > 28:
            return "RISK-OFF", 1
        elif current_vix > 22:
            return "CAUTION", 1
        elif current_vix > 16:
            return "NEUTRAL", 1
        elif current_vix > 12:
            return "RISK-ON", 1
        else:
            return "EUPHORIA", 1
    except Exception as e:
        log.warning("VIX fallback failed: %s — defaulting to NEUTRAL", e)
        return "NEUTRAL", 1


def get_current_regime(force_regime: str = None, force_transition: str = None) -> tuple:
    """
    Determine current regime.
    Returns (regime_name, days_in_regime, transition_str_or_None).
    """
    if force_regime:
        regime = force_regime.upper()
        if regime not in VALID_REGIMES:
            log.error("Invalid regime: %s", regime)
            sys.exit(1)
        return regime, 1, force_transition

    state = load_regime_state()
    if state:
        regime = state.get("current_regime", state.get("regime", "NEUTRAL"))
        days = state.get("days_in_regime", state.get("days", 1))
        transition = state.get("transition")
        return regime, days, transition

    # Fallback to VIX
    regime, days = determine_regime_from_vix()
    return regime, days, None


# ===================================================================
# Price fetching
# ===================================================================
def fetch_current_prices(symbols: list) -> dict:
    """
    Fetch current prices and today's open for a list of NSE symbols.
    Uses yfinance (free).

    Returns dict: {symbol: {"price": float, "open": float}} or empty if failed.
    """
    import yfinance as yf

    yf_symbols = [s + NSE_SUFFIX for s in symbols]
    results = {}

    try:
        # Batch download — 1d period gets today's data
        tickers = yf.Tickers(" ".join(yf_symbols))
        for sym, yf_sym in zip(symbols, yf_symbols):
            try:
                ticker = tickers.tickers.get(yf_sym)
                if ticker is None:
                    continue
                hist = ticker.history(period="1d")
                if hist.empty:
                    continue
                results[sym] = {
                    "price": float(hist["Close"].iloc[-1]),
                    "open": float(hist["Open"].iloc[-1]),
                }
            except Exception as e:
                log.debug("Failed to fetch %s: %s", sym, e)
                continue
    except Exception as e:
        log.error("yfinance batch fetch failed: %s", e)

    return results


# ===================================================================
# Core scan logic
# ===================================================================
def scan_for_breaks(
    profile: dict,
    regime: str,
    days_in_regime: int,
    positioning: dict,
    prices: dict,
) -> list:
    """
    Scan all stocks with Phase A signals for current regime.
    Returns list of break dicts.
    """
    breaks = []

    # Profile format: {stock_profiles: {SYMBOL: {by_transition: {"FROM->TO": stats}}}}
    stock_profiles = profile.get("stock_profiles", {})

    for symbol, data in stock_profiles.items():
        by_transition = data.get("by_transition", {})

        # Find stats for transitions ending in current regime
        stats = None
        for trans_key, trans_stats in by_transition.items():
            parts = trans_key.split("->")
            if len(parts) == 2 and parts[1].strip().upper() == regime.upper():
                stats = trans_stats
                break  # take first matching transition

        if not stats:
            continue

        # Map Phase A field names to what we need
        drift_1d_mean = stats.get("avg_drift_1d")
        # Use actual std from profile if available, fall back to estimate
        drift_5d_std = stats.get("std_drift_5d")
        if drift_5d_std is None or drift_5d_std < 0.001:
            # Fallback: estimate as 3x avg drift magnitude, floor 2%
            drift_5d_avg = stats.get("avg_drift_5d", 0)
            drift_5d_std = max(abs(drift_5d_avg) * 3, 0.02)

        if drift_1d_mean is None:
            log.debug("Skipping %s — missing drift_1d for %s", symbol, regime)
            continue

        # Skip if std is too small (no meaningful deviation possible)
        if drift_5d_std < 0.001:
            log.debug("Skipping %s — drift_5d_std too small (%.4f)", symbol, drift_5d_std)
            continue

        # Check tradeable rate if available
        tradeable_rate = stats.get("tradeable_rate", 1.0)
        if tradeable_rate < 0.5:
            continue

        # Get current price data
        price_data = prices.get(symbol)
        if not price_data:
            log.debug("No price data for %s — skipping", symbol)
            continue

        current_price = price_data["price"]
        today_open = price_data["open"]

        if today_open <= 0:
            continue

        # Compute deviation — all values in percent
        expected_return = drift_1d_mean * 100  # decimal → percent
        expected_std = (drift_5d_std / math.sqrt(5)) * 100  # daily sigma in percent
        actual_return = (current_price / today_open - 1) * 100

        deviation = actual_return - expected_return
        z_score = deviation / expected_std if expected_std > 0.1 else 0

        if abs(z_score) <= Z_THRESHOLD:
            continue

        # --- Correlation break detected ---
        log.info("BREAK detected: %s z=%.2f (expected=%.2f%%, actual=%.2f%%)",
                 symbol, z_score, expected_return, actual_return)

        # OI cross-reference
        stock_oi = positioning.get(symbol, {})
        pcr_value = stock_oi.get("pcr", stock_oi.get("put_call_ratio"))
        oi_anomaly = stock_oi.get("oi_anomaly", False)
        oi_anomaly_type = stock_oi.get("anomaly_type", None)

        if pcr_value is not None:
            pcr_class = classify_pcr(pcr_value)
        else:
            pcr_class = "NEUTRAL"  # no data = neutral assumption
            pcr_value = None

        # Classify
        classification, action = classify_break(
            expected_return=expected_return,
            actual_return=actual_return,
            z_score=z_score,
            pcr_class=pcr_class,
            oi_anomaly=oi_anomaly,
        )

        # Build detailed trade parameters for ADD actions (stored as trade_detail)
        trade_detail = None
        if action == "ADD":
            direction = "LONG" if expected_return > 0 else "SHORT"
            stop_distance = 1.5 * expected_std
            target = stats.get("drift_5d_mean", stats.get("drift_5d", {}).get("mean", expected_return * 3))
            trade_detail = {
                "direction": direction,
                "entry": "market",
                "stop_pct": round(stop_distance, 2),
                "target_pct": round(target, 2) if target else None,
                "hold_days": 3,
                "size_inr": 50000,
            }

        now = datetime.now(IST)
        break_entry = {
            "symbol": symbol,
            "date": now.strftime("%Y-%m-%d"),
            "time": now.strftime("%H:%M:%S"),
            "regime": regime,
            "days_in_regime": days_in_regime,
            "expected_return": round(expected_return, 2),
            "actual_return": round(actual_return, 2),
            "z_score": round(z_score, 2),
            "classification": classification,
            "action": action,
            "pcr": round(pcr_value, 2) if pcr_value is not None else None,
            "pcr_class": pcr_class,
            "oi_anomaly": oi_anomaly,
            "oi_anomaly_type": oi_anomaly_type,
            "trade_detail": trade_detail,
        }

        # Add direction-audit fields + trade_rec string (spec §3 + §4.1)
        # enrich_break_with_direction is the single source of truth for trade_rec
        enrich_break_with_direction(break_entry)

        breaks.append(break_entry)

    # Sort by absolute z-score descending (strongest breaks first)
    breaks.sort(key=lambda b: abs(b["z_score"]), reverse=True)
    return breaks


# ===================================================================
# Output
# ===================================================================
def print_breaks(breaks: list, regime: str, days_in_regime: int):
    """Print break report to console."""
    if not breaks:
        print(f"\nNo correlation breaks detected for regime {regime} (day {days_in_regime})")
        return

    print(f"\n{'='*60}")
    print(f"  CORRELATION BREAK SCANNER")
    print(f"  Regime: {regime} (day {days_in_regime})")
    print(f"  Breaks detected: {len(breaks)}")
    print(f"{'='*60}")

    for b in breaks:
        print(f"\nCORRELATION BREAK: {b['symbol']}")
        print(f"  Regime: {b['regime']} (day {b['days_in_regime']})")
        print(f"  Expected: {b['expected_return']:+.1f}% | "
              f"Actual: {b['actual_return']:+.1f}% | "
              f"Z-score: {abs(b['z_score']):.1f}s")
        print(f"  Classification: {b['classification']}")

        pcr_str = f"{b['pcr']:.2f} ({b['pcr_class']})" if b['pcr'] is not None else "N/A"
        oi_str = b['oi_anomaly_type'] if b['oi_anomaly'] else "None"
        print(f"  PCR: {pcr_str} | OI Anomaly: {oi_str}")

        if b['action'] == "ADD" and b.get('trade_detail'):
            tr = b['trade_detail']
            print(f"  Action: ADD \u2014 standalone {tr['direction']} {b['symbol']} "
                  f"@ market, {tr['hold_days']}d hold")
        else:
            action_detail = {
                "HOLD": "monitor, no action",
                "REDUCE": "reduce existing exposure",
                "EXIT": "exit if in position",
            }
            print(f"  Action: {b['action']} \u2014 {action_detail.get(b['action'], '')}")

    print(f"\n{'='*60}")


def save_breaks(breaks: list, dry_run: bool = False):
    """Save breaks to state files."""
    if dry_run:
        log.info("Dry run — skipping state file writes")
        return

    # Ensure data directory exists
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    today = datetime.now(IST).strftime("%Y-%m-%d")

    # --- Today's breaks (overwritten daily) ---
    today_data = {
        "date": today,
        "scan_time": datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S"),
        "breaks": breaks,
    }

    # If file exists and is from today, merge (keep latest per symbol)
    if BREAKS_FILE.exists():
        try:
            with open(BREAKS_FILE, "r") as f:
                existing = json.load(f)
            if existing.get("date") == today:
                # Merge: keep latest entry per symbol
                existing_map = {b["symbol"]: b for b in existing.get("breaks", [])}
                for b in breaks:
                    existing_map[b["symbol"]] = b  # overwrite with latest
                today_data["breaks"] = list(existing_map.values())
        except (json.JSONDecodeError, IOError):
            pass  # overwrite corrupted file

    with open(BREAKS_FILE, "w") as f:
        json.dump(today_data, f, indent=2)
    log.info("Wrote %d breaks to %s", len(today_data["breaks"]), BREAKS_FILE)

    # --- Append to history ---
    history = []
    if BREAK_HISTORY_FILE.exists():
        try:
            with open(BREAK_HISTORY_FILE, "r") as f:
                history = json.load(f)
        except (json.JSONDecodeError, IOError):
            history = []

    history.extend(breaks)

    with open(BREAK_HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=2)
    log.info("Appended %d breaks to history (%d total)", len(breaks), len(history))


# ===================================================================
# Main
# ===================================================================
def main():
    parser = argparse.ArgumentParser(
        description="Reverse Regime Correlation Break Detector (Phase C)"
    )
    parser.add_argument("--regime", type=str, default=None,
                        help="Force a specific regime (e.g. RISK-OFF)")
    parser.add_argument("--transition", type=str, default=None,
                        help="Transition label (e.g. NEUTRAL->RISK-OFF)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print results but don't write state files")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Enable debug logging")
    args = parser.parse_args()

    # Logging
    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    # 1. Load Phase A profile
    profile = load_profile()
    if not profile:
        print("ERROR: Phase A profile not found at", PROFILE_FILE)
        print("Run reverse_regime_analysis.py first to generate the profile.")
        sys.exit(1)

    # 2. Determine current regime
    regime, days_in_regime, transition = get_current_regime(
        force_regime=args.regime,
        force_transition=args.transition,
    )
    log.info("Current regime: %s (day %d)%s",
             regime, days_in_regime,
             f" transition: {transition}" if transition else "")

    # 3. Identify stocks with signals for this regime
    # Profile format: {stock_profiles: {SYMBOL: {by_transition: {"FROM->TO": stats}}}}
    stock_profiles = profile.get("stock_profiles", {})
    candidate_symbols = []
    for symbol, data in stock_profiles.items():
        by_transition = data.get("by_transition", {})
        # Check if any transition targets this regime
        for trans_key in by_transition:
            parts = trans_key.split("->")
            if len(parts) == 2 and parts[1].strip().upper() == regime.upper():
                candidate_symbols.append(symbol)
                break

    if not candidate_symbols:
        print(f"No stocks have Phase A signals for regime {regime}")
        sys.exit(0)

    log.info("Found %d candidates with signals for %s", len(candidate_symbols), regime)

    # 4. Fetch current prices
    print(f"Fetching prices for {len(candidate_symbols)} stocks...")
    prices = fetch_current_prices(candidate_symbols)
    log.info("Got prices for %d / %d stocks", len(prices), len(candidate_symbols))

    if not prices:
        print("ERROR: Could not fetch any price data. Check yfinance / network.")
        sys.exit(1)

    # 5. Load OI positioning (optional)
    positioning = load_positioning()
    if positioning:
        log.info("Loaded positioning data for %d stocks", len(positioning))
    else:
        log.info("No positioning data available — OI cross-reference disabled")

    # 6. Scan for breaks
    breaks = scan_for_breaks(
        profile=profile,
        regime=regime,
        days_in_regime=days_in_regime,
        positioning=positioning,
        prices=prices,
    )

    # 7. Output
    print_breaks(breaks, regime, days_in_regime)

    # 8. Save state
    if breaks:
        save_breaks(breaks, dry_run=args.dry_run)
    elif not args.dry_run:
        # Still write today's file even if no breaks (indicates scan ran)
        save_breaks([], dry_run=args.dry_run)


if __name__ == "__main__":
    main()
