"""
Anka Research Pipeline — Website Data Exporter
Reads the 31-ETF Global Regime Score and open positions, writes
global_regime.json + live_status.json for the live dashboard at askanka.com.

Run after each signal cycle or on-demand:
    python website_exporter.py
"""

import hashlib
import json
import os
import subprocess
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

# A hit-rate is only trustworthy with enough precedents. "100% after 1 occurrence"
# is noise, not signal. Cards below this threshold are marked not-meaningful and
# demoted in the sort so robust samples outrank lucky ones.
MIN_PRECEDENTS = 5


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
        episodes = r.get("episodes", 0) or 0
        out.append({
            "ticker": r.get("symbol", ""),
            "direction": r.get("direction", ""),
            "conviction": conviction,
            "trigger": r.get("regime", ""),
            "source": "ranker",
            "source_timestamp": src_ts,
            "is_stale": stale,
            "hit_rate": r.get("hit_rate", 0),
            "episodes": episodes,
            "hit_rate_meaningful": episodes >= MIN_PRECEDENTS,
            "_abs_drift": abs_drift,
        })
    # Filter: never publish sub-50% hit-rate recs to the website (investor-facing)
    out = [s for s in out if s.get("hit_rate", 0) >= 0.50]
    # Dedup by ticker (keep highest conviction variant)
    seen = set()
    deduped = []
    for s in out:
        if s["ticker"] not in seen:
            seen.add(s["ticker"])
            deduped.append(s)
    out = deduped
    # Demote non-meaningful hit-rates so robust samples rank above lucky ones.
    out.sort(key=lambda s: (
        -int(s["hit_rate_meaningful"]),
        -_CONV_RANK.get(s["conviction"], 0),
        -s["_abs_drift"],
    ))
    for card in out:
        card.pop("_abs_drift", None)
        card.pop("hit_rate_meaningful", None)
    return out[:3]


def _build_news_recs() -> list:
    """Render the news-driven card list from events + backtest verdicts.

    Schema contract (must match upstream writers, not what "feels right"):
      - events carry `categories` as a list (news_intelligence.py),
        `matched_stocks` as a list of tickers, not scalar `symbol`.
      - verdicts carry `recommendation` in {ADD, CUT, MONITOR, NO_ACTION}
        with `direction` in {LONG, SHORT, None} (news_backtest.py:98).
      Drift from these names = empty card list.
    """
    events_raw = _load_json(NEWS_EVENTS_FILE) or {}
    verdicts_raw = _load_json(NEWS_VERDICTS_FILE) or []
    src_ts = events_raw.get("last_scan")
    stale = stale_check(src_ts)

    # Index latest verdict per (symbol, category). Last write wins.
    verdict_idx: dict = {}
    for v in verdicts_raw:
        key = (v.get("symbol"), v.get("category"))
        verdict_idx[key] = v

    seen: set = set()
    out: list = []
    for ev in events_raw.get("events", []) or []:
        stocks = ev.get("matched_stocks") or []
        if isinstance(stocks, str):
            try:
                stocks = json.loads(stocks.replace("'", '"'))
            except Exception:
                stocks = []
        cats = ev.get("categories") or []
        if isinstance(cats, str):
            try:
                cats = json.loads(cats.replace("'", '"'))
            except Exception:
                cats = []
        if not stocks or not cats:
            continue
        # Try every (stock, category) pair — events can be multi-category.
        for sym in stocks:
            for cat in cats:
                v = verdict_idx.get((sym, cat))
                if not v or v.get("recommendation") not in ("ADD", "CUT"):
                    continue
                dedup_key = (sym, cat)
                if dedup_key in seen:
                    continue
                seen.add(dedup_key)
                precedents = v.get("precedent_count", 0) or 0
                out.append({
                    "ticker": sym,
                    "headline": ev.get("title", ""),
                    "category": cat,
                    "direction": v.get("direction", ""),
                    "shelf_days": v.get("shelf_days", 0),
                    "historical_hit_rate": v.get("historical_hit_rate", 0),
                    "precedent_count": precedents,
                    "hit_rate_meaningful": precedents >= MIN_PRECEDENTS,
                    "source_timestamp": src_ts,
                    "is_stale": stale,
                })
    # Meaningful rates rank above lucky 100%@1 cards.
    out.sort(key=lambda n: (
        -int(n["hit_rate_meaningful"]),
        -(n.get("historical_hit_rate") or 0),
    ))
    for card in out:
        card.pop("hit_rate_meaningful", None)
    return out[:3]


