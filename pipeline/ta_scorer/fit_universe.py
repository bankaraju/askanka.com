"""Sunday 01:30 IST — fit RELIANCE TA model via 2y/3mo walk-forward.

Writes pipeline/data/ta_feature_models.json. Universe-size=1 for v1 pilot.
"""
from __future__ import annotations
import logging
from datetime import datetime
from pathlib import Path
import pandas as pd

from pipeline.ta_scorer import features, labels, model, storage, walk_forward

log = logging.getLogger(__name__)

_PIPELINE_DIR = Path(__file__).resolve().parent.parent
_REPO_ROOT = _PIPELINE_DIR.parent
_STOCK_HISTORICAL_DIR = _PIPELINE_DIR / "data" / "fno_historical"
_INDEX_HISTORICAL_DIR = _PIPELINE_DIR / "data" / "india_historical" / "indices"
_MODELS_OUT = _PIPELINE_DIR / "data" / "ta_feature_models.json"

_PILOT_TICKER = "RELIANCE"
_SECTOR_INDEX = "NIFTYENERGY"  # RELIANCE sector


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
            lbl = labels.make_label(prices, entry_date=d, horizon_days=1)
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


def main() -> int:
    prices = _load_csv(_STOCK_HISTORICAL_DIR / f"{_PILOT_TICKER}.csv")
    sector = _load_csv(_INDEX_HISTORICAL_DIR / f"{_SECTOR_INDEX}_daily.csv")
    nifty = _load_csv(_INDEX_HISTORICAL_DIR / "NIFTY_daily.csv")
    if prices is None or sector is None or nifty is None:
        log.warning("missing input CSVs — writing UNAVAILABLE model entry")
        storage.write_models({
            "version": "1.0",
            "fitted_at": datetime.now().isoformat(),
            "universe_size": 1,
            "models": {_PILOT_TICKER: {"health": "UNAVAILABLE",
                                       "source": "own",
                                       "reason": "missing input CSVs"}},
        }, out=_MODELS_OUT)
        return 0

    frame = _build_training_frame(prices, sector, nifty)
    if frame is None or len(frame) < 400:
        storage.write_models({
            "version": "1.0",
            "fitted_at": datetime.now().isoformat(),
            "universe_size": 1,
            "models": {_PILOT_TICKER: {"health": "UNAVAILABLE",
                                       "source": "own",
                                       "reason": "insufficient training frame"}},
        }, out=_MODELS_OUT)
        return 0

    as_of = frame["date"].iloc[-1]
    result = walk_forward.run_walk_forward(frame, train_years=2, test_months=3,
                                           as_of=as_of, max_folds=6)
    entry: dict = {
        "source": "own", "ticker": _PILOT_TICKER, "horizon": "1d",
        "health": result["health"],
        "mean_auc": result["mean_auc"], "min_fold_auc": result["min_fold_auc"],
        "n_folds": result["n_folds"], "folds": result["folds"],
    }
    if result["health"] in ("GREEN", "AMBER"):
        feature_cols = [c for c in frame.columns if c not in ("date", "y")]
        X = model.build_interaction_columns(frame[feature_cols])
        clf = model.fit_logistic(X, frame["y"])
        entry["coefficients"] = model.coefficients_dict(clf, list(X.columns))
    storage.write_models({
        "version": "1.0",
        "fitted_at": datetime.now().isoformat(),
        "universe_size": 1,
        "models": {_PILOT_TICKER: entry},
    }, out=_MODELS_OUT)
    log.info("fit %s → %s (mean_auc=%s, folds=%s)",
             _PILOT_TICKER, entry["health"], entry["mean_auc"], entry["n_folds"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
