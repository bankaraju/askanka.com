"""
AutoResearch — ETF Re-Optimizer + Indian Market Data Loader

This module serves two related purposes:

1. **Indian Market Data Loader** (`load_indian_data`):
   Reads the most recent daily dump (pipeline/data/daily/YYYY-MM-DD.json),
   flows snapshot (pipeline/data/flows/YYYY-MM-DD.json), and positioning.json
   to extract Indian-specific signals: FII/DII equity flows, India VIX, Nifty
   close, Bank Nifty close, PCR, RSI-14, and breadth indicators.  These values
   are used as additional inputs to the ETF regime engine so that global-ETF
   signals are cross-checked against domestic participation data before a
   regime call is finalised.

2. **ETF Re-Optimizer** (forthcoming):
   Will periodically re-run the weight-optimisation sweep from
   etf_weight_optimizer.py incorporating the Indian signals above, replacing
   the static `etf_optimal_weights.json` with a rolling optimised set.

Usage:
    from pipeline.autoresearch.etf_reoptimize import load_indian_data
    data = load_indian_data()   # uses default prod paths
    print(data["india_vix"], data["fii_net"])
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default paths (relative to repo root)
# ---------------------------------------------------------------------------
_REPO = Path(__file__).resolve().parent.parent.parent  # askanka.com/
_DAILY_DIR: Path = _REPO / "pipeline" / "data" / "daily"
_FLOWS_DIR: Path = _REPO / "pipeline" / "data" / "flows"
_POSITIONING_PATH: Path = _REPO / "pipeline" / "data" / "positioning.json"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_indian_data(
    daily_dir: Optional[Path] = None,
    flows_dir: Optional[Path] = None,
    positioning_path: Optional[Path] = None,
) -> dict:
    """Load the latest Indian market data from local JSON snapshots.

    Parameters
    ----------
    daily_dir : Path, optional
        Directory containing dated daily dump files (``YYYY-MM-DD.json``).
        Defaults to ``pipeline/data/daily/``.
    flows_dir : Path, optional
        Directory containing dated FII/DII flow files (``YYYY-MM-DD.json``).
        Defaults to ``pipeline/data/flows/``.
    positioning_path : Path, optional
        Path to the positioning snapshot (``positioning.json``).
        Defaults to ``pipeline/data/positioning.json``.

    Returns
    -------
    dict
        Keys (all ``float | None``):
        - ``fii_net``           — FII equity net (crore INR)
        - ``dii_net``           — DII equity net (crore INR)
        - ``india_vix``         — India VIX close
        - ``nifty_close``       — Nifty 50 close
        - ``banknifty_close``   — Bank Nifty close (if available)
        - ``pcr``               — Market-wide put/call ratio
        - ``nifty_rsi_14``      — Nifty 14-day RSI (if stored)
        - ``pct_above_200dma``  — % of F&O stocks above 200 DMA (if stored)
        - ``pct_above_50dma``   — % of F&O stocks above 50 DMA (if stored)
        - ``sector_breadth``    — Advance/decline breadth score (if stored)

    Missing fields are ``None`` — callers must handle ``None`` gracefully.
    """
    daily_dir = Path(daily_dir) if daily_dir is not None else _DAILY_DIR
    flows_dir = Path(flows_dir) if flows_dir is not None else _FLOWS_DIR
    positioning_path = (
        Path(positioning_path) if positioning_path is not None else _POSITIONING_PATH
    )

    result: dict = {
        "fii_net": None,
        "dii_net": None,
        "india_vix": None,
        "nifty_close": None,
        "banknifty_close": None,
        "pcr": None,
        "nifty_rsi_14": None,
        "pct_above_200dma": None,
        "pct_above_50dma": None,
        "sector_breadth": None,
    }

    # --- daily dump ---
    result.update(_load_daily(daily_dir))

    # --- flows ---
    result.update(_load_flows(flows_dir))

    # --- positioning ---
    result.update(_load_positioning(positioning_path))

    return result


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _latest_dated_file(directory: Path) -> Optional[Path]:
    """Return the most recent ``YYYY-MM-DD.json`` file in *directory*, or None."""
    if not directory.is_dir():
        return None
    candidates = sorted(directory.glob("????-??-??.json"))
    return candidates[-1] if candidates else None


def _load_daily(daily_dir: Path) -> dict:
    """Extract VIX and Nifty close from the most recent daily dump."""
    out: dict = {}
    path = _latest_dated_file(daily_dir)
    if path is None:
        logger.debug("load_indian_data: no daily dump found in %s", daily_dir)
        return out

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("load_indian_data: failed to parse %s — %s", path, exc)
        return out

    indices: dict = data.get("indices", {})

    # India VIX — stored under indices as "INDIA VIX"
    vix_entry = indices.get("INDIA VIX") or {}
    if vix_entry.get("close") is not None:
        try:
            out["india_vix"] = float(vix_entry["close"])
        except (TypeError, ValueError):
            pass

    # Nifty 50 close
    nifty_entry = indices.get("Nifty 50") or {}
    if nifty_entry.get("close") is not None:
        try:
            out["nifty_close"] = float(nifty_entry["close"])
        except (TypeError, ValueError):
            pass

    # Bank Nifty close (may or may not be present)
    banknifty_entry = (
        indices.get("Nifty Bank")
        or indices.get("BANKNIFTY")
        or indices.get("Bank Nifty")
        or {}
    )
    if banknifty_entry.get("close") is not None:
        try:
            out["banknifty_close"] = float(banknifty_entry["close"])
        except (TypeError, ValueError):
            pass

    # Breadth / RSI fields (stored in top-level or metadata when available)
    meta: dict = data.get("metadata", {})
    for field in ("nifty_rsi_14", "pct_above_200dma", "pct_above_50dma", "sector_breadth"):
        raw = meta.get(field)
        if raw is not None:
            try:
                out[field] = float(raw)
            except (TypeError, ValueError):
                pass

    return out


def _load_flows(flows_dir: Path) -> dict:
    """Extract FII/DII equity net flows from the most recent flows file."""
    out: dict = {}
    path = _latest_dated_file(flows_dir)
    if path is None:
        logger.debug("load_indian_data: no flows file found in %s", flows_dir)
        return out

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("load_indian_data: failed to parse %s — %s", path, exc)
        return out

    for dest_key, src_key in (("fii_net", "fii_equity_net"), ("dii_net", "dii_equity_net")):
        raw = data.get(src_key)
        if raw is not None:
            try:
                out[dest_key] = float(raw)
            except (TypeError, ValueError):
                pass

    return out


def _load_positioning(positioning_path: Path) -> dict:
    """Extract market-wide PCR from positioning.json if present."""
    out: dict = {}
    if not positioning_path.is_file():
        logger.debug("load_indian_data: positioning file not found at %s", positioning_path)
        return out

    try:
        data = json.loads(positioning_path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("load_indian_data: failed to parse %s — %s", positioning_path, exc)
        return out

    # Market-wide PCR may be stored at top level or under a "NIFTY" key
    pcr = data.get("pcr") or data.get("market_pcr")
    if pcr is None:
        nifty_block = data.get("NIFTY") or {}
        pcr = nifty_block.get("pcr")

    if pcr is not None:
        try:
            out["pcr"] = float(pcr)
        except (TypeError, ValueError):
            pass

    return out
