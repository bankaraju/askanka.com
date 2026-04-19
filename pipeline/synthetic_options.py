"""Synthetic options orchestrator — builds leverage matrix from vol + pricer + regime data."""
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pipeline import vol_engine
from pipeline import options_pricer

log = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))

TIERS = [
    {"horizon": "1_month", "days": 30, "experimental": False},
    {"horizon": "15_day", "days": 15, "experimental": False},
    {"horizon": "same_day", "days": 1, "experimental": True},
]

_DATA = Path(__file__).resolve().parent / "data"
_SHADOW_PATH = _DATA / "signals" / "synthetic_options_shadow.json"
_BACKTEST_RESULTS = _DATA / "vol_backtest_results.json"


def _load_vol_scalar() -> float:
    if not _BACKTEST_RESULTS.exists():
        return 1.0
    try:
        data = json.loads(_BACKTEST_RESULTS.read_text(encoding="utf-8"))
        return data.get("aggregate", {}).get("vol_scalar", 1.0)
    except Exception:
        return 1.0


def classify_tier(net_edge: float, tier_name: str) -> str:
    if net_edge <= 0:
        return "NEGATIVE CARRY"
    if tier_name == "same_day":
        return "EXPERIMENTAL"
    return "HIGH-ALPHA SYNTHETIC"


def build_caution_badges(tiers: list[dict], oi_data: dict | None) -> list[str]:
    badges = []
    has_negative_non_experimental = any(
        t["net_edge_pct"] <= 0 and not t.get("experimental", False)
        for t in tiers
    )
    if has_negative_non_experimental:
        badges.append("NEGATIVE_CARRY")

    has_sameday = any(t.get("experimental", False) for t in tiers)
    has_oi_anomaly = bool(oi_data and any(
        v.get("oi_anomaly_type") not in (None, "NONE", "")
        for v in oi_data.values()
    ))
    if has_sameday and not has_oi_anomaly:
        badges.append("LOW_CONVICTION_GAMMA")

    month_tier = next((t for t in tiers if t["horizon"] == "1_month"), None)
    if month_tier and month_tier["net_edge_pct"] > 1.5:
        badges.append("DRIFT_EXCEEDS_RENT")

    return badges


def _weighted_vol(legs: list[dict], vol_fn, scalar: float = 1.0) -> float | None:
    vols = []
    weights = []
    for leg in legs:
        v = vol_fn(leg["ticker"])
        if v is None:
            return None
        vols.append(v * scalar)
        weights.append(leg.get("weight", 1.0))
    total_w = sum(weights)
    if total_w == 0:
        return None
    return sum(v * w for v, w in zip(vols, weights)) / total_w


def _avg_drift(legs: list[dict], profiles: dict) -> float:
    drifts = []
    for leg in legs:
        stock = profiles.get("stock_profiles", {}).get(leg["ticker"], {})
        drift = stock.get("summary", {}).get("avg_drift_5d", 0.0)
        drifts.append(abs(drift))
    return sum(drifts) / len(drifts) if drifts else 0.0


