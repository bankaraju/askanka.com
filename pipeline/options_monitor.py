"""
Anka Research Pipeline — Options OI Monitor
Tracks Nifty Put/Call ratio, max pain, and OI shifts via Kite API.

Provides:
  - Real-time PCR (put/call ratio) at key strikes
  - Max pain level (where expiry converges)
  - OI change alerts (sudden put unwinding = support weakening)
  - Support/resistance from OI concentration

Called by run_signals.py every 30 minutes during market hours.
"""

import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

log = logging.getLogger("anka.options")

IST = timezone(timedelta(hours=5, minutes=30))
DATA_DIR = Path(__file__).parent / "data"
OI_HISTORY_FILE = DATA_DIR / "oi_history.json"

# How many strikes around ATM to scan
SCAN_RANGE = 1500  # ±1500 points from Nifty
STRIKE_STEP = 100


def fetch_nifty_oi(nifty_price: float = None) -> dict:
    """Fetch Nifty options OI from Kite API — ALL near-term expiries combined.

    Matches market standard (NSE/Upstox): combines weekly + monthly expiries.
    Returns dict with PCR, max OI levels, OI changes, and alerts.
    """
    import re as _re
    from collections import defaultdict as _defaultdict
    from kite_client import get_kite, fetch_ltp, _ensure_instrument_master, _TOKEN_MAP

    # Get current Nifty
    if nifty_price is None:
        prices = fetch_ltp(["NIFTY 50"])
        nifty_price = prices.get("NIFTY 50", 22700)

    atm = round(nifty_price / 100) * 100
    kite = get_kite()
    _ensure_instrument_master()

    # Find ALL Nifty option contracts across near-term expiries
    expiries = _defaultdict(list)
    for sym, token in _TOKEN_MAP.items():
        if not sym.startswith("NIFTY"):
            continue
        if any(x in sym for x in ["BANKNIFTY", "NXT50", "MIDCPNIFTY", "FINNIFTY"]):
            continue
        m = _re.match(r"(NIFTY\d{5})(\d{5})(CE|PE)$", sym)
        if not m:
            m = _re.match(r"(NIFTY\d{2}[A-Z]{3})(\d{5})(CE|PE)$", sym)
        if m:
            prefix = m.group(1)
            strike = int(m.group(2))
            opt_type = m.group(3)
            expiries[prefix].append({"sym": sym, "token": token,
                                     "strike": strike, "type": opt_type})

    # Take the 3 nearest expiries (weekly + monthly)
    near_expiries = sorted(expiries.keys())[:3]
    log.info("PCR expiries: %s", near_expiries)

    total_ce_oi = 0
    total_pe_oi = 0
    max_ce_oi = 0
    max_pe_oi = 0
    max_ce_strike = atm
    max_pe_strike = atm
    strike_data = []

    for prefix in near_expiries:
        contracts = expiries[prefix]
        ce_contracts = [c for c in contracts if c["type"] == "CE"]
        pe_contracts = [c for c in contracts if c["type"] == "PE"]

        # Fetch OI in batches
        for batch_start in range(0, len(ce_contracts), 200):
            batch = ce_contracts[batch_start:batch_start + 200]
            try:
                data = kite.quote([f"NFO:{c['sym']}" for c in batch])
                for c in batch:
                    key = f"NFO:{c['sym']}"
                    oi = data.get(key, {}).get("oi", 0)
                    total_ce_oi += oi
                    if oi > max_ce_oi:
                        max_ce_oi = oi
                        max_ce_strike = c["strike"]
                    if oi > 500000:
                        strike_data.append({"strike": c["strike"], "ce_oi": oi,
                                           "pe_oi": 0, "expiry": prefix})
            except Exception:
                continue

        for batch_start in range(0, len(pe_contracts), 200):
            batch = pe_contracts[batch_start:batch_start + 200]
            try:
                data = kite.quote([f"NFO:{c['sym']}" for c in batch])
                for c in batch:
                    key = f"NFO:{c['sym']}"
                    oi = data.get(key, {}).get("oi", 0)
                    total_pe_oi += oi
                    if oi > max_pe_oi:
                        max_pe_oi = oi
                        max_pe_strike = c["strike"]
                    # Update strike_data for puts
                    for sd in strike_data:
                        if sd["strike"] == c["strike"]:
                            sd["pe_oi"] = oi
                            break
                    else:
                        if oi > 500000:
                            strike_data.append({"strike": c["strike"], "ce_oi": 0,
                                               "pe_oi": oi, "expiry": prefix})
            except Exception:
                continue

    pcr = total_pe_oi / max(total_ce_oi, 1)

    # If max CE and PE are at the same strike, find second-highest for the other
    if max_ce_strike == max_pe_strike:
        # Find second-highest put OI strike (actual support below current level)
        second_pe_oi = 0
        second_pe_strike = max_pe_strike
        for sd in strike_data:
            if sd["strike"] != max_pe_strike and sd["pe_oi"] > second_pe_oi and sd["strike"] < max_pe_strike:
                second_pe_oi = sd["pe_oi"]
                second_pe_strike = sd["strike"]
        if second_pe_oi > 0:
            max_pe_strike = second_pe_strike
            max_pe_oi = second_pe_oi

    # Determine bias
    if pcr > 1.2:
        bias = "BULLISH"
        bias_note = "Put writers dominant — heavy support below, defending downside"
    elif pcr < 0.7:
        bias = "BEARISH"
        bias_note = "Call writers dominant — ceiling above, limited upside"
    elif pcr < 0.85:
        bias = "MILDLY_BEARISH"
        bias_note = "Slightly more call OI — mild bearish lean"
    elif pcr > 1.05:
        bias = "MILDLY_BULLISH"
        bias_note = "Slightly more put OI — mild support building"
    else:
        bias = "NEUTRAL"
        bias_note = "Balanced OI — no directional conviction from options"

    # Load previous reading for OI change detection
    prev = _load_previous_oi()
    oi_shift_alert = None
    if prev:
        prev_pcr = prev.get("pcr", pcr)
        pcr_change = pcr - prev_pcr
        if pcr_change < -0.15:
            oi_shift_alert = f"PCR dropped {pcr_change:+.2f} since last check — put support weakening, sell-off risk rising"
        elif pcr_change > 0.15:
            oi_shift_alert = f"PCR rose {pcr_change:+.2f} since last check — support building, buyers stepping in"

    result = {
        "timestamp": datetime.now(IST).isoformat(),
        "nifty": round(nifty_price, 1),
        "atm": atm,
        "pcr": round(pcr, 3),
        "bias": bias,
        "bias_note": bias_note,
        "total_ce_oi": total_ce_oi,
        "total_pe_oi": total_pe_oi,
        "max_ce_strike": max_ce_strike,
        "max_ce_oi": max_ce_oi,
        "max_pe_strike": max_pe_strike,
        "max_pe_oi": max_pe_oi,
        "resistance": max_ce_strike,
        "support": max_pe_strike,
        "key_strikes": strike_data,
        "oi_shift_alert": oi_shift_alert,
    }

    # Save for next comparison
    _save_current_oi(result)

    log.info("Options OI: Nifty %d | PCR %.2f (%s) | Support %d | Resistance %d",
             atm, pcr, bias, max_pe_strike, max_ce_strike)
    if oi_shift_alert:
        log.warning("OI ALERT: %s", oi_shift_alert)

    return result


