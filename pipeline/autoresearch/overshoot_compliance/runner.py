"""End-to-end compliance runner for H-2026-04-23-001.

Usage:
  python -m pipeline.autoresearch.overshoot_compliance.runner \
      --out-dir pipeline/autoresearch/results/compliance_H-2026-04-23-001_<stamp> \
      [--smoke]
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from pipeline.autoresearch.overshoot_reversion_backtest import (
    classify_events,
    compute_residuals,
    load_price_panel,
    load_sector_map,
    MIN_COHORT_SIZE,
)
from pipeline.autoresearch.overshoot_per_ticker_stats import (
    per_ticker_fade_stats,
    _today_breaks,
)

from . import (
    beta_regression,
    cusum_decay,
    data_audit,
    defense_filter,
    direction_audit,
    execution_window,
    fragility,
    gate_checklist,
    impl_risk,
    imputer_sector_beta,
    manifest,
    metrics,
    naive_comparators,
    portfolio_gate,
    slippage_grid,
    universe_snapshot,
)

_REPO = Path(__file__).resolve().parents[3]
_FNO_DIR = _REPO / "pipeline" / "data" / "fno_historical"
_UNIVERSE_HIST = _REPO / "pipeline" / "data" / "fno_universe_history.json"
_WAIVER = _REPO / "docs" / "superpowers" / "waivers" / "2026-04-23-phase-c-residual-reversion-survivorship.md"
_BREAKS = _REPO / "pipeline" / "data" / "correlation_breaks.json"
_COST_MODEL_VERSION = "zerodha-ssf-2025-04"
_STRATEGY_VERSION = "0.1.0"
_HYPOTHESIS_ID = "H-2026-04-23-001"
_EXECUTION_MODE = "MODE_A"
_SENSITIVITY_MIN_OBS = 60


def _build_strategy_pnl_panel(events: pd.DataFrame) -> pd.DataFrame:
    ev = events.copy()
    ev["date"] = pd.to_datetime(ev["date"])
    ev["pnl_pct"] = np.where(ev["direction"].eq("UP"), -1.0, 1.0) * ev["next_ret"]
    ev["key"] = ev["ticker"] + "-" + ev["direction"]
    panel = ev.pivot_table(index="date", columns="key", values="pnl_pct", aggfunc="mean")
    return panel.fillna(0.0)


def _load_nifty_returns() -> pd.Series:
    p = _FNO_DIR / "NIFTY.csv"
    if not p.exists():
        return pd.Series(dtype=float)
    df = pd.read_csv(p, parse_dates=["Date"]).sort_values("Date").set_index("Date")
    return df["Close"].pct_change().dropna()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument(
        "--research-sensitivity",
        action="store_true",
        help="Run sector-beta imputation on missing bars and emit "
             "metrics_grid_sensitivity.json + sensitivity_manifest.json alongside "
             "the authoritative raw-only artifacts. Gate-checklist never reads them.",
    )
    args = parser.parse_args(argv)

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)

    sector_of = load_sector_map()
    if args.smoke:
        sector_of = {t: s for i, (t, s) in enumerate(sector_of.items()) if i < 5}
    tickers = sorted(sector_of.keys())

    closes = load_price_panel(tickers)

    # Step 1 - manifest
    price_files = [p for p in (_FNO_DIR / f"{t}.csv" for t in tickers) if p.exists()]
    m = manifest.build_manifest(
        hypothesis_id=_HYPOTHESIS_ID,
        strategy_version=_STRATEGY_VERSION,
        cost_model_version=_COST_MODEL_VERSION,
        random_seed=42,
        data_files=price_files,
        config={"smoke": args.smoke, "n_tickers": len(tickers), "min_cohort_size": MIN_COHORT_SIZE},
    )
    manifest.write_manifest(m, out)

    # Step 2 - data audit + per-ticker flagged-dates map (raw-bar canonicity)
    # Load frames first so we can build the observed NSE trading calendar from
    # long-history tickers (encodes exchange holidays without external dep).
    ticker_frames: dict[str, pd.DataFrame] = {}
    for t in tickers:
        p = _FNO_DIR / f"{t}.csv"
        if not p.exists():
            continue
        df = pd.read_csv(p, parse_dates=["Date"]).sort_values("Date").drop_duplicates("Date", keep="last").set_index("Date")
        ticker_frames[t] = df

    long_hist_dates: set[pd.Timestamp] = set()
    for t, df in ticker_frames.items():
        if len(df) >= 1000:
            long_hist_dates.update(pd.DatetimeIndex(df.index).normalize())
    if long_hist_dates:
        bdays = pd.DatetimeIndex(sorted(long_hist_dates))
    elif not closes.empty:
        bdays = pd.bdate_range(closes.index.min(), closes.index.max())
    else:
        bdays = pd.DatetimeIndex([])

    per_ticker = {}
    flagged_by_ticker: dict[str, dict] = {}
    for t, df in ticker_frames.items():
        per_ticker[t] = data_audit.audit_ticker(t, df, bdays)
        flagged_by_ticker[t] = execution_window.build_flagged_dates(t, df, bdays)
    da = data_audit.aggregate(per_ticker) if per_ticker else {"classification": "INSUFFICIENT_DATA", "impaired_pct": 0.0, "total_bars": 0, "impaired_bars": 0, "per_ticker": {}}
    (out / "data_audit.json").write_text(json.dumps(da, indent=2, default=str), encoding="utf-8")

    # Step 3 - universe snapshot
    us = universe_snapshot.build_snapshot(tickers, _UNIVERSE_HIST, _WAIVER)
    (out / "universe_snapshot.json").write_text(json.dumps(us, indent=2, default=str), encoding="utf-8")

    # Step 4 - residuals at windows 15, 20, 25 for fragility
    events_by_window: dict[int, pd.DataFrame] = {}
    import pipeline.autoresearch.overshoot_reversion_backtest as ORB
    for w in (15, 20, 25):
        old_w = ORB.ROLL_STD_WINDOW
        ORB.ROLL_STD_WINDOW = w
        try:
            if closes.empty:
                events_by_window[w] = pd.DataFrame()
                continue
            _, resids, zs = compute_residuals(closes, sector_of)
            returns = closes.pct_change() * 100
            ev_list = classify_events(returns, resids, zs)
            ev_df = pd.DataFrame(ev_list)
            if not ev_df.empty:
                ev_df["direction"] = np.where(ev_df["z"] > 0, "UP", "DOWN")
            events_by_window[w] = ev_df
        finally:
            ORB.ROLL_STD_WINDOW = old_w

    # Step 4b - raw-bar canonicity gate (drops invalid trades from every window)
    invalid_trades: list[dict] = []
    filtered_events_by_window: dict[int, pd.DataFrame] = {}
    for w, ev_df in events_by_window.items():
        if ev_df.empty:
            filtered_events_by_window[w] = ev_df
            continue
        valid_rows: list[int] = []
        for idx, row in ev_df.iterrows():
            audit = {"flagged_dates": flagged_by_ticker.get(row["ticker"], {})}
            valid, reasons = execution_window.is_tradeable(
                row["ticker"], row["date"], _EXECUTION_MODE, audit,
            )
            if valid:
                valid_rows.append(idx)
            elif w == 20:
                invalid_trades.append({
                    "ticker": row["ticker"],
                    "date": str(pd.Timestamp(row["date"]).normalize().date()),
                    "direction": row.get("direction"),
                    "z": float(row.get("z", 0.0)),
                    "mode": _EXECUTION_MODE,
                    "reasons": reasons,
                })
        filtered_events_by_window[w] = ev_df.loc[valid_rows].reset_index(drop=True)
    events_by_window = filtered_events_by_window
    events = events_by_window[20]

    n_scored = int(sum(len(df) for df in events_by_window.values()))
    rejection_rate = len(invalid_trades) / max(1, len(invalid_trades) + len(events))
    (out / "invalid_trades.json").write_text(json.dumps({
        "mode": _EXECUTION_MODE,
        "n_invalid": len(invalid_trades),
        "rejection_rate_pct": round(rejection_rate * 100.0, 3),
        "trades": invalid_trades,
    }, indent=2, default=str), encoding="utf-8")

    m["invalid_trade_count"] = len(invalid_trades)
    m["invalid_trade_log_path"] = "invalid_trades.json"
    if len(events) > 0 and rejection_rate > 0.05:
        m.setdefault("warnings", []).append("WARN_HIGH_REJECTION_RATE")
    manifest.write_manifest(m, out)

    # Step 5 - per-ticker fade stats
    n_shuffles = 500 if args.smoke else 100_000
    ticker_returns = {c: closes[c].pct_change().dropna().mul(100).tolist() for c in closes.columns} if not closes.empty else {}
    ev_as_dicts = events.to_dict("records") if len(events) else []
    fade_rows = per_ticker_fade_stats(
        ev_as_dicts, ticker_returns, min_z=3.0,
        n_shuffles=n_shuffles, seed=42,
    ) if ev_as_dicts else []

    # Step 6 - slippage grid + metrics
    if not events.empty:
        events["trade_ret_pct"] = np.where(events["direction"].eq("UP"), -1.0, 1.0) * events["next_ret"]
    grid_rows = []
    for lvl in ("S0", "S1", "S2", "S3"):
        if events.empty:
            continue
        grid = slippage_grid.apply_level(events, lvl)
        for (tk, direction), sub in grid.groupby(["ticker", "direction"]):
            core = metrics.per_bucket_metrics(sub["net_ret_pct"].to_numpy())
            grid_rows.append({"ticker": tk, "direction": direction, "level": lvl, **core})
    (out / "metrics_grid.json").write_text(json.dumps({"rows": grid_rows}, indent=2, default=str), encoding="utf-8")

    # Step 7 - naive comparators
    comp_suite = naive_comparators.run_suite(events, seed=42) if not events.empty else {}
    strat_mean = float(events["trade_ret_pct"].mean()) if not events.empty else 0.0
    strongest_name = max(comp_suite, key=lambda k: comp_suite[k]["mean_ret_pct"]) if comp_suite else None
    strongest_mean = comp_suite[strongest_name]["mean_ret_pct"] if strongest_name else 0.0
    (out / "comparators.json").write_text(json.dumps({
        "strategy_mean_ret_pct": strat_mean,
        "comparators": comp_suite,
        "strongest_name": strongest_name,
        "beaten_strongest": strat_mean > strongest_mean,
    }, indent=2, default=str), encoding="utf-8")

    # Step 8 - permutation summary
    (out / "permutations_100k.json").write_text(json.dumps({
        "n_shuffles": n_shuffles,
        "floor_required": 100_000 if not args.smoke else 500,
        "rows": fade_rows,
    }, indent=2, default=str), encoding="utf-8")

    # Step 9 - fragility
    if all(not events_by_window[w].empty for w in (15, 20, 25)):
        fr = fragility.evaluate(events_by_window, {"min_z": 3.0, "roll_window": 20, "cost_pct": 0.30})
    else:
        fr = {"verdict": "INSUFFICIENT_DATA", "neighbor_rows": []}
    (out / "fragility.json").write_text(json.dumps(fr, indent=2, default=str), encoding="utf-8")

    # Step 10 - beta regression
    panel = _build_strategy_pnl_panel(events) if not events.empty else pd.DataFrame()
    nifty_rets = _load_nifty_returns()
    beta_rows: dict = {}
    if not panel.empty and not nifty_rets.empty:
        for col in panel.columns:
            beta_rows[col] = beta_regression.regress_on_nifty(panel[col] / 100.0, nifty_rets)
    gross_sharpe_avg = float(np.mean([v["gross_sharpe"] for v in beta_rows.values()])) if beta_rows else 0.0
    residual_sharpe_avg = float(np.mean([v["residual_sharpe"] for v in beta_rows.values()])) if beta_rows else 0.0
    (out / "beta_residual.json").write_text(json.dumps({
        "gross_sharpe_avg": gross_sharpe_avg,
        "residual_sharpe_avg": residual_sharpe_avg,
        "per_strategy": beta_rows,
    }, indent=2, default=str), encoding="utf-8")

    # Step 11 - impl-risk
    if not events.empty:
        ir = impl_risk.simulate_combined(
            events[["ticker", "direction", "date", "next_ret"]],
            baseline_sharpe_s1=gross_sharpe_avg * 0.8 if gross_sharpe_avg else 0.0,
            baseline_dd_s1=0.15, seed=42,
        )
    else:
        ir = {"verdict": "INSUFFICIENT_DATA"}
    (out / "impl_risk.json").write_text(json.dumps(ir, indent=2, default=str), encoding="utf-8")

    # Step 12 - CUSUM decay
    if not events.empty:
        cd = cusum_decay.analyse(events[["date", "trade_ret_pct"]])
    else:
        cd = {"verdict": "INSUFFICIENT_DATA"}
    (out / "cusum_decay.json").write_text(json.dumps(cd, indent=2, default=str), encoding="utf-8")

    # Step 13 - portfolio gate + defense filter
    survivors = [r for r in fade_rows if r.get("edge_net_pct", 0) > 0 and r.get("p_value", 1.0) <= 1.17e-4]
    kept, flagged = defense_filter.partition(survivors, sector_of)
    keys_kept = {f"{r['ticker']}-{r['direction']}" for r in kept}
    pnl_survivors = panel[[c for c in panel.columns if c in keys_kept]] if not panel.empty else pd.DataFrame()
    if not pnl_survivors.empty:
        pg = portfolio_gate.evaluate(
            pnl_survivors,
            sectors={f"{t}-{d}": sector_of.get(t, "Unmapped") for t in tickers for d in ("UP", "DOWN")},
        )
    else:
        pg = {"overall_verdict": "NO_SURVIVORS", "n_strategies": 0}
    (out / "portfolio_gate.json").write_text(json.dumps({
        "gate": pg, "kept": kept, "defense_flagged": flagged,
    }, indent=2, default=str), encoding="utf-8")

    # Step 14 - direction audit
    engine_calls: dict = {}
    try:
        breaks = _today_breaks()
    except Exception:
        breaks = []
    for b in breaks:
        t = b.get("symbol")
        z = b.get("z_score") or 0
        exp_ret = b.get("expected_return") or 0
        if t:
            engine_calls[t] = {"direction": "LONG" if exp_ret >= 0 else "SHORT", "z": z}
    direction_ad = direction_audit.audit(kept, engine_calls)
    (out / "direction_audit.json").write_text(json.dumps(direction_ad, indent=2, default=str), encoding="utf-8")

    # Step 15 - gate checklist
    s0_rows = [r for r in grid_rows if r["level"] == "S0"]
    s1_rows = [r for r in grid_rows if r["level"] == "S1"]
    s0_sharpe = float(np.mean([r["sharpe"] for r in s0_rows])) if s0_rows else 0.0
    s0_hit = float(np.mean([r["hit_rate"] for r in s0_rows])) if s0_rows else 0.0
    s0_dd = float(np.mean([r["max_drawdown_pct"] for r in s0_rows]) / 100.0) if s0_rows else 0.0
    s1_sharpe = float(np.mean([r["sharpe"] for r in s1_rows])) if s1_rows else 0.0
    s1_dd = float(np.mean([r["max_drawdown_pct"] for r in s1_rows]) / 100.0) if s1_rows else 0.0
    s1_cum = float(np.sum([r["mean_ret_pct"] * r["n_trades"] for r in s1_rows])) if s1_rows else 0.0
    min_n_ok = bool(s0_rows) and all(r["n_trades"] >= 30 for r in s0_rows)

    checklist_inputs = {
        "slippage_s0_s1": {"s0_sharpe": s0_sharpe, "s0_hit": s0_hit, "s0_max_dd": s0_dd,
                            "s1_sharpe": s1_sharpe, "s1_max_dd": s1_dd, "s1_cum_pnl_pct": s1_cum},
        "metrics_present": bool(grid_rows),
        "data_audit": {"classification": da["classification"], "impaired_pct": da["impaired_pct"]},
        "universe_snapshot": us,
        "execution_mode": "MODE_A",
        "direction_audit": {"conflicts": direction_ad.get("conflicts", 0),
                            "n_survivors": direction_ad.get("n_survivors", 0)},
        "power_analysis": {"min_n_per_regime_met": min_n_ok,
                            "underpowered_count": sum(1 for r in s0_rows if r["n_trades"] < 30)},
        "fragility": {"verdict": fr.get("verdict", "UNKNOWN")},
        "comparators": {"beaten_strongest": strat_mean > strongest_mean, "strongest_name": strongest_name or "none"},
        "permutations": {"n_shuffles": n_shuffles, "floor_required": 100_000 if not args.smoke else 500},
        "holdout": {"pct": 0.06, "target": 0.20},
        "beta_regression": {"residual_sharpe": residual_sharpe_avg, "gross_sharpe": gross_sharpe_avg},
    }
    gc_report = gate_checklist.build(checklist_inputs, hypothesis_id=_HYPOTHESIS_ID)
    gate_checklist.write(gc_report, out)

    # Step 16 - sensitivity track (parallel, never read by gate_checklist)
    if args.research_sensitivity:
        _write_sensitivity_artifacts(
            out, tickers, ticker_frames, per_ticker, flagged_by_ticker,
            nifty_rets=nifty_rets, min_obs=_SENSITIVITY_MIN_OBS,
        )

    return 0


def _write_sensitivity_artifacts(
    out: Path,
    tickers: list[str],
    ticker_frames: dict,
    per_ticker_audit: dict,
    flagged_by_ticker: dict,
    *,
    nifty_rets: pd.Series,
    min_obs: int,
) -> None:
    """Parallel analytical-aid emission per §5 of the canonicity policy.

    Invokes the sector-beta imputer for every `missing` bar in every ticker's
    audit. The authoritative compliance path is untouched; this writes two
    artifacts that the gate checklist MUST NOT read:

    - metrics_grid_sensitivity.json: per-ticker imputation counts + proxy beta stats
    - sensitivity_manifest.json: imputer config, policy pointer, timestamps
    """
    imputed_rows: list[dict] = []
    n_imputed = 0
    n_failed = 0
    for t in tickers:
        df = ticker_frames.get(t)
        if df is None or df.empty:
            continue
        flagged = flagged_by_ticker.get(t, {})
        missing_dates = [dt for dt, flags in flagged.items() if "missing" in flags]
        if not missing_dates:
            continue
        close = df["Close"].astype(float)
        t_rets = close.pct_change().dropna()
        proxy: list[dict] = []
        for gap in missing_dates:
            r_sec = float(nifty_rets.loc[nifty_rets.index.normalize() == pd.Timestamp(gap).normalize()].sum()) \
                if not nifty_rets.empty else 0.0
            res = imputer_sector_beta.impute(
                ticker_returns=t_rets,
                sector_returns=nifty_rets,
                raw_close=close,
                gap_date=gap,
                sector_return_at_t=r_sec,
                min_obs=min_obs,
            )
            if res is None:
                n_failed += 1
                continue
            n_imputed += 1
            proxy.append({
                "date": str(pd.Timestamp(gap).normalize().date()),
                "P_imputed": round(res["P_imputed"], 4),
                "beta_value": round(res["beta_value"], 6),
                "r_sector_used": round(res["r_sector_used"], 6),
                "source": res["source"],
            })
        if proxy:
            imputed_rows.append({"ticker": t, "n_imputed": len(proxy), "samples": proxy[:5]})

    (out / "metrics_grid_sensitivity.json").write_text(json.dumps({
        "track": "sensitivity",
        "n_imputed_bars": n_imputed,
        "n_imputation_failures": n_failed,
        "per_ticker": imputed_rows,
        "note": "Sector-beta proxy. Raw compliance path (metrics_grid.json) is authoritative.",
    }, indent=2, default=str), encoding="utf-8")

    (out / "sensitivity_manifest.json").write_text(json.dumps({
        "imputer": "sector_beta",
        "policy_ref": "docs/superpowers/policies/2026-04-23-raw-bar-canonicity.md",
        "min_obs": min_obs,
        "sector_index": "NIFTY",
        "n_imputed_bars": n_imputed,
        "n_imputation_failures": n_failed,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }, indent=2, default=str), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
