"""Intraday entry point — applies cached models to live features.

Reads ticker_feature_models.json, builds a live feature vector for each
GREEN/AMBER ticker, applies a sigmoid dot-product of features + interactions
against cached coefficients to produce a 0-100 attractiveness score.
"""
from __future__ import annotations
import logging
import math
from datetime import datetime
from typing import Any

from pipeline.feature_scorer import storage
from pipeline.feature_scorer.model import _INTERACTIONS

log = logging.getLogger(__name__)


def _build_live_features(ticker: str) -> dict[str, float] | None:
    """Compose a live feature vector for `ticker`. Returns None if essential data missing.

    v1: placeholder that returns None — wired up properly in Task 11 when
    we integrate with the live ETF/sector/regime/positioning data flows.
    """
    return None


def _apply_interactions(features: dict[str, float]) -> dict[str, float]:
    out = dict(features)
    for a, b in _INTERACTIONS:
        if a in features and b in features:
            out[f"{a}__x__{b}"] = features[a] * features[b]
    return out


def _score_from_coefficients(features: dict[str, float],
                              coefs: dict[str, float]) -> tuple[int, list[dict]]:
    """Dot product + sigmoid → 0-100 score. Returns score + top-3 contributors."""
    enriched = _apply_interactions(features)
    contributions: list[tuple[str, float]] = []
    logit = 0.0
    for name, coef in coefs.items():
        v = enriched.get(name, 0.0)
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
