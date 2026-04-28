"""NSE F&O bhavcopy backfill — historical OI for the intraday-v1 kickoff fit.

Closes the in-sample feature 1 (delta_pcr_2d) data gap. The live oi_scanner
archive at ``pipeline/data/oi_history_stocks/`` only covers 2026-04-19 onward
(8 days at the time of writing). This module downloads NSE's daily F&O
bhavcopy (the durable archive that has been continuously available — see
``reference_nse_bulk_deals_history_unavailable.md`` for the contrast: this is
the SECOND historical NSE archive we've integrated, after bulk_deals which is
not durable), parses strike-level OI, aggregates per-symbol next-month
put/call totals, and writes JSONs matching the live oi_scanner schema in the
exact same archive directory.

Source URL (verified 2026-04-28):

    https://nsearchives.nseindia.com/content/fo/BhavCopy_NSE_FO_0_0_0_<YYYYMMDD>_F_0000.csv.zip

NSE migrated F&O bhavcopy to this UDiFF format on 2024-07-08. The legacy URL
``content/historical/DERIVATIVES/<YYYY>/<MMM>/fo<DDMMM><YYYY>bhav.csv.zip``
is no longer served (returns 404 even on known trading days). Probe across
2026-02-28 → 2026-04-29 confirms the UDiFF endpoint is the live one.

UDiFF column mapping (vs. legacy spec):
    INSTRUMENT  -> FinInstrmTp   (STO=stock options, IDO=index options,
                                  STF=stock futures, IDF=index futures)
    SYMBOL      -> TckrSymb
    EXPIRY_DT   -> XpryDt        (ISO YYYY-MM-DD)
    OPTION_TYP  -> OptnTp        (CE / PE)
    OPEN_INT    -> OpnIntrst

Hard contract (per ``feedback_no_hallucination_mandate.md``):
- 404 / parse failure -> skip the date silently. No file written.
- Pre-existing file at the same date (e.g., richer live oi_scanner snapshot)
  -> preserve. Bhavcopy never overwrites a live snapshot.
- A symbol with only one expiry on date D has no 'next' chain and is omitted.
- Output blob populates ONLY the fields ``pcr_producer.py`` consumes:
  ``symbol``, ``timestamp``, ``near.expiry``, ``near.call_oi``, ``near.put_oi``,
  ``next.expiry``, ``next.call_oi``, ``next.put_oi``. The richer fields the
  live oi_scanner emits (``max_pain``, ``pinning``, ``pcr``, ``sentiment``,
  ``call_walls``, ``put_walls``, ``oi_anomaly``, ``pcr_flip``,
  ``rollover_ratio``, ``oi_change``, ``prev_total_oi``) are deliberately
  omitted — bhavcopy does not give us walls or pin distance, and fabricating
  them would violate the no-hallucination mandate.

Phase 4 fit consumer pattern (per task spec, "pick whichever pattern is
simpler"):
    The Phase 4 (kickoff fit) consumer simply re-uses the existing
    per-date pcr_producer.produce_pcr_snapshots(eval_date=...) call once per
    in-sample date, walking the full archive. No new schema, no parquet, no
    date-keyed subdir. Reasoning: pcr_producer already handles "today" +
    "2 days ago" anchoring against archive-file ordering (skipping weekends/
    holidays naturally), so the fit just iterates each archive date as the
    eval_date and reads the resulting per-symbol JSONs from a tmp output_dir
    one date at a time. This avoids changing pcr_producer's signature or
    runtime contract — the existing 5 tests all keep passing untouched.

CLI:
    python -m pipeline.research.intraday_v1.bhavcopy_backfill
        # backfills 2026-02-28 → 2026-04-29 into pipeline/data/oi_history_stocks/

Strategy gate: this module does NOT match the trading-rule regex
(*_strategy.py / *_signal_generator.py / *_backtest.py / *_ranker.py /
*_engine.py) so the pre-commit hook does not require a hypothesis-registry
entry. It is a data ingestor, not a trading rule.
"""
from __future__ import annotations

import io
import json
import logging
import zipfile
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
import requests

PIPELINE_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = PIPELINE_ROOT / "data" / "oi_history_stocks"

