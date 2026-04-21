"""V4 → V5 signal adapter.

Reads the Phase C V4 in-sample ledger (docs/research/phase-c-validation/
in_sample_ledger.parquet) and reshapes it into the V5 signal schema expected
by V5.1-V5.7 variants:

    date, symbol, sector, sector_index, classification, direction,
    expected_return, confidence

Writes to pipeline/data/research/phase_c/opportunity_signals.parquet.
"""
from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

from pipeline.scorecard_v2.sector_mapper import SectorMapper

log = logging.getLogger("v4_adapter")

# ---------------------------------------------------------------------------
# Sector → sector index mapping
# ---------------------------------------------------------------------------
_SECTOR_INDEX_MAP: dict[str, str] = {
    "Banks": "BANKNIFTY",
    "IT_Services": "NIFTYIT",
    "NBFC_HFC": "FINNIFTY",
    "Capital_Markets": "FINNIFTY",
    "Insurance": "FINNIFTY",
    # All other sectors fall back to NIFTY (handled in code below)
}

# ---------------------------------------------------------------------------
# Canonical paths (derived from this file's location)
# ---------------------------------------------------------------------------
# V5 output schema columns (exported for tests)
V5_SCHEMA_COLS: tuple[str, ...] = (
    "date", "symbol", "sector", "sector_index",
    "classification", "direction", "expected_return", "confidence",
)

_PIPELINE_DIR = Path(__file__).resolve().parent.parent.parent
_REPO_DIR = _PIPELINE_DIR.parent

V4_LEDGER_PATH = _REPO_DIR / "docs" / "research" / "phase-c-validation" / "in_sample_ledger.parquet"
V5_SIGNALS_PATH = _PIPELINE_DIR / "data" / "research" / "phase_c" / "opportunity_signals.parquet"


def _sector_index(sector: str) -> str:
    """Return the sector index ticker for a given sector, defaulting to NIFTY."""
    return _SECTOR_INDEX_MAP.get(sector, "NIFTY")


def build_v5_signals_from_v4(
    v4_path: Path | None = None,
    out_path: Path | None = None,
) -> pd.DataFrame:
    """Read V4 in-sample ledger, reshape to V5 schema, write parquet.

    Parameters
    ----------
    v4_path:
        Override for the V4 ledger path (used in tests).
    out_path:
        Override for the output path (used in tests).

    Returns
    -------
    pd.DataFrame with V5 schema columns.

    Raises
    ------
    FileNotFoundError if v4_path does not exist.
    ValueError if the DataFrame ends up empty after filtering.
    """
    v4_path = Path(v4_path) if v4_path is not None else V4_LEDGER_PATH
    out_path = Path(out_path) if out_path is not None else V5_SIGNALS_PATH

    if not v4_path.is_file():
        raise FileNotFoundError(f"V4 ledger not found: {v4_path}")

    raw = pd.read_parquet(v4_path)
    log.info("V4 ledger loaded: %d rows", len(raw))

    # Filter to OPPORTUNITY rows only
    opps = raw[raw["label"] == "OPPORTUNITY"].copy()
    log.info("OPPORTUNITY rows: %d", len(opps))

    # Build sector mapping
    sector_map: dict[str, str] = {
        sym: info["sector"]
        for sym, info in SectorMapper().map_all().items()
    }

    # Reshape to V5 schema
    rows: list[dict] = []
    dropped = 0
    for _, r in opps.iterrows():
        sym = str(r["symbol"])
        sector = sector_map.get(sym)
        if sector is None:
            log.debug("dropping %s — not in sector map", sym)
            dropped += 1
            continue

        confidence = float(min(abs(r["z_score"]) / 3.0, 1.0))
        rows.append(
            {
                "date": pd.Timestamp(r["entry_date"]),
                "symbol": sym,
                "sector": sector,
                "sector_index": _sector_index(sector),
                "classification": "OPPORTUNITY",
                "direction": str(r["side"]),           # "LONG" / "SHORT"
                "expected_return": float(r["expected_return"]),
                "confidence": confidence,
            }
        )

    if dropped:
        log.warning("Dropped %d rows with no sector mapping", dropped)

    if not rows:
        raise ValueError("No V5 signals produced — all rows were dropped or ledger empty")

    out_df = pd.DataFrame(rows)
    out_df["date"] = pd.to_datetime(out_df["date"])

    # Ensure output directory exists
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_parquet(out_path, index=False)
    log.info("Wrote %d V5 signals to %s", len(out_df), out_path)

    return out_df
