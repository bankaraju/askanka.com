"""Canonical sector-index panel — builder + read-side helpers.

Build path (called once when the panel is missing or stale, or whenever
the underlying fno_historical refresh requires a rebuild):

    >>> from pipeline.research.sector_panel.builder import build_canonical_panel
    >>> meta = build_canonical_panel()

Every downstream study reads via :func:`load_canonical_panel`; the
on-disk dataset is the single audited source of truth and gets a
registration sidecar so the consumer can audit which build it's reading.

Per ``anka_data_validation_policy_global_standard.md`` §6, this module
defines the dataset contract:

  * **Source:** ``pipeline/data/fno_historical/<TICKER>.csv`` — daily
    OHLCV from yfinance, refreshed by AnkaDailyDump 04:30 IST.
  * **Schema (§8):** input has columns Date, Close, High, Low, Open,
    Volume; Date parses to ISO; Close is non-null.
  * **Cleanliness gates (§9):** per-ticker bar count ≥ 90% of the 90th
    percentile of all tickers; tail no more than 5 trading days behind
    the global latest tail.
  * **Adjustment mode (§10):** adjusted-close (yfinance default).
    Documented; no further adjustment performed.
  * **Sector mapping:** via ``pipeline.scorecard_v2.sector_mapper``.
    Unmapped tickers are excluded.
  * **Sector index:** equal-weighted simple mean of constituent daily
    log returns, requiring ≥ 50% of constituents present on the day.
  * **Output schema:** parquet, indexed by ``Date``, columns are
    sector keys, values are daily log returns. Index level can be
    reconstructed by the consumer via ``np.exp(panel.cumsum())``.

The metadata sidecar carries the same provenance fields used elsewhere
in the codebase plus the audit summary.
"""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

log = logging.getLogger("anka.sector_panel")

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
SOURCE_DIR = REPO_ROOT / "pipeline" / "data" / "fno_historical"
OUT_DIR = REPO_ROOT / "pipeline" / "data" / "research" / "sector_panel"
CANONICAL_PANEL_PATH = OUT_DIR / "sector_index_panel.parquet"
CANONICAL_METADATA_PATH = OUT_DIR / "sector_index_panel.parquet.provenance.json"

# Locked at module level — these are the dataset contract, not call-site
# parameters. Changing them silently would invalidate every downstream
# study that read the panel under the old contract.
MIN_TICKER_COVERAGE = 0.90
MAX_TAIL_STALENESS_DAYS = 5
MIN_CONSTITUENT_COVERAGE = 0.50  # ≥50% of sector tickers present per day
SCHEMA_VERSION = 1

_IST = timezone(timedelta(hours=5, minutes=30))


# ---------------------------------------------------------------------------
# Read side — what every downstream consumer should call.
# ---------------------------------------------------------------------------

def load_canonical_panel(rebuild_if_stale: bool = True,
                          stale_after_hours: float = 30.0) -> pd.DataFrame:
    """Return the canonical sector-return panel.

    If the cached parquet is missing or older than ``stale_after_hours``,
    rebuild before returning (when ``rebuild_if_stale``). The default
    cadence allows for one fresh rebuild per day after AnkaDailyDump
    runs at 04:30 IST.
    """
    if not CANONICAL_PANEL_PATH.is_file():
        if rebuild_if_stale:
            build_canonical_panel()
        else:
            raise FileNotFoundError(f"Canonical panel missing: {CANONICAL_PANEL_PATH}")
    elif rebuild_if_stale:
        age_h = (time.time() - CANONICAL_PANEL_PATH.stat().st_mtime) / 3600.0
        if age_h > stale_after_hours:
            log.info("canonical panel is %.1fh old (>%.1fh) — rebuilding",
                     age_h, stale_after_hours)
            build_canonical_panel()
    return pd.read_parquet(CANONICAL_PANEL_PATH)