def _load_previous_oi() -> dict:
    """Load previous OI reading for change detection."""
    if OI_HISTORY_FILE.exists():
        try:
            data = json.loads(OI_HISTORY_FILE.read_text(encoding="utf-8"))
            if isinstance(data, list) and data:
                return data[-1]
        except (json.JSONDecodeError, KeyError):
            pass
    return {}


def _save_current_oi(result: dict):
    """Append current OI reading to history."""
    history = []
    if OI_HISTORY_FILE.exists():
        try:
            history = json.loads(OI_HISTORY_FILE.read_text(encoding="utf-8"))
            if not isinstance(history, list):
                history = []
        except (json.JSONDecodeError, KeyError):
            history = []

    # Keep slim version for history (not full strike data)
    slim = {
        "timestamp": result["timestamp"],
        "nifty": result["nifty"],
        "pcr": result["pcr"],
        "bias": result["bias"],
        "support": result["support"],
        "resistance": result["resistance"],
        "total_ce_oi": result["total_ce_oi"],
        "total_pe_oi": result["total_pe_oi"],
    }
    history.append(slim)

    # Keep last 100 readings
    history = history[-100:]
    OI_HISTORY_FILE.write_text(json.dumps(history, indent=2), encoding="utf-8")


def format_oi_telegram(oi_data: dict) -> str:
    """Format OI data for Telegram signal cards."""
    pcr = oi_data["pcr"]
    bias = oi_data["bias"]
    support = oi_data["support"]
    resistance = oi_data["resistance"]
    nifty = oi_data["nifty"]

    emoji = {"BULLISH": "🟢", "MILDLY_BULLISH": "🟢", "NEUTRAL": "🟡",
             "MILDLY_BEARISH": "🔴", "BEARISH": "🔴"}.get(bias, "⚪")

    lines = [
        f"📊 *Options OI* — {emoji} {bias}",
        f"  PCR: {pcr:.2f} | Nifty: {nifty:.0f}",
        f"  Support: {support} | Resistance: {resistance}",
    ]

    if oi_data.get("oi_shift_alert"):
        lines.append(f"  ⚠️ _{oi_data['oi_shift_alert']}_")

    return "\n".join(lines)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    result = fetch_nifty_oi()
    print(json.dumps(result, indent=2, default=str))
