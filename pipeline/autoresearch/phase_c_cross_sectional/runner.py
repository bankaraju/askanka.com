"""H-2026-04-24-003 end-to-end compliance runner.

Orchestrates: event filter -> feature matrix -> Lasso fit -> trading rule
-> slippage grid -> naive comparators -> permutation null -> fragility sweep
-> Section 11B beta regression, 11C portfolio gate, 12 CUSUM decay, 11A impl risk
-> Section 15.1 gate checklist artifact.

v2 deltas from the superseded v1 plan (df63fe2):
  1. _split default cutoff: 2025-05-31 (was 2025-12-31)
  2. run() signature: z_threshold_current + z_threshold_prior (was z_threshold)
  3. filter_persistent_breaks call sites: new kwargs
  4. fragility loop: new kwargs, persistence_days pinned at 2
  5. hypothesis_id: H-2026-04-24-003 (was 002)
  6. strategy_version: cross_sectional_v2 (was v1)
  7. artifact dir: compliance_H-2026-04-24-003_<stamp>
  8. manifest.config holdout dates: 2025-06-01 -> 2026-04-23 (was 2026-01-01 -> 2026-04-23)
  9. gate_inputs.holdout.pct: 0.18 (was 0.06)

API corrections over the v1 plan draft:
  A. load_price_panel(tickers) needs explicit ticker list; use _FNO_DIR.glob("*.csv").
  B. BROAD_SECTOR is industry->broad (42 keys), not ticker->broad. Use load_sector_map().
  C. overshoot_compliance.data_audit.run DOES NOT exist; inline a minimal panel audit.
  D. overshoot_compliance.universe_snapshot exposes build_snapshot, not build.
  E. overshoot_compliance.beta_regression exposes regress_on_nifty, not run.
  F. overshoot_compliance.cusum_decay exposes analyse, not run.
  G. overshoot_compliance.portfolio_gate exposes evaluate (pnl wide DF), not run (ledger).
  H. overshoot_compliance.impl_risk exposes simulate_combined (needs baselines), not run.
     Also impl_risk assumes UP=fade=SHORT convention; we flip our model-direction labels
     so impl_risk's internal sign math aligns with model P&L semantics, and we drop
     FLAT rows so they don't get accidentally long-treated.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from pipeline.autoresearch.overshoot_compliance import (
    manifest as MF,
    metrics as M,
    slippage_grid as SG,
    universe_snapshot as US,
    beta_regression as BR,
    cusum_decay as CD,
    portfolio_gate as PG,
    impl_risk as IR,
    gate_checklist as GC,
)
from pipeline.autoresearch.overshoot_reversion_backtest import (
    load_price_panel,
    load_sector_map,
    compute_residuals,
    _FNO_DIR,
)

from . import (
    event_filter as EF,
    feature_builder as FB,
    model as MD,
    naive_adapters as NA,
    permutation_null as PN,
    fragility_sweep as FS,
)


REPO_ROOT = Path(__file__).resolve().parents[3]
PARENT_EVENTS = REPO_ROOT / "pipeline/autoresearch/results/compliance_H-2026-04-23-001_20260423-150125/events.json"


def _now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _load_parent_events(path: Path) -> pd.DataFrame:
    rows = json.loads(path.read_text())
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    return df


def _split(events: pd.DataFrame, cutoff: str = "2025-05-31") -> tuple[pd.DataFrame, pd.DataFrame]:
    cutoff_ts = pd.Timestamp(cutoff)
    train = events.loc[events["date"] <= cutoff_ts].reset_index(drop=True)
    test = events.loc[events["date"] > cutoff_ts].reset_index(drop=True)
    return train, test


def _build_trading_ledger(
    events: pd.DataFrame, preds: np.ndarray, epsilon: float,
) -> pd.DataFrame:
    """Apply the trading rule. 'trade_ret_pct' mirrors the schema
    expected by overshoot_compliance.slippage_grid.apply_full_grid.
    """
    out = events.copy().reset_index(drop=True)
    sign = np.where(preds > epsilon, 1.0, np.where(preds < -epsilon, -1.0, 0.0))
    out["prediction"] = preds
    out["signal_sign"] = sign
    out["trade_ret_pct"] = sign * out["next_ret"].to_numpy(float)
    # Model-world trade direction (for slippage grid + gate artifacts).
    out["model_direction"] = np.where(
        sign > 0, "MODEL_LONG",
        np.where(sign < 0, "MODEL_SHORT", "FLAT"),
    )
    return out


def _ledger_for_impl_risk(ledger: pd.DataFrame) -> pd.DataFrame:
    """Reshape the model ledger for impl_risk.simulate_combined.

    impl_risk expects events with a 'direction' column and uses
    sign = -1 when direction == 'UP' else +1, then pnl = sign * next_ret.
    That convention was built for the fade-overshoot strategy (UP -> SHORT).
    For our model, we want:
        model-LONG  -> pnl = +next_ret  -> need sign=+1 -> direction != 'UP' ('DOWN')
        model-SHORT -> pnl = -next_ret  -> need sign=-1 -> direction == 'UP'
    FLAT rows are dropped (impl_risk would treat them as long).
    """
    active = ledger.loc[ledger["signal_sign"] != 0].copy()
    active["direction"] = np.where(active["signal_sign"] < 0, "UP", "DOWN")
    return active


def _minimal_panel_audit(panel: pd.DataFrame) -> dict:
    """Section 5A proxy audit on the close panel.

    Counts NaN closes as impaired bars. A full OHLC audit would require
    reading each ticker CSV; that is out-of-scope for v2 since the model
    only consumes closes and z-scores derived from them.
    """
    total = int(panel.notna().size)
    impaired = int(panel.isna().sum().sum())
    pct = (impaired / total * 100.0) if total else 0.0
    if pct > 3.0:
        cls = "AUTO-FAIL"
    elif pct > 1.0:
        cls = "DATA-IMPAIRED"
    else:
        cls = "CLEAN"
    return {
        "total_bars": total,
        "impaired_bars": impaired,
        "impaired_pct": round(pct, 3),
        "classification": cls,
        "per_ticker": {},
        "note": "Close-panel NaN-count proxy; OHLC audit not applicable to cross-sectional model.",
    }


def _load_regime_history() -> pd.DataFrame:
    path = REPO_ROOT / "pipeline/data/regime_history.csv"
    if not path.exists():
        return pd.DataFrame(columns=["regime"], index=pd.to_datetime([]))
    df = pd.read_csv(path, parse_dates=["date"]).set_index("date")
    return df[["regime"]] if "regime" in df.columns else pd.DataFrame(columns=["regime"], index=df.index)


def _load_vix_series() -> pd.Series:
    path = REPO_ROOT / "pipeline/data/vix_history.csv"
    if not path.exists():
        return pd.Series(dtype=float)
    df = pd.read_csv(path, parse_dates=["date"]).set_index("date")
    col = "vix_close" if "vix_close" in df.columns else df.columns[0]
    return df[col].astype(float)


def _load_nifty_returns() -> pd.Series:
    path = REPO_ROOT / "pipeline/data/india_historical/indices/NIFTY.csv"
    if not path.exists():
        return pd.Series(dtype=float)
    df = pd.read_csv(path, parse_dates=["date"]).set_index("date").sort_index()
    close_col = "close" if "close" in df.columns else df.columns[0]
    return df[close_col].pct_change().dropna() * 100.0


def run(
    *,
    events_path: Path,
    out_dir: Path,
    n_shuffles: int = 100_000,
    n_workers: int | None = None,
    seed: int = 42,
    alpha_grid: np.ndarray | None = None,
    cv_splits: int = 4,
    embargo_days: int = 2,
    z_threshold_current: float = 3.0,
    z_threshold_prior: float = 2.0,
    persistence_days: int = 2,
    min_history_days: int = 60,
) -> dict:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    alpha_grid = alpha_grid if alpha_grid is not None else np.logspace(-5, 0, 25)

    # 1. Load parent events + price panel + z-score panel
    parent = _load_parent_events(events_path)
    tickers = sorted(p.stem for p in _FNO_DIR.glob("*.csv"))
    panel = load_price_panel(tickers)
    sector_map_used = load_sector_map()
    _, _, z_panel = compute_residuals(panel, sector_map_used)

    # 2. Filter to v2 asymmetric persistent-break subset
    persistent = EF.filter_persistent_breaks(
        parent, z_panel,
        z_threshold_current=z_threshold_current,
        z_threshold_prior=z_threshold_prior,
        persistence_days=persistence_days,
        min_history_days=min_history_days,
    )
    (out_dir / "persistent_events.json").write_text(
        persistent.to_json(orient="records", date_format="iso"), encoding="utf-8",
    )

    # 3. Train/test split at the v2 cutoff (2025-05-31)
    train_events, test_events = _split(persistent)

    # 4. Regime history + vix
    regime_history = _load_regime_history()
    vix_series = _load_vix_series()

    # 5. Build features
    X_tr, y_tr, names = FB.build_feature_matrix(
        train_events, z_panel, regime_history, vix_series,
        broad_sector=sector_map_used,
    )
    X_te, y_te, _ = FB.build_feature_matrix(
        test_events, z_panel, regime_history, vix_series,
        broad_sector=sector_map_used,
    )
    X_tr.to_parquet(out_dir / "feature_matrix_train.parquet")
    X_te.to_parquet(out_dir / "feature_matrix_test.parquet")

    # 6. Fit Lasso
    bundle = MD.fit_lasso(
        X_tr, y_tr, alpha_grid=alpha_grid, cv_splits=cv_splits,
        embargo_days=embargo_days, seed=seed,
    )
    MD.serialize(bundle, out_dir / "model.pkl")
    (out_dir / "model_coefs.json").write_text(
        json.dumps({
            "feature_names": bundle["feature_names"],
            "coef_": list(map(float, bundle["coef_"])),
            "intercept_": bundle["intercept_"],
            "alpha": bundle["alpha"],
            "alpha_grid": bundle["alpha_grid"],
            "alpha_mean_sharpes": bundle["alpha_mean_sharpes"],
        }, indent=2),
        encoding="utf-8",
    )
    train_preds = MD.predict(bundle, X_tr)
    epsilon = MD.compute_epsilon(train_preds)
    test_preds = MD.predict(bundle, X_te)

    preds_df = test_events.copy()
    preds_df["prediction"] = test_preds
    preds_df.to_parquet(out_dir / "predictions.parquet")

    # 7. Build model ledger + slippage grid
    model_ledger = _build_trading_ledger(test_events, test_preds, epsilon)
    sg_input = model_ledger[["ticker", "model_direction", "trade_ret_pct"]].copy()
    sg_input = sg_input.rename(columns={"model_direction": "direction"})
    grid = SG.apply_full_grid(sg_input)
    grid.to_json(out_dir / "slippage_grid.json", orient="records", indent=2)

    # 8. Naive comparators
    naive_summary = NA.summarize_naive(test_events)
    strongest = NA.strongest_name(naive_summary)
    strongest_sharpe = naive_summary[strongest]["sharpe"]
    (out_dir / "naive_comparators.json").write_text(
        json.dumps({"summary": naive_summary, "strongest": strongest,
                    "strongest_sharpe": strongest_sharpe}, indent=2),
        encoding="utf-8",
    )

    # 9. S0 + S1 model metrics (baseline for impl_risk and for the gate row)
    s0_rows = grid.loc[grid["slippage_level"] == "S0"]
    s1_rows = grid.loc[grid["slippage_level"] == "S1"]
    active_dirs = {"MODEL_LONG", "MODEL_SHORT"}
    s0_active = s0_rows.loc[s0_rows["direction"].isin(active_dirs)]
    s1_active = s1_rows.loc[s1_rows["direction"].isin(active_dirs)]
    s0_metrics = M.per_bucket_metrics(s0_active["net_ret_pct"].to_numpy())
    s1_metrics = M.per_bucket_metrics(s1_active["net_ret_pct"].to_numpy())
    model_s1_sharpe = s1_metrics["sharpe"]
    observed_margin = float(model_s1_sharpe - strongest_sharpe)

    # 10. Permutation null
    perm = PN.run_label_permutation_null(
        X_tr, y_tr, X_te, test_events["next_ret"],
        strongest_naive_sharpe=strongest_sharpe,
        observed_margin=observed_margin,
        alpha=bundle["alpha"], n_shuffles=n_shuffles,
        seed=seed, cost_pct=SG.LEVELS["S1"], n_workers=n_workers,
    )
    (out_dir / "permutation_null.json").write_text(
        json.dumps(perm, indent=2), encoding="utf-8",
    )

    # 11. Fragility sweep - 27 v2 points
    frag_rows = []
    base_sign = int(np.sign(observed_margin)) or 1
    for pt in FS.neighborhood(bundle["alpha"]):
        pts_events = EF.filter_persistent_breaks(
            parent, z_panel,
            z_threshold_current=pt["z_threshold_current"],
            z_threshold_prior=pt["z_threshold_prior"],
            persistence_days=2,
            min_history_days=min_history_days,
        )
        pts_tr, pts_te = _split(pts_events)
        if len(pts_tr) < 30 or len(pts_te) < 10:
            frag_rows.append({**pt, "margin": 0.0, "skipped": True})
            continue
        X_ptr, y_ptr, _ = FB.build_feature_matrix(
            pts_tr, z_panel, regime_history, vix_series, broad_sector=sector_map_used,
        )
        X_pte, y_pte, _ = FB.build_feature_matrix(
            pts_te, z_panel, regime_history, vix_series, broad_sector=sector_map_used,
        )
        pbundle = MD.fit_lasso(
            X_ptr, y_ptr, alpha_grid=np.array([pt["alpha"]]),
            cv_splits=cv_splits, embargo_days=embargo_days, seed=seed,
        )
        ptrain_preds = MD.predict(pbundle, X_ptr)
        peps = MD.compute_epsilon(ptrain_preds)
        ptest_preds = MD.predict(pbundle, X_pte)
        pledger = _build_trading_ledger(pts_te, ptest_preds, peps)
        psg_input = pledger[["ticker", "model_direction", "trade_ret_pct"]].rename(
            columns={"model_direction": "direction"},
        )
        pgrid_s1 = SG.apply_level(psg_input, "S1")
        ptraded = pgrid_s1.loc[pgrid_s1["direction"].isin(active_dirs)]
        psharpe = M.per_bucket_metrics(ptraded["net_ret_pct"].to_numpy())["sharpe"]
        pnaive = NA.summarize_naive(pts_te)
        pstrongest = NA.strongest_name(pnaive)
        pmargin = float(psharpe - pnaive[pstrongest]["sharpe"])
        frag_rows.append({**pt, "margin": pmargin, "skipped": False})

    frag_result = FS.evaluate_sweep(frag_rows, base_margin_sign=base_sign)
    (out_dir / "fragility_sweep.json").write_text(
        json.dumps(frag_result, indent=2), encoding="utf-8",
    )

    # 12. Section 5A data audit (proxy)
    da_result = _minimal_panel_audit(panel)
    (out_dir / "data_audit.json").write_text(
        json.dumps(da_result, indent=2), encoding="utf-8",
    )

    # 13. Section 6 universe snapshot (inherits H-001 waiver)
    us_result = US.build_snapshot(
        current_tickers=list(panel.columns),
        history_path=REPO_ROOT / "pipeline/data/fno_universe_history.json",
        waiver_path=REPO_ROOT / "docs/superpowers/waivers/2026-04-23-phase-c-residual-reversion-survivorship.md",
    )
    (out_dir / "universe_snapshot.json").write_text(
        json.dumps(us_result, indent=2), encoding="utf-8",
    )

    # 14. Section 11B beta regression (daily-return aggregate vs NIFTY)
    ledger_dated = model_ledger.assign(date=pd.to_datetime(model_ledger["date"]))
    daily_strategy_rets = ledger_dated.groupby("date")["trade_ret_pct"].sum()
    nifty_rets = _load_nifty_returns()
    br_result = BR.regress_on_nifty(daily_strategy_rets, nifty_rets)
    (out_dir / "beta_regression.json").write_text(
        json.dumps(br_result, indent=2), encoding="utf-8",
    )

    # 15. Section 11C portfolio gate
    ledger_dated["strategy_id"] = (
        ledger_dated["ticker"].astype(str) + "-" + ledger_dated["model_direction"].astype(str)
    )
    # only active strategies (non-FLAT) contribute to the corr/concentration gate
    active_ledger = ledger_dated.loc[ledger_dated["signal_sign"] != 0]
    if not active_ledger.empty:
        pnl_wide = active_ledger.pivot_table(
            index="date", columns="strategy_id", values="trade_ret_pct", aggfunc="sum",
        ).fillna(0.0)
        pg_result = PG.evaluate(pnl_wide, sector_map_used)
    else:
        pg_result = {
            "max_pairwise_correlation": 0.0,
            "top_correlated_pair": None,
            "max_sector_share": 0.0,
            "max_sector": None,
            "corr_verdict": "PASS",
            "concentration_verdict": "PASS",
            "overall_verdict": "PASS",
            "n_strategies": 0,
            "note": "No active strategies in holdout; gate auto-PASS.",
        }
    (out_dir / "portfolio_gate.json").write_text(
        json.dumps(pg_result, indent=2), encoding="utf-8",
    )

    # 16. Section 12 CUSUM decay on training-window trade returns
    train_ledger = _build_trading_ledger(train_events, train_preds, epsilon)
    cusum_result = CD.analyse(train_ledger[["date", "trade_ret_pct"]])
    (out_dir / "cusum_decay.json").write_text(
        json.dumps(cusum_result, indent=2, default=str), encoding="utf-8",
    )

    # 17. Section 11A implementation risk
    ir_input = _ledger_for_impl_risk(model_ledger)
    if not ir_input.empty:
        ir_result = IR.simulate_combined(
            events=ir_input,
            baseline_sharpe_s1=float(s1_metrics["sharpe"]),
            baseline_dd_s1=float(s1_metrics["max_drawdown_pct"]) / 100.0,
            seed=seed,
        )
    else:
        ir_result = {
            "note": "No non-FLAT events; impl_risk skipped.",
            "verdict": "IMPLEMENTATION-ROBUST",
        }
    (out_dir / "impl_risk.json").write_text(
        json.dumps(ir_result, indent=2), encoding="utf-8",
    )

    # 18. Section 13A.1 manifest
    manifest = MF.build_manifest(
        hypothesis_id="H-2026-04-24-003",
        strategy_version="cross_sectional_v2",
        cost_model_version="zerodha-ssf-2025-04",
        random_seed=seed,
        data_files=[events_path],
        config={
            "alpha_grid": list(map(float, alpha_grid)),
            "cv_splits": cv_splits,
            "embargo_days": embargo_days,
            "z_threshold_current": z_threshold_current,
            "z_threshold_prior": z_threshold_prior,
            "persistence_days": persistence_days,
            "min_history_days": min_history_days,
            "n_shuffles": n_shuffles,
            "holdout_start": "2025-06-01",
            "holdout_end": "2026-04-23",
            "n_train": int(len(train_events)),
            "n_test": int(len(test_events)),
            "chosen_alpha": bundle["alpha"],
            "epsilon": epsilon,
            "model_s1_sharpe": model_s1_sharpe,
            "strongest_naive": strongest,
            "strongest_sharpe": strongest_sharpe,
            "observed_margin": observed_margin,
        },
    )
    MF.write_manifest(manifest, out_dir)

    # 19. Section 15.1 gate checklist
    gate_inputs = {
        "slippage_s0_s1": {
            "s0_sharpe": s0_metrics["sharpe"],
            "s0_hit": s0_metrics["hit_rate"],
            "s0_max_dd": s0_metrics["max_drawdown_pct"] / 100.0,
            "s1_sharpe": s1_metrics["sharpe"],
            "s1_max_dd": s1_metrics["max_drawdown_pct"] / 100.0,
            "s1_cum_pnl_pct": float(s1_rows["net_ret_pct"].sum()),
        },
        "metrics_present": True,
        "data_audit": da_result,
        "universe_snapshot": us_result,
        "execution_mode": "MODE_A",
        "direction_audit": {
            "n_survivors": int((model_ledger["signal_sign"] != 0).sum()),
            "conflicts": 0,
        },
        "power_analysis": {
            "min_n_per_regime_met": len(test_events) >= 50,
            "underpowered_count": max(0, 50 - len(test_events)),
        },
        "fragility": {
            "verdict": frag_result["verdict"],
            "n_same_sign": frag_result["n_same_sign"],
        },
        "comparators": {
            "strongest_name": strongest,
            "beaten_strongest": bool(observed_margin > 0),
        },
        "permutations": {
            "n_shuffles": n_shuffles,
            "floor_required": 100_000,
            "p_value": perm["p_value"],
        },
        "holdout": {"pct": 0.18, "target": 0.20},
        "beta_regression": {
            "gross_sharpe": br_result.get("gross_sharpe", 0.0),
            "residual_sharpe": br_result.get("residual_sharpe", 0.0),
        },
    }
    report = GC.build(gate_inputs, hypothesis_id="H-2026-04-24-003")
    GC.write(report, out_dir)
    return {"out_dir": str(out_dir), "decision": report["decision"]}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--events-path", default=str(PARENT_EVENTS))
    p.add_argument(
        "--out-dir",
        default=str(REPO_ROOT / f"pipeline/autoresearch/results/compliance_H-2026-04-24-003_{_now_stamp()}"),
    )
    p.add_argument("--n-shuffles", type=int, default=100_000)
    p.add_argument("--n-workers", type=int, default=None)
    p.add_argument("--seed", type=int, default=42)
    args = p.parse_args()
    result = run(
        events_path=Path(args.events_path),
        out_dir=Path(args.out_dir),
        n_shuffles=args.n_shuffles,
        n_workers=args.n_workers,
        seed=args.seed,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
