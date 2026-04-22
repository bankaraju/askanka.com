"""Sector cohort construction from sector_concentration.json.

If a ticker is a named constituent of a NIFTY sector index, that index is
its cohort. Otherwise it falls into MIDCAP_GENERIC (conceptually built from
MIDCPNIFTY + NIFTYNXT50; in v1 we just use the fallback label — the fitter
does the actual pooling).
"""
from __future__ import annotations
import json
from pathlib import Path

_PIPELINE_DIR = Path(__file__).parent.parent
_SECTOR_CONCENTRATION_FILE = _PIPELINE_DIR / "config" / "sector_concentration.json"
_FALLBACK_COHORT = "MIDCAP_GENERIC"


def _load_concentration() -> dict:
    try:
        return json.loads(_SECTOR_CONCENTRATION_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}


def ticker_to_cohort(ticker: str) -> str:
    """Return the sector cohort label for a ticker; fallback to MIDCAP_GENERIC."""
    t = (ticker or "").upper()
    data = _load_concentration()
    for cohort_name, meta in data.items():
        for c in meta.get("constituents", []):
            if (c.get("symbol") or "").upper() == t:
                return cohort_name
    return _FALLBACK_COHORT


def cohort_members(cohort: str, exclude: str | None = None) -> list[str]:
    """Return ticker list for a cohort, optionally excluding one ticker."""
    data = _load_concentration()
    meta = data.get(cohort) or {}
    excl = (exclude or "").upper()
    members = [
        (c.get("symbol") or "").upper()
        for c in meta.get("constituents", [])
        if (c.get("symbol") or "").upper() != excl
    ]
    return [m for m in members if m]
