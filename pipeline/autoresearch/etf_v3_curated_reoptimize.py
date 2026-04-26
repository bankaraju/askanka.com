"""ETF v3 curated weekly reoptimizer — production replacement for etf_reoptimize.

Mirrors `etf_reoptimize.run_reoptimize` but with three structural improvements:

1. **Reads from canonical loader** (`etf_v3_loader.build_panel`) — not yfinance —
   so we cannot silently drop features (the v2 GLOBAL_ETFS-vs-optimal_weights
   bug is impossible by construction).
2. **v3 engineered features** (5d returns, VIX 5d change, FII/DII 5d sums,
   NIFTY 1d/5d/RSI14) — not raw levels, so the optimizer doesn't get
   dominated by NIFTY-level autocorrelation.
3. **CURATED_FOREIGN_ETFS** (30 ETFs from cureated ETF.txt) — only the ETFs
   with explicit India-channel rationale, no overfitting room from extras.

Outputs:
- `pipeline/autoresearch/etf_v3_curated_optimal_weights.json` — weights + zone thresholds
- Updates `pipeline/autoresearch/regime_trade_map.json` with today's zone

Zone thresholds are calibrated from the distribution of weighted signals over
the most recent eval window (2024-04-23 → today). Uses mean ± std bands
matching v2's structure.

Schedule: Saturday 22:00 IST (replaces AnkaETFReoptimize). Run once tonight to
seed Monday's first signal.

Usage:
    python -m pipeline.autoresearch.etf_v3_curated_reoptimize
    python -m pipeline.autoresearch.etf_v3_curated_reoptimize --dry-run
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from pipeline.autoresearch.etf_v3_loader import (
    CURATED_FOREIGN_ETFS,
    audit_panel,
    build_panel,
)
from pipeline.autoresearch.etf_v3_research import (
    build_features,
    build_target,
    fit_weights,
    _weighted_signal,
)

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
WEIGHTS_PATH = HERE / "etf_v3_curated_optimal_weights.json"
TRADE_MAP_PATH = HERE / "regime_trade_map.json"

DEFAULT_LOOKBACK_DAYS = 756
DEFAULT_N_ITER = 2000
DEFAULT_SEED = 42
ZONE_CALIBRATION_START = "2024-04-23"   # signal distribution sample window


def _signal_to_zone(signal: float, center: float, band: float) -> str:
    """Map a scalar signal to a regime zone using mean ± std bands.

    Same shape as v2's `_signal_to_zone` but with v3's calibrated center/band
    (v3's signal scale differs from v2 because of 5d returns + engineered
    Indian features).
    """
    if signal >= center + 2 * band:
        return "EUPHORIA"
    if signal >= center + band:
        return "RISK-ON"
    if signal >= center - band:
        return "NEUTRAL"
    if signal >= center - 2 * band:
        return "CAUTION"
    return "RISK-OFF"


def run_reoptimize(
    *,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    n_iterations: int = DEFAULT_N_ITER,
    seed: int = DEFAULT_SEED,
    dry_run: bool = False,
) -> dict:
    """Weekly v3-curated Karpathy refit.

    Steps:
      1. Audit panel (loader §9 cleanliness gate)
      2. Build v3 features for the curated 30 ETFs
      3. Fit weights on the most recent `lookback_days` of data
      4. Compute signal distribution over the calibration window for zone bands
      5. Compute today's signal → today's zone
      6. Write weights JSON + update regime_trade_map.json
    """
    timestamp = datetime.now(tz=timezone.utc).isoformat()

    # 1. Audit (hard fail if any input is too gap-y)
    audit = audit_panel()
    if any(r.status == "fail" for r in audit):
        bad = [r.series for r in audit if r.status == "fail"]
        raise RuntimeError(f"loader audit FAIL on: {bad}")
    logger.info("v3-curated reoptimize: audit PASS (%d series)", len(audit))

    # 2. Build features (CURATED_FOREIGN_ETFS only; no extras)
    panel = build_panel(t1_anchor=True)
    feats = build_features(panel, foreign_cols=list(CURATED_FOREIGN_ETFS))
    target = build_target(panel)
    common = feats.index.intersection(target.index).dropna()
    feats, target = feats.loc[common], target.loc[common]
    feats = feats.dropna()
    common = feats.index.intersection(target.index)
    feats, target = feats.loc[common], target.loc[common]

    n_features = feats.shape[1]
    n_train = feats.shape[0]
    logger.info("v3-curated reoptimize: %d features × %d obs", n_features, n_train)

    # 3. Fit on the most recent `lookback_days`
    if n_train > lookback_days:
        Xtr = feats.iloc[-lookback_days:]
        ytr = target.loc[Xtr.index]
    else:
        Xtr, ytr = feats, target
    fit = fit_weights(Xtr, ytr, n_iterations=n_iterations, seed=seed)
    logger.info("v3-curated reoptimize: fit acc=%.2f%% sharpe=%.3f",
                fit.accuracy, fit.sharpe)

    # 4. Calibrate zone thresholds from the eval-window signal distribution.
    # Compute signal across the calibration window so thresholds reflect the
    # operational regime distribution, not just today's value.
    cal_start = pd.Timestamp(ZONE_CALIBRATION_START)
    cal_mask = feats.index >= cal_start
    Xcal = feats.loc[cal_mask]
    sig_cal = _weighted_signal(Xcal, fit.weights)
    sig_cal = sig_cal.dropna()
    if len(sig_cal) < 50:
        raise RuntimeError(
            f"calibration window too small ({len(sig_cal)} obs); "
            f"need >= 50 to derive stable zone thresholds"
        )
    center = float(sig_cal.mean())
    band = float(sig_cal.std())
    pcts = {f"p{p}": float(np.percentile(sig_cal, p)) for p in (5, 10, 25, 50, 75, 90, 95)}
    logger.info("v3-curated reoptimize: zone center=%.4f band=%.4f (n=%d cal obs)",
                center, band, len(sig_cal))

    # 5. Today's signal = signal at the most recent panel row
    sig_full = _weighted_signal(feats, fit.weights)
    today_signal = float(sig_full.iloc[-1])
    today_zone = _signal_to_zone(today_signal, center, band)
    today_direction = "UP" if today_signal > 0 else "DOWN"
    logger.info("v3-curated reoptimize: today signal=%.4f -> zone=%s direction=%s",
                today_signal, today_zone, today_direction)

    # 6. Build the weights payload
    payload = {
        "schema_version": "v3_curated_1",
        "model": "etf_v3_curated",
        "feature_set": "curated_30",
        "n_features": n_features,
        "n_train_obs": int(len(Xtr)),
        "optimal_weights": fit.weights,
        "zone_thresholds": {
            "center": center,
            "band": band,
            "calibration_window_start": ZONE_CALIBRATION_START,
            "calibration_n_obs": int(len(sig_cal)),
            "signal_pct": pcts,
        },
        "best_accuracy": fit.accuracy,
        "best_sharpe": fit.sharpe,
        "today_signal": today_signal,
        "today_zone": today_zone,
        "today_direction": today_direction,
        "fit_iterations": n_iterations,
        "fit_seed": seed,
        "fit_timestamp": timestamp,
        "curated_etfs": list(CURATED_FOREIGN_ETFS),
    }

    result = {
        "status": "dry_run" if dry_run else "saved",
        "today_zone": today_zone,
        "today_signal": today_signal,
        "today_direction": today_direction,
        "best_accuracy": fit.accuracy,
        "best_sharpe": fit.sharpe,
        "n_features": n_features,
        "zone_center": center,
        "zone_band": band,
    }
    if dry_run:
        logger.info("dry_run=True — not writing files")
        return result

    # 7. Save weights JSON
    WEIGHTS_PATH.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    logger.info("wrote %s", WEIGHTS_PATH)

    # 8. Update regime_trade_map.json (preserve other keys; replace zone-related)
    trade_map: dict = {}
    if TRADE_MAP_PATH.is_file():
        try:
            trade_map = json.loads(TRADE_MAP_PATH.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("could not read existing trade map (%s) — starting fresh", exc)
    trade_map["today_zone"] = today_zone
    trade_map["today_signal"] = today_signal
    trade_map["today_direction"] = today_direction
    trade_map["signal_computed_at"] = timestamp
    trade_map["signal_source"] = "etf_v3_curated"  # so consumers know origin
    TRADE_MAP_PATH.write_text(json.dumps(trade_map, indent=2), encoding="utf-8")
    logger.info("updated %s with v3-curated zone=%s", TRADE_MAP_PATH, today_zone)

    return result


def main() -> int:
    p = argparse.ArgumentParser(description="ETF v3 curated weekly reoptimizer")
    p.add_argument("--lookback-days", type=int, default=DEFAULT_LOOKBACK_DAYS)
    p.add_argument("--n-iterations", type=int, default=DEFAULT_N_ITER)
    p.add_argument("--seed", type=int, default=DEFAULT_SEED)
    p.add_argument("--dry-run", action="store_true",
                   help="run end-to-end but don't write files")
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    result = run_reoptimize(
        lookback_days=args.lookback_days,
        n_iterations=args.n_iterations,
        seed=args.seed,
        dry_run=args.dry_run,
    )
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
