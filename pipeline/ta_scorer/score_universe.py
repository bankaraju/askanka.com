"""Daily 16:00 IST — apply cached TA models across the F&O universe."""
from __future__ import annotations
import logging
import math
import os
from datetime import datetime
from pathlib import Path
import pandas as pd

from pipeline.ta_scorer import features, model, storage

log = logging.getLogger(__name__)

_PIPELINE_DIR = Path(__file__).resolve().parent.parent
_STOCK_HISTORICAL_DIR = _PIPELINE_DIR / "data" / "fno_historical"
_INDEX_HISTORICAL_DIR = _PIPELINE_DIR / "data" / "india_historical" / "indices"
_MODELS_IN = _PIPELINE_DIR / "data" / "ta_feature_models.json"
_SCORES_OUT = _PIPELINE_DIR / "data" / "ta_attractiveness_scores.json"

_INTERCEPT_KEY = "__intercept__"


def _band(score: int) -> str:
    if score >= 80: return "VERY_HIGH"
    if score >= 60: return "HIGH"
    if score >= 40: return "MEDIUM"
    return "LOW"


def _load_csv(path: Path) -> pd.DataFrame | None:
    if not path.exists():
        return None
    df = pd.read_csv(path)
    df.columns = [c.lower() for c in df.columns]
    return df


def _score_one(coefs: dict, enriched: dict) -> tuple[int, list[dict]]:
    logit = float(coefs.get(_INTERCEPT_KEY, 0.0))
    contribs: list[tuple[str, float]] = []
    for name, coef in coefs.items():
        if name == _INTERCEPT_KEY:
            continue
        v = float(enriched.get(name, 0.0) or 0.0)
        c = coef * v
        logit += c
        contribs.append((name, c))
    prob = 1.0 / (1.0 + math.exp(-logit))
    contribs.sort(key=lambda x: abs(x[1]), reverse=True)
    top = [{"name": n, "contribution": round(c, 3),
            "sign": "+" if c >= 0 else "-",
            "magnitude": round(abs(c) * 100, 1)}
           for n, c in contribs[:3]]
    return int(round(prob * 100)), top


def _empty_entry(ticker: str, meta: dict, ts: str) -> dict:
    return {
        "ticker": ticker, "score": None, "band": "UNAVAILABLE",
        "health": meta.get("health", "UNAVAILABLE"),
        "source": "own", "top_features": [], "computed_at": ts,
    }


def main() -> int:
    models = storage.read_models(path=_MODELS_IN).get("models", {})
    nifty = _load_csv(_INDEX_HISTORICAL_DIR / "NIFTY_daily.csv")
    ts = datetime.now().isoformat()
    scores: dict[str, dict] = {}
    counts = {"scored": 0, "unavailable": 0}
    for ticker, meta in models.items():
        if meta.get("health") not in ("GREEN", "AMBER"):
            scores[ticker] = _empty_entry(ticker, meta, ts)
            counts["unavailable"] += 1
            continue
        coefs = meta.get("coefficients") or {}
        if not coefs:
            scores[ticker] = _empty_entry(ticker, meta, ts)
            counts["unavailable"] += 1
            continue
        prices = _load_csv(_STOCK_HISTORICAL_DIR / f"{ticker}.csv")
        if prices is None or nifty is None:
            scores[ticker] = _empty_entry(ticker, meta, ts)
            counts["unavailable"] += 1
            continue
        try:
            as_of = str(prices["date"].iloc[-1])
            vec = features.build_feature_vector(
                prices=prices, sector=nifty, nifty=nifty,
                as_of=as_of, regime="NEUTRAL", sector_breadth=0.5,
            )
            if not vec:
                scores[ticker] = _empty_entry(ticker, meta, ts)
                counts["unavailable"] += 1
                continue
            enriched = model.build_interaction_columns(pd.DataFrame([vec])).iloc[0].to_dict()
            score, top = _score_one(coefs, enriched)
            scores[ticker] = {
                "ticker": ticker, "horizon": meta.get("horizon", "5d"),
                "score": score, "band": _band(score),
                "health": meta["health"], "source": "own",
                "p_hat": round(score / 100, 3),
                "mean_auc": meta.get("mean_auc"),
                "min_fold_auc": meta.get("min_fold_auc"),
                "top_features": top, "computed_at": ts,
            }
            counts["scored"] += 1
        except Exception as exc:
            log.warning("score failed for %s: %s", ticker, exc)
            scores[ticker] = _empty_entry(ticker, meta, ts)
            counts["unavailable"] += 1
    storage.write_scores({"updated_at": ts, "scores": scores}, out=_SCORES_OUT)
    log.info("done — scored=%d unavailable=%d", counts["scored"], counts["unavailable"])
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=os.environ.get("TA_LOG_LEVEL", "INFO"),
                        format="%(asctime)s %(levelname)s %(message)s")
    raise SystemExit(main())
