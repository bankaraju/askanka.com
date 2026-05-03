"""End-to-end orchestrator for H-2026-05-04 fit job.

Loads frozen universe, builds features per stock, fits PCA on training panel,
runs walk-forward + qualifier per (stock, direction), applies BH-FDR across
the cell grid, freezes final models for qualifying cells, writes manifest.

CLI: python -m pipeline.research.h_2026_05_04_cross_asset_perstock_lasso.runner --train-end 2025-10-31
"""
from __future__ import annotations

import argparse
import json
import pickle
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from pipeline.autoresearch.etf_v3_loader import build_panel, CURATED_FOREIGN_ETFS  # noqa: E402
from pipeline.research.h_2026_05_04_cross_asset_perstock_lasso.feature_extractor import (  # noqa: E402
    build_full_feature_matrix,
)
from pipeline.research.h_2026_05_04_cross_asset_perstock_lasso.pca_model import (  # noqa: E402
    fit_pca, apply_pca, save_pca,
)
from pipeline.research.h_2026_05_04_cross_asset_perstock_lasso.elastic_net_fit import (  # noqa: E402
    exp_decay_weights, fit_en_cell, score_en_cell,
)
from pipeline.research.h_2026_05_04_cross_asset_perstock_lasso.walk_forward import (  # noqa: E402
    expanding_quarter_folds, qualifier_check, bh_fdr_per_direction, permutation_p_value,
)
from pipeline.research.h_2026_05_04_cross_asset_perstock_lasso.sector_mapping import (  # noqa: E402
    index_csv_for_sector,
    load_sectoral_index_close,
)
from pipeline.scorecard_v2.sector_mapper import SectorMapper  # noqa: E402

OUT_DIR = REPO / "pipeline" / "research" / "h_2026_05_04_cross_asset_perstock_lasso"
FNO_CSV_DIR = REPO / "pipeline" / "data" / "fno_historical"
SECTORAL_DIR = REPO / "pipeline" / "data" / "sectoral_indices"

C_GRID = (0.01, 0.03, 0.1, 0.3, 1.0, 3.0)
L1_GRID = (0.1, 0.3, 0.5, 0.7, 0.9)
HL = 90
LABEL_THRESHOLD_PCT = 0.4
NIFTY_EMPHASIS = 1.5
# §9B.2 requires >=100,000 permutations when FDR is in effect.
# Bumped from 10,000 in A2 amendment 2026-05-03.
N_PERMUTATIONS = 100_000
FOLD_AUC_THRESHOLD = 0.53  # A2 amendment, was 0.55 at v1.0


def _load_universe() -> list[str]:
    p = OUT_DIR / "universe_frozen.json"
    return json.loads(p.read_text())["tickers"]


def _normalise_ohlcv(df: pd.DataFrame) -> pd.DataFrame | None:
    rename = {}
    for c in df.columns:
        lc = c.lower()
        if lc in {"date", "open", "high", "low", "close", "volume"}:
            rename[c] = lc.capitalize() if lc != "date" else "Date"
    df = df.rename(columns=rename)
    if not {"Date", "Open", "High", "Low", "Close", "Volume"}.issubset(df.columns):
        return None
    df["Date"] = pd.to_datetime(df["Date"])
    return df.set_index("Date").sort_index()


def _load_bars(ticker: str) -> pd.DataFrame | None:
    p = FNO_CSV_DIR / f"{ticker}.csv"
    if not p.exists():
        return None
    try:
        return _normalise_ohlcv(pd.read_csv(p))
    except Exception:
        return None


def _label(bars: pd.DataFrame, threshold_pct: float) -> tuple[pd.Series, pd.Series]:
    """T+1 open-to-close binary labels (LONG, SHORT) at +/- threshold_pct."""
    open_t1 = bars["Open"].shift(-1)
    close_t1 = bars["Close"].shift(-1)
    fwd_ret_pct = (close_t1 - open_t1) / open_t1 * 100
    y_long = (fwd_ret_pct >= threshold_pct).astype(int)
    y_short = (-fwd_ret_pct >= threshold_pct).astype(int)
    return y_long, y_short


