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
RECOMMENDATIONS_FILE = DATA_DIR / "recommendations.json"
RANKER_STATE_FILE = DATA_DIR / "regime_ranker_state.json"
NEWS_EVENTS_FILE = DATA_DIR / "news_events_today.json"
NEWS_VERDICTS_FILE = DATA_DIR / "news_verdicts.json"
STALE_HOURS = 4


def _load_json(path: Path) -> list | dict:
    if not path.exists():
        return [] if "signal" in path.name else {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return [] if "signal" in path.name else {}


def stale_check(timestamp_str) -> bool:
    """Return True if the given ISO timestamp is older than STALE_HOURS or unparseable."""
    if not timestamp_str:
        return True
    try:
        ts = datetime.fromisoformat(timestamp_str)
    except (ValueError, TypeError):
        return True
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=IST)
    age = datetime.now(IST) - ts
    return age > timedelta(hours=STALE_HOURS)


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


def export_today_recommendations() -> dict:
    """Build the unified recommendations view for the website.

    Reads spread engine, ranker, and news intelligence outputs; returns top-3
    of each as a single dict with per-card freshness flags.
    """
    regime_raw = _load_json(TODAY_REGIME_FILE) or {}
    regime_zone = regime_raw.get("regime", "UNKNOWN")
    regime_ts = regime_raw.get("timestamp")

    spreads = _build_spread_recs()
    stocks = _build_stock_recs()
    news_driven = _build_news_recs()

    return {
        "updated_at": datetime.now(IST).isoformat(),
        "regime_zone": regime_zone,
        "regime_source_timestamp": regime_ts,
        "spreads": spreads,
        "stocks": stocks,
        "news_driven": news_driven,
        "holiday_mode": False,
    }


_CONV_RANK = {"HIGH": 3, "MEDIUM": 2, "LOW": 1, "NONE": 0}


def _build_spread_recs() -> list:
    raw = _load_json(RECOMMENDATIONS_FILE) or {}
    src_ts = raw.get("timestamp")
    stale = stale_check(src_ts)
    out = []
    for r in raw.get("recommendations", []) or []:
        if r.get("action") not in ("ENTER", "EXIT"):
            continue
        if r.get("conviction") in (None, "NONE"):
            continue
        out.append({
            "name": r.get("name", ""),
            "action": r.get("action", ""),
            "conviction": r.get("conviction", "NONE"),
            "z_score": r.get("z_score", 0),
            "reason": r.get("reason", ""),
            "source_timestamp": src_ts,
            "is_stale": stale,
        })
    out.sort(key=lambda s: (-_CONV_RANK.get(s["conviction"], 0), -abs(s.get("z_score") or 0)))
    return out[:3]


def _build_stock_recs() -> list:
    raw = _load_json(RANKER_STATE_FILE) or {}
    src_ts = raw.get("updated")
    stale = stale_check(src_ts)
    out = []
    for r in raw.get("active_recommendations", []) or []:
        drift = r.get("drift_5d_mean", 0) or 0
        abs_drift = abs(drift)
        if abs_drift >= 0.30:
            conviction = "HIGH"
        elif abs_drift >= 0.15:
            conviction = "MEDIUM"
        else:
            conviction = "LOW"
        out.append({
            "ticker": r.get("symbol", ""),
            "direction": r.get("direction", ""),
            "conviction": conviction,
            "trigger": r.get("regime", ""),
            "source": "ranker",
            "source_timestamp": src_ts,
            "is_stale": stale,
            "hit_rate": r.get("hit_rate", 0),
            "episodes": r.get("episodes", 0),
            "_abs_drift": abs_drift,
        })
    out.sort(key=lambda s: (-_CONV_RANK.get(s["conviction"], 0), -s["_abs_drift"]))
    for card in out:
        card.pop("_abs_drift", None)
    return out[:3]


