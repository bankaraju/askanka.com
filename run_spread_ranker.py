"""
OPUS ANKA — Spread Trade Ranker

Takes the regime engine's sector call (e.g., "BUY Defence, SELL OMCs")
and picks the BEST stock within each sector using:
1. Screener financials (fast — no PDF analysis needed)
2. Key forensic ratios per sector
3. Valuation gap (current PE vs sector fair PE)

Output: Specific spread trade → "BUY BEL @ Rs X / SELL BPCL @ Rs Y"

Usage:
    python run_spread_ranker.py
    python run_spread_ranker.py --sector defence,omcs
"""

import json
import sys
import time
from pathlib import Path
from datetime import datetime, timezone, timedelta

from pipeline.retrieval.screener_client import ScreenerClient

IST = timezone(timedelta(hours=5, minutes=30))
ARTIFACTS = Path(__file__).parent / "artifacts"

# ── Signal Universe ─────────────────────────────────────────────────

UNIVERSE = {
    "defence": {
        "direction": "long",
        "stocks": ["HAL", "BEL", "BDL"],
        "key_ratios": ["order_book_years", "revenue_growth_3yr", "roe", "pe", "opm"],
    },
    "it": {
        "direction": "short",
        "stocks": ["TCS", "INFY", "WIPRO", "HCLTECH"],
        "key_ratios": ["revenue_growth_3yr", "opm", "roe", "pe", "attrition_proxy"],
    },
    "upstream_energy": {
        "direction": "long",
        "stocks": ["ONGC", "COALINDIA"],
        "key_ratios": ["revenue_growth_3yr", "opm", "roe", "pe", "dividend_yield"],
    },
    "omcs": {
        "direction": "short",
        "stocks": ["BPCL", "HPCL", "IOC"],
        "key_ratios": ["opm", "roe", "pe", "debt_to_equity_proxy"],
    },
    "banks": {
        "direction": "either",
        "stocks": ["HDFCBANK", "ICICIBANK", "SBIN", "KOTAKBANK", "AXISBANK"],
        "key_ratios": ["roe", "pe", "pb", "revenue_growth_3yr"],
    },
    "pharma": {
        "direction": "hedge",
        "stocks": ["SUNPHARMA", "DRREDDY", "CIPLA"],
        "key_ratios": ["revenue_growth_3yr", "opm", "roe", "pe"],
    },
    "auto": {
        "direction": "either",
        "stocks": ["TATAMOTORS", "M&M", "MARUTI"],
        "key_ratios": ["revenue_growth_3yr", "opm", "roe", "pe"],
    },
}


def parse_num(s):
    if not s:
        return None
    try:
        return float(str(s).replace(",", "").replace("%", ""))
    except:
        return None


def fetch_stock_snapshot(symbol: str, screener: ScreenerClient) -> dict:
    """Fetch key metrics for a stock from Screener.in."""
    out_dir = ARTIFACTS / symbol
    cache = out_dir / "screener_financials.json"

    # Use cache if less than 24 hours old
    if cache.exists():
        age_hours = (time.time() - cache.stat().st_mtime) / 3600
        if age_hours < 24:
            data = json.loads(cache.read_text(encoding="utf-8"))
            return _extract_snapshot(symbol, data)

    # Fetch fresh
    data = screener.get_financials(symbol)
    if data:
        out_dir.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    return _extract_snapshot(symbol, data) if data else {}


def _extract_snapshot(symbol: str, data: dict) -> dict:
    """Extract key metrics from Screener data."""
    about = data.get("about", {})
    pl = data.get("profit_loss", [])

    def get_row(label):
        for row in pl:
            l = row.get("", "").strip().rstrip("+")
            if l == label.rstrip("+"):
                return row
        return {}

    # Current metrics from about section
    pe = parse_num(about.get("Stock P/E", ""))
    roe = parse_num(about.get("ROE", ""))
    roce = parse_num(about.get("ROCE", ""))
    pb = parse_num(about.get("Book Value", ""))
    div_yield = parse_num(about.get("Dividend Yield", ""))
    mcap = parse_num(about.get("Market Cap", ""))
    price = parse_num(about.get("Current Price", ""))

    # Revenue growth (3-year CAGR)
    sales_row = get_row("Sales") or get_row("Sales+")
    years = sorted([k for k in sales_row if k.startswith("Mar ")], key=lambda x: int(x.split()[-1]))
    rev_3yr_cagr = None
    if len(years) >= 4:
        recent = parse_num(sales_row.get(years[-1]))
        three_ago = parse_num(sales_row.get(years[-4]))
        if recent and three_ago and three_ago > 0:
            rev_3yr_cagr = round(((recent / three_ago) ** (1/3) - 1) * 100, 1)

    # OPM from latest year
    opm = None
    opm_row = get_row("OPM %")
    if opm_row and years:
        opm = parse_num(opm_row.get(years[-1]))

    # Latest revenue and profit
    latest_rev = parse_num(sales_row.get(years[-1])) if years else None
    np_row = get_row("Net Profit") or get_row("Net Profit+")
    latest_pat = parse_num(np_row.get(years[-1])) if years and np_row else None

    return {
        "symbol": symbol,
        "price": price,
        "market_cap": mcap,
        "pe": pe,
        "roe": roe,
        "roce": roce,
        "pb": pb,
        "dividend_yield": div_yield,
        "opm": opm,
        "revenue_growth_3yr": rev_3yr_cagr,
        "latest_revenue": latest_rev,
        "latest_pat": latest_pat,
    }


