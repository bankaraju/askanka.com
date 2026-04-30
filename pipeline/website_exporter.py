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
    """Return the public-facing label for a spread/strategy.

    Curated cryptic alias if this is one of the marketed spread baskets
    (Defence vs IT -> Sovereign Shield Alpha, etc.). Otherwise return the
    upstream name verbatim — Phase C single-ticker breaks already arrive
    as "Phase C: TATAELXSI OPPORTUNITY_LAG" and other engines name their
    own positions, so anonymising them as "Strategy 734" was destroying
    information the rest of the terminal needs to disambiguate rows.
    """
    if spread_name in _CRYPTIC_NAMES:
        return _CRYPTIC_NAMES[spread_name]
    return spread_name or "Unnamed strategy"


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

    def _mtm_leg(leg: dict, is_long: bool, sig: dict) -> dict:
        ticker = leg["ticker"]
        entry = leg.get("price", 0) or 0
        current = current_prices.get(ticker)
        if current is None or not entry:
            current = entry
            pnl_pct = 0.0
        else:
            pnl_pct = ((current / entry - 1) * 100) if is_long else ((1 - current / entry) * 100)
        # prev_close comes from the EOD snapshot signal_tracker writes via
        # snapshot_eod_prices(). Day-1 positions have no prev_close yet — fall
        # back to entry so today's move == cumulative since entry (correct
        # semantics for a same-day open). Surfacing this lets the frontend
        # live-ticker recompute today's move every 5s from fresh LTPs.
        prev_close_dict = (sig.get("_prev_close_long") if is_long
                           else sig.get("_prev_close_short")) or {}
        prev_close = prev_close_dict.get(ticker, entry)
        return {
            "ticker": ticker,
            "entry": round(entry, 2),
            "current": round(float(current), 2),
            "pnl_pct": round(pnl_pct, 2),
            "prev_close": round(float(prev_close), 2) if prev_close else None,
        }

    # Fresh trust score lookup (per-stock files, not stale signal data)
    try:
        from signal_enrichment import load_trust_scores
        _fresh_trust = load_trust_scores()
    except Exception:
        _fresh_trust = {}

    # Recompute todays_move from FRESH current_prices every export call (30s).
    # Old path read _data_levels.todays_move which is only refreshed by the
    # 15-min intraday signal_tracker cycle — between cycles the dashboard
    # showed a stale Today P&L while LTP kept moving. Reported 4×; fixing at
    # the source so backend and frontend can agree.
    try:
        from signal_tracker import _compute_todays_spread_move as _today_move_fn
    except Exception:
        _today_move_fn = None  # graceful degrade — UI just falls back to dl.todays_move

    positions = []
    for sig in open_sigs:
        dl = sig.get("_data_levels", {})
        long_mtm  = [_mtm_leg(l, is_long=True,  sig=sig) for l in sig.get("long_legs", [])]
        short_mtm = [_mtm_leg(s, is_long=False, sig=sig) for s in sig.get("short_legs", [])]

        # Compute spread-level P&L from per-leg MTM when signal_tracker hasn't
        # yet written _data_levels (which is common for freshly-opened signals).
        # Average pnl_pct across each side, sum for the spread.
        def _avg(legs):
            pnls = [l["pnl_pct"] for l in legs]
            return sum(pnls) / len(pnls) if pnls else 0.0

        computed_spread_pnl = round(_avg(long_mtm) + _avg(short_mtm), 2)
        # spread_pnl_pct must agree with the per-leg current/pnl_pct in this same
        # response — otherwise the UI shows entry→entry on the leg and a non-zero
        # P&L on the spread, which is the 2026-04-30 PETRONET ₹278.45→₹278.45/-0.92%
        # contradiction (#75). signal_tracker writes _data_levels.cumulative from
        # an earlier intraday cycle's LTP fetch; reusing that here while the legs
        # show today's fresh fetch is what desyncs them. Always use the freshly
        # computed value so all three views (entry, current, P&L) agree.
        cumulative = computed_spread_pnl
        # todays_move = avg(per-leg today-move vs prev_close), computed from
        # the SAME fresh current_prices used for cumulative above. Falls back
        # to dl.todays_move only when signal_tracker import is unavailable.
        if _today_move_fn is not None:
            try:
                todays_move = round(_today_move_fn(sig, current_prices), 2)
            except Exception:
                todays_move = dl.get("todays_move") if dl.get("todays_move") else computed_spread_pnl
        else:
            todays_move = dl.get("todays_move") if dl.get("todays_move") else computed_spread_pnl
        # Peak = best (highest) cumulative since entry; clamped to 0 because a
        # position that's only ever been red has no positive peak to lock the
        # trail to. Old fallback to computed_spread_pnl displayed the live
        # negative P&L as "Peak", which is nonsense for a trailing-stop UI.
        peak = max(sig.get("peak_spread_pnl_pct") or 0.0, 0.0)

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


