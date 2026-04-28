"""Retro-score each Phase C SHORT event with current FCS coefficients
and bucket outcomes by score band.

Inputs (read-only):
- pipeline/data/research/mechanical_replay/v2/phase_c_roster.csv
- pipeline/data/ticker_feature_models.json
- pipeline/data/fno_historical/<ticker>.csv  (PIT bars)
- pipeline/data/india_historical/indices/<sector>_daily.csv
- data/trust_scores.json
- pipeline/feature_scorer.features (pure, no I/O)

Output:
- pipeline/data/research/phase_c_fcs_bucket/<run_date>/
    - per_event.csv        (one row per event: date, ticker, score, ...)
    - bucket_summary.csv   (per-bucket counts, win-rate, avg return)
    - report.md            (human-readable one-pager)

Run:
    python -m pipeline.research.phase_c_fcs_bucket.analysis
"""
from __future__ import annotations

import csv
import json
import math
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd

from pipeline.feature_scorer import features as fcs_features
from pipeline.feature_scorer import cohorts
from pipeline.feature_scorer.model import _INTERACTIONS

_PIPELINE_DIR = Path(__file__).resolve().parents[2]
_REPO_ROOT = _PIPELINE_DIR.parent
_DATA_DIR = _PIPELINE_DIR / "data"

ROSTER_CSV = _DATA_DIR / "research" / "mechanical_replay" / "v2" / "phase_c_roster.csv"
MODELS_JSON = _DATA_DIR / "ticker_feature_models.json"
FNO_HIST_DIR = _DATA_DIR / "fno_historical"
INDEX_HIST_DIR = _DATA_DIR / "india_historical" / "indices"
TRUST_SCORES_JSON = _REPO_ROOT / "data" / "trust_scores.json"
OUT_BASE = _DATA_DIR / "research" / "phase_c_fcs_bucket"

BUCKETS = [
    ("<40", 0, 40),
    ("40-55", 40, 55),
    ("55-70", 55, 70),
    (">=70", 70, 101),
]
DEFAULT_DTE = 10


def _bucket_for(score: int) -> str:
    for label, lo, hi in BUCKETS:
        if lo <= score < hi:
            return label
    return ">=70"