_CRYPTIC_NAMES = {
    "Defence vs IT": "Sovereign Shield Alpha",
    "Upstream vs Downstream": "Energy Chain Divergence",
    "Coal vs OMCs": "Fossil Arbitrage",
    "Reliance vs OMCs": "Refinery Spread",
    "Pharma vs Cyclicals": "Defensive Rotation",
    "PSU Banks vs Private Banks": "Banking Regime Play",
    "PSU Commodity vs Banks": "Commodity-Credit Divergence",
    "IT vs Banks": "Global-Local Pivot",
    "Infra Capex Beneficiaries": "Capex Momentum",
    "Auto vs FMCG": "Discretionary Shift",
    "Metals vs FMCG": "Cyclical-Staple Spread",
    "Telecom vs Media": "Network Effect Arb",
    "Real Estate vs IT": "Asset-Income Rotation",
}


def _cryptic_name(spread_name: str) -> str:
    if spread_name in _CRYPTIC_NAMES:
        return _CRYPTIC_NAMES[spread_name]
    # md5 for stable IDs across process restarts (Python's hash() is randomized).
    digest = hashlib.md5(spread_name.encode("utf-8")).hexdigest()
    return f"Strategy {int(digest[:8], 16) % 900 + 100}"


def _refresh_trust(sig: dict, fresh_trust: dict) -> dict:
    """Rebuild trust_scores for a signal using fresh per-stock data."""
    all_tickers = set()
    for leg in sig.get("long_legs", []) + sig.get("short_legs", []):
        all_tickers.add(leg["ticker"])
    result = {}
    for t in all_tickers:
        if t in fresh_trust:
            result[t] = fresh_trust[t]
        else:
            old = (sig.get("trust_scores") or {}).get(t)
            if old:
                result[t] = old
    return result or sig.get("trust_scores")


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

    # Fresh trust score lookup (per-stock files, not stale signal data)
    try:
        from signal_enrichment import load_trust_scores
        _fresh_trust = load_trust_scores()
    except Exception:
        _fresh_trust = {}

    positions = []
    for sig in open_sigs:
        dl = sig.get("_data_levels", {})
        long_mtm  = [_mtm_leg(l, is_long=True)  for l in sig.get("long_legs", [])]
        short_mtm = [_mtm_leg(s, is_long=False) for s in sig.get("short_legs", [])]

        # Compute spread-level P&L from per-leg MTM when signal_tracker hasn't
        # yet written _data_levels (which is common for freshly-opened signals).
        # Average pnl_pct across each side, sum for the spread.
        def _avg(legs):
            pnls = [l["pnl_pct"] for l in legs]
            return sum(pnls) / len(pnls) if pnls else 0.0

        computed_spread_pnl = round(_avg(long_mtm) + _avg(short_mtm), 2)
        # Prefer tracker's cumulative if it has a non-zero value; fall back to MTM.
        cumulative = dl.get("cumulative") if dl.get("cumulative") else computed_spread_pnl
        todays_move = dl.get("todays_move") if dl.get("todays_move") else computed_spread_pnl
        peak = sig.get("peak_spread_pnl_pct") or computed_spread_pnl

        positions.append({
            "signal_id": sig.get("signal_id", ""),
            "spread_name": _cryptic_name(sig.get("spread_name", "")),
            "category": sig.get("category", ""),
            "tier": sig.get("tier", "SIGNAL"),
            "open_date": sig.get("open_timestamp", "")[:10],
            "long_legs":  long_mtm,
            "short_legs": short_mtm,
            "spread_pnl_pct": cumulative,
            "todays_move": todays_move,
            "daily_stop": dl.get("daily_stop", 0),
            "two_day_stop": dl.get("two_day_stop", 0),
            "trail_stop": dl.get("trail_stop"),
            "trail_budget": dl.get("trail_budget"),
            "avg_favorable": dl.get("avg_favorable"),
            # Provenance for the Stop cell. "fallback" → muted dot in the UI
            # (ATR was attempted but unavailable, so we're using spread-stats
            # defaults that aren't volatility-calibrated for this ticker).
            # Default to "spread_stats" for legacy rows without the key.
            "stop_source": dl.get("stop_source", "spread_stats"),
            "peak_pnl": peak,
            "source": sig.get("source", "SPREAD"),
            "trust_scores": _refresh_trust(sig, _fresh_trust),
            "regime_rank": sig.get("regime_rank"),
            "correlation_breaks": sig.get("correlation_breaks"),
            "oi_anomalies": sig.get("oi_anomalies"),
            "conviction_score": sig.get("conviction_score"),
            "gate_reason": sig.get("gate_reason"),
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


def _derive_close_reason(sig: dict) -> str:
    """Human-readable close reason from the signal's final state."""
    status = sig.get("status", "")
    dl = sig.get("_data_levels", {}) or {}
    if status == "STOPPED_OUT_TRAIL":
        cum = dl.get("cumulative")
        ts = dl.get("trail_stop")
        peak = dl.get("peak")
        budget = dl.get("trail_budget")
        if all(v is not None for v in (cum, ts, peak, budget)):
            return (f"Trail stop: cum {cum:+.2f}% <= trail {ts:+.2f}% "
                    f"(peak {peak:+.2f}% - budget {budget:.2f}%)")
        return "Trail stop hit"
    if status == "STOPPED_OUT":
        tm = dl.get("todays_move")
        ds = dl.get("daily_stop")
        if tm is not None and ds is not None:
            return f"Daily stop: today {tm:+.2f}% <= stop {ds:+.2f}%"
        return "Daily stop hit"
    if status == "STOPPED_OUT_2DAY":
        return "2-day running stop hit (two consecutive losing days)"
    if status == "EXPIRED":
        return "Holding period expired"
    return status or "Closed"


def export_track_record(limit: int = 20) -> dict:
    """Export the most recent N closed signals for the Track Record section."""
    closed_raw = _load_json(CLOSED_FILE) or []
    rows = []
    for sig in closed_raw:
        fp = sig.get("final_pnl", {}) or {}
        rows.append({
            "signal_id": sig.get("signal_id", ""),
            "spread_name": _cryptic_name(sig.get("spread_name", "")),
            "category": sig.get("category", ""),
            "tier": sig.get("tier", ""),
            "event_headline": sig.get("event_headline", ""),
            "open_date": (sig.get("open_timestamp") or "")[:10],
            "close_date": (sig.get("close_timestamp") or "")[:10],
            "days_open": sig.get("days_open", 0) or 0,
            "peak_pnl_pct": sig.get("peak_spread_pnl_pct", 0) or 0,
            "final_pnl_pct": fp.get("spread_pnl_pct", 0) or 0,
            "close_reason": _derive_close_reason(sig),
        })
    # Most recent first by close_date desc
    rows.sort(key=lambda r: r["close_date"], reverse=True)
    rows = rows[:limit]

    # Aggregate stats over all closed (not just the shown N)
    all_final = [
        (s.get("final_pnl") or {}).get("spread_pnl_pct", 0) or 0
        for s in closed_raw
    ]
    wins = sum(1 for p in all_final if p > 0)
    losses = sum(1 for p in all_final if p <= 0)
    total = len(all_final)
    win_rate = (wins / total * 100) if total else 0
    avg_pnl = (sum(all_final) / total) if total else 0

    return {
        "updated_at": datetime.now(IST).isoformat(),
        "total_closed": total,
        "win_rate_pct": round(win_rate, 1),
        "avg_pnl_pct": round(avg_pnl, 2),
        "recent": rows,
    }


def export_trust_scores() -> dict:
    """Export trust scores — prefer V2 if available."""
    v2_path = Path(__file__).resolve().parent.parent / "data" / "trust_scores_v2.json"
    if v2_path.exists():
        try:
            v2 = json.loads(v2_path.read_text(encoding="utf-8"))
            if v2.get("version") == "2.0":
                return v2
        except Exception:
            pass

    # Fallback to V1 (existing code below)
    try:
        from signal_enrichment import load_trust_scores
        scores = load_trust_scores()
    except Exception:
        scores = {}

    stocks = []
    for sym in sorted(scores):
        s = scores[sym]
        stocks.append({
            "symbol": sym,
            "trust_grade": s.get("trust_grade"),
            "trust_score": s.get("trust_score"),
            "thesis": (s.get("thesis") or "")[:200],
        })

    return {
        "updated_at": datetime.now(IST).isoformat(),
        "total_scored": len(stocks),
        "stocks": stocks,
    }


def run_export():
    """Run full export to website JSON files."""
    WEBSITE_DIR.mkdir(parents=True, exist_ok=True)

    regime = export_global_regime()
    live = export_live_status()
    recs = export_today_recommendations()
    track = export_track_record()
    trust = export_trust_scores()

    for name, data in [
        ("global_regime.json", regime),
        ("live_status.json", live),
        ("today_recommendations.json", recs),
        ("track_record.json", track),
        ("trust_scores.json", trust),
    ]:
        path = WEBSITE_DIR / name
        path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        print(f"  Exported {name} ({path})")

    print(f"\nWebsite data exported to {WEBSITE_DIR}")
    print(f"  Regime zone:    {regime['zone']} (score {regime['score']})")
    print(f"  Open positions: {len(live['positions'])}")
    print(f"  Recommendations: {len(recs['spreads'])} spreads, "
          f"{len(recs['stocks'])} stocks, {len(recs['news_driven'])} news")

    if os.environ.get("WEBSITE_AUTODEPLOY", "1") != "0":
        deploy_to_site()


DEPLOY_FILES = [
    "data/global_regime.json",
    "data/live_status.json",
    "data/today_recommendations.json",
    "data/track_record.json",
    "data/trust_scores.json",
    "data/gap_risk.json",
    "data/spread_stats.json",
    "data/articles_index.json",
    "data/fno_news.json",
]


def deploy_to_site():
    """Stage + commit + push website data JSONs. Noop if nothing staged.

    WHY: website_exporter writes data/*.json locally but GitHub Pages only
    serves committed state. Without this, the live site lags until the next
    human-initiated push.
    """
    repo = Path(__file__).parent.parent
    existing = [f for f in DEPLOY_FILES if (repo / f).exists()]
    if not existing:
        return
    try:
        subprocess.run(["git", "-C", str(repo), "add", "--"] + existing,
                       check=True, capture_output=True, text=True)
        diff = subprocess.run(["git", "-C", str(repo), "diff", "--cached", "--quiet", "--"] + existing,
                              capture_output=True)
        if diff.returncode == 0:
            print("  [deploy] no data changes to push")
            return
        ts = datetime.now(IST).strftime("%Y-%m-%d %H:%M IST")
        msg = f"data: auto-refresh website JSONs {ts}"
        subprocess.run(["git", "-C", str(repo), "commit", "-m", msg],
                       check=True, capture_output=True, text=True)
        push = subprocess.run(["git", "-C", str(repo), "push"],
                              capture_output=True, text=True, timeout=60)
        if push.returncode == 0:
            print(f"  [deploy] pushed: {msg}")
        else:
            print(f"  [deploy] push failed (non-fatal): {push.stderr.strip()[:200]}")
    except subprocess.TimeoutExpired:
        print("  [deploy] push timed out after 60s (non-fatal)")
    except subprocess.CalledProcessError as e:
        print(f"  [deploy] git error (non-fatal): {e.stderr.strip()[:200] if e.stderr else e}")


if __name__ == "__main__":
    run_export()