# Engine taxonomy — maps closed-signal sources to user-facing engine families.
# Each engine has a stable key (used by the UI for filtering + colour),
# a display label, a short theme tag (the trade thesis in 4-6 words), and
# a longer description that surfaces on hover so a layperson understands
# what the engine actually does.
_ENGINE_META = {
    "phase_c": {
        "key": "phase_c",
        "label": "Phase C — Z-Break",
        "theme": "Catch the laggard",
        "description": "Intraday correlation breaks. When a stock diverges >2σ from its sector peer it's traded back toward fair value (LAG continuation, OVERSHOOT fade). Mechanical 14:30 IST close.",
        "cadence": "intraday",
        "color": "#10b981",  # emerald
    },
    "spread_hormuz": {
        "key": "spread_hormuz",
        "label": "Sovereign Shield Alpha",
        "theme": "Defence > IT — geopolitics",
        "description": "Long Defence basket / Short IT services basket — fired by Strait of Hormuz / Israel–Iran headlines. Multi-day hold with trailing stop.",
        "cadence": "multi-day",
        "color": "#f59e0b",  # amber
    },
    "spread_sanctions": {
        "key": "spread_sanctions",
        "label": "Energy Chain Divergence",
        "theme": "Upstream > Downstream — sanctions",
        "description": "Long Upstream oil & gas / Short Downstream refiners — fired by sanctions / supply-side oil headlines. Multi-day hold.",
        "cadence": "multi-day",
        "color": "#ef4444",  # red
    },
    "spread_commodity": {
        "key": "spread_commodity",
        "label": "Fossil Arbitrage",
        "theme": "Coal/OMC chain — commodities",
        "description": "Pair trades along the fossil-fuel chain (Coal vs OMCs, Reliance vs OMCs) when commodity-price regimes shift.",
        "cadence": "multi-day",
        "color": "#8b5cf6",  # violet
    },
    "spread_other": {
        "key": "spread_other",
        "label": "Other Spreads",
        "theme": "Cross-sector arb",
        "description": "Other regime-gated cross-sector spread baskets (PSU Banks vs Private, IT vs Banks, etc.).",
        "cadence": "multi-day",
        "color": "#0ea5e9",  # sky
    },
    "sigma_break": {
        "key": "sigma_break",
        "label": "H-001 Sigma Break",
        "theme": "Mechanical mean-reversion",
        "description": "Pre-registered |z|≥2.0 mechanical break fade — single-touch holdout 2026-04-27 → 2026-05-26. Fade direction, ATR(14)×2 stop, 14:30 TIME_STOP.",
        "cadence": "intraday",
        "color": "#06b6d4",  # cyan
    },
    "secrsi": {
        "key": "secrsi",
        "label": "SECRSI Pair",
        "theme": "Sector RS pair, market-neutral",
        "description": "11:00 IST sector snapshot → long top-2 stocks of top-2 sectors / short bottom-2 of bottom-2 (8 legs). Holdout 2026-04-28 → 2026-07-31.",
        "cadence": "intraday",
        "color": "#14b8a6",  # teal
    },
    "ta_karpathy": {
        "key": "ta_karpathy",
        "label": "TA-Karpathy Lasso",
        "theme": "Per-stock TA, 09:15→15:25",
        "description": "Per-stock daily TA Lasso (top-10 NIFTY pilot). Frozen models, 5-gate qualifier. Holdout 2026-04-29 → 2026-05-28.",
        "cadence": "intraday",
        "color": "#a855f7",  # purple
    },
    "pattern_scanner": {
        "key": "pattern_scanner",
        "label": "Pattern Scanner",
        "theme": "Daily TA patterns, Top-10",
        "description": "Daily F&O 12-pattern scan. Top-10 patterns fire paired (futures + ATM options) shadow trades, mechanical 15:30 close.",
        "cadence": "intraday",
        "color": "#ec4899",  # pink
    },
    "other": {
        "key": "other",
        "label": "Other",
        "theme": "Uncategorised",
        "description": "Trades that pre-date the engine taxonomy.",
        "cadence": "—",
        "color": "#94a3b8",  # slate
    },
}


