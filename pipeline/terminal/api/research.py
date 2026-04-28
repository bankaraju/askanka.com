"""GET /api/research/digest — intelligence digest with grounding enforcement."""
import csv
import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from fastapi import APIRouter

log = logging.getLogger(__name__)

router = APIRouter()

_HERE = Path(__file__).resolve().parent.parent
_DATA = _HERE.parent / "data"

# Phase C paired-shadow ledger paths (spec §11.3)
_PHASE_C_OPTIONS_LEDGER = _HERE.parent / "data" / "research" / "phase_c" / "live_paper_options_ledger.json"
_PHASE_C_FUTURES_LEDGER = _HERE.parent / "data" / "research" / "phase_c" / "live_paper_ledger.json"
_TODAY_REGIME = _DATA / "today_regime.json"
_RECOMMENDATIONS = _DATA / "recommendations.json"
_CORRELATION_BREAKS = _DATA / "correlation_breaks.json"
_POSITIONING = _DATA / "positioning.json"
_FLOWS_DIR = _DATA / "flows"
_REGIME_PROFILE = _HERE.parent / "autoresearch" / "reverse_regime_profile.json"
_OPEN_SIGNALS = _DATA / "signals" / "open_signals.json"
_OPTIONS_SHADOW = _DATA / "signals" / "synthetic_options_shadow.json"

# Karpathy v1 holdout ledger (spec H-2026-04-29-ta-karpathy-v1)
_KARP_DIR = _HERE.parent / "data" / "research" / "h_2026_04_29_ta_karpathy_v1"
_KARP_LEDGER = _KARP_DIR / "recommendations.csv"
_KARP_TEST_LEDGER = _KARP_DIR / "recommendations_test.csv"
_KARP_PREDICTIONS = _KARP_DIR / "today_predictions.json"
_KARP_HOLDOUT_START = "2026-04-29"
_KARP_HOLDOUT_END = "2026-05-28"

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


def _build_leverage_matrices(spread_theses: list, positioning: dict) -> list:
    try:
        from pipeline.synthetic_options import build_leverage_matrix
    except ImportError:
        return []

    profiles = _read_json(_REGIME_PROFILE)
    signals = _read_json(_OPEN_SIGNALS, default=[])
    if not isinstance(signals, list):
        signals = []

    matrices = []
    for s in spread_theses:
        if s.get("score", 0) < 65:
            continue
        matching_signal = next(
            (sig for sig in signals if sig.get("spread_name") == s["name"] and sig.get("status") == "OPEN"),
            None,
        )
        if not matching_signal:
            matching_signal = {
                "signal_id": f"DIGEST-{s['name'].replace(' ', '_')}",
                "spread_name": s["name"],
                "conviction": s.get("score", 0),
                "long_legs": [],
                "short_legs": [],
            }
        try:
            matrix = build_leverage_matrix(matching_signal, profiles, oi_data=positioning)
            matrices.append(matrix)
        except Exception as exc:
            log.warning("Leverage matrix failed for %s: %s", s["name"], exc)
    return matrices


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

    leverage_matrices = _build_leverage_matrices(spread_theses, positioning_raw)

    return {
        "generated_at": regime_raw.get("timestamp", datetime.now(IST).isoformat()),
        "regime_thesis": thesis,
        "spread_theses": spread_theses,
        "correlation_breaks": corr_breaks,
        "backtest_validation": backtest,
        "grounding_failures": grounding_failures,
        "leverage_matrices": leverage_matrices,
    }


@router.get("/research/options-shadow")
def options_shadow():
    data = _read_json(_OPTIONS_SHADOW, default=[])
    if not isinstance(data, list):
        data = []
    return data


# ---------------------------------------------------------------------------
# Phase C paired-shadow endpoint (spec §11.3)
# ---------------------------------------------------------------------------

def _zero_expiry_bucket() -> dict:
    return {"n": 0, "win_rate": 0.0, "mean_options_pnl_pct": 0.0}


