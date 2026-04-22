"""Weekly Sunday 01:30 IST — fit TA models across the F&O universe.

Writes pipeline/data/ta_feature_models.json with one entry per ticker that
has enough history. Broad-NIFTY is used as the sector proxy for every ticker
until per-sector CSVs are backfilled.
"""
from __future__ import annotations
import logging
import os
from datetime import datetime
from pathlib import Path
import pandas as pd

from pipeline.ta_scorer import features, labels, model, storage, walk_forward

log = logging.getLogger(__name__)

_PIPELINE_DIR = Path(__file__).resolve().parent.parent
_STOCK_HISTORICAL_DIR = _PIPELINE_DIR / "data" / "fno_historical"
_INDEX_HISTORICAL_DIR = _PIPELINE_DIR / "data" / "india_historical" / "indices"
_MODELS_OUT = _PIPELINE_DIR / "data" / "ta_feature_models.json"

_HORIZON_DAYS = 5
_WIN_THRESHOLD = 0.025
_MIN_FRAME_ROWS = 400


def _load_csv(path: Path) -> pd.DataFrame | None:
    if not path.exists():
        return None
    df = pd.read_csv(path)
    df.columns = [c.lower() for c in df.columns]
    return df


def _build_training_frame(prices: pd.DataFrame, sector: pd.DataFrame,
                          nifty: pd.DataFrame) -> pd.DataFrame | None:
    rows: list[dict] = []
    skipped_errors = 0
    for i, d in enumerate(prices["date"]):
        if i < 210:
            continue
        try:
            vec = features.build_feature_vector(
                prices=prices, sector=sector, nifty=nifty,
                as_of=d, regime="NEUTRAL", sector_breadth=0.5,
            )
            if not vec:
                continue
            lbl = labels.make_label(prices, entry_date=d,
                                   horizon_days=_HORIZON_DAYS,
                                   win_threshold=_WIN_THRESHOLD)
            if not lbl:
                continue
            vec["date"] = d
            vec["y"] = lbl["y"]
            rows.append(vec)
        except Exception as exc:
            skipped_errors += 1
            log.debug("row %s: skip on exception %s", d, exc)
    if skipped_errors:
        log.info("training frame built with %d row-level skips", skipped_errors)
    if not rows:
        return None
    return pd.DataFrame(rows)


def _fit_one(ticker: str, nifty: pd.DataFrame) -> dict:
    prices = _load_csv(_STOCK_HISTORICAL_DIR / f"{ticker}.csv")
    if prices is None or len(prices) < 250:
        return {"source": "own", "ticker": ticker, "horizon": f"{_HORIZON_DAYS}d",
                "health": "UNAVAILABLE", "reason": "insufficient history"}
    sector = nifty  # broad-market proxy until per-sector CSVs land
    frame = _build_training_frame(prices, sector, nifty)
    if frame is None or len(frame) < _MIN_FRAME_ROWS:
        return {"source": "own", "ticker": ticker, "horizon": f"{_HORIZON_DAYS}d",
                "health": "UNAVAILABLE", "reason": "insufficient training frame",
                "sector_proxy": True}
    as_of = frame["date"].iloc[-1]
    result = walk_forward.run_walk_forward(frame, train_years=2, test_months=3,
                                           as_of=as_of, max_folds=6)
    entry: dict = {
        "source": "own", "ticker": ticker, "horizon": f"{_HORIZON_DAYS}d",
        "health": result["health"],
        "mean_auc": result["mean_auc"], "min_fold_auc": result["min_fold_auc"],
        "n_folds": result["n_folds"], "folds": result["folds"],
        "sector_proxy": True,
    }
    if result["health"] in ("GREEN", "AMBER"):
        feature_cols = [c for c in frame.columns if c not in ("date", "y")]
        X = model.build_interaction_columns(frame[feature_cols])
        clf = model.fit_logistic(X, frame["y"])
        entry["coefficients"] = model.coefficients_dict(clf, list(X.columns))
    return entry


def main() -> int:
    nifty = _load_csv(_INDEX_HISTORICAL_DIR / "NIFTY_daily.csv")
    if nifty is None:
        log.error("NIFTY_daily.csv missing — cannot run universe fit")
        return 1
    tickers = sorted(p.stem for p in _STOCK_HISTORICAL_DIR.glob("*.csv"))
    log.info("fitting %d tickers (horizon=%dd, threshold=%.3f)",
             len(tickers), _HORIZON_DAYS, _WIN_THRESHOLD)
    models: dict[str, dict] = {}
    counts = {"GREEN": 0, "AMBER": 0, "RED": 0, "UNAVAILABLE": 0}
    for i, t in enumerate(tickers):
        try:
            entry = _fit_one(t, nifty)
        except Exception as exc:
            log.warning("fit failed for %s: %s", t, exc)
            entry = {"source": "own", "ticker": t, "horizon": f"{_HORIZON_DAYS}d",
                     "health": "UNAVAILABLE", "reason": f"exception: {exc}"}
        models[t] = entry
        counts[entry.get("health", "UNAVAILABLE")] = counts.get(entry.get("health", "UNAVAILABLE"), 0) + 1
        if (i + 1) % 25 == 0 or (i + 1) == len(tickers):
            log.info("progress %d/%d — green=%d amber=%d red=%d unavail=%d",
                     i + 1, len(tickers), counts["GREEN"], counts["AMBER"],
                     counts["RED"], counts["UNAVAILABLE"])
    storage.write_models({
        "version": "1.0",
        "fitted_at": datetime.now().isoformat(),
        "universe_size": len(tickers),
        "horizon_days": _HORIZON_DAYS,
        "win_threshold": _WIN_THRESHOLD,
        "sector_proxy_note": "broad NIFTY used as sector proxy for all tickers",
        "health_counts": counts,
        "models": models,
    }, out=_MODELS_OUT)
    log.info("done — GREEN=%d AMBER=%d RED=%d UNAVAILABLE=%d",
             counts["GREEN"], counts["AMBER"], counts["RED"], counts["UNAVAILABLE"])
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=os.environ.get("TA_LOG_LEVEL", "INFO"),
                        format="%(asctime)s %(levelname)s %(message)s")
    raise SystemExit(main())