def _classify_engine(sig: dict) -> str:
    """Map a closed signal to its engine family key (see _ENGINE_META)."""
    sid = (sig.get("signal_id") or "").upper()
    cat = (sig.get("category") or "").lower()
    name = (sig.get("spread_name") or "")

    # Hypothesis-test ledgers (only present when those engines write into closed_signals.json).
    if sid.startswith("H-2026-04-26") or sid.startswith("H-2026-04-26-001") or sid.startswith("H-2026-04-26-002"):
        return "sigma_break"
    if sid.startswith("H-2026-04-27-003") or "SECRSI" in sid:
        return "secrsi"
    if sid.startswith("H-2026-04-29") or "KARPATHY" in sid:
        return "ta_karpathy"
    if sid.startswith("SCN-") or "PATTERN" in sid:
        return "pattern_scanner"

    # Phase C — single-ticker correlation breaks.
    if sid.startswith("BRK-") or cat == "phase_c":
        return "phase_c"

    # Spread baskets — bucket by category, fall back to spread_name keyword match.
    if cat == "hormuz" or "Defence vs IT" in name:
        return "spread_hormuz"
    if cat == "sanctions" or "Upstream" in name:
        return "spread_sanctions"
    if cat in ("oil_positive", "oil_negative") or "Coal" in name or "Reliance vs OMCs" in name:
        return "spread_commodity"
    if sid.startswith("SIG-"):
        return "spread_other"

    return "other"