def score_for_long(snapshot: dict) -> float:
    """Score a stock for LONG position. Higher = better long candidate."""
    score = 0
    # Prefer: high growth, high ROE, reasonable PE, high OPM
    if snapshot.get("revenue_growth_3yr"):
        score += min(snapshot["revenue_growth_3yr"], 30) * 2  # Cap at 30%
    if snapshot.get("roe"):
        score += min(snapshot["roe"], 40)  # ROE contribution
    if snapshot.get("pe") and snapshot["pe"] > 0:
        # Lower PE = better value. Penalize very high PE.
        if snapshot["pe"] < 20:
            score += 20
        elif snapshot["pe"] < 30:
            score += 10
        elif snapshot["pe"] > 50:
            score -= 15
    if snapshot.get("opm"):
        score += min(snapshot["opm"], 35)
    if snapshot.get("roce"):
        score += min(snapshot["roce"], 30) * 0.5
    return round(score, 1)


def score_for_short(snapshot: dict) -> float:
    """Score a stock for SHORT position. Higher = better short candidate."""
    score = 0
    # Prefer to short: low growth, low ROE, high PE (overvalued), low OPM
    if snapshot.get("revenue_growth_3yr"):
        score += max(0, 15 - snapshot["revenue_growth_3yr"]) * 2  # Low growth = good short
    if snapshot.get("roe"):
        score += max(0, 20 - snapshot["roe"])  # Low ROE = good short
    if snapshot.get("pe") and snapshot["pe"] > 0:
        if snapshot["pe"] > 40:
            score += 25  # Very expensive
        elif snapshot["pe"] > 25:
            score += 15
    if snapshot.get("opm"):
        score += max(0, 20 - snapshot["opm"])  # Low margins = good short
    return round(score, 1)


