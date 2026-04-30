"""One-off: build the 5y regime tape used by Task #24 backtest.

Output: pipeline/data/research/etf_v3/regime_tape_5y_pit.csv

Methodology
-----------
Uses the FROZEN V3 CURATED-30 weights from
`pipeline/autoresearch/etf_v3_curated_optimal_weights.json` (same file the
production daily signal reads) applied to historical features at each
trading date in [2021-04-23, 2026-04-22].

This is *frozen-weights-applied-to-history*, not contemporaneous-weights.
That matters in two ways:

1. **For Task #24 (this consumer):** the regime label is a CONDITIONING
   variable, not a trade signal. Any small hindsight in the label only
   shifts which days fall into which regime bucket, not whether the
   basket trade earns money on a given day. Acceptable for partitioning.
2. **NOT a substitute for `regime_history.csv`:** that file is built with
   v2 weights (different model entirely) and is contaminated for ANY
   purpose per `memory/reference_regime_history_csv_contamination.md`.

The output file is tagged with `regime_assigned_using_2026-04-26-weights`
provenance so downstream consumers cannot mistake it for a contemporaneous
walk-forward tape.
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from pipeline.autoresearch.etf_v3_curated_signal import _signal_to_zone  # noqa: E402
from pipeline.autoresearch.etf_v3_loader import CURATED_FOREIGN_ETFS, build_panel  # noqa: E402
from pipeline.autoresearch.etf_v3_research import build_features, _weighted_signal  # noqa: E402

WEIGHTS_PATH = REPO_ROOT / "pipeline" / "autoresearch" / "etf_v3_curated_optimal_weights.json"
OUT_DIR = REPO_ROOT / "pipeline" / "data" / "research" / "etf_v3"
OUT_FILE = OUT_DIR / "regime_tape_5y_pit.csv"


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s | %(message)s")
    log = logging.getLogger("build_regime_tape")

    if not WEIGHTS_PATH.exists():
        log.error("Weights file not found: %s", WEIGHTS_PATH)
        return 1

    weights_data = json.loads(WEIGHTS_PATH.read_text(encoding="utf-8"))
    weights = weights_data["optimal_weights"]
    center = weights_data["zone_thresholds"]["center"]
    band = weights_data["zone_thresholds"]["band"]
    log.info("Loaded %d weights, center=%.4f, band=%.4f", len(weights), center, band)

    log.info("Building panel via canonical loader (this can take a minute)...")
    panel = build_panel()
    log.info("Panel shape: %s, span %s -> %s", panel.shape, panel.index.min(), panel.index.max())

    log.info("Building features...")
    features = build_features(panel, foreign_cols=list(CURATED_FOREIGN_ETFS))

    log.info("Computing weighted signal series...")
    sig = _weighted_signal(features, weights)
    sig = sig.dropna()

    log.info("Mapping signal -> zone for %d dates", len(sig))
    zones = sig.apply(lambda v: _signal_to_zone(v, center, band))

    df = pd.DataFrame({
        "date": sig.index,
        "regime": zones.values,
        "signal_score": sig.values,
    })
    df["date"] = pd.to_datetime(df["date"]).dt.date

    df = df[(df["date"] >= date(2021, 4, 23)) & (df["date"] <= date(2026, 4, 22))]
    df = df.sort_values("date").reset_index(drop=True)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT_FILE, index=False)
    log.info("Wrote %d rows to %s", len(df), OUT_FILE)

    counts = df["regime"].value_counts().to_dict()
    log.info("Regime distribution: %s", counts)

    # Provenance sidecar
    sidecar = OUT_FILE.with_suffix(".provenance.json")
    sidecar.write_text(
        json.dumps(
            {
                "built_at": pd.Timestamp.utcnow().isoformat(),
                "weights_file": str(WEIGHTS_PATH.relative_to(REPO_ROOT)),
                "weights_frozen_at_commit": weights_data.get("frozen_at_commit"),
                "n_features_used": len(weights),
                "zone_center": center,
                "zone_band": band,
                "limitation": (
                    "regime_assigned_using_2026-04-26-weights — this tape applies "
                    "today's frozen V3 CURATED-30 weights to historical feature "
                    "vectors. NOT a contemporaneous walk-forward tape. Consumer "
                    "must treat regime label as a *conditioning bucket*, not a "
                    "trade signal."
                ),
                "row_count": len(df),
                "regime_distribution": counts,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    log.info("Wrote provenance sidecar to %s", sidecar)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