def _compute_metrics(rows: list) -> dict:
    """Extended portfolio metrics across the full closed-trade list.

    rows is the list of dicts emitted by export_track_record (already
    has final_pnl_pct, days_open, close_date, etc.).
    """
    import math

    if not rows:
        return {
            "sharpe": None, "max_drawdown_pct": 0.0,
            "profit_factor": None, "expectancy_pct": 0.0,
            "avg_win_pct": 0.0, "avg_loss_pct": 0.0,
            "best_trade_pct": 0.0, "worst_trade_pct": 0.0,
            "best_day_pnl_pct": 0.0, "worst_day_pnl_pct": 0.0,
            "avg_hold_days": 0.0, "win_streak": 0, "loss_streak": 0,
            "best_engine": None, "worst_engine": None,
            "daily_pnl": [],
        }

    pnls = [r.get("final_pnl_pct", 0) or 0 for r in rows]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]

    # Annualised Sharpe — sample stdev across closed trades, scale by sqrt(252).
    # IMPORTANT: this is a per-trade Sharpe scaled to annual; it does NOT
    # represent a portfolio Sharpe (which would need a single equity curve).
    n = len(pnls)
    mean = sum(pnls) / n
    var = sum((p - mean) ** 2 for p in pnls) / max(n - 1, 1)
    std = math.sqrt(var)
    sharpe = (mean / std * math.sqrt(252)) if std > 0 else None

    # Profit factor = sum(wins) / |sum(losses)|.
    sum_wins = sum(wins)
    sum_losses = abs(sum(losses))
    profit_factor = (sum_wins / sum_losses) if sum_losses > 0 else (float("inf") if sum_wins > 0 else None)

    # Per-day stats — average P&L across trades closed that day, NOT the sum.
    # Summing 17 same-day trades at +3% each into "+51% best day" double-counts
    # because each trade was paper-traded as a standalone position, not 17×
    # leverage. The honest per-day metric is the mean.
    chrono = sorted(rows, key=lambda r: r.get("close_date", ""))
    by_day: dict = {}
    for r in rows:
        d = r.get("close_date") or ""
        if not d:
            continue
        by_day.setdefault(d, []).append(r.get("final_pnl_pct", 0) or 0)
    daily_avg = [
        {"date": d, "avg_pnl_pct": round(sum(v) / len(v), 2), "trades": len(v)}
        for d, v in sorted(by_day.items())
    ]
    best_day_avg = max((d["avg_pnl_pct"] for d in daily_avg), default=0.0)
    worst_day_avg = min((d["avg_pnl_pct"] for d in daily_avg), default=0.0)

    # Drawdown of per-trade-average curve. Track the running average as new
    # trades land; max drawdown is the largest fall from the running peak.
    cum = 0.0
    avg_curve = []
    for i, r in enumerate(chrono, start=1):
        cum += r.get("final_pnl_pct", 0) or 0
        avg_curve.append(cum / i)
    peak = 0.0
    max_dd = 0.0
    for v in avg_curve:
        if v > peak:
            peak = v
        dd = peak - v
        if dd > max_dd:
            max_dd = dd

    # Streaks (longest consecutive win / loss in chronological order).
    win_streak = loss_streak = 0
    cur_w = cur_l = 0
    for r in chrono:
        p = r.get("final_pnl_pct", 0) or 0
        if p > 0:
            cur_w += 1; cur_l = 0
        else:
            cur_l += 1; cur_w = 0
        win_streak = max(win_streak, cur_w)
        loss_streak = max(loss_streak, cur_l)

    return {
        "sharpe": round(sharpe, 2) if sharpe is not None else None,
        "max_drawdown_pct": round(max_dd, 2),  # of per-trade-average curve
        "profit_factor": round(profit_factor, 2) if profit_factor not in (None, float("inf")) else profit_factor,
        "expectancy_pct": round(mean, 2),
        "avg_win_pct": round(sum_wins / len(wins), 2) if wins else 0.0,
        "avg_loss_pct": round(sum(losses) / len(losses), 2) if losses else 0.0,
        "best_trade_pct": round(max(pnls), 2),
        "worst_trade_pct": round(min(pnls), 2),
        "best_day_avg_pct": round(best_day_avg, 2),
        "worst_day_avg_pct": round(worst_day_avg, 2),
        "sum_pnl_pct": round(sum(pnls), 2),  # raw sum, for "if sized 1 unit per trade" view
        "avg_hold_days": round(sum(r.get("days_open", 0) or 0 for r in rows) / n, 1),
        "win_streak": win_streak,
        "loss_streak": loss_streak,
        "daily_avg": daily_avg,
    }


