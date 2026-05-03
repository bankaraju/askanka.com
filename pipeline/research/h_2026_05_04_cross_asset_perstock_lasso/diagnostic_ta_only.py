"""TA-only sanity-baseline diagnostic for H-2026-05-04.

Purpose: discriminate "broken gates" vs "weak cross-asset signal" after the
production runner produced 0 of 202 qualifying cells.

Design:
  - Same universe (101 sector-resolvable F&O stocks)
  - Same training window (2021-05-04 -> 2025-10-31)
  - Same labels (T+1 09:15 -> close, +/- 0.4%)
  - Same EN logistic, same 4-fold walk-forward, same exp-decay weights
  - **Strip cross-asset block:** 6 stock TA + 3 DOW = 9 features (no PCA, no
    K_ETF PCs, no 4 Indian macro)
  - **Real perm_beat_pct:** computed as (null_aucs < observed_auc).mean()
    so the gate is a genuine measurement, not a synthetic 0.96/0.0 mapping
    of BH-FDR survival.

This is a diagnostic, NOT a registered hypothesis. It does not consume the
single-touch on H-2026-05-04. Outputs to diagnostic_ta_only_results.json.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from pipeline.research.h_2026_05_04_cross_asset_perstock_lasso.elastic_net_fit import (  # noqa: E402
    exp_decay_weights, fit_en_cell, score_en_cell,
)
from pipeline.research.h_2026_05_04_cross_asset_perstock_lasso.feature_extractor import (  # noqa: E402
    build_dow,
    build_stock_ta,
)
from pipeline.research.h_2026_05_04_cross_asset_perstock_lasso.runner import (  # noqa: E402
    _load_bars, _label, C_GRID, L1_GRID, HL, LABEL_THRESHOLD_PCT,
)
from pipeline.research.h_2026_05_04_cross_asset_perstock_lasso.sector_mapping import (  # noqa: E402
    index_csv_for_sector, load_sectoral_index_close,
)
from pipeline.research.h_2026_05_04_cross_asset_perstock_lasso.walk_forward import (  # noqa: E402
    bh_fdr, expanding_quarter_folds,
)
from pipeline.scorecard_v2.sector_mapper import SectorMapper  # noqa: E402

OUT_DIR = REPO / "pipeline" / "research" / "h_2026_05_04_cross_asset_perstock_lasso"
SECTORAL_DIR = REPO / "pipeline" / "data" / "sectoral_indices"
TRAIN_END = pd.Timestamp("2025-10-31")
N_PERMUTATIONS = 10000


def _load_universe() -> list[str]:
    return json.loads((OUT_DIR / "universe_frozen.json").read_text())["tickers"]


def perm_p_and_beat(
    *, y_true: np.ndarray, y_score: np.ndarray, n_permutations: int, random_state: int
) -> tuple[float, float]:
    """Compute (two-sided permutation p-value, one-sided perm_beat_pct)."""
    from sklearn.metrics import roc_auc_score
    if len(np.unique(y_true)) < 2:
        return 1.0, 0.0
    observed = roc_auc_score(y_true, y_score)
    rng = np.random.default_rng(random_state)
    null = []
    for _ in range(n_permutations):
        shuffled = rng.permutation(y_true)
        if len(np.unique(shuffled)) < 2:
            null.append(0.5)
            continue
        null.append(roc_auc_score(shuffled, y_score))
    null = np.array(null)
    p = float((np.abs(null - 0.5) >= abs(observed - 0.5)).mean())
    perm_beat = float((null < observed).mean())
    return p, perm_beat


def main() -> int:
    print("=" * 70)
    print("DIAGNOSTIC: TA-only sanity baseline for H-2026-05-04")
    print("=" * 70)
    universe = _load_universe()
    print(f"[diag] universe size = {len(universe)}")

    sector_map = SectorMapper().map_all()
    cell_records: list[dict] = []
    n_skipped = 0

    for ticker in universe:
        bars = _load_bars(ticker)
        if bars is None:
            n_skipped += 1
            continue
        bars = bars.loc[bars.index <= TRAIN_END]
        if len(bars) < 800:
            n_skipped += 1
            continue
        info = sector_map.get(ticker)
        sector_key = info.get("sector") if info else None
        sector_path = index_csv_for_sector(sector_key, SECTORAL_DIR)
        if sector_path is None or not sector_path.exists():
            n_skipped += 1
            continue
        sector_close = load_sectoral_index_close(sector_path)
        sector_ret_5d = sector_close.pct_change(5)

        # 9 features only: 6 TA + 3 DOW
        ta = build_stock_ta(bars, sector_ret_5d)
        dow = build_dow(bars.index)
        X_pre = pd.concat([ta, dow], axis=1).dropna()

        y_long, y_short = _label(bars, LABEL_THRESHOLD_PCT)
        for direction, y in (("LONG", y_long), ("SHORT", y_short)):
            aligned = X_pre.join(y.rename("y"), how="inner").dropna()
            if len(aligned) < 500:
                continue
            X_arr = aligned.drop(columns=["y"]).values
            y_arr = aligned["y"].values

            folds = expanding_quarter_folds(aligned.index, n_folds=4)
            fold_aucs = []
            from sklearn.metrics import roc_auc_score
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
                fold_aucs.append(roc_auc_score(y_arr[va_idx], p_va))

            if len(fold_aucs) < 4:
                continue

            w_full = exp_decay_weights(len(X_arr), HL)
            try:
                final_model, cv_meta = fit_en_cell(
                    X_train=X_arr, y_train=y_arr,
                    sample_weights=w_full, C_grid=C_GRID, l1_ratio_grid=L1_GRID,
                    cv_n_splits=3, random_state=0,
                )
            except Exception:
                continue

            isho_n = min(125, len(X_arr) // 4)
            y_isho = y_arr[-isho_n:]
            p_isho = score_en_cell(final_model, X_arr[-isho_n:])
            single_class_isho = len(np.unique(y_isho)) < 2
            if single_class_isho:
                isho_auc = 0.5
            else:
                isho_auc = float(roc_auc_score(y_isho, p_isho))
            isho_label_rate = float(y_isho.mean())

            # n_pred_pos at multiple thresholds, to surface whether 0.6 was the wrong cutoff
            n_pp_50 = int((p_isho >= 0.50).sum())
            n_pp_55 = int((p_isho >= 0.55).sum())
            n_pp_60 = int((p_isho >= 0.60).sum())

            perm_p, perm_beat = perm_p_and_beat(
                y_true=y_isho, y_score=p_isho,
                n_permutations=N_PERMUTATIONS, random_state=0,
            )

            cell_records.append({
                "ticker": ticker, "direction": direction,
                "fold_aucs": fold_aucs, "mean_fold_auc": float(np.mean(fold_aucs)),
                "fold_auc_std": float(np.std(fold_aucs)),
                "isho_auc": isho_auc,
                "isho_single_class": single_class_isho,
                "isho_label_rate": isho_label_rate,
                "n_pred_pos_50": n_pp_50, "n_pred_pos_55": n_pp_55, "n_pred_pos_60": n_pp_60,
                "perm_p_value": perm_p, "perm_beat_pct": perm_beat,
                "cv_best_C": cv_meta["best_C"], "cv_best_l1": cv_meta["best_l1_ratio"],
                "cv_mean_auc": cv_meta["cv_mean_auc"],
            })

    print(f"[diag] cells fit = {len(cell_records)}, skipped = {n_skipped}")

    p_arr = np.array([c["perm_p_value"] for c in cell_records])
    survivors = bh_fdr(p_arr, alpha=0.05)
    for c, surv in zip(cell_records, survivors):
        c["bh_fdr_survivor"] = bool(surv)
    n_bh = int(survivors.sum())
    print(f"[diag] BH-FDR survivors = {n_bh}")

    out = {
        "diagnostic_id": "H-2026-05-04-TA-ONLY-SANITY",
        "run_at": datetime.now().isoformat(),
        "train_end": str(TRAIN_END.date()),
        "universe_size": len(universe),
        "n_cells_fit": len(cell_records),
        "bh_fdr_survivors": n_bh,
        "frozen_thresholds": {
            "C_grid": list(C_GRID), "l1_ratio_grid": list(L1_GRID),
            "hl_trading_days": HL, "label_threshold_pct": LABEL_THRESHOLD_PCT,
            "n_permutations": N_PERMUTATIONS,
        },
        "cells": cell_records,
    }
    out_path = OUT_DIR / "diagnostic_ta_only_results.json"
    out_path.write_text(json.dumps(out, indent=2, default=str))
    print(f"[diag] wrote {out_path}")

    # Summary stats so the result is visible without re-loading the JSON
    mean_aucs = [c["mean_fold_auc"] for c in cell_records]
    perm_beats = [c["perm_beat_pct"] for c in cell_records]
    isho_aucs = [c["isho_auc"] for c in cell_records]
    n_single_class = sum(1 for c in cell_records if c["isho_single_class"])
    print()
    print("[diag] Headline distributions:")
    print(f"  mean_fold_auc: median={np.median(mean_aucs):.3f}  p75={np.quantile(mean_aucs, 0.75):.3f}  max={max(mean_aucs):.3f}")
    print(f"  perm_beat_pct: median={np.median(perm_beats):.3f}  p75={np.quantile(perm_beats, 0.75):.3f}  max={max(perm_beats):.3f}")
    print(f"  isho_auc:      median={np.median(isho_aucs):.3f}  p75={np.quantile(isho_aucs, 0.75):.3f}  max={max(isho_aucs):.3f}")
    print(f"  isho single-class cells: {n_single_class} / {len(cell_records)} ({100*n_single_class/len(cell_records):.1f}%)")
    print(f"  cells with mean_fold_auc >= 0.55: {sum(1 for x in mean_aucs if x >= 0.55)}")
    print(f"  cells with perm_beat_pct >= 0.95: {sum(1 for x in perm_beats if x >= 0.95)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
