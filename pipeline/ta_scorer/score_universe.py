"""Daily 16:00 IST — apply cached RELIANCE TA model to today's close."""
from __future__ import annotations
import logging
import math
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

_PILOT_TICKER = "RELIANCE"
_SECTOR_INDEX = "NIFTYENERGY"


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


_INTERCEPT_KEY = "__intercept__"


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


def main() -> int:
    models = storage.read_models(path=_MODELS_IN).get("models", {})
    meta = models.get(_PILOT_TICKER) or {}
    ts = datetime.now().isoformat()
    payload_empty = {"updated_at": ts, "scores": {_PILOT_TICKER: {
        "ticker": _PILOT_TICKER, "score": None, "band": "UNAVAILABLE",
        "health": meta.get("health", "UNAVAILABLE"),
        "source": "own", "top_features": [], "computed_at": ts,
    }}}
    if meta.get("health") not in ("GREEN", "AMBER"):
        storage.write_scores(payload_empty, out=_SCORES_OUT)
        log.info("skip scoring — model health=%s", meta.get("health"))
        return 0
    coefs = meta.get("coefficients") or {}
    if not coefs:
        storage.write_scores(payload_empty, out=_SCORES_OUT)
        return 0

    prices = _load_csv(_STOCK_HISTORICAL_DIR / f"{_PILOT_TICKER}.csv")
    sector = _load_csv(_INDEX_HISTORICAL_DIR / f"{_SECTOR_INDEX}_daily.csv")
    nifty = _load_csv(_INDEX_HISTORICAL_DIR / "NIFTY_daily.csv")
    if prices is None or sector is None or nifty is None:
        storage.write_scores(payload_empty, out=_SCORES_OUT)
        return 0

    as_of = str(prices["date"].iloc[-1])
    vec = features.build_feature_vector(
        prices=prices, sector=sector, nifty=nifty,
        as_of=as_of, regime="NEUTRAL", sector_breadth=0.5,
    )
    if not vec:
        storage.write_scores(payload_empty, out=_SCORES_OUT)
        return 0
    enriched = model.build_interaction_columns(pd.DataFrame([vec])).iloc[0].to_dict()
    score, top = _score_one(coefs, enriched)
    storage.write_scores({"updated_at": ts, "scores": {_PILOT_TICKER: {
        "ticker": _PILOT_TICKER, "horizon": "1d",
        "score": score, "band": _band(score),
        "health": meta["health"], "source": "own",
        "p_hat": round(score / 100, 3),
        "mean_auc": meta.get("mean_auc"),
        "min_fold_auc": meta.get("min_fold_auc"),
        "top_features": top, "computed_at": ts,
    }}}, out=_SCORES_OUT)
    log.info("scored %s: %d", _PILOT_TICKER, score)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
