"""H-2026-04-29-ta-karpathy-v1 daily forward prediction.

Loads frozen models from `models/<TICKER>_<DIRECTION>.pkl`, fetches latest bars,
rebuilds the feature matrix, and emits today's prediction probabilities.

Spec ref: docs/superpowers/specs/2026-04-29-ta-karpathy-v1-design.md sections 10, 14.

Schedule: AnkaTAKarpathyPredict at 04:30 IST -- after AnkaDailyDump completes
on VPS but before market open.

Usage:
  python -m pipeline.ta_scorer.karpathy_predict

Output: pipeline/data/research/h_2026_04_29_ta_karpathy_v1/today_predictions.json
"""
from __future__ import annotations

import argparse
import json
import logging
import pickle
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from .karpathy_data import (
    INDIAVIX_SYMBOL, NIFTY_SYMBOL, NIFTY_TOP_10, SECTOR_MAP,
    fetch_macro, fetch_one,
)
from .karpathy_features import (
    FEATURE_COLUMNS, build_feature_matrix, make_labels,
)

log = logging.getLogger("karpathy.predict")

REPO_ROOT = Path(__file__).resolve().parents[2]
RUN_ROOT = REPO_ROOT / "pipeline" / "data" / "research" / "h_2026_04_29_ta_karpathy_v1"

# Spec section 10: per-direction thresholds for trade signal
P_LONG_ENTRY = 0.6
P_SHORT_GATE = 0.4
P_SHORT_ENTRY = 0.6
P_LONG_GATE = 0.4


def load_model(model_path: Path) -> dict:
    with model_path.open("rb") as f:
        return pickle.load(f)


def score_one(
    ticker: str,
    macro: dict[str, pd.DataFrame],
    *,
    models_dir: Path,
) -> dict:
    """Score today's row for one ticker.

    Returns a row with date, ticker, p_long, p_short, signal_long, signal_short.
    Returns None on missing model/data.
    """
    long_path = models_dir / f"{ticker}_long.pkl"
    short_path = models_dir / f"{ticker}_short.pkl"
    if not (long_path.exists() or short_path.exists()):
        log.warning("%s: no models found -- skipping", ticker)
        return None

    bars = fetch_one(ticker, force=True)  # force-refresh in case yfinance is stale
    feat = build_feature_matrix(
        bars=bars,
        nifty=macro[NIFTY_SYMBOL][["date", "close"]],
        vix=macro[INDIAVIX_SYMBOL][["date", "close"]],
        sector=macro[SECTOR_MAP[ticker]][["date", "close"]],
        regime=pd.DataFrame({"date": pd.to_datetime([]), "regime": []}),
    )
    feat = feat.dropna(subset=FEATURE_COLUMNS)
    if len(feat) == 0:
        log.warning("%s: feature matrix empty", ticker)
        return None
    last = feat.iloc[-1:].reset_index(drop=True)
    asof_date = last["date"].iloc[0]

    out = {
        "ticker": ticker,
        "asof_date": str(asof_date.date()),
        "predicted_for_open": "T+1 09:15 IST",
    }

    for direction, mp in [("long", long_path), ("short", short_path)]:
        if not mp.exists():
            out[f"p_{direction}"] = None
            out[f"logit_{direction}"] = None
            out[f"n_features_active_{direction}"] = None
            continue
        m = load_model(mp)
        cols = m["feature_columns"]
        # Standardise
        x = last[cols].values[0].astype(float)
        mu = np.array([m["stats_mean"][c] for c in cols])
        sd = np.array([m["stats_std"][c] for c in cols])
        z = (x - mu) / np.where(sd == 0, 1.0, sd)
        coef = np.array(m["coef"])
        intercept = m["intercept"]
        logit = float(np.dot(z, coef) + intercept)
        # sigmoid
        p = 1.0 / (1.0 + np.exp(-logit))
        out[f"p_{direction}"] = p
        out[f"logit_{direction}"] = logit
        out[f"n_features_active_{direction}"] = int(np.sum(np.abs(coef) > 1e-10))

    if out["p_long"] is not None and out["p_short"] is not None:
        out["signal_long"] = bool(out["p_long"] >= P_LONG_ENTRY and out["p_short"] < P_SHORT_GATE)
        out["signal_short"] = bool(out["p_short"] >= P_SHORT_ENTRY and out["p_long"] < P_LONG_GATE)
    else:
        out["signal_long"] = False
        out["signal_short"] = False
    return out


def predict_all(*, run_root: Path = RUN_ROOT, tickers: list[str] = None) -> list[dict]:
    if tickers is None:
        tickers = list(NIFTY_TOP_10)
    models_dir = run_root / "models"
    if not models_dir.exists():
        raise RuntimeError(
            f"models dir not found: {models_dir}. "
            f"Run pipeline.ta_scorer.karpathy_runner first."
        )
    macro = fetch_macro()
    rows = []
    for tk in tickers:
        try:
            r = score_one(tk, macro, models_dir=models_dir)
            if r is not None:
                rows.append(r)
        except Exception as exc:
            log.error("%s: scoring failed: %s", tk, exc)
    return rows


def main():
    p = argparse.ArgumentParser(description="H-2026-04-29 daily forward prediction")
    p.add_argument("--tickers", nargs="+", default=list(NIFTY_TOP_10))
    p.add_argument("--run-root", type=Path, default=RUN_ROOT)
    args = p.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    rows = predict_all(run_root=args.run_root, tickers=args.tickers)

    out_path = args.run_root / "today_predictions.json"
    out_path.write_text(json.dumps({
        "hypothesis_id": "H-2026-04-29-ta-karpathy-v1",
        "generated_at": datetime.now().isoformat(),
        "n_predictions": len(rows),
        "predictions": rows,
    }, indent=2))
    log.info("wrote %d predictions to %s", len(rows), out_path)
    n_long = sum(1 for r in rows if r.get("signal_long"))
    n_short = sum(1 for r in rows if r.get("signal_short"))
    log.info("signals: %d LONG, %d SHORT", n_long, n_short)


if __name__ == "__main__":
    main()
