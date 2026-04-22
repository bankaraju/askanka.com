"""
Anka Research — Sector Rotation Detector
Detects sector rotation patterns and generates spread ideas at market open.

What it does:
  1. Tracks daily sector index returns (14 Nifty sectoral indices)
  2. Identifies which sectors are gaining/losing relative strength
  3. Detects rotation patterns: money flowing FROM sector A TO sector B
  4. Generates spread trade ideas from detected rotations
  5. Checks if rotation patterns PERSIST (multi-day momentum)

Fires at morning open (09:42) with overnight rotation analysis.
Also checks intraday rotation at midday (12:00).

Key insight: Indian markets often look flat on Nifty, but underneath
there's 3-5% sector rotation happening. That's the spread opportunity.
"""

import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

log = logging.getLogger("anka.sector_rotation")

IST = timezone(timedelta(hours=5, minutes=30))
DATA_DIR = Path(__file__).parent / "data"
ROTATION_HISTORY = DATA_DIR / "sector_rotation_history.json"

SECTOR_INDICES = [
    "NIFTY BANK", "NIFTY IT", "NIFTY PHARMA", "NIFTY AUTO",
    "NIFTY METAL", "NIFTY REALTY", "NIFTY ENERGY", "NIFTY FMCG",
    "NIFTY PSU BANK", "NIFTY MEDIA", "NIFTY INFRA",
    "NIFTY COMMODITIES", "NIFTY CONSUMPTION", "NIFTY FIN SERVICE",
]

# Map sector indices to our spread universe tickers
SECTOR_TO_TICKERS = {
    "NIFTY BANK": ["HDFCBANK", "ICICIBANK", "AXISBANK", "KOTAKBANK", "SBI"],
    "NIFTY IT": ["TCS", "INFY", "WIPRO", "HCLTECH", "TECHM"],
    "NIFTY PHARMA": ["SUNPHARMA", "DRREDDY", "CIPLA", "DIVISLAB"],
    "NIFTY AUTO": ["TATAMOTORS", "M&M", "MARUTI"],
    "NIFTY METAL": ["HINDALCO", "TATASTEEL", "JSPL", "VEDL", "SAIL", "NMDC"],
    "NIFTY ENERGY": ["ONGC", "RELIANCE", "COALINDIA", "OIL", "NTPC", "TATAPOWER"],
    "NIFTY FMCG": ["HUL", "ITC", "BRITANNIA", "DABUR"],
    "NIFTY PSU BANK": ["SBI", "BANKBARODA"],
    "NIFTY REALTY": ["DLF", "GODREJPROP", "OBEROIRLTY", "SOBHA"],
    "NIFTY INFRA": ["LT", "NBCC", "SIEMENS"],
    "NIFTY FIN SERVICE": ["BAJFINANCE", "HDFCBANK", "ICICIBANK", "LICHSGFIN"],
}

# Sector pairs that make logical spread trades
ROTATION_PAIRS = [
    {"long_sector": "NIFTY PHARMA", "short_sector": "NIFTY AUTO",
     "name": "Pharma → Auto rotation", "thesis": "Defensive rotation into pharma, out of cyclical autos"},
    {"long_sector": "NIFTY ENERGY", "short_sector": "NIFTY IT",
     "name": "Energy → IT rotation", "thesis": "Commodity/energy benefiting from crude, IT hit by rupee and FII selling"},
    {"long_sector": "NIFTY METAL", "short_sector": "NIFTY IT",
     "name": "Metals → IT rotation", "thesis": "Metals benefiting from supply disruptions, IT de-rated on growth fears"},
    {"long_sector": "NIFTY PSU BANK", "short_sector": "NIFTY BANK",
     "name": "PSU Bank → Private Bank rotation", "thesis": "PSU banks catching up on valuation re-rating vs expensive private banks"},
    {"long_sector": "NIFTY FMCG", "short_sector": "NIFTY AUTO",
     "name": "FMCG → Auto rotation", "thesis": "Defensive staples outperforming discretionary autos in risk-off"},
    {"long_sector": "NIFTY ENERGY", "short_sector": "NIFTY BANK",
     "name": "Energy → Banks rotation", "thesis": "Energy benefits from oil, banks hurt by rate/NPA cycle"},
    {"long_sector": "NIFTY PHARMA", "short_sector": "NIFTY IT",
     "name": "Pharma → IT rotation", "thesis": "Both export earners, but pharma is defensive while IT is growth-dependent"},
    {"long_sector": "NIFTY METAL", "short_sector": "NIFTY REALTY",
     "name": "Metals → Realty rotation", "thesis": "Raw material producers winning vs builders on cost inflation"},
    {"long_sector": "NIFTY INFRA", "short_sector": "NIFTY FIN SERVICE",
     "name": "Infra → Financials rotation", "thesis": "Govt capex driving infra, financials facing rate headwinds"},
    {"long_sector": "NIFTY COMMODITIES", "short_sector": "NIFTY CONSUMPTION",
     "name": "Commodities → Consumption rotation", "thesis": "Commodity producers gaining at expense of consumer companies"},
]