def _build_engine_buckets(rows: list) -> list:
    """Aggregate closed trades into per-engine buckets with stats + sparkline."""
    buckets: dict = {}
    for r in rows:
        ek = r.get("engine_key") or "other"
        buckets.setdefault(ek, []).append(r)

    out = []
    for ek, items in buckets.items():
        meta = _ENGINE_META.get(ek, _ENGINE_META["other"])
        pnls = [it.get("final_pnl_pct", 0) or 0 for it in items]
        wins = sum(1 for p in pnls if p > 0)
        n = len(pnls)
        sum_pnl = sum(pnls)
        # Sparkline = chronological RUNNING AVERAGE of per-trade returns.
        # Plotting running sum overstates engine performance because each
        # trade is a standalone paper position, not portfolio-sized.
        chrono = sorted(items, key=lambda r: r.get("close_date", ""))
        cum = 0.0
        spark = []
        for i, it in enumerate(chrono, start=1):
            cum += it.get("final_pnl_pct", 0) or 0
            spark.append(round(cum / i, 2))
        out.append({
            "engine_key": ek,
            "label": meta["label"],
            "theme": meta["theme"],
            "description": meta["description"],
            "cadence": meta["cadence"],
            "color": meta["color"],
            "trades": n,
            "wins": wins,
            "losses": n - wins,
            "win_rate_pct": round(wins / n * 100, 1) if n else 0,
            "avg_pnl_pct": round(sum_pnl / n, 2) if n else 0,
            "sum_pnl_pct": round(sum_pnl, 2),
            "best_trade_pct": round(max(pnls), 2) if pnls else 0,
            "worst_trade_pct": round(min(pnls), 2) if pnls else 0,
            "sparkline": spark,
        })
    # Order: most-active engine first.
    out.sort(key=lambda b: (-b["trades"], -b["sum_pnl_pct"]))
    return out