URL_TEMPLATE = (
    "https://nsearchives.nseindia.com/content/fo/"
    "BhavCopy_NSE_FO_0_0_0_{yyyymmdd}_F_0000.csv.zip"
)

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120 Safari/537.36"
)
REQUEST_HEADERS = {
    "User-Agent": UA,
    "Referer": "https://www.nseindia.com/all-reports-derivatives",
}

OPTION_INSTR_TYPES = ("STO", "IDO")  # stock options + index options

log = logging.getLogger("intraday_v1.bhavcopy_backfill")


# ---------------------------------------------------------------------------
# Step 1 — download
# ---------------------------------------------------------------------------

def download_bhavcopy(date_obj: date) -> Optional[bytes]:
    """Fetch the F&O bhavcopy ZIP for ``date_obj``.

    Returns the raw ZIP bytes on HTTP 200, ``None`` on HTTP 404 (weekend/
    holiday/unavailable). Any other unexpected exception is propagated so
    callers can decide whether to log and continue or abort.
    """
    url = URL_TEMPLATE.format(yyyymmdd=date_obj.strftime("%Y%m%d"))
    try:
        r = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    except requests.RequestException as e:
        log.warning(f"bhavcopy fetch network error for {date_obj}: {e}")
        return None
    if r.status_code == 404:
        return None
    if r.status_code != 200:
        log.warning(f"bhavcopy fetch unexpected status {r.status_code} for {date_obj}")
        return None
    if not r.content:
        return None
    return r.content


# ---------------------------------------------------------------------------
# Step 2 — parse
# ---------------------------------------------------------------------------

def parse_bhavcopy(zip_bytes: bytes) -> pd.DataFrame:
    """Extract the single CSV member from ``zip_bytes`` and return as DataFrame.

    Column dtypes are coerced minimally: ``OpnIntrst`` -> Int64 (nullable),
    ``XpryDt`` left as ISO string (parsed downstream by the aggregator).
    """
    zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
    members = zf.namelist()
    if not members:
        raise ValueError("bhavcopy ZIP is empty")
    # NSE always packs exactly one CSV; pick the first.
    csv_text = zf.read(members[0]).decode("utf-8")
    df = pd.read_csv(io.StringIO(csv_text))
    # Whitespace defense (UDiFF historically clean, but be safe).
    if "TckrSymb" in df.columns:
        df["TckrSymb"] = df["TckrSymb"].astype(str).str.strip()
    if "FinInstrmTp" in df.columns:
        df["FinInstrmTp"] = df["FinInstrmTp"].astype(str).str.strip()
    if "OptnTp" in df.columns:
        df["OptnTp"] = df["OptnTp"].astype(str).str.strip()
    if "XpryDt" in df.columns:
        df["XpryDt"] = df["XpryDt"].astype(str).str.strip()
    if "OpnIntrst" in df.columns:
        df["OpnIntrst"] = pd.to_numeric(df["OpnIntrst"], errors="coerce").astype("Int64")
    return df


# ---------------------------------------------------------------------------
# Step 3 — aggregate
# ---------------------------------------------------------------------------