def fetch_sector_returns(days: int = 5) -> dict:
    """Fetch multi-day returns for all sector indices.
    Returns {sector_name: {price, return_1d, return_3d, return_5d}}
    """
    from kite_client import get_kite, fetch_ltp

    # Get current prices
    current = fetch_ltp(SECTOR_INDICES + ["NIFTY 50"])

    # Get historical candles for return calculation
    kite = get_kite()
    now = datetime.now(IST)
    from_date = (now - timedelta(days=max(days + 5, 10))).strftime("%Y-%m-%d")
    to_date = now.strftime("%Y-%m-%d")

    results = {}
    from kite_client import resolve_token

    for sector in SECTOR_INDICES:
        token = resolve_token(sector)
        if not token:
            continue

        try:
            candles = kite.historical_data(token, from_date, to_date, "day")
            if len(candles) < 2:
                continue

            closes = [c["close"] for c in candles]
            curr = current.get(sector, closes[-1])

            ret_1d = (curr / closes[-2] - 1) * 100 if len(closes) >= 2 else 0
            ret_3d = (curr / closes[-4] - 1) * 100 if len(closes) >= 4 else ret_1d
            ret_5d = (curr / closes[-6] - 1) * 100 if len(closes) >= 6 else ret_3d

            results[sector] = {
                "price": round(curr, 2),
                "return_1d": round(ret_1d, 2),
                "return_3d": round(ret_3d, 2),
                "return_5d": round(ret_5d, 2),
            }
        except Exception as exc:
            log.debug("Historical data failed for %s: %s", sector, exc)

    # Add Nifty 50 as benchmark
    if "NIFTY 50" in current:
        token = resolve_token("NIFTY 50")
        if token:
            try:
                candles = kite.historical_data(token, from_date, to_date, "day")
                closes = [c["close"] for c in candles]
                curr = current.get("NIFTY 50", closes[-1])
                results["NIFTY 50"] = {
                    "price": round(curr, 2),
                    "return_1d": round((curr / closes[-2] - 1) * 100, 2) if len(closes) >= 2 else 0,
                    "return_3d": round((curr / closes[-4] - 1) * 100, 2) if len(closes) >= 4 else 0,
                    "return_5d": round((curr / closes[-6] - 1) * 100, 2) if len(closes) >= 6 else 0,
                }
            except Exception:
                pass

    return results


def detect_rotations(sector_returns: dict, min_spread: float = 2.0) -> list:
    """Detect sector rotation patterns.

    A rotation is detected when:
      - Long sector outperforms short sector by min_spread% over 1-5 days
      - The rotation is ACCELERATING (1d spread > 3d spread per day)
      - Or the rotation is PERSISTENT (positive across 1d, 3d, and 5d)

    Returns list of rotation dicts sorted by strength.
    """
    nifty = sector_returns.get("NIFTY 50", {})
    nifty_1d = nifty.get("return_1d", 0)

    rotations = []
    for pair in ROTATION_PAIRS:
        long_sec = sector_returns.get(pair["long_sector"], {})
        short_sec = sector_returns.get(pair["short_sector"], {})

        if not long_sec or not short_sec:
            continue

        # Calculate rotation spreads
        spread_1d = long_sec.get("return_1d", 0) - short_sec.get("return_1d", 0)
        spread_3d = long_sec.get("return_3d", 0) - short_sec.get("return_3d", 0)
        spread_5d = long_sec.get("return_5d", 0) - short_sec.get("return_5d", 0)

        # Check if rotation is significant
        if abs(spread_1d) < min_spread * 0.3 and abs(spread_5d) < min_spread:
            continue

        # Determine rotation strength and persistence
        is_persistent = (spread_1d > 0 and spread_3d > 0 and spread_5d > 0)
        is_accelerating = abs(spread_1d) > abs(spread_3d / 3) if spread_3d != 0 else False
        is_strong = abs(spread_5d) >= min_spread

        if not (is_persistent or is_accelerating or is_strong):
            continue

        # Direction: positive spread = long sector winning
        direction = "LONG_WINNING" if spread_1d > 0 else "SHORT_WINNING"

        # Strength score
        strength = abs(spread_5d) * (1.5 if is_persistent else 1.0) * (1.3 if is_accelerating else 1.0)

        # Get tradeable tickers
        long_tickers = SECTOR_TO_TICKERS.get(pair["long_sector"], [])[:3]
        short_tickers = SECTOR_TO_TICKERS.get(pair["short_sector"], [])[:3]

        rotations.append({
            "name": pair["name"],
            "thesis": pair["thesis"],
            "long_sector": pair["long_sector"],
            "short_sector": pair["short_sector"],
            "spread_1d": round(spread_1d, 2),
            "spread_3d": round(spread_3d, 2),
            "spread_5d": round(spread_5d, 2),
            "long_sector_1d": round(long_sec.get("return_1d", 0), 2),
            "short_sector_1d": round(short_sec.get("return_1d", 0), 2),
            "direction": direction,
            "is_persistent": is_persistent,
            "is_accelerating": is_accelerating,
            "strength": round(strength, 2),
            "long_tickers": long_tickers,
            "short_tickers": short_tickers,
            "nifty_1d": round(nifty_1d, 2),
        })

    # Sort by strength
    rotations.sort(key=lambda x: -x["strength"])

    # Save to history
    _save_rotation_history(rotations)

    return rotations


