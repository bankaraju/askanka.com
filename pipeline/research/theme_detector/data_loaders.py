"""Data loader helpers for theme detector signals.

Reads from existing project data sources. Returns pandas DataFrames keyed by
symbol. PIT-aware — every loader takes a `cutoff_date` and refuses to return
bars after the cutoff.

Spec data audit: docs/superpowers/specs/2026-05-01-theme-detector-data-source-audit.md
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Literal

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[3]
FNO_HISTORICAL_DIR = REPO_ROOT / "pipeline" / "data" / "fno_historical"
INDICES_DIR = REPO_ROOT / "pipeline" / "data" / "india_historical" / "indices"
NIFTY_50_PATH = INDICES_DIR / "NIFTY_daily.csv"
TRENDLYNE_ROOT = REPO_ROOT / "pipeline" / "data" / "trendlyne" / "raw_exports"

MultigroupView = Literal["returns_shareholding", "technical_dvm_valuation", "fundamentals_fno"]
FIIPolarity = Literal["increasing", "decreasing"]


def load_nifty_50(cutoff_date: date) -> pd.DataFrame | None:
    """Load NIFTY-50 daily bars up to (and including) cutoff_date.

    Schema is lower-case (date,open,high,low,close,volume) — different from
    fno_historical/. This loader normalizes to capitalized columns to match
    `load_daily_bars` output.
    """
    if not NIFTY_50_PATH.exists():
        return None
    df = pd.read_csv(NIFTY_50_PATH, parse_dates=["date"])
    df = df.rename(columns={
        "date": "Date", "open": "Open", "high": "High",
        "low": "Low", "close": "Close", "volume": "Volume",
    })
    df = df[df["Date"].dt.date <= cutoff_date]
    if df.empty:
        return None
    return df.sort_values("Date").reset_index(drop=True)


def load_daily_bars(symbol: str, cutoff_date: date) -> pd.DataFrame | None:
    """Load daily bars for one symbol up to (and including) cutoff_date.

    Returns DataFrame indexed by Date with columns Open/High/Low/Close/Volume,
    or None when the CSV is absent.
    """
    csv_path = FNO_HISTORICAL_DIR / f"{symbol}.csv"
    if not csv_path.exists():
        return None
    df = pd.read_csv(csv_path, parse_dates=["Date"])
    df = df[df["Date"].dt.date <= cutoff_date]
    if df.empty:
        return None
    return df.sort_values("Date").reset_index(drop=True)


def load_theme_member_bars(
    members: list[str], cutoff_date: date
) -> dict[str, pd.DataFrame]:
    """Load bars for every available theme member.

    Returns dict keyed by symbol. Symbols whose CSV is absent are silently
    omitted; caller decides how to handle thin coverage.
    """
    out: dict[str, pd.DataFrame] = {}
    for sym in members:
        df = load_daily_bars(sym, cutoff_date)
        if df is not None and len(df) > 0:
            out[sym] = df
    return out


def _latest_snapshot_path(subfolder: str, prefix: str, suffix: str = ".xlsx") -> Path | None:
    """Return the latest snapshot file under TRENDLYNE_ROOT/<subfolder>/ matching
    `<prefix>*<suffix>`. None if directory absent or empty.
    """
    sd = TRENDLYNE_ROOT / subfolder
    if not sd.is_dir():
        return None
    cands = sorted(sd.glob(f"{prefix}*{suffix}"))
    return cands[-1] if cands else None


def load_multigroup_curtailed(
    cutoff_date: date, view: MultigroupView
) -> pd.DataFrame | None:
    """Load the latest multigroup-curtailed Trendlyne snapshot at-or-before cutoff.

    The XLSX has 3-row preamble (curtailment notice + blank + spacer) before the
    real header at row index 3. ~2,000 rows of NSE-listed stocks.

    Returns DataFrame indexed by NSE Code (so signals can lookup by symbol).
    Returns None when the file is missing.
    """
    p = _latest_snapshot_path(
        "multigroup_curtailed", f"multigroup_curtailed_{view}_", suffix=".xlsx"
    )
    if p is None:
        return None
    snapshot_date = _date_from_filename(p.name)
    if snapshot_date is not None and snapshot_date > cutoff_date:
        return None
    df = pd.read_excel(p, header=3)
    if "NSE Code" not in df.columns:
        return None
    df = df[df["NSE Code"].notna()].copy()
    df.set_index("NSE Code", inplace=True)
    return df


def load_fii_screener(
    cutoff_date: date, polarity: FIIPolarity
) -> pd.DataFrame | None:
    """Load the latest FII increasing/decreasing screener at-or-before cutoff.

    Returns DataFrame indexed by NSE Code with FII holding change QoQ % column.
    For DECREASING the FULL panel (30 cols) is preferred when present (richer
    Promoter/MF/Institutional context), falling back to the 15-col summary.
    """
    sd = TRENDLYNE_ROOT / "fii_screener"
    if not sd.is_dir():
        return None
    if polarity == "decreasing":
        cands = sorted(sd.glob("fii_decreasing_full_shareholding_panel_*.csv")) or sorted(
            sd.glob("fii_decreasing_with_valuation_*.csv")
        )
    else:
        cands = sorted(sd.glob("fii_increasing_*.csv"))
    if not cands:
        return None
    p = cands[-1]
    snapshot_date = _date_from_filename(p.name)
    if snapshot_date is not None and snapshot_date > cutoff_date:
        return None
    df = pd.read_csv(p, encoding="utf-8-sig")
    if "NSE Code" not in df.columns:
        return None
    df = df[df["NSE Code"].notna()].copy()
    df.set_index("NSE Code", inplace=True)
    return df


def load_ipo_calendar(cutoff_date: date) -> pd.DataFrame | None:
    """Concat all listed_ipos_<YYYY>.csv files, parse LISTING DATE to date, filter
    to listings <= cutoff_date - 7d (per spec §3.1 B5 PIT cutoff).

    Returns DataFrame with parsed `listing_date` column and `is_mainboard` bool.
    """
    sd = TRENDLYNE_ROOT / "ipo_calendar"
    if not sd.is_dir():
        return None
    parts = []
    for p in sorted(sd.glob("listed_ipos_*.csv")):
        df = pd.read_csv(p, encoding="utf-8-sig")
        parts.append(df)
    if not parts:
        return None
    full = pd.concat(parts, ignore_index=True)
    full["listing_date"] = pd.to_datetime(full["LISTING DATE"], format="%d %b %y", errors="coerce").dt.date
    full = full.dropna(subset=["listing_date"])
    full["is_mainboard"] = full["MAINBOARD/SME"].astype(str).str.upper().eq("MAINBOARD")
    pit_cutoff = cutoff_date - timedelta(days=7)
    full = full[full["listing_date"] <= pit_cutoff]
    return full.reset_index(drop=True)


def _normalize_stock_name(name: str | None) -> str | None:
    """Normalize a Trendlyne 'Stock' or 'Stock Name' string for cross-snapshot
    fuzzy matching. Strips common corporate-form suffixes + non-alphanumeric.
    """
    if not isinstance(name, str):
        return None
    import re

    s = name.lower()
    for suf in (" ltd.", " ltd", " limited", " inc.", " corp.", " corporation", ".."):
        s = s.replace(suf, "")
    s = re.sub(r"[^a-z0-9]", "", s)
    return s.strip() or None


def _build_name_to_nse_bridge(cutoff_date: date) -> dict[str, str]:
    """Union of every available "Stock Name → NSE Code" mapping at-or-before cutoff.

    Trendlyne exports use full company names ("Reliance Industries Ltd.") while
    every theme membership / signal lookup is keyed by NSE Code ("RELIANCE").
    Different exports cover different universes — multigroup_curtailed has 2,000
    NSE-listed stocks, the F&O multigroup has 209, and the periodic Nifty 500+
    fundamentals export has ~537. Union all three to maximize canonical
    cross-snapshot joinability.

    Returns dict normalized_name → NSE Code. Names are normalized via
    `_normalize_stock_name` (lowercase + corporate-suffix strip + alphanumeric).
    """
    bridge: dict[str, str] = {}

    multigroup_dir = TRENDLYNE_ROOT / "multigroup"
    if multigroup_dir.is_dir():
        for p in sorted(multigroup_dir.glob("*.xlsx")):
            snap_d = _date_from_filename(p.name)
            if snap_d is not None and snap_d > cutoff_date:
                continue
            try:
                df = pd.read_excel(p)
            except Exception:
                continue
            if "Stock Name" not in df.columns or "NSE Code" not in df.columns:
                continue
            for n, nse in zip(df["Stock Name"].apply(_normalize_stock_name), df["NSE Code"]):
                if isinstance(n, str) and isinstance(nse, str):
                    bridge.setdefault(n, nse)

    curtailed_dir = TRENDLYNE_ROOT / "multigroup_curtailed"
    if curtailed_dir.is_dir():
        for p in sorted(curtailed_dir.glob("multigroup_curtailed_returns_shareholding_*.xlsx")):
            snap_d = _date_from_filename(p.name)
            if snap_d is not None and snap_d > cutoff_date:
                continue
            try:
                df = pd.read_excel(p, header=3)
            except Exception:
                continue
            if "Stock Name" not in df.columns or "NSE Code" not in df.columns:
                continue
            for n, nse in zip(df["Stock Name"].apply(_normalize_stock_name), df["NSE Code"]):
                if isinstance(n, str) and isinstance(nse, str):
                    bridge.setdefault(n, nse)

    return bridge


def load_results_dashboard(cutoff_date: date) -> pd.DataFrame | None:
    """Load the latest Trendlyne results_dashboard quarterly snapshot at-or-before
    cutoff, joined to NSE Code via the union of all multigroup name→NSE bridges
    available at-or-before cutoff (multigroup + multigroup_curtailed).

    Canonical TD-D9 source: the quarterly_results CSV exposes "Net Profit
    Surprise Qtr %" (actual vs consensus) and "Revenue Surprise Qtr %" — these
    are the proper EPS-surprise fields the C5 spec calls for, in contrast to
    the v1 proxy (Net Profit QoQ Growth %).

    The CSV is keyed by full company name ("Reliance Industries Ltd."); we
    rebuild the NSE Code via fuzzy normalization against the curtailed
    snapshot. Rows whose name fails to match any NSE Code are dropped (they
    are typically non-F&O small-caps outside our universe).

    Surprise columns are coerced to numeric — Trendlyne uses literal "-" for
    "consensus not available", which becomes NaN. Caller decides how to handle
    NaN coverage.

    Returns DataFrame indexed by NSE Code with columns:
        - "Stock" (full company name)
        - "Last Result Updated"
        - "Net Profit Surprise Qtr %" (numeric)
        - "Revenue Surprise Qtr %" (numeric)
        - "Net Profit Qtr Growth YoY %" (numeric)
        - "Revenue Growth Qtr YoY %" (numeric)

    Returns None when CSV missing OR bridge snapshot missing OR < 1 row matches.
    """
    sd = TRENDLYNE_ROOT / "results_dashboard"
    if not sd.is_dir():
        return None
    cands = sorted(sd.glob("quarterly_results_*.csv"))
    if not cands:
        return None
    p = cands[-1]
    snapshot_date = _date_from_filename(p.name)
    if snapshot_date is not None and snapshot_date > cutoff_date:
        return None
    rd = pd.read_csv(p, encoding="utf-8-sig")
    if "Stock" not in rd.columns:
        return None

    name_to_nse = _build_name_to_nse_bridge(cutoff_date)
    if not name_to_nse:
        return None

    rd["_norm"] = rd["Stock"].apply(_normalize_stock_name)
    rd["NSE Code"] = rd["_norm"].map(name_to_nse)
    rd = rd[rd["NSE Code"].notna()].copy()
    if rd.empty:
        return None

    for col in (
        "Net Profit Surprise Qtr %",
        "Revenue Surprise Qtr %",
        "Net Profit Qtr Growth YoY %",
        "Revenue Growth Qtr YoY %",
    ):
        if col in rd.columns:
            rd[col] = pd.to_numeric(rd[col], errors="coerce")

    rd = rd.drop(columns=["_norm"])
    rd = rd.drop_duplicates(subset=["NSE Code"], keep="first")
    rd = rd.set_index("NSE Code")
    return rd


_NIFTY500_WEIGHTS_DIR = TRENDLYNE_ROOT / "nifty500_weights"


def load_nifty500_weights(
    cutoff_date: date,
    index_name: str = "NIFTY 500",
) -> pd.DataFrame | None:
    """Load NSE-source index constituent weights at-or-before cutoff_date.

    Source: pipeline/scripts/fetch_nse_index_weights.py — pulls
    /api/equity-stockIndices and computes weight_pct = ffmc / sum(ffmc).
    Snapshots written to TRENDLYNE_ROOT/nifty500_weights/<slug>_weights_<date>.csv.

    Returns DataFrame indexed by NSE symbol with columns:
        snapshot_date, index_name, ffmc_inr, weight_pct, last_price,
        p_change_1d, p_change_30d, p_change_365d, year_high, year_low,
        total_traded_value_inr.

    Returns None if no snapshot at-or-before cutoff exists for the requested
    index. Forward-only: history starts from first scraper run (2026-05-02).

    TD-D1 canonical source. Replaces v1 C2 cap_drift proxy once 6m of history
    has accumulated (≈ 2026-11-02).
    """
    if not _NIFTY500_WEIGHTS_DIR.is_dir():
        return None
    slug = index_name.lower().replace(" ", "_")
    cands = sorted(_NIFTY500_WEIGHTS_DIR.glob(f"{slug}_weights_*.csv"))
    if not cands:
        return None
    chosen: Path | None = None
    for p in reversed(cands):
        snapshot_date = _date_from_filename(p.name)
        if snapshot_date is None:
            continue
        if snapshot_date <= cutoff_date:
            chosen = p
            break
    if chosen is None:
        return None
    df = pd.read_csv(chosen)
    if "nse_symbol" not in df.columns:
        return None
    df = df.dropna(subset=["nse_symbol"]).set_index("nse_symbol")
    return df


def load_trendlyne_nifty500_weights(cutoff_date: date) -> pd.DataFrame | None:
    """Load Trendlyne-source NIFTY-500 weights at-or-before cutoff_date.

    Source: docs/superpowers/specs/New folder/nifty 500.xlsx → manually parsed
    to TRENDLYNE_ROOT/nifty500_weights/trendlyne_nifty500_parsed_<date>.csv.

    Schema: snapshot_date, source, Company, nse_symbol, weight_pct.

    Sister of load_nifty500_weights for cross-validation. Note: methodology
    differs (free-float vs Trendlyne adj) — HDFCBANK NSE 6.03% vs Trendlyne 3.0%.
    Returns None if no parsed CSV at-or-before cutoff exists.
    """
    if not _NIFTY500_WEIGHTS_DIR.is_dir():
        return None
    cands = sorted(_NIFTY500_WEIGHTS_DIR.glob("trendlyne_nifty500_parsed_*.csv"))
    if not cands:
        return None
    chosen: Path | None = None
    for p in reversed(cands):
        snapshot_date = _date_from_filename(p.name)
        if snapshot_date is None:
            continue
        if snapshot_date <= cutoff_date:
            chosen = p
            break
    if chosen is None:
        return None
    df = pd.read_csv(chosen)
    if "nse_symbol" not in df.columns:
        return None
    df = df.dropna(subset=["nse_symbol"]).set_index("nse_symbol")
    return df


def load_shareholding_panel(cutoff_date: date) -> pd.DataFrame | None:
    """Load the latest standalone shareholding_panel snapshot at-or-before cutoff.

    Lighter-weight than multigroup_curtailed_returns_shareholding but only
    50 rows; used as a sanity-check companion.
    """
    sd = TRENDLYNE_ROOT / "shareholding_panel"
    if not sd.is_dir():
        return None
    cands = sorted(sd.glob("shareholding_panel_*.csv"))
    if not cands:
        return None
    p = cands[-1]
    snapshot_date = _date_from_filename(p.name)
    if snapshot_date is not None and snapshot_date > cutoff_date:
        return None
    df = pd.read_csv(p, encoding="utf-8-sig")
    return df


def _date_from_filename(name: str) -> date | None:
    """Extract a YYYY-MM-DD from a filename. Returns None if not found."""
    import re

    m = re.search(r"(\d{4}-\d{2}-\d{2})", name)
    if m is None:
        return None
    try:
        return datetime.strptime(m.group(1), "%Y-%m-%d").date()
    except ValueError:
        return None