def main(train_end: pd.Timestamp) -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "feature_matrices").mkdir(exist_ok=True)
    (OUT_DIR / "models").mkdir(exist_ok=True)
    (OUT_DIR / "pca_projections").mkdir(exist_ok=True)

    print(f"[runner] train_end = {train_end.date()}")
    universe = _load_universe()
    print(f"[runner] universe size = {len(universe)}")

    # 0. Sector resolution (frozen at fit time; tickers without a sectoral
    #    index CSV are excluded — preflight already enforced this filter at
    #    universe-freeze time, so this is a defensive check.)
    sector_map = SectorMapper().map_all()

    # 1. Build panel and ETF 1d returns
    panel = build_panel()
    etf_cols = [c for c in CURATED_FOREIGN_ETFS if c in panel.columns]
    etf_1d = panel[etf_cols].pct_change(1)
    etf_1d.columns = [f"{c}_1d" for c in etf_cols]
    nifty_close = panel["nifty_close"]
    india_vix = panel["india_vix"]

    # 2. Fit PCA on training-window ETF returns
    train_mask = (etf_1d.index >= pd.Timestamp("2021-05-04")) & (etf_1d.index <= train_end)
    etf_train = etf_1d.loc[train_mask].dropna()
    pca_model = fit_pca(etf_train, variance_target=0.85, max_K=12)
    print(f"[runner] PCA: K_ETF={pca_model.K_ETF}, cum_var={pca_model.cum_var_at_K:.3f}")
    save_pca(pca_model, OUT_DIR / "pca_projections" / "final.npz")

    # 3. Per-stock fit
    cell_records = []
    for ticker in universe:
        bars = _load_bars(ticker)
        if bars is None:
            continue
        bars = bars.loc[bars.index <= train_end]
        if len(bars) < 800:
            continue

        # Sector ret 5d (read from sectoral_indices via SECTOR_TO_INDEX_FILE map)
        info = sector_map.get(ticker)
        sector_key = info.get("sector") if info else None
        if not sector_key or sector_key == "Unmapped":
            continue
        sector_path = index_csv_for_sector(sector_key, SECTORAL_DIR)
        if sector_path is None or not sector_path.exists():
            continue
        sector_close = load_sectoral_index_close(sector_path)
        sector_ret_5d = sector_close.pct_change(5)

        X_pre = build_full_feature_matrix(
            bars=bars,
            etf_returns_1d=etf_1d,
            nifty_near_month_close=nifty_close,
            india_vix=india_vix,
            sector_ret_5d=sector_ret_5d,
            nifty_emphasis_factor=NIFTY_EMPHASIS,
        )
        # Apply PCA to ETF columns only
        etf_block_cols = [c for c in X_pre.columns if c.endswith("_1d") and not c.startswith("nifty_")]
        pcs = apply_pca(X_pre[etf_block_cols], pca_model)
        non_etf = X_pre.drop(columns=etf_block_cols)
        X = pd.concat([pcs, non_etf], axis=1).dropna()
        X.to_parquet(OUT_DIR / "feature_matrices" / f"{ticker}.parquet")

        y_long, y_short = _label(bars, LABEL_THRESHOLD_PCT)
        for direction, y in (("LONG", y_long), ("SHORT", y_short)):
            aligned = X.join(y.rename("y"), how="inner").dropna()
            if len(aligned) < 500:
                continue
            X_arr = aligned.drop(columns=["y"]).values
            y_arr = aligned["y"].values

            # Walk-forward folds
            folds = expanding_quarter_folds(aligned.index, n_folds=4)
            fold_aucs = []
            for tr_idx, va_idx in folds:
                if len(np.unique(y_arr[tr_idx])) < 2 or len(np.unique(y_arr[va_idx])) < 2:
                    continue
                w = exp_decay_weights(len(tr_idx), HL)
                try:
                    m, _ = fit_en_cell(
                        X_train=X_arr[tr_idx], y_train=y_arr[tr_idx],
                        sample_weights=w, C_grid=C_GRID, l1_ratio_grid=L1_GRID,
                        cv_n_splits=3, random_state=0,
                    )
                except Exception:
                    continue
                p_va = score_en_cell(m, X_arr[va_idx])
                from sklearn.metrics import roc_auc_score
                fold_aucs.append(roc_auc_score(y_arr[va_idx], p_va))

            if len(fold_aucs) < 4:
                continue

            # Final model on full training window (use median CV hyperparameters via re-CV on full)
            w_full = exp_decay_weights(len(X_arr), HL)
            try:
                final_model, cv_meta = fit_en_cell(
                    X_train=X_arr, y_train=y_arr,
                    sample_weights=w_full, C_grid=C_GRID, l1_ratio_grid=L1_GRID,
                    cv_n_splits=3, random_state=0,
                )
            except Exception:
                continue

            # In-sample holdout: last 6 months of training (~125 days).
            # Per A2 amendment: isho_auc and n_pred_pos retained as INFORMATIONAL
            # outputs only. They no longer gate qualification (§9C.2 forbids them).
            isho_n = min(125, len(X_arr) // 4)
            p_isho = score_en_cell(final_model, X_arr[-isho_n:])
            from sklearn.metrics import roc_auc_score
            y_isho = y_arr[-isho_n:]
            isho_single_class = len(np.unique(y_isho)) < 2
            isho_auc = roc_auc_score(y_isho, p_isho) if not isho_single_class else 0.5

            # Permutation null on the isho window. N_PERMUTATIONS=100,000 per §9B.2.
            perm_p = permutation_p_value(
                y_true=y_isho, y_score=p_isho,
                n_permutations=N_PERMUTATIONS, random_state=0,
            )

            cell_records.append({
                "ticker": ticker, "direction": direction,
                "fold_aucs": fold_aucs, "mean_fold_auc": float(np.mean(fold_aucs)),
                "fold_auc_std": float(np.std(fold_aucs)),
                # Informational (not gating per A2):
                "isho_auc": float(isho_auc),
                "isho_single_class": isho_single_class,
                "n_pred_pos_isho_50": int((p_isho >= 0.50).sum()),
                "n_pred_pos_isho_55": int((p_isho >= 0.55).sum()),
                "n_pred_pos_isho_60": int((p_isho >= 0.60).sum()),
                # Gate B input:
                "perm_p_value": perm_p,
                "cv_best_C": cv_meta["best_C"], "cv_best_l1": cv_meta["best_l1_ratio"],
                "cv_mean_auc": cv_meta["cv_mean_auc"],
            })

            # Save final model
            with open(OUT_DIR / "models" / f"{ticker}_{direction}.pkl", "wb") as f:
                pickle.dump(final_model, f)

        print(f"  {ticker}: {len([c for c in cell_records if c['ticker']==ticker])} directions fit")

    # 4. BH-FDR PER-DIRECTION (§9C.3): LONG and SHORT each form their own family.
    if not cell_records:
        print("[runner] FAIL: 0 cells fit")
        return 1

    surv_map = bh_fdr_per_direction(cell_records, alpha=0.05)
    for c in cell_records:
        c["bh_fdr_survivor"] = surv_map.get((c["ticker"], c["direction"]), False)

    # 5. Apply revised cell-level qualifier (Gate A: fold-AUC; Gate B: BH-FDR survivor).
    qualifying = []
    for c in cell_records:
        ok, reasons = qualifier_check(
            fold_aucs=c["fold_aucs"],
            bh_fdr_survivor=c["bh_fdr_survivor"],
            fold_auc_threshold=FOLD_AUC_THRESHOLD,
        )
        c["qualified"] = ok
        c["fail_reasons"] = reasons
        if ok:
            qualifying.append((c["ticker"], c["direction"]))

    # 6. Manifest
    n_long = sum(1 for c in cell_records if c["direction"] == "LONG")
    n_short = sum(1 for c in cell_records if c["direction"] == "SHORT")
    n_long_surv = sum(1 for c in cell_records if c["direction"] == "LONG" and c["bh_fdr_survivor"])
    n_short_surv = sum(1 for c in cell_records if c["direction"] == "SHORT" and c["bh_fdr_survivor"])
    manifest = {
        "hypothesis_id": "H-2026-05-04-cross-asset-perstock-lasso-v1",
        "run_at": datetime.now().isoformat(),
        "train_end": str(train_end.date()),
        "universe_size": len(universe),
        "K_ETF": pca_model.K_ETF, "cum_var_at_K": pca_model.cum_var_at_K,
        "n_cells_fit": len(cell_records),
        "n_qualifying": len(qualifying),
        "qualifying_cells": qualifying,
        "bh_fdr_per_direction": {
            "long_family_size": n_long,
            "long_bh_fdr_survivors": n_long_surv,
            "short_family_size": n_short,
            "short_bh_fdr_survivors": n_short_surv,
        },
        "frozen_thresholds": {
            "C_grid": list(C_GRID), "l1_ratio_grid": list(L1_GRID),
            "hl_trading_days": HL, "label_threshold_pct": LABEL_THRESHOLD_PCT,
            "nifty_emphasis": NIFTY_EMPHASIS,
            "n_permutations": N_PERMUTATIONS,
            "fold_auc_threshold": FOLD_AUC_THRESHOLD,
        },
        "amendments_applied": ["A1_PRE_HOLDOUT_FIX_2026_05_03", "A2_GATE_RECONFIG_2026_05_03"],
        "standards_version": "1.1_2026-05-03",
    }
    (OUT_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2, default=str))
    (OUT_DIR / "walk_forward_results.json").write_text(json.dumps(cell_records, indent=2, default=str))

    print(f"[runner] DONE: {len(cell_records)} cells fit, {len(qualifying)} qualified")
    print(f"[runner] Manifest: {OUT_DIR / 'manifest.json'}")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--train-end", type=str, default="2025-10-31")
    args = parser.parse_args()
    sys.exit(main(pd.Timestamp(args.train_end)))