def _build_futures_signal_id_set(futures_rows: list) -> set:
    """Derive signal_ids from futures ledger rows using build_signal_id helper."""
    try:
        from pipeline.phase_c_options_shadow import build_signal_id
    except ImportError:
        return set()
    ids = set()
    for row in futures_rows:
        ids.add(build_signal_id(row))
    return ids


def _project_open_pair(row: dict) -> dict:
    """Project an OPEN options ledger row to the endpoint's open_pairs schema."""
    return {
        "signal_id": row.get("signal_id", ""),
        "symbol": row.get("symbol", ""),
        "side": row.get("side", ""),
        "option_type": row.get("option_type", ""),
        "tradingsymbol": row.get("tradingsymbol", ""),
        "strike": row.get("strike"),
        "expiry_date": row.get("expiry_date", ""),
        "is_expiry_day": row.get("is_expiry_day", False),
        "drift_vs_rent_tier": row.get("drift_vs_rent_tier", "UNKNOWN"),
        "futures_pnl_pct": None,
        "options_pnl_pct": None,
        "entry_mid": row.get("entry_mid"),
        "entry_iv": row.get("entry_iv"),
        "entry_delta": row.get("entry_delta"),
    }


@router.get("/research/phase-c-options-shadow")
def phase_c_options_shadow():
    """Live OPEN paired-shadow rows + cumulative tier/expiry breakdown. Spec §11.3."""
    opts_rows = _read_json(_PHASE_C_OPTIONS_LEDGER, default=[])
    if not isinstance(opts_rows, list):
        opts_rows = []

    futs_rows = _read_json(_PHASE_C_FUTURES_LEDGER, default=[])
    if not isinstance(futs_rows, list):
        futs_rows = []

    # Open pairs: OPEN status only, no live mark-to-market
    open_pairs = [_project_open_pair(r) for r in opts_rows if r.get("status") == "OPEN"]

    # Cumulative: CLOSED status only (SKIPPED_LIQUIDITY and others excluded)
    closed = [r for r in opts_rows if r.get("status") == "CLOSED"]

    # Unmatched: CLOSED options rows with no matching CLOSED futures row
    futures_sig_ids = _build_futures_signal_id_set(
        [r for r in futs_rows if r.get("status") == "CLOSED"]
    )
    n_unmatched = sum(1 for r in closed if r.get("signal_id", "") not in futures_sig_ids)

    # by_tier aggregation
    by_tier: dict = {}
    for r in closed:
        tier = r.get("drift_vs_rent_tier", "UNKNOWN") or "UNKNOWN"
        pnl = r.get("pnl_net_pct", 0.0) or 0.0
        win = 1 if pnl > 0 else 0
        if tier not in by_tier:
            by_tier[tier] = {"n": 0, "wins": 0, "pnl_sum": 0.0}
        by_tier[tier]["n"] += 1
        by_tier[tier]["wins"] += win
        by_tier[tier]["pnl_sum"] += pnl

    by_tier_out = {}
    for tier, agg in by_tier.items():
        n = agg["n"]
        by_tier_out[tier] = {
            "n": n,
            "win_rate": round(agg["wins"] / n, 4) if n else 0.0,
            "mean_options_pnl_pct": round(agg["pnl_sum"] / n, 6) if n else 0.0,
        }

    # by_expiry_day aggregation (string keys "true"/"false")
    expiry_agg: dict = {
        "true": {"n": 0, "wins": 0, "pnl_sum": 0.0},
        "false": {"n": 0, "wins": 0, "pnl_sum": 0.0},
    }
    for r in closed:
        key = "true" if r.get("is_expiry_day") else "false"
        pnl = r.get("pnl_net_pct", 0.0) or 0.0
        expiry_agg[key]["n"] += 1
        expiry_agg[key]["wins"] += (1 if pnl > 0 else 0)
        expiry_agg[key]["pnl_sum"] += pnl

    by_expiry_day = {}
    for key, agg in expiry_agg.items():
        n = agg["n"]
        by_expiry_day[key] = {
            "n": n,
            "win_rate": round(agg["wins"] / n, 4) if n else 0.0,
            "mean_options_pnl_pct": round(agg["pnl_sum"] / n, 6) if n else 0.0,
        }

    return {
        "open_pairs": open_pairs,
        "cumulative": {
            "n_closed": len(closed),
            "n_unmatched": n_unmatched,
            "by_tier": by_tier_out,
            "by_expiry_day": by_expiry_day,
        },
    }