def export_track_record(limit: int = 20) -> dict:
    """Export closed-signal track record with engine taxonomy + extended metrics.

    Returns:
        - total_closed / win_rate_pct / avg_pnl_pct — top-line KPIs.
        - metrics — extended portfolio metrics (sharpe, max_dd, profit_factor,
          expectancy, avg_win/loss, best/worst trade, best/worst day, streaks,
          daily_pnl[]).
        - by_engine — per-engine buckets (Phase C, spreads, hypothesis tests, …)
          with theme + colour + sparkline + per-engine stats.
        - trades — ALL closed trades, most-recent-first, enriched with engine_key.
        - recent — back-compat: most recent N (limit) for older callers.
    """
    closed_raw = _load_json(CLOSED_FILE) or []
    rows = []
    for sig in closed_raw:
        fp = sig.get("final_pnl", {}) or {}
        engine_key = _classify_engine(sig)
        meta = _ENGINE_META.get(engine_key, _ENGINE_META["other"])
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
            "engine_key": engine_key,
            "engine_label": meta["label"],
            "engine_color": meta["color"],
        })
    # Most recent first by close_date desc.
    rows.sort(key=lambda r: r["close_date"], reverse=True)

    # Aggregate stats over all closed (not just the shown N).
    all_final = [r["final_pnl_pct"] for r in rows]
    wins = sum(1 for p in all_final if p > 0)
    total = len(all_final)
    win_rate = (wins / total * 100) if total else 0
    avg_pnl = (sum(all_final) / total) if total else 0
    sum_pnl = sum(all_final) if total else 0

    metrics = _compute_metrics(rows)
    by_engine = _build_engine_buckets(rows)

    return {
        "updated_at": datetime.now(IST).isoformat(),
        "total_closed": total,
        "win_rate_pct": round(win_rate, 1),
        "avg_pnl_pct": round(avg_pnl, 2),
        "cum_pnl_pct": round(sum_pnl, 2),
        "metrics": metrics,
        "by_engine": by_engine,
        "trades": rows,
        "recent": rows[:limit],
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


def export_fno_news(source: Path | None = None, out: Path | None = None) -> int:
    """Derive data/fno_news.json from pipeline/data/news_verdicts.json.

    Filters to HIGH_IMPACT + MODERATE verdicts with ADD or CUT recommendations.
    Other rows (NO_ACTION, LOW impact) are dropped.

    Args:
        source: path to news_verdicts.json (defaults to NEWS_VERDICTS_FILE).
        out: path to fno_news.json (defaults to WEBSITE_DIR/fno_news.json).

    Returns: count of rows written.
    """
    source = source or NEWS_VERDICTS_FILE
    out = out or (WEBSITE_DIR / "fno_news.json")
    if not source.exists():
        return 0
    try:
        rows_in = json.loads(source.read_text(encoding="utf-8"))
    except Exception:
        return 0
    rows_out = []
    for v in rows_in:
        if v.get("impact") not in ("HIGH_IMPACT", "MODERATE"):
            continue
        if v.get("recommendation") not in ("ADD", "CUT"):
            continue
        rows_out.append({
            "ticker": v.get("symbol"),
            "category": v.get("category"),
            "direction": v.get("recommendation"),
            "impact": v.get("impact"),
            "title": v.get("event_title", ""),
            "hit_rate": v.get("historical_avg_5d"),
        })
    # Sort HIGH_IMPACT first, then |hit_rate| desc — strong CUT signals
    # (negative hit_rate) rank alongside strong ADDs.
    rows_out.sort(key=lambda r: (
        r.get("impact") != "HIGH_IMPACT",
        -abs(r.get("hit_rate") or 0),
    ))
    out.write_text(json.dumps(rows_out, indent=2, default=str, ensure_ascii=False),
                   encoding="utf-8")
    return len(rows_out)


def run_export():
    """Run full export to website JSON files."""
    WEBSITE_DIR.mkdir(parents=True, exist_ok=True)

    regime = export_global_regime()
    live = export_live_status()
    recs = export_today_recommendations()
    track = export_track_record()
    trust = export_trust_scores()
    fno_n = export_fno_news()

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
    print(f"  FnO news:       {fno_n} actionable verdicts (HIGH_IMPACT+MODERATE, ADD/CUT)")

    if os.environ.get("WEBSITE_AUTODEPLOY", "1") != "0":
        deploy_to_site()


DEPLOY_FILES = [
    "data/global_regime.json",
    # "data/live_status.json",          # WITHHELD 2026-04-26: strategy under re-validation, no public live positions until pre-registered rule + holdout-validated results ship
    # "data/today_recommendations.json",# WITHHELD 2026-04-26: contains active trade list (spreads/stocks/news_driven). H-2026-04-26-001 forward paper test runs locally only; nothing reaches the public site until 30-day holdout + Tier 1 null both clear.
    # "data/track_record.json",         # WITHHELD 2026-04-26: same reason — track record cleared on master, do not re-publish until new H-2026-04-26-001 forward test concludes
    "data/trust_scores.json",
    "data/gap_risk.json",
    "data/spread_stats.json",
    "data/articles_index.json",
    "data/fno_news.json",
]


def deploy_to_site():
    """Publish website data JSONs to origin/master via the shared deploy
    helper. Noop if nothing to publish.

    WHY: website_exporter writes data/*.json locally but GitHub Pages only
    serves committed state on `master`. Without this, the live site lags
    until the next manual push — and if the active dev branch isn't master
    (which it almost never is), a plain `git push` publishes to the dev
    branch, leaving the public site frozen indefinitely. The helper routes
    through a dedicated master worktree so dev state is never disturbed.
    """
    try:
        from pipeline import deploy_helper
    except ImportError:
        import deploy_helper
    ts = datetime.now(IST).strftime("%Y-%m-%d %H:%M IST")
    msg = f"data: auto-refresh website JSONs {ts}"
    try:
        result = deploy_helper.publish(DEPLOY_FILES, msg)
    except deploy_helper.DeployError as e:
        print(f"  [deploy] worktree setup failed (non-fatal): {e}")
        return
    if result["pushed"]:
        print(f"  [deploy] pushed to master: {msg}")
    else:
        print(f"  [deploy] not pushed: {result['reason']}")


if __name__ == "__main__":
    run_export()
