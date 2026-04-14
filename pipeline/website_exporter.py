"""
Anka Research Pipeline — Website Data Exporter
Reads pipeline state (signals, MSI, backtest) and writes JSON files
for the live dashboard at askanka.com.

Run after each signal cycle or on-demand:
    python website_exporter.py
"""

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from config import INDIA_SPREAD_PAIRS, INDIA_SIGNAL_STOCKS

IST = timezone(timedelta(hours=5, minutes=30))
DATA_DIR = Path(__file__).parent / "data"
SIGNALS_DIR = DATA_DIR / "signals"
WEBSITE_DIR = Path(__file__).parent.parent / "data"  # askanka.com/data/ when synced

OPEN_FILE = SIGNALS_DIR / "open_signals.json"
CLOSED_FILE = SIGNALS_DIR / "closed_signals.json"
MSI_HISTORY = DATA_DIR / "msi_history.json"
PATTERN_LOOKUP = DATA_DIR / "pattern_lookup.json"
SPREAD_STATS = DATA_DIR / "spread_stats.json"


def _load_json(path: Path) -> list | dict:
    if not path.exists():
        return [] if "signal" in path.name else {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return [] if "signal" in path.name else {}


def export_live_status() -> dict:
    """Export current pipeline state for the live dashboard."""
    open_sigs = _load_json(OPEN_FILE)
    closed_sigs = _load_json(CLOSED_FILE)
    msi_history = _load_json(MSI_HISTORY)

    # Latest MSI
    latest_msi = msi_history[-1] if msi_history else {"msi_score": 50, "regime": "MACRO_NEUTRAL"}

    # Stats
    total_signals = len(open_sigs) + len(closed_sigs)
    wins = sum(1 for s in closed_sigs if s.get("final_pnl", {}).get("spread_pnl_pct", 0) > 0)
    losses = len(closed_sigs) - wins
    win_rate = (wins / len(closed_sigs) * 100) if closed_sigs else 0

    # Cumulative P&L
    closed_pnls = [s.get("final_pnl", {}).get("spread_pnl_pct", 0) for s in closed_sigs]
    cumulative_pnl = sum(closed_pnls)

    # Open positions for display
    positions = []
    for sig in open_sigs:
        dl = sig.get("_data_levels", {})
        positions.append({
            "signal_id": sig.get("signal_id", ""),
            "spread_name": sig.get("spread_name", ""),
            "category": sig.get("category", ""),
            "tier": sig.get("tier", "SIGNAL"),
            "open_date": sig.get("open_timestamp", "")[:10],
            "long_legs": [
                {"ticker": l["ticker"], "entry": l["price"],
                 "current": l.get("price", 0)}
                for l in sig.get("long_legs", [])
            ],
            "short_legs": [
                {"ticker": s["ticker"], "entry": s["price"],
                 "current": s.get("price", 0)}
                for s in sig.get("short_legs", [])
            ],
            "spread_pnl_pct": dl.get("cumulative", 0),
            "todays_move": dl.get("todays_move", 0),
            "daily_stop": dl.get("daily_stop", 0),
            "two_day_stop": dl.get("two_day_stop", 0),
            "peak_pnl": sig.get("peak_spread_pnl_pct", 0),
        })

    # Days active (from first signal)
    all_dates = []
    for s in open_sigs + closed_sigs:
        ts = s.get("open_timestamp", "")
        if ts:
            all_dates.append(ts[:10])
    first_date = min(all_dates) if all_dates else datetime.now(IST).strftime("%Y-%m-%d")
    days_active = (datetime.now(IST).date() - datetime.strptime(first_date, "%Y-%m-%d").date()).days

    # Fragility scores
    fragility = {}
    frag_file = DATA_DIR / "fragility_scores.json"
    if frag_file.exists():
        try:
            frag_data = json.loads(frag_file.read_text(encoding="utf-8"))
            fragility = frag_data.get("scores", {})
        except Exception:
            pass

    return {
        "updated_at": datetime.now(IST).isoformat(),
        "msi": {
            "score": latest_msi.get("msi_score", 50),
            "regime": latest_msi.get("regime", "MACRO_NEUTRAL"),
            "date": latest_msi.get("date", ""),
        },
        "stats": {
            "open_positions": len(open_sigs),
            "total_signals": total_signals,
            "wins": wins,
            "losses": losses,
            "win_rate_pct": round(win_rate, 1),
            "cumulative_pnl_pct": round(cumulative_pnl, 2),
            "days_active": days_active,
        },
        "positions": positions,
        "fragility": fragility,
    }


def export_track_record() -> dict:
    """Export closed trades for the track record table."""
    closed_sigs = _load_json(CLOSED_FILE)

    trades = []
    for sig in closed_sigs:
        pnl = sig.get("final_pnl", {})
        trades.append({
            "signal_id": sig.get("signal_id", ""),
            "spread_name": sig.get("spread_name", ""),
            "category": sig.get("category", ""),
            "tier": sig.get("tier", "SIGNAL"),
            "open_date": sig.get("open_timestamp", "")[:10],
            "close_date": sig.get("close_timestamp", "")[:10],
            "status": sig.get("status", ""),
            "spread_pnl_pct": pnl.get("spread_pnl_pct", 0),
            "long_pnl_pct": pnl.get("long_pnl_pct", 0),
            "short_pnl_pct": pnl.get("short_pnl_pct", 0),
            "peak_pnl_pct": sig.get("peak_spread_pnl_pct", 0),
        })

    # Sort by close date descending
    trades.sort(key=lambda t: t.get("close_date", ""), reverse=True)

    # Summary stats
    pnls = [t["spread_pnl_pct"] for t in trades]
    return {
        "updated_at": datetime.now(IST).isoformat(),
        "trades": trades,
        "summary": {
            "total": len(trades),
            "wins": sum(1 for p in pnls if p > 0),
            "losses": sum(1 for p in pnls if p <= 0),
            "win_rate_pct": round(sum(1 for p in pnls if p > 0) / len(pnls) * 100, 1) if pnls else 0,
            "avg_pnl_pct": round(sum(pnls) / len(pnls), 2) if pnls else 0,
            "best_trade_pct": round(max(pnls), 2) if pnls else 0,
            "worst_trade_pct": round(min(pnls), 2) if pnls else 0,
            "cumulative_pnl_pct": round(sum(pnls), 2),
        },
    }


def export_spread_universe() -> dict:
    """Export all 25 spreads with backtest stats for the heatmap."""
    pattern_data = _load_json(PATTERN_LOOKUP)
    spread_backtests = pattern_data.get("spread_backtests", {})

    spreads = []
    for pair in INDIA_SPREAD_PAIRS:
        name = pair["name"]
        backtest = spread_backtests.get(name, {})

        # Build category stats
        cat_stats = {}
        for cat, stats in backtest.items():
            cat_stats[cat] = {
                "hit_rate": stats.get("hit_rate", 0),
                "spread_1d": stats.get("1d_spread_median", 0),
                "spread_5d": stats.get("5d_spread_median", 0),
                "n": stats.get("n", 0),
            }

        # Best trigger
        best_cat = max(cat_stats.items(), key=lambda x: x[1]["hit_rate"]) if cat_stats else (None, {})

        spreads.append({
            "name": name,
            "long": pair["long"],
            "short": pair["short"],
            "triggers": pair.get("triggers", []),
            "notes": pair.get("notes", ""),
            "best_trigger": best_cat[0],
            "best_hit_rate": best_cat[1].get("hit_rate", 0) if best_cat[0] else 0,
            "categories": cat_stats,
        })

    # All unique categories across all spreads
    all_cats = sorted(set(
        cat for s in spreads for cat in s["categories"]
    ))

    return {
        "updated_at": datetime.now(IST).isoformat(),
        "spreads": spreads,
        "categories": all_cats,
        "total_spreads": len(spreads),
        "total_categories": len(all_cats),
    }


def export_msi_history() -> list:
    """Export MSI history for the chart."""
    return _load_json(MSI_HISTORY)


def run_export():
    """Run full export to website JSON files."""
    WEBSITE_DIR.mkdir(parents=True, exist_ok=True)

    live = export_live_status()
    track = export_track_record()
    universe = export_spread_universe()
    msi = export_msi_history()

    for name, data in [
        ("live_status.json", live),
        ("track_record.json", track),
        ("spread_universe.json", universe),
        ("msi_history.json", msi),
    ]:
        path = WEBSITE_DIR / name
        path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        print(f"  Exported {name} ({path})")

    # Copy F&O news data if available
    fno_news = DATA_DIR / "fno_news.json"
    if fno_news.exists():
        import shutil
        shutil.copy2(fno_news, WEBSITE_DIR / "fno_news.json")
        print(f"  Exported fno_news.json ({WEBSITE_DIR / 'fno_news.json'})")

    print(f"\nWebsite data exported to {WEBSITE_DIR}")
    print(f"  Open positions: {live['stats']['open_positions']}")
    print(f"  Closed trades:  {track['summary']['total']}")
    print(f"  Spread pairs:   {universe['total_spreads']}")
    print(f"  MSI history:    {len(msi)} days")


if __name__ == "__main__":
    run_export()