# ---------------------------------------------------------------------------
# Karpathy v1 holdout endpoint (spec H-2026-04-29-ta-karpathy-v1)
# ---------------------------------------------------------------------------

def _read_karp_csv(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    try:
        with path.open("r", encoding="utf-8", newline="") as f:
            return list(csv.DictReader(f))
    except OSError:
        return []


def _coerce_float(v):
    if v in (None, ""):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _project_karp_row(r: dict, *, is_test: bool) -> dict:
    return {
        "signal_id": r.get("signal_id", ""),
        "ticker": r.get("ticker", ""),
        "date": r.get("date", ""),
        "direction": r.get("direction", ""),
        "side": r.get("side", ""),
        "regime": r.get("regime", ""),
        "p_long": _coerce_float(r.get("p_long")),
        "p_short": _coerce_float(r.get("p_short")),
        "entry_time": r.get("entry_time", ""),
        "entry_px": _coerce_float(r.get("entry_px")),
        "atr_14": _coerce_float(r.get("atr_14")),
        "stop_px": _coerce_float(r.get("stop_px")),
        "exit_time": r.get("exit_time", ""),
        "exit_px": _coerce_float(r.get("exit_px")),
        "exit_reason": r.get("exit_reason", ""),
        "pnl_pct": _coerce_float(r.get("pnl_pct")),
        "status": r.get("status", ""),
        "is_test": is_test,
    }


def _karp_summary(rows: list[dict]) -> dict:
    closed = [r for r in rows if r["status"] == "CLOSED" and r["pnl_pct"] is not None]
    n_closed = len(closed)
    n_open = sum(1 for r in rows if r["status"] == "OPEN")
    n_test = sum(1 for r in rows if r["is_test"])
    if n_closed:
        wins = sum(1 for r in closed if r["pnl_pct"] > 0)
        avg = sum(r["pnl_pct"] for r in closed) / n_closed
        win_rate = wins / n_closed * 100.0
    else:
        wins = 0
        avg = None
        win_rate = None
    return {
        "n_open": n_open,
        "n_closed": n_closed,
        "n_test": n_test,
        "wins": wins,
        "win_rate_pct": round(win_rate, 2) if win_rate is not None else None,
        "avg_pnl_pct": round(avg, 4) if avg is not None else None,
    }


@router.get("/research/karpathy-v1")
def karpathy_v1():
    """Per-stock TA Lasso (top-10 NIFTY pilot) holdout ledger.

    Spec: docs/superpowers/specs/2026-04-29-ta-karpathy-v1-design.md
    Holdout: 2026-04-29 -> 2026-05-28 (single-touch).
    """
    real = [_project_karp_row(r, is_test=False)
            for r in _read_karp_csv(_KARP_LEDGER)]
    test = [_project_karp_row(r, is_test=True)
            for r in _read_karp_csv(_KARP_TEST_LEDGER)]

    rows = real + test
    rows.sort(key=lambda r: (r["date"] or "", r["ticker"] or "", r["direction"] or ""))

    today_iso = datetime.now(IST).date().isoformat()
    in_holdout = _KARP_HOLDOUT_START <= today_iso <= _KARP_HOLDOUT_END

    n_predictions = None
    if _KARP_PREDICTIONS.is_file():
        try:
            doc = json.loads(_KARP_PREDICTIONS.read_text(encoding="utf-8"))
            preds = doc.get("predictions", []) or []
            n_predictions = len(preds)
        except (OSError, json.JSONDecodeError):
            n_predictions = None

    return {
        "engine_label": "ta_karpathy_v1",
        "spec_id": "H-2026-04-29-ta-karpathy-v1",
        "holdout_window": [_KARP_HOLDOUT_START, _KARP_HOLDOUT_END],
        "in_holdout": in_holdout,
        "today_iso": today_iso,
        "n_predictions": n_predictions,
        "rows": rows,
        "summary": _karp_summary(rows),
    }
