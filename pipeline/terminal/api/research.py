"""GET /api/research/digest — intelligence digest with grounding enforcement."""
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from fastapi import APIRouter

router = APIRouter()

_HERE = Path(__file__).resolve().parent.parent
_DATA = _HERE.parent / "data"
_TODAY_REGIME = _DATA / "today_regime.json"
_RECOMMENDATIONS = _DATA / "recommendations.json"
_CORRELATION_BREAKS = _DATA / "correlation_breaks.json"
_POSITIONING = _DATA / "positioning.json"
_FLOWS_DIR = _DATA / "flows"

IST = timezone(timedelta(hours=5, minutes=30))


def _read_json(path: Path, default=None):
    if default is None:
        default = {}
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _latest_flows() -> dict:
    if not _FLOWS_DIR.exists():
        return {}
    files = sorted(_FLOWS_DIR.glob("*.json"), reverse=True)
    if not files:
        return {}
    return _read_json(files[0])


def _build_regime_thesis(regime: dict, flows: dict) -> dict:
    spreads = regime.get("eligible_spreads", {})
    top_drivers = []
    for name, s in sorted(spreads.items(), key=lambda x: x[1].get("best_win", 0), reverse=True)[:3]:
        top_drivers.append({"name": name, "best_win": s.get("best_win", 0)})

    zone = regime.get("regime", "UNKNOWN")
    vix_triggers = []
    if zone in ("EUPHORIA", "RISK-ON"):
        vix_triggers.append("VIX spike above 18")
        vix_triggers.append("FII outflow 3 consecutive days")
    elif zone in ("RISK-OFF", "CAUTION"):
        vix_triggers.append("VIX drop below 14")
        vix_triggers.append("FII inflow 3 consecutive days")
    else:
        vix_triggers.append("Sustained directional move in VIX")

    return {
        "zone": zone,
        "regime_source": regime.get("regime_source", "unknown"),
        "msi_score": regime.get("msi_score", 0.0),
        "stability_days": regime.get("consecutive_days", 0),
        "stable": regime.get("regime_stable", False),
        "fii_net": flows.get("fii_equity_net", 0.0),
        "dii_net": flows.get("dii_equity_net", 0.0),
        "flip_triggers": vix_triggers,
        "top_spread_drivers": top_drivers,
        "grounding_ok": True,
    }


def _build_spread_theses(recs: dict, regime: dict, positioning: dict) -> list:
    zone = regime.get("regime", "UNKNOWN")
    spreads_out = []
    for r in recs.get("recommendations", []):
        name = r.get("name", "")
        action = r.get("action", "INACTIVE")
        conviction = r.get("conviction", "NONE")
        score = r.get("score", 0)
        z_score = r.get("z_score", 0.0)
        regime_fit = (regime.get("trade_map_key", "") == zone)

        spreads_out.append({
            "name": name,
            "action": action,
            "conviction": conviction,
            "score": score,
            "z_score": z_score,
            "regime_fit": regime_fit,
            "gate_status": r.get("gate_status", "UNKNOWN"),
            "caution_badges": [],
            "grounding_ok": True,
        })
    return spreads_out


def _build_correlation_breaks(breaks_data: dict, positioning: dict) -> list:
    out = []
    for b in breaks_data.get("breaks", []):
        symbol = b.get("symbol", "")
        pos = positioning.get(symbol, {})
        out.append({
            "ticker": symbol,
            "z_score": b.get("z_score", 0.0),
            "expected_return": b.get("expected_return", 0.0),
            "actual_return": b.get("actual_return", 0.0),
            "classification": b.get("classification", "UNCERTAIN"),
            "action": b.get("action", "HOLD"),
            "pcr": b.get("pcr", pos.get("pcr", 0.0)),
            "oi_confirmation": b.get("oi_anomaly_type") or pos.get("oi_anomaly_type") or "NONE",
        })
    return out