def _load_trust_scores() -> dict:
    try:
        data = json.loads(TRUST_SCORES_JSON.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    stocks = data.get("stocks", data) if isinstance(data, dict) else data
    if isinstance(stocks, list):
        return {(s.get("symbol") or "").upper(): s.get("sector_grade")
                for s in stocks if s.get("symbol")}
    return stocks or {}


def _load_ticker_bars(ticker: str) -> Optional[pd.DataFrame]:
    p = FNO_HIST_DIR / f"{ticker}.csv"
    if not p.exists():
        return None
    df = pd.read_csv(p)
    df.columns = [c.lower() for c in df.columns]
    return df


def _load_sector_bars(cohort: str) -> Optional[pd.DataFrame]:
    label = cohort if cohort != "MIDCAP_GENERIC" else "MIDCPNIFTY"
    p = INDEX_HIST_DIR / f"{label}_daily.csv"
    if not p.exists():
        return None
    df = pd.read_csv(p)
    df.columns = [c.lower() for c in df.columns]
    return df


def _nifty_breadth_pit(as_of: str) -> float:
    """Direction-only PIT proxy for NIFTY 5d breadth (matches live `_nifty_breadth_5d`)."""
    p = INDEX_HIST_DIR / "NIFTY_daily.csv"
    if not p.exists():
        return 0.5
    try:
        df = pd.read_csv(p)
        df.columns = [c.lower() for c in df.columns]
        as_of_ts = pd.Timestamp(as_of)
        mask = pd.to_datetime(df["date"]) <= as_of_ts
        tail = df.loc[mask, "close"].tail(6).tolist()
        if len(tail) < 6:
            return 0.5
        return 0.6 if tail[-1] > tail[0] else 0.4
    except Exception:
        return 0.5


def _apply_interactions(features_dict: dict) -> dict:
    out = dict(features_dict)
    for a, b in _INTERACTIONS:
        if a in features_dict and b in features_dict:
            va = features_dict[a]
            vb = features_dict[b]
            if va is None or vb is None:
                out[f"{a}__x__{b}"] = 0.0
            else:
                out[f"{a}__x__{b}"] = va * vb
    return out


def _score(features_dict: dict, coefs: dict) -> int:
    enriched = _apply_interactions(features_dict)
    logit = 0.0
    for name, coef in coefs.items():
        v = enriched.get(name, 0.0)
        if v is None:
            v = 0.0
        logit += coef * v
    prob = 1.0 / (1.0 + math.exp(-logit))
    return int(round(prob * 100))


def retro_score_event(
    *,
    ticker: str,
    as_of: str,
    regime: str,
    coefs: dict,
    trust_grade: Optional[str],
) -> Optional[int]:
    bars = _load_ticker_bars(ticker)
    if bars is None or len(bars) < 20:
        return None
    cohort = cohorts.ticker_to_cohort(ticker)
    sector_bars = _load_sector_bars(cohort)
    if sector_bars is None or len(sector_bars) < 20:
        return None
    breadth = _nifty_breadth_pit(as_of)
    try:
        feats = fcs_features.build_feature_vector(
            prices=bars,
            sector=sector_bars,
            as_of=as_of,
            regime=regime,
            dte=DEFAULT_DTE,
            trust_grade=trust_grade,
            nifty_breadth_5d=breadth,
            pcr_z_score=None,
        )
    except Exception:
        return None
    return _score(feats, coefs)


def run(*, output_dir: Path | None = None) -> Path:
    if not ROSTER_CSV.exists():
        raise FileNotFoundError(f"phase_c_roster missing: {ROSTER_CSV}")
    if not MODELS_JSON.exists():
        raise FileNotFoundError(f"feature models missing: {MODELS_JSON}")

    roster = pd.read_csv(ROSTER_CSV)
    roster = roster[roster["trade_rec"].astype(str).str.upper() == "SHORT"].copy()

    models_blob = json.loads(MODELS_JSON.read_text(encoding="utf-8"))
    models = models_blob.get("models", {})
    trust_map = _load_trust_scores()

    rows: list[dict] = []
    n_skipped_no_model = 0
    n_skipped_no_data = 0
    for _, ev in roster.iterrows():
        ticker = str(ev["ticker"]).upper()
        meta = models.get(ticker) or {}
        coefs = meta.get("coefficients") or {}
        if not coefs:
            n_skipped_no_model += 1
            continue
        score = retro_score_event(
            ticker=ticker,
            as_of=str(ev["date"]),
            regime=str(ev.get("regime") or "NEUTRAL"),
            coefs=coefs,
            trust_grade=trust_map.get(ticker),
        )
        if score is None:
            n_skipped_no_data += 1
            continue
        actual_return = float(ev["actual_return"])
        win = actual_return < 0  # SHORT wins when underlying falls
        rows.append({
            "date": str(ev["date"]),
            "ticker": ticker,
            "regime": ev.get("regime"),
            "classification": ev.get("classification"),
            "event_geometry": ev.get("event_geometry"),
            "z_score": float(ev["z_score"]),
            "actual_return": actual_return,
            "short_pnl": -actual_return,  # SHORT P&L is opposite of price return
            "fcs_score": score,
            "fcs_bucket": _bucket_for(score),
            "fcs_band": meta.get("health"),
            "win": int(win),
        })

    if not rows:
        raise RuntimeError("no events scored — investigate skip counts")

    out_dir = output_dir or (OUT_BASE / datetime.now().strftime("%Y-%m-%d"))
    out_dir.mkdir(parents=True, exist_ok=True)

    per_event_path = out_dir / "per_event.csv"
    with per_event_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        for r in rows:
            w.writerow(r)

    df = pd.DataFrame(rows)
    by_bucket = df.groupby("fcs_bucket", sort=False)
    summary_rows: list[dict] = []
    for label, _, _ in BUCKETS:
        if label not in by_bucket.groups:
            summary_rows.append({
                "bucket": label,
                "n": 0,
                "wins": 0,
                "win_rate": None,
                "avg_short_pnl": None,
                "avg_actual_return": None,
            })
            continue
        g = by_bucket.get_group(label)
        n = len(g)
        wins = int(g["win"].sum())
        summary_rows.append({
            "bucket": label,
            "n": n,
            "wins": wins,
            "win_rate": round(wins / n, 4) if n else None,
            "avg_short_pnl": round(float(g["short_pnl"].mean()), 6) if n else None,
            "avg_actual_return": round(float(g["actual_return"].mean()), 6) if n else None,
        })

    summary_path = out_dir / "bucket_summary.csv"
    with summary_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(summary_rows[0].keys()))
        w.writeheader()
        for r in summary_rows:
            w.writerow(r)

    report_path = out_dir / "report.md"
    report_path.write_text(_render_report(
        rows=rows,
        summary_rows=summary_rows,
        n_events=len(roster),
        n_scored=len(rows),
        n_skipped_no_model=n_skipped_no_model,
        n_skipped_no_data=n_skipped_no_data,
    ), encoding="utf-8")

    print(f"phase_c_fcs_bucket: scored {len(rows)} of {len(roster)} SHORT events "
          f"(skipped: {n_skipped_no_model} no model, {n_skipped_no_data} no data)")
    print(f"output: {out_dir}")
    return out_dir


