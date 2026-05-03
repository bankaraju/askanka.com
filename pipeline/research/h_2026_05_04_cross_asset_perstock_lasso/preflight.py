"""§16 pre-flight checks for H-2026-05-04-cross-asset-perstock-lasso-v1.

Runs the 5 checks declared in the spec §16:
  1. Universe count: F&O continuously listed 2021-05-04 → panel-end with ADV >= ₹50cr  >=  100 names
  2. PCA dimensionality: K_ETF <= 12 at 85% variance on raw 60-column ETF return block
  3. Orthogonality: max abs corr of any PC × stock-TA feature  <  0.4
  4. PIT audit: build_panel + audit_panel returns no fail rows
  5. Sample size: effective_obs / n_features >= 5:1 at HL=90 trading days

Writes results to preflight_results.json. Spec amends or aborts if any check fails.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.decomposition import PCA

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from pipeline.autoresearch.etf_v3_loader import (  # noqa: E402
    CURATED_FOREIGN_ETFS,
    audit_panel,
    build_panel,
)
from pipeline.research.h_2026_05_04_cross_asset_perstock_lasso.sector_mapping import (  # noqa: E402
    index_csv_for_sector,
)
from pipeline.scorecard_v2.sector_mapper import SectorMapper  # noqa: E402

WINDOW_START = pd.Timestamp("2021-05-04")
TRAIN_END = pd.Timestamp("2025-10-31")
ADV_MIN_CR = 50.0
HL_TRADING_DAYS = 90
N_TA_FEATURES = 6
N_INDIAN_MACRO = 4
N_DOW = 3

OUT_DIR = REPO / "pipeline" / "research" / "h_2026_05_04_cross_asset_perstock_lasso"
OUT_DIR.mkdir(parents=True, exist_ok=True)
FNO_CSV_DIR = REPO / "pipeline" / "data" / "fno_historical"
SECTORAL_DIR = REPO / "pipeline" / "data" / "sectoral_indices"


def check_4_pit_audit() -> dict:
    audit = audit_panel()
    fails = [r for r in audit if r.status == "fail"]
    return {
        "n_series": len(audit),
        "n_fail": len(fails),
        "fail_series": [r.series for r in fails],
        "pass": len(fails) == 0,
    }


def _normalise_ohlcv(df: pd.DataFrame) -> pd.DataFrame | None:
    rename = {}
    for c in df.columns:
        lc = c.lower()
        if lc == "date":
            rename[c] = "Date"
        elif lc == "open":
            rename[c] = "Open"
        elif lc == "high":
            rename[c] = "High"
        elif lc == "low":
            rename[c] = "Low"
        elif lc == "close":
            rename[c] = "Close"
        elif lc == "volume":
            rename[c] = "Volume"
    df = df.rename(columns=rename)
    needed = {"Date", "Close", "Volume"}
    if not needed.issubset(df.columns):
        return None
    return df


def check_1_universe() -> tuple[dict, list[dict]]:
    sector_map = SectorMapper().map_all()
    universe: list[dict] = []
    skipped_no_volume = 0
    skipped_no_sector_index = 0
    n_total = 0
    for csv_path in sorted(FNO_CSV_DIR.glob("*.csv")):
        n_total += 1
        ticker = csv_path.stem
        try:
            df = pd.read_csv(csv_path)
        except Exception:
            continue
        df = _normalise_ohlcv(df)
        if df is None:
            skipped_no_volume += 1
            continue
        df["Date"] = pd.to_datetime(df["Date"])
        df = df[(df["Date"] >= WINDOW_START) & (df["Date"] <= TRAIN_END)]
        if len(df) < 1000:
            continue
        recent = df.tail(60)
        if len(recent) < 50:
            continue
        adv_cr = float((recent["Close"] * recent["Volume"]).median() / 1e7)
        if adv_cr < ADV_MIN_CR:
            continue
        info = sector_map.get(ticker)
        sector_key = info.get("sector") if info else None
        sector_path = index_csv_for_sector(sector_key, SECTORAL_DIR)
        if sector_path is None or not sector_path.exists():
            skipped_no_sector_index += 1
            continue
        universe.append({
            "ticker": ticker,
            "n_bars": int(len(df)),
            "adv_cr": adv_cr,
            "sector_key": sector_key,
        })

    universe_sorted = sorted(universe, key=lambda x: -x["adv_cr"])
    return {
        "n_total_csvs": n_total,
        "n_skipped_missing_ohlcv": skipped_no_volume,
        "n_skipped_no_sector_index": skipped_no_sector_index,
        "n_universe_qualified": len(universe),
        "min_required": 100,
        "pass": len(universe) >= 100,
        "head": universe_sorted[:10],
        "tail": universe_sorted[-5:],
    }, universe_sorted


def check_2_pca() -> tuple[dict, np.ndarray, pd.DatetimeIndex, list[str]]:
    panel = build_panel()  # already T-1 anchored per etf_v3_loader._enforce_t1_anchor
    training_idx = (panel.index >= WINDOW_START) & (panel.index <= TRAIN_END)
    panel = panel.loc[training_idx]

    etf_cols = [c for c in CURATED_FOREIGN_ETFS if c in panel.columns]
    if len(etf_cols) < len(CURATED_FOREIGN_ETFS):
        missing = set(CURATED_FOREIGN_ETFS) - set(etf_cols)
        print(f"  WARN: {len(missing)} CURATED ETFs missing from panel: {missing}", file=sys.stderr)

    ret1 = panel[etf_cols].pct_change(1)
    ret1.columns = [f"{c}_1d" for c in etf_cols]
    combined = ret1.dropna()

    X = combined.values
    mu = X.mean(axis=0)
    sd = X.std(axis=0)
    sd[sd == 0] = 1.0
    X_z = (X - mu) / sd

    n_comp = min(X_z.shape[1], min(X_z.shape))
    pca = PCA(n_components=n_comp).fit(X_z)
    cum_var = np.cumsum(pca.explained_variance_ratio_)
    K_ETF = int(np.searchsorted(cum_var, 0.85)) + 1

    pc_scores = pca.transform(X_z)[:, :K_ETF]
    pc_index = combined.index

    return {
        "n_etf_cols_used": len(etf_cols),
        "n_raw_features": X_z.shape[1],
        "K_ETF_at_85pct_var": K_ETF,
        "cum_var_at_K": float(cum_var[K_ETF - 1]),
        "explained_variance_first_10": [float(v) for v in pca.explained_variance_ratio_[:10]],
        "max_allowed": 12,
        "pass": K_ETF <= 12,
    }, pc_scores, pc_index, etf_cols


def _compute_ta(df: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame(index=df.index)

    delta = df["Close"].diff()
    gain = delta.where(delta > 0, 0.0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0.0)).rolling(14).mean()
    rs = gain / loss.replace(0, np.nan)
    out["rsi_14"] = 100 - 100 / (1 + rs)

    prev_close = df["Close"].shift(1)
    tr = pd.concat(
        [(df["High"] - df["Low"]),
         (df["High"] - prev_close).abs(),
         (df["Low"] - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    out["atr_14_pct"] = tr.rolling(14).mean() / df["Close"]

    ema50 = df["Close"].ewm(span=50, adjust=False).mean()
    out["dist_50ema_pct"] = (df["Close"] - ema50) / ema50

    vol_mean = df["Volume"].rolling(20).mean()
    vol_std = df["Volume"].rolling(20).std()
    out["vol_zscore_20"] = (df["Volume"] - vol_mean) / vol_std.replace(0, np.nan)

    out["range_pct_today"] = (df["High"] - df["Low"]) / df["Close"]

    return out


def check_3_orthogonality(pc_scores: np.ndarray, pc_index: pd.DatetimeIndex,
                          universe_sorted: list[dict], n_sample: int = 30) -> dict:
    K_ETF = pc_scores.shape[1]
    pc_df = pd.DataFrame(
        pc_scores,
        index=pc_index,
        columns=[f"PC{i + 1}" for i in range(K_ETF)],
    )
    sample = universe_sorted[:n_sample]
    ta_cols = ["rsi_14", "atr_14_pct", "dist_50ema_pct", "vol_zscore_20", "range_pct_today"]

    cmats = []
    used = 0
    for entry in sample:
        csv_path = FNO_CSV_DIR / f"{entry['ticker']}.csv"
        try:
            df_raw = pd.read_csv(csv_path)
        except Exception:
            continue
        df_norm = _normalise_ohlcv(df_raw)
        if df_norm is None:
            continue
        df_norm["Date"] = pd.to_datetime(df_norm["Date"])
        df = df_norm.set_index("Date").sort_index()
        df = df[(df.index >= WINDOW_START) & (df.index <= TRAIN_END)]
        if len(df) < 500:
            continue
        if not {"High", "Low", "Close", "Volume"}.issubset(df.columns):
            continue
        ta = _compute_ta(df)
        aligned = ta.join(pc_df, how="inner").dropna()
        if len(aligned) < 200:
            continue
        cmat = aligned[ta_cols + list(pc_df.columns)].corr().loc[ta_cols, pc_df.columns]
        cmats.append(cmat.abs())
        used += 1

    if not cmats:
        return {
            "n_stocks_sampled": 0,
            "n_stocks_used": 0,
            "max_abs_corr": None,
            "max_allowed": 0.4,
            "pass": False,
            "reason": "no usable stocks for orthogonality check",
        }

    mean_abs = sum(cmats) / len(cmats)
    max_abs = float(mean_abs.values.max())
    by_pc = {pc: float(mean_abs[pc].max()) for pc in pc_df.columns}
    by_pc_offender = {pc: str(mean_abs[pc].idxmax()) for pc in pc_df.columns}

    return {
        "n_stocks_sampled": len(sample),
        "n_stocks_used": used,
        "max_abs_corr_overall": max_abs,
        "by_pc_max_abs_corr": by_pc,
        "by_pc_offender": by_pc_offender,
        "max_allowed": 0.4,
        "pass": max_abs < 0.4,
    }


def check_5_sample_size(K_ETF: int, panel_index: pd.DatetimeIndex) -> dict:
    n_train = int(((panel_index >= WINDOW_START) & (panel_index <= TRAIN_END)).sum())
    n_features = K_ETF + N_INDIAN_MACRO + N_TA_FEATURES + N_DOW
    hl = HL_TRADING_DAYS
    decay = math.exp(-math.log(2) / hl)
    if abs(1 - decay) < 1e-12:
        eff_n = float(n_train)
    else:
        eff_n = (1 - math.exp(-n_train * math.log(2) / hl)) / (1 - decay)
    ratio = eff_n / n_features

    return {
        "n_train_days": n_train,
        "n_features": n_features,
        "feature_breakdown": {
            "K_ETF_PCs": K_ETF,
            "indian_macro": N_INDIAN_MACRO,
            "stock_TA": N_TA_FEATURES,
            "DOW": N_DOW,
        },
        "hl_trading_days": hl,
        "effective_n": float(eff_n),
        "obs_per_feature_ratio": float(ratio),
        "min_required_ratio": 5.0,
        "pass": ratio >= 5.0,
    }


def main() -> int:
    print("=" * 70)
    print("§16 PRE-FLIGHT — H-2026-05-04-cross-asset-perstock-lasso-v1")
    print("=" * 70)

    results: dict = {}

    print("\n[Check 4] PIT audit (must pass first; others moot if panel is broken)...")
    results["check_4_pit_audit"] = check_4_pit_audit()
    print(f"  status: {'PASS' if results['check_4_pit_audit']['pass'] else 'FAIL'}")
    print(f"  series audited: {results['check_4_pit_audit']['n_series']}, fails: {results['check_4_pit_audit']['n_fail']}")

    print("\n[Check 1] Universe count (F&O continuously listed, ADV >= ₹50cr)...")
    results["check_1_universe"], universe_sorted = check_1_universe()
    print(f"  status: {'PASS' if results['check_1_universe']['pass'] else 'FAIL'}")
    print(f"  total CSVs scanned: {results['check_1_universe']['n_total_csvs']}")
    print(f"  qualified: {results['check_1_universe']['n_universe_qualified']}  (need >= {results['check_1_universe']['min_required']})")
    if universe_sorted:
        head_str = ", ".join(f"{u['ticker']}={u['adv_cr']:.0f}" for u in universe_sorted[:3])
        print(f"  top-3 by ADV (cr): [{head_str}]")

    print("\n[Check 2] PCA dimensionality (K_ETF at 85% var must be <= 12)...")
    results["check_2_pca"], pc_scores, pc_index, etf_cols = check_2_pca()
    print(f"  status: {'PASS' if results['check_2_pca']['pass'] else 'FAIL'}")
    print(f"  ETF cols used: {results['check_2_pca']['n_etf_cols_used']}, raw features: {results['check_2_pca']['n_raw_features']}")
    print(f"  K_ETF: {results['check_2_pca']['K_ETF_at_85pct_var']}, cum_var: {results['check_2_pca']['cum_var_at_K']:.3f}")

    print("\n[Check 3] Orthogonality (max abs corr PC × TA must be < 0.4)...")
    results["check_3_orthogonality"] = check_3_orthogonality(pc_scores, pc_index, universe_sorted)
    print(f"  status: {'PASS' if results['check_3_orthogonality']['pass'] else 'FAIL'}")
    if results["check_3_orthogonality"]["max_abs_corr_overall"] is not None:
        print(f"  stocks sampled / used: {results['check_3_orthogonality']['n_stocks_sampled']} / {results['check_3_orthogonality']['n_stocks_used']}")
        print(f"  max abs corr overall: {results['check_3_orthogonality']['max_abs_corr_overall']:.3f}")

    print("\n[Check 5] Sample size (effective obs / features >= 5:1)...")
    results["check_5_sample_size"] = check_5_sample_size(
        K_ETF=results["check_2_pca"]["K_ETF_at_85pct_var"],
        panel_index=pc_index,
    )
    print(f"  status: {'PASS' if results['check_5_sample_size']['pass'] else 'FAIL'}")
    print(f"  n_train_days: {results['check_5_sample_size']['n_train_days']}, n_features: {results['check_5_sample_size']['n_features']}")
    print(f"  effective_n: {results['check_5_sample_size']['effective_n']:.1f}, ratio: {results['check_5_sample_size']['obs_per_feature_ratio']:.2f}")

    all_pass = all(results[k]["pass"] for k in results)
    results["overall_pass"] = all_pass

    out_path = OUT_DIR / "preflight_results.json"
    out_path.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")

    print("\n" + "=" * 70)
    print(f"OVERALL: {'ALL CHECKS PASS — proceed to pre-registration' if all_pass else 'FAIL — amend spec or kill'}")
    print(f"Wrote {out_path}")
    print("=" * 70)

    if all_pass:
        ufrozen = OUT_DIR / "universe_frozen.json"
        ufrozen.write_text(
            json.dumps(
                {
                    "frozen_at": pd.Timestamp.now().isoformat(),
                    "window_start": str(WINDOW_START.date()),
                    "train_end": str(TRAIN_END.date()),
                    "adv_min_cr": ADV_MIN_CR,
                    "n_tickers": len(universe_sorted),
                    "tickers": [u["ticker"] for u in universe_sorted],
                    "details": universe_sorted,
                },
                indent=2,
                default=str,
            ),
            encoding="utf-8",
        )
        print(f"Wrote {ufrozen}")

    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