def run(sectors=None):
    """Run spread ranker across all sectors."""
    screener = ScreenerClient()

    print(f"{'='*70}")
    print(f"  OPUS ANKA — Spread Trade Ranker")
    print(f"  {datetime.now(IST).strftime('%B %d, %Y %H:%M IST')}")
    print(f"{'='*70}")

    results = {}
    all_snapshots = {}

    sector_list = sectors if sectors else list(UNIVERSE.keys())

    for sector_name in sector_list:
        sector = UNIVERSE.get(sector_name)
        if not sector:
            print(f"\n  Unknown sector: {sector_name}")
            continue

        direction = sector["direction"]
        stocks = sector["stocks"]

        print(f"\n  {'─'*60}")
        print(f"  {sector_name.upper()} ({direction.upper()})")
        print(f"  {'─'*60}")

        snapshots = []
        for sym in stocks:
            print(f"    Fetching {sym}...", end=" ")
            snap = fetch_stock_snapshot(sym, screener)
            if snap:
                # Score for both long and short
                snap["long_score"] = score_for_long(snap)
                snap["short_score"] = score_for_short(snap)
                snapshots.append(snap)
                all_snapshots[sym] = snap
                print(f"PE={snap.get('pe', '?')} ROE={snap.get('roe', '?')}% Growth={snap.get('revenue_growth_3yr', '?')}% OPM={snap.get('opm', '?')}%")
            else:
                print("FAILED")
            time.sleep(0.5)

        if not snapshots:
            continue

        # Rank
        if direction == "long":
            ranked = sorted(snapshots, key=lambda x: x["long_score"], reverse=True)
            best = ranked[0]
            print(f"\n    BEST LONG: {best['symbol']} (score {best['long_score']}) @ Rs {best.get('price', '?')}")
        elif direction == "short":
            ranked = sorted(snapshots, key=lambda x: x["short_score"], reverse=True)
            best = ranked[0]
            print(f"\n    BEST SHORT: {best['symbol']} (score {best['short_score']}) @ Rs {best.get('price', '?')}")
        else:
            long_ranked = sorted(snapshots, key=lambda x: x["long_score"], reverse=True)
            short_ranked = sorted(snapshots, key=lambda x: x["short_score"], reverse=True)
            print(f"\n    BEST LONG: {long_ranked[0]['symbol']} (score {long_ranked[0]['long_score']})")
            print(f"    BEST SHORT: {short_ranked[0]['symbol']} (score {short_ranked[0]['short_score']})")
            ranked = long_ranked

        # Print ranking table
        print(f"\n    {'Symbol':10s} {'Price':>8s} {'PE':>6s} {'ROE':>6s} {'Growth':>7s} {'OPM':>6s} {'L-Score':>8s} {'S-Score':>8s}")
        print(f"    {'─'*62}")
        for s in ranked:
            print(f"    {s['symbol']:10s} {(s.get('price') or 0):>8,.0f} {(s.get('pe') or 0):>6.1f} {(s.get('roe') or 0):>5.1f}% {(s.get('revenue_growth_3yr') or 0):>6.1f}% {(s.get('opm') or 0):>5.1f}% {s['long_score']:>8.1f} {s['short_score']:>8.1f}")

        results[sector_name] = {
            "direction": direction,
            "rankings": [{k: v for k, v in s.items()} for s in ranked],
            "best": ranked[0]["symbol"],
        }

    # ── Generate Specific Spread Recommendations ─────────────────
    print(f"\n{'='*70}")
    print(f"  RECOMMENDED SPREAD TRADES")
    print(f"{'='*70}")

    spread_trades = []

    # Defence vs IT
    if "defence" in results and "it" in results:
        long_sym = results["defence"]["best"]
        short_sym = results["it"]["best"]
        long_snap = all_snapshots[long_sym]
        short_snap = all_snapshots[short_sym]
        trade = {
            "name": f"{long_sym} vs {short_sym}",
            "long": long_sym, "long_price": long_snap.get("price"),
            "long_reason": f"PE={long_snap.get('pe')}, ROE={long_snap.get('roe')}%, Growth={long_snap.get('revenue_growth_3yr')}%",
            "short": short_sym, "short_price": short_snap.get("price"),
            "short_reason": f"PE={short_snap.get('pe')}, ROE={short_snap.get('roe')}%, Growth={short_snap.get('revenue_growth_3yr')}%",
        }
        spread_trades.append(trade)
        print(f"\n  1. BUY {long_sym} @ Rs {long_snap.get('price', '?'):,.0f} / SELL {short_sym} @ Rs {short_snap.get('price', '?'):,.0f}")
        print(f"     Long:  {trade['long_reason']}")
        print(f"     Short: {trade['short_reason']}")

    # Upstream vs OMCs
    if "upstream_energy" in results and "omcs" in results:
        long_sym = results["upstream_energy"]["best"]
        short_sym = results["omcs"]["best"]
        long_snap = all_snapshots[long_sym]
        short_snap = all_snapshots[short_sym]
        trade = {
            "name": f"{long_sym} vs {short_sym}",
            "long": long_sym, "long_price": long_snap.get("price"),
            "long_reason": f"PE={long_snap.get('pe')}, ROE={long_snap.get('roe')}%, Div={long_snap.get('dividend_yield')}%",
            "short": short_sym, "short_price": short_snap.get("price"),
            "short_reason": f"PE={short_snap.get('pe')}, ROE={short_snap.get('roe')}%, OPM={short_snap.get('opm')}%",
        }
        spread_trades.append(trade)
        print(f"\n  2. BUY {long_sym} @ Rs {long_snap.get('price', '?'):,.0f} / SELL {short_sym} @ Rs {short_snap.get('price', '?'):,.0f}")
        print(f"     Long:  {trade['long_reason']}")
        print(f"     Short: {trade['short_reason']}")

    # Banks: best long vs worst
    if "banks" in results:
        rankings = results["banks"]["rankings"]
        if len(rankings) >= 2:
            best_bank = rankings[0]
            worst_bank = rankings[-1]
            trade = {
                "name": f"{best_bank['symbol']} vs {worst_bank['symbol']}",
                "long": best_bank['symbol'], "long_price": best_bank.get("price"),
                "long_reason": f"PE={best_bank.get('pe')}, ROE={best_bank.get('roe')}%",
                "short": worst_bank['symbol'], "short_price": worst_bank.get("price"),
                "short_reason": f"PE={worst_bank.get('pe')}, ROE={worst_bank.get('roe')}%",
            }
            spread_trades.append(trade)
            print(f"\n  3. BUY {best_bank['symbol']} @ Rs {best_bank.get('price', '?'):,.0f} / SELL {worst_bank['symbol']} @ Rs {worst_bank.get('price', '?'):,.0f}")
            print(f"     Long:  {trade['long_reason']}")
            print(f"     Short: {trade['short_reason']}")

    # Save results
    output = {
        "generated_at": datetime.now(IST).isoformat(),
        "sector_rankings": results,
        "spread_trades": spread_trades,
        "all_snapshots": all_snapshots,
    }
    out_path = ARTIFACTS / "spread_rankings.json"
    out_path.write_text(json.dumps(output, indent=2, default=str), encoding="utf-8")

    print(f"\n{'='*70}")
    print(f"  Saved: {out_path}")
    print(f"{'='*70}")

    return output


if __name__ == "__main__":
    sectors = None
    if len(sys.argv) > 1 and sys.argv[1] == "--sector":
        sectors = sys.argv[2].split(",") if len(sys.argv) > 2 else None
    run(sectors)
