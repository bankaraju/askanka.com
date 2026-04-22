"""Intraday entry point — applies cached models to live features.

Reads ticker_feature_models.json, builds a live feature vector for each
GREEN/AMBER ticker, applies a sigmoid dot-product of features + interactions
against cached coefficients to produce a 0-100 attractiveness score.
"""
from __future__ import annotations
import json
import logging
import math
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from pipeline.feature_scorer import cohorts, features, storage
from pipeline.feature_scorer.model import _INTERACTIONS

log = logging.getLogger(__name__)

_PIPELINE_DIR = Path(__file__).parent.parent
_REPO_ROOT = _PIPELINE_DIR.parent
_DATA_DIR = _PIPELINE_DIR / "data"
_STOCK_HISTORICAL_DIR = _DATA_DIR / "fno_historical"
_INDEX_HISTORICAL_DIR = _DATA_DIR / "india_historical"


# --- Live data loaders ---

def _load_today_regime() -> dict:
    p = _DATA_DIR / "today_regime.json"
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"zone": "NEUTRAL"}


def _load_positioning() -> dict:
    p = _DATA_DIR / "positioning.json"
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}


def _load_trust_scores() -> dict:
    p = _REPO_ROOT / "data" / "trust_scores.json"
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        stocks = data.get("stocks", data) if isinstance(data, dict) else data
        if isinstance(stocks, list):
            return {(s.get("symbol") or "").upper(): s.get("sector_grade")
                    for s in stocks if s.get("symbol")}
        return stocks
    except FileNotFoundError:
        return {}


def _load_ticker_bars(ticker: str) -> pd.DataFrame | None:
    p = _STOCK_HISTORICAL_DIR / f"{ticker}.csv"
    return pd.read_csv(p) if p.exists() else None


def _load_sector_bars(cohort: str) -> pd.DataFrame | None:
    p = _INDEX_HISTORICAL_DIR / f"{cohort}_daily.csv"
    return pd.read_csv(p) if p.exists() else None


def _nifty_breadth_5d() -> float:
    """Percentage of NIFTY constituents with 5d positive returns. Fallback 0.5.

    v1: sector-index-derived proxy (NIFTY direction over 5 days).
    v2 can walk NIFTY's 50 constituents.
    """
    try:
        nifty_bars = _load_sector_bars("NIFTY")
        if nifty_bars is None or len(nifty_bars) < 6:
            return 0.5
        closes = nifty_bars["close"].tail(6).tolist()
        return 0.6 if closes[-1] > closes[0] else 0.4
    except Exception:
        return 0.5


def _build_live_features(ticker: str) -> dict[str, float] | None:
    bars = _load_ticker_bars(ticker)
    cohort = cohorts.ticker_to_cohort(ticker)
    sector_bars = _load_sector_bars(cohort if cohort != "MIDCAP_GENERIC" else "MIDCPNIFTY")
    if bars is None or sector_bars is None or len(bars) < 20 or len(sector_bars) < 20:
        return None
    as_of = str(bars["date"].iloc[-1])
    regime = _load_today_regime().get("zone") or "NEUTRAL"

    positioning = _load_positioning()
    pos = positioning.get(ticker) or {}
    dte = pos.get("days_to_expiry") or 10
    pcr_z = None  # placeholder — proper z requires 20d history; keep None → 0 fallback

    trust = _load_trust_scores().get(ticker.upper())
    breadth = _nifty_breadth_5d()

    return features.build_feature_vector(
        prices=bars, sector=sector_bars, as_of=as_of,
        regime=regime, dte=dte, trust_grade=trust,
        nifty_breadth_5d=breadth, pcr_z_score=pcr_z,
    )


def _apply_interactions(features_dict: dict[str, float]) -> dict[str, float]:
    out = dict(features_dict)
    for a, b in _INTERACTIONS:
        if a in features_dict and b in features_dict:
            out[f"{a}__x__{b}"] = features_dict[a] * features_dict[b]
    return out


def _score_from_coefficients(features_dict: dict[str, float],
                              coefs: dict[str, float]) -> tuple[int, list[dict]]:
    """Dot product + sigmoid → 0-100 score. Returns score + top-3 contributors."""
    enriched = _apply_interactions(features_dict)
    contributions: list[tuple[str, float]] = []
    logit = 0.0
    for name, coef in coefs.items():
        v = enriched.get(name, 0.0)
        # Features produced by build_feature_vector may be None for insufficient data
        if v is None:
            v = 0.0
        c = coef * v
        logit += c
        contributions.append((name, c))
    prob = 1.0 / (1.0 + math.exp(-logit))
    score = int(round(prob * 100))
    contributions.sort(key=lambda x: abs(x[1]), reverse=True)
    top = [{"name": n, "contribution": round(c, 3)} for n, c in contributions[:3]]
    return score, top


def main() -> int:
    models = storage.read_models().get("models", {})
    scores_out: dict[str, Any] = {}
    snapshots: list[dict] = []
    ts = datetime.now().isoformat()

    for ticker, meta in models.items():
        if meta.get("health") not in ("GREEN", "AMBER"):
            continue
        coefs = meta.get("coefficients") or {}
        if not coefs:
            continue
        live = _build_live_features(ticker)
        if not live:
            continue
        score, top = _score_from_coefficients(live, coefs)
        scores_out[ticker] = {
            "score": score,
            "band": meta["health"],
            "source": meta.get("source", "own"),
            "top_features": top,
            "computed_at": ts,
        }
        snapshots.append({
            "ts": ts, "ticker": ticker, "score": score,
            "band": meta["health"], "features": live,
        })

    storage.write_scores({"updated_at": ts, "scores": scores_out})
    if snapshots:
        storage.append_snapshots(snapshots)
    log.info("scored %d tickers", len(scores_out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
