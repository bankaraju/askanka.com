"""Sunday 01:00 IST entry point.

Fits per-ticker logistic regression models for the full F&O universe
using quarterly walk-forward validation. Falls back to the sector cohort
model when own history is insufficient. Writes ticker_feature_models.json.
"""
from __future__ import annotations
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any
import pandas as pd

from pipeline.feature_scorer import cohorts, features, labels, model, storage, walk_forward

log = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).parent.parent.parent
_PIPELINE_DIR = Path(__file__).parent.parent
_FNO_UNIVERSE_FILE = _REPO_ROOT / "opus" / "config" / "fno_stocks.json"
_STOCK_HISTORICAL_DIR = _PIPELINE_DIR / "data" / "fno_historical"
_INDEX_HISTORICAL_DIR = _PIPELINE_DIR / "data" / "india_historical"


def _ticker_universe() -> list[str]:
    """Return list of F&O ticker symbols from opus/config/fno_stocks.json."""
    try:
        data = json.loads(_FNO_UNIVERSE_FILE.read_text(encoding="utf-8"))
        return list(data.get("symbols", []) or data.get("tickers", []))
    except FileNotFoundError:
        log.warning("F&O universe file not found; fitter will produce an empty model set")
        return []


def _load_ticker_prices(ticker: str) -> pd.DataFrame | None:
    """Load a single ticker's daily price history from pipeline/data/fno_historical/."""
    p = _STOCK_HISTORICAL_DIR / f"{ticker}.csv"
    if not p.exists():
        return None
    return pd.read_csv(p)


def _load_sector_bars(cohort: str) -> pd.DataFrame | None:
    """Load a sector index's daily history from pipeline/data/india_historical/."""
    p = _INDEX_HISTORICAL_DIR / f"{cohort}_daily.csv"
    if not p.exists():
        return None
    return pd.read_csv(p)


def _load_regime_history() -> dict[str, str]:
    """date (ISO) → regime-zone name. Returns {} if unavailable."""
    p = _PIPELINE_DIR / "data" / "msi_history.json"
    if not p.exists():
        return {}
    try:
        rows = json.loads(p.read_text(encoding="utf-8"))
        return {r.get("date"): r.get("zone") or r.get("regime") for r in rows if r.get("date")}
    except Exception as e:
        log.warning("failed to load msi_history.json: %s", e)
        return {}


def _build_training_frame(ticker: str, sector_df: pd.DataFrame,
                          regime_map: dict[str, str]) -> pd.DataFrame | None:
    """For each day in ticker history, build feature vector + label. Returns a DataFrame."""
    prices = _load_ticker_prices(ticker)
    if prices is None or len(prices) < 100:
        return None
    prices = prices.sort_values("date").reset_index(drop=True)
    rows = []
    for i, d in enumerate(prices["date"]):
        if i < 20:  # need lookback
            continue
        label = labels.simulated_pnl_label(prices, entry_date=d, horizon_days=5)
        if label is None:
            continue
        regime = regime_map.get(str(d)[:10], "NEUTRAL")
        vec = features.build_feature_vector(
            prices=prices, sector=sector_df, as_of=d,
            regime=regime, dte=10, trust_grade=None,
            nifty_breadth_5d=None, pcr_z_score=None,
        )
        vec["date"] = d
        vec["y"] = label["y"]
        rows.append(vec)
    if not rows:
        return None
    return pd.DataFrame(rows)


def _fit_one(ticker: str, sector_df: pd.DataFrame, regime_map: dict,
              as_of: str) -> dict[str, Any]:
    frame = _build_training_frame(ticker, sector_df, regime_map)
    if frame is None:
        return {"health": "UNAVAILABLE", "source": "own",
                "reason": "no training frame"}
    result = walk_forward.run_walk_forward(frame, train_years=2, test_months=3, as_of=as_of)
    if result["health"] in ("GREEN", "AMBER"):
        X = frame.drop(columns=["date", "y"])
        y = frame["y"]
        final = model.fit_logistic(X, y)
        result["coefficients"] = model.coefficients_dict(final)
        result["source"] = "own"
    else:
        result["source"] = "own"
    return result


def main() -> int:
    as_of = datetime.now().strftime("%Y-%m-%d")
    tickers = _ticker_universe()
    regime_map = _load_regime_history()
    models_out: dict[str, Any] = {}

    for ticker in tickers:
        cohort = cohorts.ticker_to_cohort(ticker)
        sector_df = _load_sector_bars(cohort) if cohort != "MIDCAP_GENERIC" else _load_sector_bars("MIDCPNIFTY")
        if sector_df is None:
            models_out[ticker] = {"health": "UNAVAILABLE", "source": "own",
                                   "reason": f"sector {cohort} bars unavailable"}
            continue
        res = _fit_one(ticker, sector_df, regime_map, as_of)
        if res["health"] == "UNAVAILABLE" or (res["health"] == "RED" and cohort):
            log.info("cohort fallback for %s (cohort=%s)", ticker, cohort)
            res["fallback_cohort"] = cohort
        models_out[ticker] = res

    out = {
        "version": "1.0",
        "fitted_at": datetime.now().isoformat(),
        "universe_size": len(tickers),
        "models": models_out,
    }
    storage.write_models(out)
    log.info("fit_universe wrote %d models", len(models_out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