def _save_rotation_history(rotations: list):
    """Save today's rotation snapshot for trend tracking."""
    history = []
    if ROTATION_HISTORY.exists():
        try:
            history = json.loads(ROTATION_HISTORY.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, KeyError):
            history = []

    today = datetime.now(IST).strftime("%Y-%m-%d")
    # Remove today's existing entry if re-running
    history = [h for h in history if h.get("date") != today]
    history.append({
        "date": today,
        "timestamp": datetime.now(IST).isoformat(),
        "rotations": [{
            "name": r["name"],
            "spread_1d": r["spread_1d"],
            "spread_5d": r["spread_5d"],
            "strength": r["strength"],
            "is_persistent": r["is_persistent"],
        } for r in rotations[:5]],
    })
    history = history[-30:]  # Keep 30 days
    ROTATION_HISTORY.write_text(json.dumps(history, indent=2), encoding="utf-8")


def format_rotation_telegram(rotations: list, sector_returns: dict) -> str:
    """Format sector rotation analysis for Telegram."""
    if not rotations:
        return ""

    nifty = sector_returns.get("NIFTY 50", {})
    nifty_1d = nifty.get("return_1d", 0)

    # Sector heatmap — top movers
    sectors_sorted = sorted(
        [(k, v) for k, v in sector_returns.items() if k != "NIFTY 50" and v],
        key=lambda x: x[1].get("return_1d", 0),
        reverse=True,
    )

    lines = [
        "━" * 22,
        "🔄 *SECTOR ROTATION* — Where Money Is Moving",
        "━" * 22,
        f"_Nifty: {nifty_1d:+.2f}% today_",
        "",
        "*Sector Heatmap (today):*",
    ]

    # Top 3 winners and bottom 3 losers
    for sector, data in sectors_sorted[:3]:
        name = sector.replace("NIFTY ", "")
        ret = data.get("return_1d", 0)
        bar = "🟢" if ret > 0.5 else "🔴" if ret < -0.5 else "⚪"
        lines.append(f"  {bar} {name}: {ret:+.2f}%")

    lines.append("  ...")
    for sector, data in sectors_sorted[-3:]:
        name = sector.replace("NIFTY ", "")
        ret = data.get("return_1d", 0)
        bar = "🟢" if ret > 0.5 else "🔴" if ret < -0.5 else "⚪"
        lines.append(f"  {bar} {name}: {ret:+.2f}%")

    # Active rotations
    lines.extend(["", "*Active Rotation Trades:*"])
    for i, rot in enumerate(rotations[:3], 1):
        persistent_tag = " 🔥 PERSISTENT" if rot["is_persistent"] else ""
        accel_tag = " ⚡ ACCELERATING" if rot["is_accelerating"] else ""

        lines.append(f"\n  *#{i} {rot['name']}*{persistent_tag}{accel_tag}")
        lines.append(f"  Today: {rot['spread_1d']:+.2f}% | 3d: {rot['spread_3d']:+.2f}% | 5d: {rot['spread_5d']:+.2f}%")
        lines.append(f"  Long: {', '.join(rot['long_tickers'])} ({rot['long_sector'].replace('NIFTY ', '')} {rot['long_sector_1d']:+.2f}%)")
        lines.append(f"  Short: {', '.join(rot['short_tickers'])} ({rot['short_sector'].replace('NIFTY ', '')} {rot['short_sector_1d']:+.2f}%)")
        lines.append(f"  _{rot['thesis']}_")

    lines.extend([
        "",
        "💡 _Rotation spreads work when Nifty is flat but sectors diverge._",
        "_Best entered at open when overnight positioning is clear._",
        "",
        "_Anka Research · Not investment advice_",
        "━" * 22,
    ])

    return "\n".join(lines)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    print("Fetching sector data...")
    returns = fetch_sector_returns(days=5)

    print(f"\n=== SECTOR RETURNS (today) ===")
    for sector in sorted(returns.keys()):
        r = returns[sector]
        print(f"  {sector:25s} 1d:{r['return_1d']:+6.2f}% | 3d:{r['return_3d']:+6.2f}% | 5d:{r['return_5d']:+6.2f}%")

    rotations = detect_rotations(returns, min_spread=1.5)
    print(f"\n=== DETECTED ROTATIONS: {len(rotations)} ===")

    if rotations:
        msg = format_rotation_telegram(rotations, returns)
        print(msg)

        from telegram_bot import send_message
        send_message(msg)
        print("\nSent to Telegram!")
    else:
        print("No significant rotations detected today")