def _build_news_recs() -> list:
    events_raw = _load_json(NEWS_EVENTS_FILE) or {}
    verdicts_raw = _load_json(NEWS_VERDICTS_FILE) or []
    src_ts = events_raw.get("last_scan")
    stale = stale_check(src_ts)

    # Index latest verdict per (symbol, category)
    verdict_idx = {}
    for v in verdicts_raw:
        key = (v.get("symbol"), v.get("category"))
        verdict_idx[key] = v  # last write wins; verdicts file is append-order

    out = []
    for ev in events_raw.get("events", []) or []:
        v = verdict_idx.get((ev.get("symbol"), ev.get("category")))
        if not v:
            continue
        if v.get("recommendation") not in ("BUY", "SELL"):
            continue
        out.append({
            "ticker": ev.get("symbol", ""),
            "headline": ev.get("title", ""),
            "category": ev.get("category", ""),
            "direction": v.get("direction", ""),
            "shelf_days": v.get("shelf_days", 0),
            "historical_hit_rate": v.get("historical_hit_rate", 0),
            "precedent_count": v.get("precedent_count", 0),
            "source_timestamp": src_ts,
            "is_stale": stale,
        })
    out.sort(key=lambda n: -(n.get("historical_hit_rate") or 0))
    return out[:3]


def export_live_status() -> dict:
    """Export current open positions for the live dashboard.

    Mark-to-market: fetches live prices for every leg ticker so current !=
    entry when the market has moved. Falls back to entry only when a fetch
    fails. Without this the dashboard shows 0% P&L indefinitely.
    """
    open_sigs = _load_json(OPEN_FILE)

    # Collect every leg ticker across all open signals and fetch once.
    all_tickers = set()
    for sig in open_sigs:
        for l in sig.get("long_legs", []) + sig.get("short_legs", []):
            all_tickers.add(l["ticker"])

    current_prices: dict = {}
    if all_tickers:
        try:
            from signal_tracker import fetch_current_prices
            current_prices = fetch_current_prices(sorted(all_tickers)) or {}
        except Exception as e:
            print(f"[live_status] fetch_current_prices failed: {e} — falling back to entry", file=sys.stderr)

    def _mtm_leg(leg: dict, is_long: bool) -> dict:
        ticker = leg["ticker"]
        entry = leg.get("price", 0) or 0
        current = current_prices.get(ticker)
        if current is None or not entry:
            current = entry
            pnl_pct = 0.0
        else:
            pnl_pct = ((current / entry - 1) * 100) if is_long else ((1 - current / entry) * 100)
        return {
            "ticker": ticker,
            "entry": round(entry, 2),
            "current": round(float(current), 2),
            "pnl_pct": round(pnl_pct, 2),
        }

    positions = []
    for sig in open_sigs:
        dl = sig.get("_data_levels", {})
        positions.append({
            "signal_id": sig.get("signal_id", ""),
            "spread_name": sig.get("spread_name", ""),
            "category": sig.get("category", ""),
            "tier": sig.get("tier", "SIGNAL"),
            "open_date": sig.get("open_timestamp", "")[:10],
            "long_legs":  [_mtm_leg(l, is_long=True)  for l in sig.get("long_legs", [])],
            "short_legs": [_mtm_leg(s, is_long=False) for s in sig.get("short_legs", [])],
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
    recs = export_today_recommendations()

    for name, data in [
        ("global_regime.json", regime),
        ("live_status.json", live),
        ("today_recommendations.json", recs),
    ]:
        path = WEBSITE_DIR / name
        path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        print(f"  Exported {name} ({path})")

    print(f"\nWebsite data exported to {WEBSITE_DIR}")
    print(f"  Regime zone:    {regime['zone']} (score {regime['score']})")
    print(f"  Open positions: {len(live['positions'])}")
    print(f"  Recommendations: {len(recs['spreads'])} spreads, "
          f"{len(recs['stocks'])} stocks, {len(recs['news_driven'])} news")


if __name__ == "__main__":
    run_export()