def _render_report(*, rows, summary_rows, n_events, n_scored,
                   n_skipped_no_model, n_skipped_no_data) -> str:
    df = pd.DataFrame(rows)
    overall_win = float(df["win"].mean()) if len(df) else 0.0
    overall_pnl = float(df["short_pnl"].mean()) if len(df) else 0.0

    lines = [
        "# Phase C x FCS bucket backtest",
        "",
        f"**Run:** {datetime.now().isoformat(timespec='seconds')}",
        f"**Events:** {n_scored} of {n_events} SHORT events scored "
        f"(skipped: {n_skipped_no_model} no model, {n_skipped_no_data} no PIT data)",
        f"**Source:** mechanical_replay v2 phase_c_roster.csv",
        f"**Coefficients:** ticker_feature_models.json (current weekly fit)",
        "",
        "## Overall (all SHORT events)",
        f"- N: {n_scored}",
        f"- Win rate: {overall_win:.2%}",
        f"- Avg SHORT P&L: {overall_pnl:+.4%}",
        "",
        "## By FCS bucket",
        "",
        "| Bucket | N | Wins | Win rate | Avg SHORT P&L | Avg underlying return |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for r in summary_rows:
        wr = f"{r['win_rate']:.2%}" if r["win_rate"] is not None else "—"
        spnl = f"{r['avg_short_pnl']:+.4%}" if r["avg_short_pnl"] is not None else "—"
        ar = f"{r['avg_actual_return']:+.4%}" if r["avg_actual_return"] is not None else "—"
        lines.append(f"| {r['bucket']} | {r['n']} | {r['wins']} | {wr} | {spnl} | {ar} |")

    lines += [
        "",
        "## Reading the table",
        "",
        "- **SHORT P&L** is the trade-side return (positive = short made money).",
        "  `short_pnl = -actual_return`.",
        "- **Avg underlying return** is the same column straight from the roster",
        "  (negative = price fell; for a SHORT, that is a win).",
        "- **Bucket boundaries:** `<40`, `40-55`, `55-70`, `>=70` on the 0-100 FCS",
        "  score that today's coefficients assign to that date's features.",
        "",
        "## Verdict logic",
        "",
        "- **Monotonic** (win-rate or avg P&L falls as bucket score rises) -> ",
        "  justifies Rule A (veto Phase C SHORTs in `>=55` bucket) and Rule C",
        "  (size proportional to `100 - score`).",
        "- **Flat / non-monotonic** -> FCS is noise for Phase C intraday;",
        "  attractiveness stays display-only and does not gate trade entry.",
        "",
        "## Caveats",
        "",
        "- Retro-scoring uses *today's* FCS coefficients on PIT features.",
        "  Genuinely out-of-sample only for events outside each ticker's training",
        "  windows in `ticker_feature_models.json`.",
        "- Trust grade uses today's snapshot (not PIT). Coefficient on",
        "  `trust_grade_ordinal` is 0 for most tickers, so impact is bounded.",
        "- DTE is fixed at 10 (single-leg event has no expiry); `dte_*` coefficients",
        "  are 0 across the model so this is inert.",
        "- N per bucket may be small. Treat sub-30 buckets as descriptive only.",
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    run()
