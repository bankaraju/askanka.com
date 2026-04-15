"""
Anka Research Pipeline — Website Data Exporter
Reads the 31-ETF Global Regime Score and open positions, writes
global_regime.json + live_status.json for the live dashboard at askanka.com.

Run after each signal cycle or on-demand:
    python website_exporter.py
"""

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))


IST = timezone(timedelta(hours=5, minutes=30))
DATA_DIR = Path(__file__).parent / "data"
SIGNALS_DIR = DATA_DIR / "signals"
WEBSITE_DIR = Path(__file__).parent.parent / "data"  # askanka.com/data/ when synced

OPEN_FILE = SIGNALS_DIR / "open_signals.json"
CLOSED_FILE = SIGNALS_DIR / "closed_signals.json"
TODAY_REGIME_FILE = DATA_DIR / "today_regime.json"


def _load_json(path: Path) -> list | dict:
    if not path.exists():
        return [] if "signal" in path.name else {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return [] if "signal" in path.name else {}


def export_global_regime() -> dict:
    """Export 31-ETF regime engine output for the website hero block."""
    raw = _load_json(TODAY_REGIME_FILE)
    if not isinstance(raw, dict) or not raw:
        return {
            "updated_at": datetime.now(IST).isoformat(),
            "zone": "UNKNOWN",
            "score": None,
            "regime_source": "unavailable",
            "stable": False,
            "consecutive_days": 0,
            "components": {},
            "top_drivers": [],
            "source_timestamp": None,
        }

    components = raw.get("components", {}) or {}
    ranked = sorted(
        components.items(),
        key=lambda kv: abs((kv[1] or {}).get("contribution", 0) or 0),
        reverse=True,
    )
    top_drivers = [name for name, _ in ranked[:3]]

    return {
        "updated_at": datetime.now(IST).isoformat(),
        "zone": raw.get("regime", "UNKNOWN"),
        "score": raw.get("msi_score"),
        "regime_source": raw.get("regime_source", "unknown"),
        "stable": raw.get("regime_stable", False),
        "consecutive_days": raw.get("consecutive_days", 0),
        "components": components,
        "top_drivers": top_drivers,
        "source_timestamp": raw.get("timestamp"),
    }


def export_live_status() -> dict:
    """Export current open positions for the live dashboard."""
    open_sigs = _load_json(OPEN_FILE)

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
                {"ticker": l["ticker"], "entry": l["price"], "current": l.get("price", 0)}
                for l in sig.get("long_legs", [])
            ],
            "short_legs": [
                {"ticker": s["ticker"], "entry": s["price"], "current": s.get("price", 0)}
                for s in sig.get("short_legs", [])
            ],
            "spread_pnl_pct": dl.get("cumulative", 0),
            "todays_move": dl.get("todays_move", 0),
            "daily_stop": dl.get("daily_stop", 0),
            "two_day_stop": dl.get("two_day_stop", 0),
            "peak_pnl": sig.get("peak_spread_pnl_pct", 0),
        })

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
        "positions": positions,
        "fragility": fragility,
    }


def run_export():
    """Run full export to website JSON files."""
    WEBSITE_DIR.mkdir(parents=True, exist_ok=True)

    regime = export_global_regime()
    live = export_live_status()

    for name, data in [
        ("global_regime.json", regime),
        ("live_status.json", live),
    ]:
        path = WEBSITE_DIR / name
        path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        print(f"  Exported {name} ({path})")

    print(f"\nWebsite data exported to {WEBSITE_DIR}")
    print(f"  Regime zone:    {regime['zone']} (score {regime['score']})")
    print(f"  Open positions: {len(live['positions'])}")


if __name__ == "__main__":
    run_export()
