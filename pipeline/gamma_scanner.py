"""
Anka Research — Gamma Exposure Scanner
Computes Gamma Exposure (GEX) across the Nifty/BankNifty option chain
to predict where market makers will pin the index.

The key insight: market makers sell options → they're short gamma →
they MUST delta-hedge → they buy dips and sell rallies around the
max-GEX strike → this PINS the index to that strike.

GEX = how much $ of hedging flow happens per 1-point index move at each strike.
Max negative GEX = strongest pinning force.

Outputs:
  - Predicted pin strike (max GEX)
  - IV skew (smart money positioning)
  - Straddle premium at pin strike
  - Manipulation alerts when GEX shifts suddenly
"""

import json
import logging
import re
import numpy as np
from datetime import datetime, timezone, timedelta
from pathlib import Path

log = logging.getLogger("anka.gamma")

IST = timezone(timedelta(hours=5, minutes=30))
DATA_DIR = Path(__file__).parent / "data"
GEX_HISTORY = DATA_DIR / "gex_history.json"

NIFTY_LOT = 75
BANKNIFTY_LOT = 30


def compute_gex(index_name: str = "NIFTY") -> dict:
    """Compute Gamma Exposure across the full option chain.

    Returns dict with: predicted_pin, gex_by_strike, iv_skew,
    straddle_premium, total_gex, manipulation_signals.
    """
    from kite_client import get_kite, fetch_ltp, _ensure_instrument_master, _TOKEN_MAP

    kite = get_kite()
    _ensure_instrument_master()

    # Config per index
    configs = {
        "NIFTY": {"symbol": "NIFTY 50", "step": 50, "lot": 75, "scan": 500},
        "BANKNIFTY": {"symbol": "NIFTY BANK", "step": 100, "lot": 30, "scan": 1000},
        "FINNIFTY": {"symbol": "NIFTY FIN SERVICE", "step": 50, "lot": 40, "scan": 500},
    }
    cfg = configs.get(index_name, configs["NIFTY"])

    # Get spot
    prices = fetch_ltp([cfg["symbol"]])
    spot = prices.get(cfg["symbol"], 0)
    if not spot:
        return {}

    atm = round(spot / cfg["step"]) * cfg["step"]

    # Find nearest expiry
    expiry_prefixes = set()
    prefix_pattern = "NIFTY" if index_name in ("NIFTY", "FINNIFTY") else "BANKNIFTY"
    for sym in _TOKEN_MAP:
        if index_name == "BANKNIFTY":
            m = re.match(r"(BANKNIFTY\d{5})\d{5}(?:CE|PE)$", sym)
        else:
            m = re.match(r"(NIFTY\d{5})\d{5}(?:CE|PE)$", sym)
            if m and "BANKNIFTY" in sym:
                continue
        if m:
            expiry_prefixes.add(m.group(1))

    if not expiry_prefixes:
        return {}

    nearest = sorted(expiry_prefixes)[0]

    # Scan option chain
    strikes = range(atm - cfg["scan"], atm + cfg["scan"] + 1, cfg["step"])
    gex_by_strike = {}
    iv_data = {}
    max_gex = 0
    max_gex_strike = atm
    total_ce_oi = 0
    total_pe_oi = 0

    for strike in strikes:
        try:
            ce_sym = f"NFO:{nearest}{strike}CE"
            pe_sym = f"NFO:{nearest}{strike}PE"
            data = kite.quote([ce_sym, pe_sym])

            ce = data.get(ce_sym, {})
            pe = data.get(pe_sym, {})

            ce_oi = ce.get("oi", 0)
            pe_oi = pe.get("oi", 0)
            ce_ltp = ce.get("last_price", 0)
            pe_ltp = pe.get("last_price", 0)

            total_ce_oi += ce_oi
            total_pe_oi += pe_oi

            # GEX computation (simplified)
            distance = abs(strike - spot) / spot
            nearness = max(0, 1 - distance * 20)
            ce_gex = -ce_oi * cfg["lot"] * nearness * 0.001
            pe_gex = -pe_oi * cfg["lot"] * nearness * 0.001
            net_gex = ce_gex + pe_gex

            gex_by_strike[strike] = {
                "gex": round(net_gex),
                "ce_oi": ce_oi,
                "pe_oi": pe_oi,
                "ce_ltp": ce_ltp,
                "pe_ltp": pe_ltp,
                "straddle": round(ce_ltp + pe_ltp, 1),
            }

            if abs(net_gex) > abs(max_gex):
                max_gex = net_gex
                max_gex_strike = strike

            # IV estimation for near-ATM
            if abs(strike - atm) <= cfg["step"] * 3:
                T = max(1 / 365, 0.001)
                ce_iv = (ce_ltp / (spot * np.sqrt(T))) * np.sqrt(2 * np.pi) * 100 if ce_ltp > 5 else 0
                pe_iv = (pe_ltp / (spot * np.sqrt(T))) * np.sqrt(2 * np.pi) * 100 if pe_ltp > 5 else 0
                iv_data[strike] = {"ce_iv": round(ce_iv, 1), "pe_iv": round(pe_iv, 1),
                                   "skew": round(pe_iv - ce_iv, 1)}

        except Exception:
            continue

    # Pin prediction
    predicted_pin = max_gex_strike

    # Straddle at predicted pin
    pin_data = gex_by_strike.get(predicted_pin, {})
    straddle_at_pin = pin_data.get("straddle", 0)
    straddle_value = straddle_at_pin * cfg["lot"]

    # IV skew at ATM
    atm_iv = iv_data.get(atm, {})
    iv_skew = atm_iv.get("skew", 0)  # Positive = puts more expensive = bearish

    # Manipulation signals
    manipulation = []
    if abs(spot - predicted_pin) > cfg["step"]:
        manipulation.append({
            "type": "PIN_PULL",
            "message": f"{index_name} at {spot:.0f} but max GEX pin is {predicted_pin}. "
                       f"Expect gravitational pull toward {predicted_pin}.",
            "direction": "DOWN" if spot > predicted_pin else "UP",
            "distance": round(abs(spot - predicted_pin)),
        })

    if iv_skew > 5:
        manipulation.append({
            "type": "BEARISH_SKEW",
            "message": f"Put IV {atm_iv.get('pe_iv', 0):.0f}% vs Call IV {atm_iv.get('ce_iv', 0):.0f}% "
                       f"— smart money buying puts (bearish positioning).",
        })
    elif iv_skew < -5:
        manipulation.append({
            "type": "BULLISH_SKEW",
            "message": f"Call IV {atm_iv.get('ce_iv', 0):.0f}% vs Put IV {atm_iv.get('pe_iv', 0):.0f}% "
                       f"— smart money buying calls (bullish positioning).",
        })

    pcr = total_pe_oi / max(total_ce_oi, 1)

    result = {
        "index": index_name,
        "spot": round(spot, 1),
        "atm": atm,
        "predicted_pin": predicted_pin,
        "pin_distance": round(abs(spot - predicted_pin)),
        "max_gex": round(max_gex),
        "straddle_at_pin": straddle_at_pin,
        "straddle_value_per_lot": round(straddle_value),
        "pcr": round(pcr, 2),
        "iv_skew": iv_skew,
        "atm_iv": atm_iv,
        "manipulation_signals": manipulation,
        "expiry": nearest,
        "top_gex_strikes": sorted(
            [(k, v["gex"]) for k, v in gex_by_strike.items()],
            key=lambda x: x[1]
        )[:5],
        "timestamp": datetime.now(IST).isoformat(),
    }

    # Save history
    _save_history(result)

    return result


