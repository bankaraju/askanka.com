"""
OPUS ANKA — Basket Construction Engine

Combines:
  1. askanka.com Regime Engine → WHICH sector direction (long/short)
  2. ANKA Trust Score → WHICH stock within each sector
  3. Forensic valuation → position sizing based on conviction

Output: A specific 6-8 position basket with:
  - Long legs: highest Trust Score + most undervalued in long sectors
  - Short legs: lowest Trust Score + most overvalued in short sectors
  - Position sizes weighted by conviction

Usage:
    python run_basket.py
    python run_basket.py --regime RISK-ON
"""

import json
import sys
import time
from pathlib import Path
from datetime import datetime, timezone, timedelta

from pipeline.retrieval.screener_client import ScreenerClient
from run_spread_ranker import fetch_stock_snapshot, score_for_long, score_for_short, UNIVERSE, parse_num

IST = timezone(timedelta(hours=5, minutes=30))
ARTIFACTS = Path(__file__).parent / "artifacts"


# ── Trust Score Letter Grade from Screener Snapshot ──────────────────
# This is a FAST approximate Trust Score based on financial ratios only.
# The full Trust Score requires annual report PDF analysis (3-5 min per stock).
# For basket construction, we use this fast proxy to rank 24 stocks quickly.

def fast_trust_proxy(snap: dict) -> dict:
    """Compute a fast Trust Score proxy from Screener financial ratios.

    This approximates management credibility using observable metrics:
    - ROE consistency (high ROE sustained = management executing)
    - Revenue growth trajectory (growing = delivering on market opportunity)
    - Margin stability (stable/expanding = not eroding)
    - PE vs growth (reasonable PE for growth = market agrees management delivers)
    - Dividend consistency (paying dividends = cash flow real, not paper)

    Returns: {"score": 0-100, "grade": "A+"-"F", "factors": {...}}
    """
    score = 50  # Start at neutral
    factors = {}

    # ROE quality (max +20)
    roe = snap.get("roe")
    if roe is not None:
        if roe > 25:
            score += 20
            factors["roe"] = f"{roe}% — exceptional capital efficiency"
        elif roe > 18:
            score += 12
            factors["roe"] = f"{roe}% — strong"
        elif roe > 12:
            score += 5
            factors["roe"] = f"{roe}% — adequate"
        elif roe > 0:
            factors["roe"] = f"{roe}% — below par"
        else:
            score -= 15
            factors["roe"] = f"{roe}% — value destruction"

    # Revenue growth trajectory (max +15)
    growth = snap.get("revenue_growth_3yr")
    if growth is not None:
        if growth > 15:
            score += 15
            factors["growth"] = f"{growth}% 3yr CAGR — strong execution"
        elif growth > 10:
            score += 10
            factors["growth"] = f"{growth}% 3yr CAGR — solid"
        elif growth > 5:
            score += 5
            factors["growth"] = f"{growth}% 3yr CAGR — modest"
        elif growth > 0:
            factors["growth"] = f"{growth}% 3yr CAGR — stalling"
        else:
            score -= 10
            factors["growth"] = f"{growth}% 3yr CAGR — declining"

    # Margin quality (max +10)
    opm = snap.get("opm")
    if opm is not None:
        if opm > 25:
            score += 10
            factors["margin"] = f"{opm}% OPM — high margin business"
        elif opm > 15:
            score += 5
            factors["margin"] = f"{opm}% OPM — healthy"
        elif opm > 8:
            factors["margin"] = f"{opm}% OPM — thin"
        else:
            score -= 5
            factors["margin"] = f"{opm}% OPM — compressed"

    # Valuation reasonableness (max +10)
    pe = snap.get("pe")
    if pe is not None and growth is not None and growth > 0:
        peg = pe / growth if growth > 0 else 99
        if peg < 1.5:
            score += 10
            factors["valuation"] = f"PEG {peg:.1f} — market undervaluing execution"
        elif peg < 2.5:
            score += 5
            factors["valuation"] = f"PEG {peg:.1f} — fairly valued for growth"
        elif peg > 4:
            score -= 10
            factors["valuation"] = f"PEG {peg:.1f} — priced for perfection"
        else:
            factors["valuation"] = f"PEG {peg:.1f} — expensive but not extreme"
    elif pe is not None:
        factors["valuation"] = f"PE {pe:.0f}x — growth too low for PEG"

    # ROCE bonus (max +5)
    roce = snap.get("roce")
    if roce is not None and roce > 20:
        score += 5
        factors["roce"] = f"{roce}% — strong capital allocation"

    # Dividend signal (max +5)
    div = snap.get("dividend_yield")
    if div is not None and div > 1.0:
        score += 5
        factors["dividend"] = f"{div}% yield — cash flow is real"

    # Clamp
    score = max(0, min(100, score))

    # Grade
    if score >= 90: grade = "A+"
    elif score >= 80: grade = "A"
    elif score >= 70: grade = "B+"
    elif score >= 60: grade = "B"
    elif score >= 40: grade = "C"
    elif score >= 20: grade = "D"
    else: grade = "F"

    return {"score": score, "grade": grade, "factors": factors}


