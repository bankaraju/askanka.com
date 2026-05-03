"""04:30 IST daily forward predictor for H-2026-05-04.

Reads frozen models/PCA from runner output. For each qualifying cell, builds
the latest feature row from the panel/bars, scores, writes today_predictions.json.

CLI: python -m pipeline.research.h_2026_05_04_cross_asset_perstock_lasso.predict_today
"""
from __future__ import annotations

import json
import pickle
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from pipeline.autoresearch.etf_v3_loader import build_panel, CURATED_FOREIGN_ETFS  # noqa: E402
from pipeline.research.h_2026_05_04_cross_asset_perstock_lasso.feature_extractor import (  # noqa: E402
    build_full_feature_matrix,
)
from pipeline.research.h_2026_05_04_cross_asset_perstock_lasso.pca_model import (  # noqa: E402
    apply_pca, load_pca,
)
from pipeline.research.h_2026_05_04_cross_asset_perstock_lasso.elastic_net_fit import (  # noqa: E402
    score_en_cell,
)
from pipeline.research.h_2026_05_04_cross_asset_perstock_lasso.runner import (  # noqa: E402
    _load_bars, NIFTY_EMPHASIS,
)

OUT_DIR = REPO / "pipeline" / "research" / "h_2026_05_04_cross_asset_perstock_lasso"


def main() -> int:
    manifest = json.loads((OUT_DIR / "manifest.json").read_text())
    qualifying = manifest["qualifying_cells"]
    if not qualifying:
        (OUT_DIR / "today_predictions.json").write_text(json.dumps({
            "as_of": datetime.now().isoformat(), "predictions": [],
            "note": "no qualifying cells",
        }))
        return 0

    pca_model = load_pca(OUT_DIR / "pca_projections" / "final.npz")
    panel = build_panel()
    etf_cols = [c for c in CURATED_FOREIGN_ETFS if c in panel.columns]
    etf_1d = panel[etf_cols].pct_change(1)
    etf_1d.columns = [f"{c}_1d" for c in etf_cols]
    nifty_close = panel["nifty_close"]
    india_vix = panel["india_vix"]

    predictions = []
    for ticker, direction in qualifying:
        bars = _load_bars(ticker)
        if bars is None or len(bars) < 100:
            continue
        try:
            from pipeline.sector_mapper import map_one
            sector_name = map_one(ticker)
            sector_path = REPO / "pipeline" / "data" / "sectoral_indices" / f"{sector_name}.csv"
            sector_df = pd.read_csv(sector_path, parse_dates=["Date"]).set_index("Date").sort_index()
            sector_ret_5d = sector_df["Close"].pct_change(5)
        except Exception:
            continue

        X_pre = build_full_feature_matrix(
            bars=bars, etf_returns_1d=etf_1d,
            nifty_near_month_close=nifty_close, india_vix=india_vix,
            sector_ret_5d=sector_ret_5d, nifty_emphasis_factor=NIFTY_EMPHASIS,
        )
        etf_block_cols = [c for c in X_pre.columns if c.endswith("_1d") and not c.startswith("nifty_")]
        pcs = apply_pca(X_pre[etf_block_cols], pca_model)
        non_etf = X_pre.drop(columns=etf_block_cols)
        X = pd.concat([pcs, non_etf], axis=1).dropna()
        if len(X) == 0:
            continue
        latest_row = X.iloc[-1]
        latest_date = X.index[-1]

        with open(OUT_DIR / "models" / f"{ticker}_{direction}.pkl", "rb") as f:
            model = pickle.load(f)
        p_hat = float(score_en_cell(model, latest_row.values.reshape(1, -1))[0])

        predictions.append({
            "ticker": ticker, "direction": direction,
            "p_hat": p_hat, "feature_date": str(latest_date.date()),
        })

    out = {
        "as_of": datetime.now().isoformat(),
        "n_predictions": len(predictions),
        "predictions": predictions,
    }
    (OUT_DIR / "today_predictions.json").write_text(json.dumps(out, indent=2))
    print(f"[predict_today] wrote {len(predictions)} predictions")
    return 0


if __name__ == "__main__":
    sys.exit(main())
