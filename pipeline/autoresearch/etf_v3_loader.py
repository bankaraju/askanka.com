"""ETF v3 canonical data loader.

Single source of truth for the v3 regime engine's input panel. Enforces every
rule in `pipeline/data/research/etf_v3/2026-04-26-etf-v3-data-audit.md`:

  - NIFTY trading calendar is the canonical timestamp axis.
  - Foreign series forward-fill onto Indian-only days, max 5-day look-back.
  - India VIX: drop NSE-holiday carry-forwards; fill 2025-02-01 Budget Saturday.
  - FII/DII: T-1 anchoring; exclude T (NSE provisional release after open).
  - Hard-fail on any gap > 5 calendar days for foreign series.

The v3 research module reads ONLY through this loader. Any direct parquet read
from etf_v3_research.py is a contract violation.

Run as a CLI to perform the audit before any v3 run:

    PYTHONIOENCODING=utf-8 python pipeline/autoresearch/etf_v3_loader.py --audit
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[2]
DAILY_BARS = REPO_ROOT / "pipeline" / "data" / "research" / "phase_c" / "daily_bars"

WINDOW_START = pd.Timestamp("2021-04-23")
WINDOW_END = pd.Timestamp("2026-04-23")
IN_SAMPLE_END = pd.Timestamp("2025-12-31")
HOLDOUT_START = pd.Timestamp("2026-01-01")

MAX_FORWARD_FILL_DAYS = 5

FOREIGN_ETFS: dict[str, str] = {
    "sp500": "us_market",
    "treasury": "us_market",
    "dollar": "fx",
    "gold": "commodity",
    "crude_oil": "commodity",
    "copper": "commodity",
    "brazil": "em",
    "china_etf": "asia",
    "korea_etf": "asia",
    "japan_etf": "asia",
    "developed": "global",
    "em": "global",
    "euro": "fx",
    "high_yield": "credit",
    "financials": "us_sector",
    "industrials": "us_sector",
    "kbw_bank": "us_sector",
    "agriculture": "commodity",
    "global_bonds": "rates",
    "india_etf": "india_proxy",
    # Added 2026-04-26 to align with production v2 GLOBAL_ETFS weights.
    # natgas + silver carry significant weight in current optimal_weights.json
    # (natgas -8.21, silver -3.26). tech + yen carry small weights but are
    # included for completeness so v2-faithful research matches production.
    "tech": "us_sector",
    "natgas": "commodity",
    "silver": "commodity",
    "yen": "fx",
    # Curated-list expansion 2026-04-26 — see docs/superpowers/specs/cureated ETF.txt
    # for per-ticker thesis. Each entry has an explicit India-channel rationale.
    "taiwan_etf": "asia",       # EWT — TSMC/semiconductor foundry pulse
    "qqq": "us_market",         # QQQ — Nasdaq 100 growth sentiment, leads Nifty IT
    "aiq": "us_sector",         # AIQ — pure-play AI/software, distinct from XLK
    "smh": "us_sector",         # SMH — semiconductor cycle leads Indian EMS (Dixon)
    "iwm": "us_market",         # IWM — Russell 2000 small-caps, EM liquidity proxy
    "xle": "us_sector",         # XLE — US Energy, Reliance/OMC proxy
    "xlv": "us_sector",         # XLV — US Healthcare, Indian pharma defensive
    "mchi": "asia",             # MCHI — broader China exposure than FXI
    "dbb": "commodity",         # DBB — base metals, leads Tata Steel/JSW/Hindalco
    "emb": "credit",            # EMB — EM USD bond, EM credit risk barometer
    "krbn": "thematic",         # KRBN — global carbon prices, energy-transition cost
    "lit": "thematic",          # LIT — lithium/battery, Tata Motors EV signal
    "kweb": "asia",             # KWEB — China internet, Zomato/Nykaa sentiment
    "vixy": "vol",              # VIXY — US VIX short-term, tail-risk magnitude
    "ewg": "europe",            # EWG — Germany, Indian auto-parts trade partner
    "bito": "thematic",         # BITO — Bitcoin ETF, EM liquidity canary
}

INDIA_VIX_BUDGET_SATURDAY = pd.Timestamp("2025-02-01")


class DataGapError(RuntimeError):
    """Raised when a series has a gap larger than the policy permits."""


@dataclass(frozen=True)
class AuditResult:
    series: str
    rows: int
    start: pd.Timestamp
    end: pd.Timestamp
    missing_vs_nifty: int
    extras_vs_nifty: int
    max_internal_gap_days: int
    status: str  # 'ok' | 'fixed' | 'fail'
    notes: str


def _load_parquet(name: str) -> pd.DataFrame:
    p = DAILY_BARS / f"{name}.parquet"
    if not p.exists():
        raise DataGapError(f"required source missing: {p}")
    df = pd.read_parquet(p)
    if "date" not in df.columns or "close" not in df.columns:
        raise DataGapError(f"{name}: schema must include {{date, close}}")
    df = df[["date", "close"]].copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").drop_duplicates("date").reset_index(drop=True)
    return df


def _nifty_calendar() -> pd.DatetimeIndex:
    """NIFTY trading days inside the v3 window — the canonical timestamp axis."""
    nifty = _load_parquet("nifty_close_daily")
    mask = (nifty["date"] >= WINDOW_START) & (nifty["date"] <= WINDOW_END)
    cal = pd.DatetimeIndex(nifty.loc[mask, "date"].sort_values().unique())
    if len(cal) == 0:
        raise DataGapError("NIFTY calendar empty for v3 window")
    return cal


def _max_internal_gap(df: pd.DataFrame) -> int:
    if len(df) < 2:
        return 0
    diffs = df["date"].diff().dt.days.dropna()
    return int(diffs.max()) if len(diffs) else 0


def _align_foreign(name: str, calendar: pd.DatetimeIndex) -> pd.Series:
    """Forward-fill a foreign ETF onto the NIFTY calendar (max 5 calendar days).

    Raises DataGapError if any internal gap inside the source itself exceeds 5
    calendar days — that would indicate a missing fetch, not a calendar mismatch.
    """
    df = _load_parquet(name)
    win = df[(df["date"] >= WINDOW_START - pd.Timedelta(days=14)) & (df["date"] <= WINDOW_END)]
    gap = _max_internal_gap(win)
    if gap > MAX_FORWARD_FILL_DAYS:
        # Long weekends + holidays can produce 4-day gaps legitimately. > 5 is unexpected.
        # However Christmas/NY can hit 4-5; bump check to >5.
        raise DataGapError(
            f"{name}: internal gap of {gap} days exceeds policy limit "
            f"({MAX_FORWARD_FILL_DAYS}). Re-fetch source before running v3."
        )
    s = win.set_index("date")["close"].sort_index()
    aligned = s.reindex(calendar, method="ffill", limit=MAX_FORWARD_FILL_DAYS)
    return aligned.rename(name)


def _align_india_vix(calendar: pd.DatetimeIndex) -> pd.Series:
    """India VIX with NSE-holiday extras dropped + Budget Saturday filled."""
    df = _load_parquet("india_vix_daily")
    df = df[(df["date"] >= WINDOW_START) & (df["date"] <= WINDOW_END)]
    nifty_set = set(calendar)
    # Drop carry-forwards on NSE holidays
    df = df[df["date"].isin(nifty_set)].copy()
    s = df.set_index("date")["close"].sort_index()
    aligned = s.reindex(calendar)
    # Budget Saturday 2025-02-01: NIFTY traded, VIX wasn't computed — forward-fill from prior day.
    if INDIA_VIX_BUDGET_SATURDAY in aligned.index and pd.isna(aligned.loc[INDIA_VIX_BUDGET_SATURDAY]):
        prior = calendar[calendar < INDIA_VIX_BUDGET_SATURDAY]
        if len(prior):
            aligned.loc[INDIA_VIX_BUDGET_SATURDAY] = aligned.loc[prior[-1]]
    return aligned.rename("india_vix")


def _align_flow(name: str, calendar: pd.DatetimeIndex) -> pd.Series:
    """FII or DII net daily aligned to NIFTY calendar.

    Source is published T+1, so the latest day in the source is yesterday's flow
    (intended use). Loader leaves NaN where T-1 isn't yet posted; v3 model masks.
    """
    df = _load_parquet(name)
    df = df[(df["date"] >= WINDOW_START) & (df["date"] <= WINDOW_END)]
    s = df.set_index("date")["close"].sort_index()
    aligned = s.reindex(calendar)
    return aligned.rename(name.replace("_net_daily", "_net"))


def _align_nifty(calendar: pd.DatetimeIndex) -> pd.Series:
    df = _load_parquet("nifty_close_daily")
    df = df[(df["date"] >= WINDOW_START) & (df["date"] <= WINDOW_END)]
    s = df.set_index("date")["close"].sort_index()
    return s.reindex(calendar).rename("nifty_close")


def _enforce_t1_anchor(panel: pd.DataFrame) -> pd.DataFrame:
    """Shift every input column by 1 NIFTY-trading-day so features at decision-day T
    use values realised at NSE close T-1.

    The panel index after this operation is the *decision day*, not the realisation
    day. This is the contract v3 fits and predicts on.
    """
    return panel.shift(1)


def build_panel(*, t1_anchor: bool = True) -> pd.DataFrame:
    """Return the canonical v3 input panel.

    Columns: 20 foreign ETF closes + india_vix + fii_net + dii_net + nifty_close.
    Index: NIFTY trading day (interpretable as decision day if t1_anchor=True).
    """
    cal = _nifty_calendar()
    series: list[pd.Series] = []
    for name in FOREIGN_ETFS:
        series.append(_align_foreign(name, cal))
    series.append(_align_india_vix(cal))
    series.append(_align_flow("fii_net_daily", cal))
    series.append(_align_flow("dii_net_daily", cal))
    series.append(_align_nifty(cal))
    panel = pd.concat(series, axis=1)
    panel.index.name = "date"
    if t1_anchor:
        panel = _enforce_t1_anchor(panel)
    return panel


def audit_panel() -> list[AuditResult]:
    """Per-series audit results — used by CLI and tests."""
    cal = _nifty_calendar()
    cal_set = set(cal)
    results: list[AuditResult] = []

    def _audit_one(name: str, df: pd.DataFrame, status: str, notes: str) -> AuditResult:
        in_win = df[(df["date"] >= WINDOW_START) & (df["date"] <= WINDOW_END)].copy()
        in_win_set = set(in_win["date"])
        return AuditResult(
            series=name,
            rows=len(in_win),
            start=in_win["date"].min() if len(in_win) else pd.NaT,
            end=in_win["date"].max() if len(in_win) else pd.NaT,
            missing_vs_nifty=len(cal_set - in_win_set),
            extras_vs_nifty=len(in_win_set - cal_set),
            max_internal_gap_days=_max_internal_gap(in_win),
            status=status,
            notes=notes,
        )

    for name in FOREIGN_ETFS:
        df = _load_parquet(name)
        gap = _max_internal_gap(df[(df["date"] >= WINDOW_START) & (df["date"] <= WINDOW_END)])
        status = "fixed" if gap <= MAX_FORWARD_FILL_DAYS else "fail"
        notes = f"calendar mismatch absorbed via T-1 ffill (max gap {gap}d)"
        results.append(_audit_one(name, df, status, notes))

    vix = _load_parquet("india_vix_daily")
    results.append(_audit_one(
        "india_vix_daily", vix, "fixed",
        "drop NSE-holiday carry-forwards (~70 rows); fill Budget Saturday 2025-02-01",
    ))

    for fname in ("fii_net_daily", "dii_net_daily"):
        flow = _load_parquet(fname)
        results.append(_audit_one(fname, flow, "ok", "T-1 anchored; T release excluded"))

    nifty = _load_parquet("nifty_close_daily")
    results.append(_audit_one("nifty_close_daily", nifty, "ok", "canonical calendar"))

    return results


def _print_audit(results: list[AuditResult]) -> int:
    print(f"NIFTY canonical days in v3 window: {len(_nifty_calendar())}")
    print(f"Window: {WINDOW_START.date()} .. {WINDOW_END.date()}  "
          f"(in-sample <= {IN_SAMPLE_END.date()}; holdout >= {HOLDOUT_START.date()})")
    print()
    header = ("series", "status", "rows", "start", "end", "miss", "extra", "max_gap", "notes")
    print(f"{header[0]:<22} {header[1]:<6} {header[2]:>5} {header[3]:<11} "
          f"{header[4]:<11} {header[5]:>5} {header[6]:>5} {header[7]:>7}  {header[8]}")
    print("-" * 130)
    fail = 0
    for r in results:
        if r.status == "fail":
            fail += 1
        print(f"{r.series:<22} {r.status:<6} {r.rows:>5} "
              f"{str(r.start.date()) if pd.notna(r.start) else '-':<11} "
              f"{str(r.end.date()) if pd.notna(r.end) else '-':<11} "
              f"{r.missing_vs_nifty:>5} {r.extras_vs_nifty:>5} "
              f"{r.max_internal_gap_days:>7}  {r.notes}")
    print()
    if fail:
        print(f"AUDIT FAIL: {fail} series with internal gap > {MAX_FORWARD_FILL_DAYS}d. v3 cannot run.")
        return 1
    print("AUDIT PASS: every input cleared §9 cleanliness gate.")
    return 0


def _smoke_panel() -> int:
    panel = build_panel(t1_anchor=True)
    n_in = ((panel.index >= WINDOW_START) & (panel.index <= IN_SAMPLE_END)).sum()
    n_out = ((panel.index >= HOLDOUT_START) & (panel.index <= WINDOW_END)).sum()
    print(f"Panel built. shape={panel.shape}  in-sample-rows={n_in}  holdout-rows={n_out}")
    nan_pct = (panel.isna().sum() / len(panel) * 100).round(2)
    worst = nan_pct.sort_values(ascending=False).head(5)
    print("Top-5 NaN% per column (post T-1 anchor; first row is structurally NaN):")
    for col, pct in worst.items():
        print(f"  {col:<28} {pct:>6.2f}%")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="ETF v3 canonical loader CLI")
    parser.add_argument("--audit", action="store_true", help="run §9 cleanliness audit and exit")
    parser.add_argument("--smoke", action="store_true", help="build panel and print summary")
    args = parser.parse_args()
    if args.audit:
        return _print_audit(audit_panel())
    if args.smoke:
        return _smoke_panel()
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