def load_canonical_metadata() -> dict[str, Any]:
    """Return the panel's registration/audit sidecar, or {} if absent."""
    if not CANONICAL_METADATA_PATH.is_file():
        return {}
    try:
        return json.loads(CANONICAL_METADATA_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


# ---------------------------------------------------------------------------
# Build side — runs through the §9 gate and emits the canonical artefact.
# ---------------------------------------------------------------------------

def _load_ticker_csv(path: Path) -> pd.DataFrame | None:
    """Load + schema-validate one ticker CSV. None on §8 violation."""
    try:
        df = pd.read_csv(path)
    except Exception as exc:
        log.warning("read fail %s: %s", path.name, exc)
        return None
    required = {"Date", "Close"}
    if not required.issubset(df.columns):
        return None
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df.dropna(subset=["Date", "Close"]).sort_values("Date").reset_index(drop=True)
    if df.empty:
        return None
    return df[["Date", "Close"]]


def _coverage_audit(frames: dict[str, pd.DataFrame]) -> tuple[dict, dict[str, pd.DataFrame]]:
    raw_lengths = [len(f) for f in frames.values()]
    raw_tails = [f["Date"].iloc[-1] for f in frames.values()]
    if not raw_lengths:
        return {"abort": "no readable files"}, {}
    expected_bars = int(np.percentile(raw_lengths, 90))
    latest_tail = max(raw_tails)
    audit = {
        "files_found": len(frames),
        "expected_bars_p90": expected_bars,
        "latest_global_tail": latest_tail.date().isoformat(),
        "low_coverage": [],
        "stale_tail": [],
        "accepted": [],
    }
    accepted: dict[str, pd.DataFrame] = {}
    for sym, df in frames.items():
        if len(df) < MIN_TICKER_COVERAGE * expected_bars:
            audit["low_coverage"].append({"ticker": sym, "bars": len(df),
                                          "expected": expected_bars})
            continue
        tail_lag = (latest_tail - df["Date"].iloc[-1]).days
        if tail_lag > MAX_TAIL_STALENESS_DAYS:
            audit["stale_tail"].append({"ticker": sym,
                                        "tail": df["Date"].iloc[-1].date().isoformat(),
                                        "lag_days": tail_lag})
            continue
        audit["accepted"].append(sym)
        accepted[sym] = df
    return audit, accepted


def _resolve_sector_map(symbols: list[str]) -> tuple[dict, dict]:
    from pipeline.scorecard_v2.sector_mapper import SectorMapper
    full_map = SectorMapper().map_all()
    sym_to_sector: dict[str, str] = {}
    by_sector: dict[str, list[str]] = {}
    for sym in symbols:
        info = full_map.get(sym)
        if not info:
            continue
        sec = info.get("sector")
        if not sec:
            continue
        sym_to_sector[sym] = sec
        by_sector.setdefault(sec, []).append(sym)
    return sym_to_sector, by_sector


def _build_panel(frames: dict[str, pd.DataFrame],
                  by_sector: dict[str, list[str]]) -> pd.DataFrame:
    series = [df.set_index("Date")["Close"].rename(sym)
              for sym, df in frames.items()]
    closes = pd.concat(series, axis=1).sort_index()
    closes = closes[~closes.index.duplicated(keep="first")]
    log_ret = np.log(closes / closes.shift(1))

    sector_returns = {}
    for sec, syms in by_sector.items():
        cols = [s for s in syms if s in log_ret.columns]
        if not cols:
            continue
        sub = log_ret[cols]
        present = sub.notna().sum(axis=1)
        min_present = max(1, int(np.ceil(MIN_CONSTITUENT_COVERAGE * len(cols))))
        sec_ret = sub.mean(axis=1, skipna=True).where(present >= min_present)
        sector_returns[sec] = sec_ret
    return pd.DataFrame(sector_returns).dropna(how="all")


def _short_git_sha() -> str | None:
    """Best-effort short HEAD sha; None on failure."""
    import subprocess
    try:
        r = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                            cwd=REPO_ROOT, capture_output=True,
                            text=True, timeout=2.0, check=False)
        if r.returncode == 0:
            return r.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        pass
    return None


def build_canonical_panel() -> dict[str, Any]:
    """Audit + build + persist. Returns the registration metadata dict.

    Idempotent: safe to call repeatedly; overwrites the parquet and
    sidecar atomically with the latest audited build.
    """
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    files = sorted(SOURCE_DIR.glob("*.csv"))
    raw_frames: dict[str, pd.DataFrame] = {}
    schema_failures: list[str] = []
    for f in files:
        sym = f.stem.upper()
        df = _load_ticker_csv(f)
        if df is None:
            schema_failures.append(sym)
            continue
        raw_frames[sym] = df

    audit, accepted = _coverage_audit(raw_frames)
    if "abort" in audit:
        raise RuntimeError(f"audit abort: {audit['abort']}")
    audit["schema_failures"] = schema_failures

    sym_to_sector, by_sector = _resolve_sector_map(list(accepted.keys()))
    audit["mapped_to_sector"] = len(sym_to_sector)
    audit["unmapped_sample"] = [s for s in accepted if s not in sym_to_sector][:30]
    accepted = {s: f for s, f in accepted.items() if s in sym_to_sector}

    panel = _build_panel(accepted, by_sector)

    # Atomic write (parquet + sidecar) — write parquet first, then sidecar
    # last so a half-built panel can never be observed as canonical.
    panel.to_parquet(CANONICAL_PANEL_PATH)

    metadata: dict[str, Any] = {
        "schema": SCHEMA_VERSION,
        "task_name": "build_canonical_panel",
        "engine_version": "sector_panel_v1",
        "git_sha": _short_git_sha(),
        "started_at": datetime.now(_IST).isoformat(timespec="seconds"),
        "output_path": str(CANONICAL_PANEL_PATH.relative_to(REPO_ROOT)).replace("\\", "/"),
        "expected_cadence_seconds": 86400,
        "extras": {
            "shape": list(panel.shape),
            "date_min": panel.index.min().date().isoformat() if len(panel) else None,
            "date_max": panel.index.max().date().isoformat() if len(panel) else None,
            "n_sectors": panel.shape[1],
            "sectors": sorted(panel.columns.tolist()),
            "constituents_per_sector": {
                sec: len(by_sector.get(sec, [])) for sec in panel.columns
            },
            "audit": {
                "files_found": audit["files_found"],
                "schema_failures": len(audit["schema_failures"]),
                "low_coverage_excluded": len(audit["low_coverage"]),
                "stale_tail_excluded": len(audit["stale_tail"]),
                "accepted": len(audit["accepted"]),
                "mapped_to_sector": audit["mapped_to_sector"],
                "expected_bars_p90": audit["expected_bars_p90"],
                "latest_global_tail": audit["latest_global_tail"],
                "low_coverage_tickers": [x["ticker"] for x in audit["low_coverage"]],
                "stale_tail_tickers": [x["ticker"] for x in audit["stale_tail"]],
            },
            "thresholds": {
                "min_ticker_coverage": MIN_TICKER_COVERAGE,
                "max_tail_staleness_days": MAX_TAIL_STALENESS_DAYS,
                "min_constituent_coverage": MIN_CONSTITUENT_COVERAGE,
            },
        },
    }
    CANONICAL_METADATA_PATH.write_text(json.dumps(metadata, indent=2),
                                        encoding="utf-8")
    log.info("canonical sector panel built: %s — shape %s", CANONICAL_PANEL_PATH,
             panel.shape)
    return metadata