# ── Basket Construction ──────────────────────────────────────────────

def build_basket(regime: str = "NEUTRAL", max_positions: int = 8) -> dict:
    """Build an ANKA Trust Score-weighted basket of spread trades.

    Args:
        regime: Current regime from askanka.com (RISK-OFF/CAUTION/NEUTRAL/RISK-ON/EUPHORIA)
        max_positions: Maximum number of individual stock positions

    Returns: Basket specification with positions, sizes, and reasoning.
    """
    screener = ScreenerClient()
    now = datetime.now(IST)

    print(f"{'='*70}")
    print(f"  ANKA BASKET CONSTRUCTION")
    print(f"  Regime: {regime} | Date: {now.strftime('%B %d, %Y')}")
    print(f"{'='*70}")

    # ── Step 1: Score all stocks ─────────────────────────────────
    print(f"\n  Scoring {sum(len(s['stocks']) for s in UNIVERSE.values())} stocks across {len(UNIVERSE)} sectors...")

    all_scored = {}
    for sector_name, sector in UNIVERSE.items():
        for sym in sector["stocks"]:
            print(f"    {sym}...", end=" ", flush=True)
            snap = fetch_stock_snapshot(sym, screener)
            if not snap or not snap.get("price"):
                print("SKIP (no data)")
                continue

            trust = fast_trust_proxy(snap)
            snap["trust_score"] = trust["score"]
            snap["trust_grade"] = trust["grade"]
            snap["trust_factors"] = trust["factors"]
            snap["long_score"] = score_for_long(snap)
            snap["short_score"] = score_for_short(snap)
            snap["sector"] = sector_name
            snap["direction"] = sector["direction"]
            all_scored[sym] = snap
            print(f"Trust: {trust['grade']} ({trust['score']}) | PE={snap.get('pe', '?')} ROE={snap.get('roe', '?')}%")
            time.sleep(0.3)

    # ── Step 2: Regime-adjusted sector weights ───────────────────
    regime_weights = {
        "RISK-OFF":  {"defence": 0, "upstream_energy": 0, "it": 0, "omcs": 0, "banks": 0, "pharma": 1.0, "auto": 0},
        "CAUTION":   {"defence": 0.5, "upstream_energy": 0.5, "it": 0.8, "omcs": 0.8, "banks": 0.3, "pharma": 0.7, "auto": 0.3},
        "NEUTRAL":   {"defence": 0.8, "upstream_energy": 0.7, "it": 0.7, "omcs": 0.7, "banks": 0.6, "pharma": 0.5, "auto": 0.5},
        "RISK-ON":   {"defence": 1.0, "upstream_energy": 1.0, "it": 1.0, "omcs": 1.0, "banks": 0.8, "pharma": 0.3, "auto": 0.8},
        "EUPHORIA":  {"defence": 1.0, "upstream_energy": 1.0, "it": 1.0, "omcs": 1.0, "banks": 1.0, "pharma": 0.2, "auto": 1.0},
    }
    weights = regime_weights.get(regime, regime_weights["NEUTRAL"])

    # ── Step 3: Select best long and short candidates ────────────
    print(f"\n  {'─'*70}")
    print(f"  SECTOR RANKINGS (regime-adjusted)")
    print(f"  {'─'*70}")

    long_candidates = []
    short_candidates = []

    for sector_name, sector in UNIVERSE.items():
        direction = sector["direction"]
        sector_weight = weights.get(sector_name, 0.5)

        if sector_weight == 0:
            print(f"\n  {sector_name.upper()}: SKIPPED (regime={regime} → weight=0)")
            continue

        stocks = [all_scored[s] for s in sector["stocks"] if s in all_scored]
        if not stocks:
            continue

        # Sort by trust score
        stocks_by_trust = sorted(stocks, key=lambda x: x["trust_score"], reverse=True)

        print(f"\n  {sector_name.upper()} ({direction}) — regime weight: {sector_weight:.1f}")
        for s in stocks_by_trust:
            flag = " ← PICK" if s == stocks_by_trust[0] else ""
            print(f"    {s['symbol']:10s} Trust: {s['trust_grade']} ({s['trust_score']:2d}) | PE={(s.get('pe') or 0):5.1f} ROE={(s.get('roe') or 0):5.1f}% Growth={(s.get('revenue_growth_3yr') or 0):5.1f}%{flag}")

        best = stocks_by_trust[0]
        worst = stocks_by_trust[-1] if len(stocks_by_trust) > 1 else None

        if direction == "long":
            long_candidates.append({
                **best, "sector_weight": sector_weight,
                "conviction": round(best["trust_score"] * sector_weight / 100, 2),
            })
        elif direction == "short":
            # For shorts: pick the LOWEST trust score (worst management)
            pick = worst if worst else best
            short_candidates.append({
                **pick, "sector_weight": sector_weight,
                "conviction": round((100 - pick["trust_score"]) * sector_weight / 100, 2),
            })
        else:  # "either" — best goes long, worst goes short
            long_candidates.append({
                **best, "sector_weight": sector_weight,
                "conviction": round(best["trust_score"] * sector_weight / 100, 2),
            })
            if worst and worst["symbol"] != best["symbol"]:
                short_candidates.append({
                    **worst, "sector_weight": sector_weight,
                    "conviction": round((100 - worst["trust_score"]) * sector_weight / 100, 2),
                })

    # ── Step 4: Size positions by conviction ─────────────────────
    # Sort by conviction, take top positions up to max
    long_candidates.sort(key=lambda x: x["conviction"], reverse=True)
    short_candidates.sort(key=lambda x: x["conviction"], reverse=True)

    max_longs = max_positions // 2 + max_positions % 2
    max_shorts = max_positions // 2

    basket_longs = long_candidates[:max_longs]
    basket_shorts = short_candidates[:max_shorts]

    # Normalize weights
    total_conv = sum(p["conviction"] for p in basket_longs + basket_shorts) or 1
    for p in basket_longs + basket_shorts:
        p["weight_pct"] = round(p["conviction"] / total_conv * 100, 1)

    # ── Step 5: Print basket ─────────────────────────────────────
    print(f"\n{'='*70}")
    print(f"  ANKA BASKET — {regime} regime")
    print(f"{'='*70}")

    print(f"\n  LONG POSITIONS:")
    print(f"  {'Symbol':10s} {'Trust':6s} {'Sector':15s} {'Price':>8s} {'PE':>6s} {'Weight':>7s} {'Conviction':>10s}")
    print(f"  {'─'*65}")
    for p in basket_longs:
        print(f"  {p['symbol']:10s} {p['trust_grade']:>4s}   {p['sector']:15s} {(p.get('price') or 0):>8,.0f} {(p.get('pe') or 0):>6.1f} {p['weight_pct']:>6.1f}% {p['conviction']:>9.2f}")

    print(f"\n  SHORT POSITIONS:")
    print(f"  {'Symbol':10s} {'Trust':6s} {'Sector':15s} {'Price':>8s} {'PE':>6s} {'Weight':>7s} {'Conviction':>10s}")
    print(f"  {'─'*65}")
    for p in basket_shorts:
        print(f"  {p['symbol']:10s} {p['trust_grade']:>4s}   {p['sector']:15s} {(p.get('price') or 0):>8,.0f} {(p.get('pe') or 0):>6.1f} {p['weight_pct']:>6.1f}% {p['conviction']:>9.2f}")

    # ── Spread trades (pair within each sector) ──────────────────
    print(f"\n  SPREAD TRADES:")
    spreads = []
    for l in basket_longs:
        matching_shorts = [s for s in basket_shorts if s["sector"] != l["sector"]]
        if matching_shorts:
            best_short = matching_shorts[0]
            spread = {
                "long": l["symbol"], "long_price": l.get("price"),
                "long_trust": l["trust_grade"], "long_sector": l["sector"],
                "short": best_short["symbol"], "short_price": best_short.get("price"),
                "short_trust": best_short["trust_grade"], "short_sector": best_short["sector"],
            }
            spreads.append(spread)
            print(f"  BUY {l['symbol']} ({l['trust_grade']}) @ Rs {(l.get('price') or 0):,.0f} / SELL {best_short['symbol']} ({best_short['trust_grade']}) @ Rs {(best_short.get('price') or 0):,.0f}")

    # ── Save ─────────────────────────────────────────────────────
    basket = {
        "generated_at": now.isoformat(),
        "regime": regime,
        "longs": [{k: v for k, v in p.items() if k != "trust_factors"} for p in basket_longs],
        "shorts": [{k: v for k, v in p.items() if k != "trust_factors"} for p in basket_shorts],
        "spreads": spreads,
        "total_positions": len(basket_longs) + len(basket_shorts),
        "stock_scores": {sym: {
            "trust_score": s["trust_score"], "trust_grade": s["trust_grade"],
            "pe": s.get("pe"), "roe": s.get("roe"),
            "growth_3yr": s.get("revenue_growth_3yr"), "opm": s.get("opm"),
            "price": s.get("price"), "sector": s.get("sector"),
            "factors": s.get("trust_factors", {}),
        } for sym, s in all_scored.items()},
    }

    out_path = ARTIFACTS / "basket.json"
    out_path.write_text(json.dumps(basket, indent=2, default=str), encoding="utf-8")
    print(f"\n  Saved: {out_path}")
    print(f"{'='*70}")

    return basket


if __name__ == "__main__":
    regime = "NEUTRAL"
    for i, arg in enumerate(sys.argv):
        if arg == "--regime" and i + 1 < len(sys.argv):
            regime = sys.argv[i + 1].upper()
    build_basket(regime)