def build_leverage_matrix(signal: dict, regime_profiles: dict, oi_data: dict | None = None) -> dict:
    long_legs = signal.get("long_legs", [])
    short_legs = signal.get("short_legs", [])

    vol_scalar = _load_vol_scalar()

    long_vol = _weighted_vol(long_legs, vol_engine.get_stock_vol, scalar=vol_scalar)
    short_vol = _weighted_vol(short_legs, vol_engine.get_stock_vol, scalar=vol_scalar)

    if long_vol is None or short_vol is None:
        missing = []
        for leg in long_legs + short_legs:
            if vol_engine.get_stock_vol(leg["ticker"]) is None:
                missing.append(leg["ticker"])
        return {
            "signal_id": signal.get("signal_id", ""),
            "spread_name": signal.get("spread_name", ""),
            "conviction_score": signal.get("conviction", 0),
            "grounding_ok": False,
            "reason": f"vol unavailable for {', '.join(missing)}",
            "tiers": [],
            "caution_badges": [],
            "long_side_vol": None,
            "short_side_vol": None,
            "vol_scalar_applied": 1.0,
        }

    avg_vol = (long_vol + short_vol) / 2.0
    long_drift = _avg_drift(long_legs, regime_profiles)
    short_drift = _avg_drift(short_legs, regime_profiles)
    expected_drift_pct = (long_drift + short_drift) * 100.0

    long_spot = sum(l.get("price", 0) * l.get("weight", 1) for l in long_legs)
    short_spot = sum(s.get("price", 0) * s.get("weight", 1) for s in short_legs)
    avg_spot = (long_spot + short_spot) / 2.0 if (long_spot + short_spot) > 0 else 100.0

    tiers = []
    for t in TIERS:
        rent = options_pricer.five_day_rent(avg_spot, avg_vol, t["days"])
        net_edge = expected_drift_pct - rent["total_rent_pct"]
        tiers.append({
            "horizon": t["horizon"],
            "days_to_expiry": t["days"],
            "premium_cost_pct": round(rent["premium_pct"], 3),
            "five_day_theta_pct": round(rent["theta_decay_5d_pct"], 3),
            "friction_pct": round(rent["friction_pct"], 3),
            "total_rent_pct": round(rent["total_rent_pct"], 3),
            "expected_drift_pct": round(expected_drift_pct, 3),
            "net_edge_pct": round(net_edge, 3),
            "classification": classify_tier(net_edge, t["horizon"]),
            "experimental": t["experimental"],
        })

    badges = build_caution_badges(tiers, oi_data)

    return {
        "signal_id": signal.get("signal_id", ""),
        "spread_name": signal.get("spread_name", ""),
        "conviction_score": signal.get("conviction", 0),
        "grounding_ok": True,
        "tiers": tiers,
        "caution_badges": badges,
        "long_side_vol": round(long_vol, 4),
        "short_side_vol": round(short_vol, 4),
        "vol_scalar_applied": round(vol_scalar, 4),
    }


def record_shadow_entry(signal: dict, matrix: dict, regime: str) -> dict | None:
    if not matrix.get("grounding_ok"):
        return None

    positive_tiers = [
        t for t in matrix.get("tiers", [])
        if t["net_edge_pct"] > 0 and not t.get("experimental", False)
    ]
    if not positive_tiers:
        return None

    existing = []
    _SHADOW_PATH.parent.mkdir(parents=True, exist_ok=True)
    if _SHADOW_PATH.exists():
        try:
            existing = json.loads(_SHADOW_PATH.read_text(encoding="utf-8"))
        except Exception:
            existing = []

    count = sum(1 for e in existing if e.get("signal_id") == signal.get("signal_id", "")) + 1
    shadow_id = f"OPT-{datetime.now(IST).strftime('%Y-%m-%d')}-{count:03d}-{signal.get('spread_name', '').replace(' ', '_')}"

    long_legs = signal.get("long_legs", [])
    short_legs = signal.get("short_legs", [])
    entry_spot_long = sum(l.get("price", 0) * l.get("weight", 1) for l in long_legs)
    entry_spot_short = sum(s.get("price", 0) * s.get("weight", 1) for s in short_legs)

    entry = {
        "shadow_id": shadow_id,
        "signal_id": signal.get("signal_id", ""),
        "entry_timestamp": datetime.now(IST).isoformat(),
        "spread_name": signal.get("spread_name", ""),
        "regime_at_entry": regime,
        "conviction_score": signal.get("conviction", 0),
        "long_legs": long_legs,
        "short_legs": short_legs,
        "entry_spot_long": entry_spot_long,
        "entry_spot_short": entry_spot_short,
        "long_side_vol": matrix.get("long_side_vol"),
        "short_side_vol": matrix.get("short_side_vol"),
        "tiers_at_entry": [
            {
                "horizon": t["horizon"],
                "premium_cost_pct": t["premium_cost_pct"],
                "total_rent_pct": t["total_rent_pct"],
                "expected_drift_pct": t["expected_drift_pct"],
                "net_edge_pct": t["net_edge_pct"],
            }
            for t in matrix.get("tiers", [])
            if not t.get("experimental", False)
        ],
        "daily_marks": [{
            "date": datetime.now(IST).strftime("%Y-%m-%d"),
            "day": 0,
            "long_price": entry_spot_long,
            "short_price": entry_spot_short,
            "spread_move_pct": 0.0,
            "repriced_1m_pnl_pct": 0.0,
            "repriced_15d_pnl_pct": 0.0,
            "cumulative_theta_1m": 0.0,
            "cumulative_theta_15d": 0.0,
        }],
        "status": "OPEN",
        "exit_reason": None,
        "final_pnl_futures_pct": None,
        "final_pnl_1m_options_pct": None,
        "final_pnl_15d_options_pct": None,
    }

    existing.append(entry)
    _SHADOW_PATH.write_text(json.dumps(existing, indent=2, default=str), encoding="utf-8")
    return entry
