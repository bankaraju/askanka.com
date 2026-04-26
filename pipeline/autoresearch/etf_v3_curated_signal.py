"""ETF v3 curated daily signal — production replacement for etf_daily_signal.

Reads pre-computed weights + zone thresholds from
`etf_v3_curated_optimal_weights.json` (written by the weekly
`etf_v3_curated_reoptimize` job) and emits today's regime call.

Three guarantees this module enforces by construction (the v2 daily-signal
bugs that cycle 3 root-caused):

1. **No daily refit.** This module only READS weights. The Karpathy fit
   happens once per week in the reoptimizer. Daily-recalibration is the
   antipattern that broke v1 — every daily refit drifts the weight vector
   and the zone thresholds simultaneously, so the regime label becomes
   non-monotonic in the input.
2. **No silent feature drop.** Both reoptimize and signal use the SAME
   canonical loader (`build_panel`) and the SAME feature builder
   (`build_features(panel, foreign_cols=list(CURATED_FOREIGN_ETFS))`).
   The v2 path fetched live yfinance for global ETFs but had no fetch
   path for Indian features; non-zero weights on india_vix / fii_net /
   dii_net / nifty_close were silently zeroed at decision time.
3. **No zone-threshold drift.** Center/band come from the weights file,
   not recomputed daily. The reoptimizer calibrated them once over the
   eval window; this module just reads them.

Output: updates `regime_trade_map.json` with today_zone, today_signal,
today_direction, signal_computed_at, signal_source: "etf_v3_curated".

Usage:
    python -m pipeline.autoresearch.etf_v3_curated_signal
    python -m pipeline.autoresearch.etf_v3_curated_signal --dry-run
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

from pipeline.autoresearch.etf_v3_loader import CURATED_FOREIGN_ETFS, build_panel
from pipeline.autoresearch.etf_v3_research import build_features, _weighted_signal

logger = logging.getLogger(__name__)

HERE = Path(__file__).resolve().parent
WEIGHTS_PATH = HERE / "etf_v3_curated_optimal_weights.json"
TRADE_MAP_PATH = HERE / "regime_trade_map.json"


def _signal_to_zone(signal: float, center: float, band: float) -> str:
    if signal >= center + 2 * band:
        return "EUPHORIA"
    if signal >= center + band:
        return "RISK-ON"
    if signal >= center - band:
        return "NEUTRAL"
    if signal >= center - 2 * band:
        return "CAUTION"
    return "RISK-OFF"


def compute_daily_signal(
    *,
    weights_path: Path = WEIGHTS_PATH,
    trade_map_path: Path = TRADE_MAP_PATH,
    dry_run: bool = False,
) -> dict:
    weights_path = Path(weights_path)
    trade_map_path = Path(trade_map_path)

    if not weights_path.is_file():
        return {"status": "error", "reason": f"weights file not found: {weights_path}"}

    try:
        weights_data = json.loads(weights_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"status": "error", "reason": f"failed to parse weights: {exc}"}

    optimal_weights: dict = weights_data.get("optimal_weights") or {}
    if not optimal_weights:
        return {"status": "error", "reason": "weights file has empty optimal_weights"}

    zone_thresholds = weights_data.get("zone_thresholds") or {}
    center = zone_thresholds.get("center")
    band = zone_thresholds.get("band")
    if center is None or band is None:
        return {"status": "error",
                "reason": "weights file missing zone_thresholds.center / .band"}

    # Provenance opt-in (skip on dry_run so test invocations don't overwrite
    # production sidecars). Per docs/superpowers/specs/2026-04-27-provenance-contract.md
    # the call goes before heavy work — "this task started running at this
    # time with this version", not "this task succeeded".
    if not dry_run:
        try:
            from pipeline import provenance as _prov
            _prov.write(
                trade_map_path,
                task_name="AnkaETFSignal",
                engine_version="v3_curated",
                expected_cadence_seconds=86400,
                extras={
                    "weights_frozen_at_commit": weights_data.get("frozen_at_commit"),
                    "weights_frozen_for_hypothesis": "H-2026-04-27-001",
                    "zone_center": center,
                    "zone_band": band,
                    "n_features": len(optimal_weights),
                },
            )
        except Exception as exc:
            logger.warning("provenance.write failed (non-fatal): %s", exc)

    # Build today's features the same way the reoptimizer did. No yfinance,
    # no silent drop — the canonical loader is the only data source.
    panel = build_panel(t1_anchor=True)
    feats = build_features(panel, foreign_cols=list(CURATED_FOREIGN_ETFS))

    # Drop rows where any feature is NaN — same shape as fit-time
    feats_clean = feats.dropna()
    if feats_clean.empty:
        return {"status": "error", "reason": "no clean rows in feature matrix"}

    # Today's signal = signal at the most recent fully-populated row
    sig = _weighted_signal(feats_clean, optimal_weights)
    today_signal = float(sig.iloc[-1])
    today_anchor = str(feats_clean.index[-1].date())
    today_zone = _signal_to_zone(today_signal, center, band)
    today_direction = "UP" if today_signal > 0 else "DOWN"

    # Sanity: warn if any weighted feature is missing from the live feature
    # matrix. With the loader-coupled architecture this should never fire,
    # but if it does we want to know immediately rather than discover via
    # silent label drift weeks later.
    missing = [k for k in optimal_weights if k not in feats_clean.columns]
    if missing:
        dropped_mass = sum(abs(optimal_weights[k]) for k in missing)
        kept_mass = sum(abs(optimal_weights[k]) for k in optimal_weights
                        if k in feats_clean.columns)
        total = kept_mass + dropped_mass
        frac = dropped_mass / total if total else 0.0
        logger.warning(
            "etf_v3_curated_signal: %d feature(s) missing from live matrix: %s "
            "(dropped magnitude %.4f / total %.4f = %.1f%%)",
            len(missing), missing, dropped_mass, total, frac * 100.0,
        )

    logger.info(
        "etf_v3_curated_signal: anchor=%s signal=%.4f center=%.4f band=%.4f -> zone=%s",
        today_anchor, today_signal, center, band, today_zone,
    )

    # Read prev_zone for change detection
    existing_map: dict = {}
    if trade_map_path.is_file():
        try:
            existing_map = json.loads(trade_map_path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("could not read trade map (%s) — starting fresh", exc)

    prev_zone = existing_map.get("today_zone", "UNKNOWN")
    changed = prev_zone != today_zone
    timestamp = datetime.now(tz=timezone.utc).isoformat()

    result = {
        "status": "dry_run" if dry_run else "updated",
        "today_zone": today_zone,
        "today_signal": today_signal,
        "today_direction": today_direction,
        "today_anchor": today_anchor,
        "prev_zone": prev_zone,
        "changed": changed,
        "signal_computed_at": timestamp,
        "signal_source": "etf_v3_curated",
        "zone_center": center,
        "zone_band": band,
    }

    if dry_run:
        logger.info("dry_run=True — not writing trade map")
        return result

    existing_map["today_zone"] = today_zone
    existing_map["today_signal"] = today_signal
    existing_map["today_direction"] = today_direction
    existing_map["signal_computed_at"] = timestamp
    existing_map["signal_source"] = "etf_v3_curated"
    existing_map["signal_anchor"] = today_anchor

    try:
        trade_map_path.write_text(json.dumps(existing_map, indent=2), encoding="utf-8")
        logger.info("etf_v3_curated_signal: updated %s zone=%s", trade_map_path, today_zone)
    except Exception as exc:
        return {"status": "error", "reason": f"failed to write trade map: {exc}"}

    return result


def main() -> int:
    p = argparse.ArgumentParser(description="ETF v3 curated daily signal")
    p.add_argument("--weights", type=Path, default=WEIGHTS_PATH)
    p.add_argument("--trade-map", type=Path, default=TRADE_MAP_PATH)
    p.add_argument("--dry-run", action="store_true",
                   help="compute signal and print, but don't write the trade map")
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    result = compute_daily_signal(
        weights_path=args.weights,
        trade_map_path=args.trade_map,
        dry_run=args.dry_run,
    )
    print(json.dumps(result, indent=2, default=str))
    return 0 if result.get("status") in ("updated", "dry_run") else 1


if __name__ == "__main__":
    sys.exit(main())