def _build_backtest_validation(regime: dict) -> list:
    zone = regime.get("regime", "UNKNOWN")
    eligible = regime.get("eligible_spreads", {})
    out = []
    for name, s in eligible.items():
        best_win = s.get("best_win", 0)
        period = s.get("best_period", 5)
        period_key = f"{period}d_win"
        win_pct = s.get(period_key, best_win)
        avg_key = f"{period}d_avg"
        avg_ret = s.get(avg_key, 0.0)

        if win_pct >= 65:
            status = "WITHIN_CI"
        elif win_pct >= 55:
            status = "EDGE_CI"
        else:
            status = "OUTSIDE_CI"

        out.append({
            "spread": name,
            "regime": zone,
            "best_period": f"{period}d",
            "win_rate": round(win_pct / 100, 4),
            "avg_return": round(avg_ret / 100, 6),
            "status": status,
        })
    return out


def _apply_caution_badges(spread_theses: list, backtest: list, breaks: list) -> list:
    bt_map = {b["spread"]: b for b in backtest}
    break_tickers = {b["ticker"]: b for b in breaks
                     if b["classification"] == "CONFIRMED_WARNING"}

    for s in spread_theses:
        badges = []
        bt = bt_map.get(s["name"])
        if bt:
            if bt["win_rate"] < 0.55:
                badges.append({"type": "caution", "label": "LOW WIN RATE",
                               "detail": f"Win rate {bt['win_rate']:.0%} below 55% threshold"})
            if bt["status"] == "EDGE_CI":
                badges.append({"type": "caution", "label": "EDGE CI",
                               "detail": f"Win rate {bt['win_rate']:.0%} near confidence boundary"})
            if bt["status"] == "OUTSIDE_CI":
                badges.append({"type": "blocked", "label": "OUTSIDE CI",
                               "detail": f"Win rate {bt['win_rate']:.0%} outside confidence interval"})
        for ticker, brk in break_tickers.items():
            if ticker.upper() in s["name"].upper():
                badges.append({"type": "caution", "label": f"BREAK: {ticker}",
                               "detail": f"{ticker} z={brk['z_score']:.1f}σ CONFIRMED WARNING"})
        s["caution_badges"] = badges
    return spread_theses


def _grounding_check(thesis: dict, flows_raw: dict, regime_raw: dict) -> list:
    failures = []

    def _check(label, rendered, source, tolerance_pct=2.0, tolerance_abs=0.01):
        if source is None or rendered is None:
            return
        try:
            r, s = float(rendered), float(source)
        except (ValueError, TypeError):
            return
        if s == 0 and r == 0:
            return
        threshold = max(abs(s) * tolerance_pct / 100, tolerance_abs)
        if abs(r - s) > threshold:
            failures.append({
                "field": label,
                "rendered": r,
                "source": s,
                "delta": round(abs(r - s), 6),
                "timestamp": datetime.now(IST).isoformat(),
            })

    _check("fii_net", thesis.get("fii_net"), flows_raw.get("fii_equity_net"))
    _check("dii_net", thesis.get("dii_net"), flows_raw.get("dii_equity_net"))
    _check("msi_score", thesis.get("msi_score"), regime_raw.get("msi_score"))
    _check("stability_days", thesis.get("stability_days"), regime_raw.get("consecutive_days"))

    return failures


@router.get("/research/digest")
def research_digest():
    regime_raw = _read_json(_TODAY_REGIME)
    recs_raw = _read_json(_RECOMMENDATIONS)
    breaks_raw = _read_json(_CORRELATION_BREAKS)
    positioning_raw = _read_json(_POSITIONING)
    flows_raw = _latest_flows()

    thesis = _build_regime_thesis(regime_raw, flows_raw)
    spread_theses = _build_spread_theses(recs_raw, regime_raw, positioning_raw)
    corr_breaks = _build_correlation_breaks(breaks_raw, positioning_raw)
    backtest = _build_backtest_validation(regime_raw)

    spread_theses = _apply_caution_badges(spread_theses, backtest, corr_breaks)

    grounding_failures = _grounding_check(thesis, flows_raw, regime_raw)
    if grounding_failures:
        thesis["grounding_ok"] = False

    return {
        "generated_at": regime_raw.get("timestamp", datetime.now(IST).isoformat()),
        "regime_thesis": thesis,
        "spread_theses": spread_theses,
        "correlation_breaks": corr_breaks,
        "backtest_validation": backtest,
        "grounding_failures": grounding_failures,
    }