def aggregate_oi_for_date(df: pd.DataFrame, date_obj: date) -> Dict[str, dict]:
    """Produce the per-symbol JSON dict matching the oi_history_stocks schema.

    For each symbol with at least 2 distinct expiries among option rows, picks
    the smallest expiry >= ``date_obj`` as ``near`` and the second-smallest as
    ``next``, then sums OpnIntrst across all strikes per (expiry, OptnTp).

    Symbols with only one option expiry on date_obj are silently dropped — no
    fabricated 'next' chain. Per the no-hallucination contract.
    """
    options = df[df["FinInstrmTp"].isin(OPTION_INSTR_TYPES)].copy()
    options = options[options["OptnTp"].isin(("CE", "PE"))]
    options = options.dropna(subset=["TckrSymb", "XpryDt", "OpnIntrst"])
    if options.empty:
        return {}

    # Group by symbol; for each, pick the two earliest expiries >= eval_date.
    # If fewer than 2 are available, skip the symbol.
    eval_iso = date_obj.isoformat()
    out: Dict[str, dict] = {}
    timestamp = f"{eval_iso}T15:30:00+0530"

    for sym, grp in options.groupby("TckrSymb", sort=True):
        # Distinct expiries for this symbol (ISO strings sort correctly).
        expiries = sorted(set(grp["XpryDt"].tolist()))
        # Drop any expiries strictly before eval_date (unlikely in a daily
        # bhavcopy but defensive).
        expiries_forward = [e for e in expiries if e >= eval_iso]
        if len(expiries_forward) < 2:
            continue
        near_exp = expiries_forward[0]
        next_exp = expiries_forward[1]

        near_rows = grp[grp["XpryDt"] == near_exp]
        next_rows = grp[grp["XpryDt"] == next_exp]

        def _sum(rows, opt_tp: str) -> int:
            sub = rows[rows["OptnTp"] == opt_tp]
            if sub.empty:
                return 0
            total = sub["OpnIntrst"].sum()
            # pd.NA -> 0 only when the column is genuinely empty — handled above.
            return int(total) if pd.notna(total) else 0

        out[sym] = {
            "symbol": sym,
            "timestamp": timestamp,
            "near": {
                "expiry": near_exp,
                "call_oi": _sum(near_rows, "CE"),
                "put_oi": _sum(near_rows, "PE"),
            },
            "next": {
                "expiry": next_exp,
                "call_oi": _sum(next_rows, "CE"),
                "put_oi": _sum(next_rows, "PE"),
            },
        }
    return out


# ---------------------------------------------------------------------------
# Step 4 — orchestrator
# ---------------------------------------------------------------------------

def backfill_range(start_date: date, end_date: date, output_dir: Path) -> Dict:
    """Iterate ``[start_date, end_date]`` inclusive; write JSON per trading day.

    Skips:
    - dates whose JSON already exists (preserves richer live oi_scanner snapshots)
    - dates returning None from download_bhavcopy (weekend/holiday/unavailable)
    - dates whose parse or aggregate raises (logged in errors list, no file written)

    Returns summary:
        {
            "days_attempted": int,
            "days_written": int,
            "days_skipped_existing": int,
            "days_skipped_404_or_holiday": int,
            "errors": [{"date": "YYYY-MM-DD", "error": "..."}],
            "dates_written": ["YYYY-MM-DD", ...],
        }
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    summary: Dict = {
        "days_attempted": 0,
        "days_written": 0,
        "days_skipped_existing": 0,
        "days_skipped_404_or_holiday": 0,
        "errors": [],
        "dates_written": [],
    }
    if start_date > end_date:
        return summary

    cur = start_date
    while cur <= end_date:
        summary["days_attempted"] += 1
        target_path = output_dir / f"{cur.isoformat()}.json"
        if target_path.exists():
            summary["days_skipped_existing"] += 1
            cur += timedelta(days=1)
            continue
        try:
            zip_bytes = download_bhavcopy(cur)
        except Exception as e:  # network defended above; this is belt-and-braces
            summary["errors"].append({"date": cur.isoformat(), "error": f"download: {e}"})
            cur += timedelta(days=1)
            continue
        if zip_bytes is None:
            summary["days_skipped_404_or_holiday"] += 1
            cur += timedelta(days=1)
            continue
        try:
            df = parse_bhavcopy(zip_bytes)
            blob = aggregate_oi_for_date(df, cur)
        except Exception as e:
            summary["errors"].append({"date": cur.isoformat(), "error": f"parse/aggregate: {e}"})
            cur += timedelta(days=1)
            continue
        if not blob:
            # Defensible empty: no option rows or all symbols had only one expiry.
            # Skip (no file) — empty file would be misleading evidence.
            summary["errors"].append({"date": cur.isoformat(), "error": "empty_aggregate"})
            cur += timedelta(days=1)
            continue
        target_path.write_text(json.dumps(blob, indent=2), encoding="utf-8")
        summary["days_written"] += 1
        summary["dates_written"].append(cur.isoformat())
        cur += timedelta(days=1)

    return summary


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    # 60 calendar days back from 2026-04-29 (kickoff-fit eval date) -> 2026-02-28.
    summary = backfill_range(
        start_date=date(2026, 2, 28),
        end_date=date(2026, 4, 29),
        output_dir=DEFAULT_OUTPUT_DIR,
    )
    print(json.dumps(summary, indent=2, default=str))