def _save_history(result: dict):
    history = []
    if GEX_HISTORY.exists():
        try:
            history = json.loads(GEX_HISTORY.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, KeyError):
            history = []

    history.append({
        "timestamp": result["timestamp"],
        "index": result["index"],
        "spot": result["spot"],
        "predicted_pin": result["predicted_pin"],
        "max_gex": result["max_gex"],
        "pcr": result["pcr"],
        "iv_skew": result.get("iv_skew", 0),
    })
    history = history[-200:]
    GEX_HISTORY.write_text(json.dumps(history, indent=2), encoding="utf-8")


def format_gex_telegram(gex: dict) -> str:
    """Format GEX analysis for Telegram — manipulation-focused."""
    if not gex:
        return ""

    lines = [
        "━" * 22,
        f"🔬 *GAMMA EXPOSURE — {gex['index']}*",
        "━" * 22,
        "",
        f"*Current:* {gex['spot']:,.0f} | *Predicted Pin:* {gex['predicted_pin']:,}",
        f"*Pin Force (GEX):* {gex['max_gex']:,} | *Distance:* {gex['pin_distance']} pts",
        f"*PCR:* {gex['pcr']:.2f} | *IV Skew:* {gex['iv_skew']:+.1f}",
        "",
        f"*ATM Straddle:* {gex['straddle_at_pin']:.0f} pts (₹{gex['straddle_value_per_lot']:,}/lot)",
        "",
    ]

    # Top 5 GEX strikes
    lines.append("*Pinning Force by Strike:*")
    for strike, gex_val in gex["top_gex_strikes"]:
        bar = "█" * min(20, abs(gex_val) // 100000)
        lines.append(f"  {strike:>6,}: {bar} ({gex_val:,})")

    # Manipulation signals
    if gex["manipulation_signals"]:
        lines.append("")
        lines.append("*⚠️ Manipulation Signals:*")
        for sig in gex["manipulation_signals"]:
            lines.append(f"  • {sig['message']}")

    # Trading recommendation
    lines.extend([
        "",
        f"*Trade:* Sell {gex['predicted_pin']} straddle at pin strike",
        f"  Premium: {gex['straddle_at_pin']:.0f} pts | Value: ₹{gex['straddle_value_per_lot']:,}/lot",
        f"  Market makers will defend this level ({gex['max_gex']:,} GEX)",
        "",
        "💡 _Negative GEX = market makers are short gamma = they buy dips and sell rallies at this strike = PIN._",
        "",
        "_Anka Research · Not investment advice_",
        "━" * 22,
    ])

    return "\n".join(lines)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    for idx in ["NIFTY", "BANKNIFTY"]:
        gex = compute_gex(idx)
        if gex:
            print(f"\n{'='*50}")
            print(f"{idx}: Spot {gex['spot']} → Predicted Pin {gex['predicted_pin']}")
            print(f"Max GEX: {gex['max_gex']:,} at {gex['predicted_pin']}")
            print(f"PCR: {gex['pcr']:.2f} | IV Skew: {gex['iv_skew']:+.1f}")
            print(f"Straddle: {gex['straddle_at_pin']:.0f} pts (₹{gex['straddle_value_per_lot']:,}/lot)")
            for sig in gex["manipulation_signals"]:
                print(f"  ⚠️ {sig['message']}")

    # Send to Telegram
    nifty_gex = compute_gex("NIFTY")
    if nifty_gex:
        msg = format_gex_telegram(nifty_gex)
        print(f"\n{msg}")
        from telegram_bot import send_message
        send_message(msg)
        print("\nSent to Telegram!")
