"""Phase C Options Paired-Shadow stratified Markdown reporter.

Joins futures + options ledgers on signal_id and emits a Markdown
one-pager with paired-diff stats. Stratified by is_expiry_day.

Spec: docs/superpowers/specs/2026-04-27-phase-c-options-paired-shadow-design.md §11
"""
from __future__ import annotations

import json
import logging
import random
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Iterable

import pandas as pd

from pipeline.phase_c_options_shadow import build_signal_id

IST = timezone(timedelta(hours=5, minutes=30))

FUTURES_LEDGER_PATH: Path = Path(
    "pipeline/data/research/phase_c/live_paper_ledger.json"
)
OPTIONS_LEDGER_PATH: Path = Path(
    "pipeline/data/research/phase_c/live_paper_options_ledger.json"
)
REPORT_PATH: Path = Path(
    "pipeline/data/research/phase_c/options_paired_report.md"
)

# Spec §11.2 thresholds
N_DESCRIPTIVE = 30
N_BOOTSTRAP = 100

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# I/O helpers
# ---------------------------------------------------------------------------

def _load_ledgers(
    futures_path: Path,
    options_path: Path,
) -> tuple[list[dict], list[dict]]:
    """Load both ledger files; raise FileNotFoundError if either is absent."""
    if not futures_path.exists():
        raise FileNotFoundError(f"Futures ledger not found: {futures_path}")
    if not options_path.exists():
        raise FileNotFoundError(f"Options ledger not found: {options_path}")
    futures = json.loads(futures_path.read_text(encoding="utf-8"))
    options = json.loads(options_path.read_text(encoding="utf-8"))
    return futures, options


def _join_on_signal_id(
    futures_rows: list[dict],
    options_rows: list[dict],
) -> tuple[pd.DataFrame, int, int, int, int, int]:
    """Inner-join CLOSED rows on signal_id.

    Returns (joined_df, futures_closed_n, options_closed_n,
             matched_n, unmatched_futures_n, unmatched_options_n).
    """
    # Build signal_id for futures rows (may already have it or derive it)
    for row in futures_rows:
        if not row.get("signal_id"):
            row["signal_id"] = build_signal_id(row)

    fut_closed = [r for r in futures_rows if r.get("status") == "CLOSED"]
    opt_closed = [r for r in options_rows if r.get("status") == "CLOSED"]

    fut_n = len(fut_closed)
    opt_n = len(opt_closed)

    if not fut_closed or not opt_closed:
        empty = pd.DataFrame(columns=[
            "signal_id", "is_expiry_day", "futures_pnl_pct", "options_pnl_pct",
            "paired_diff", "drift_vs_rent_tier", "entry_iv", "days_to_expiry",
        ])
        return empty, fut_n, opt_n, 0, fut_n, opt_n

    df_fut = pd.DataFrame(fut_closed)
    df_opt = pd.DataFrame(opt_closed)

    # Compute futures pnl pct
    df_fut["futures_pnl_pct"] = df_fut["pnl_net_inr"].astype(float) / df_fut["notional_inr"].astype(float)

    # Select columns needed from each side
    fut_cols = ["signal_id", "futures_pnl_pct"]
    opt_cols = [
        "signal_id", "is_expiry_day", "pnl_net_pct", "drift_vs_rent_tier",
        "entry_iv", "days_to_expiry",
    ]
    # Ensure opt_cols exist (guard against missing columns in synthetic fixtures)
    for col in opt_cols:
        if col not in df_opt.columns:
            df_opt[col] = None

    merged = df_fut[fut_cols].merge(df_opt[opt_cols], on="signal_id", how="inner")
    merged["options_pnl_pct"] = merged["pnl_net_pct"].astype(float)
    merged["paired_diff"] = merged["options_pnl_pct"] - merged["futures_pnl_pct"]

    matched_n = len(merged)
    unmatched_fut = fut_n - matched_n
    unmatched_opt = opt_n - matched_n

    return merged, fut_n, opt_n, matched_n, unmatched_fut, unmatched_opt


# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------

def _bootstrap_ci(
    values: list[float],
    iters: int,
    seed: int,
) -> tuple[float, float]:
    """95% bootstrap CI on the mean via percentile method."""
    rng = random.Random(seed)
    n = len(values)
    means = []
    for _ in range(iters):
        sample = [rng.choice(values) for _ in range(n)]
        means.append(sum(sample) / n)
    means.sort()
    lo = means[int(0.025 * iters)]
    hi = means[int(0.975 * iters)]
    return lo, hi


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

def _format_pct(v: float | None) -> str:
    if v is None:
        return "--"
    sign = "+" if v >= 0 else ""
    return f"{sign}{v * 100:.2f}%"


def _format_win_rate(v: float | None) -> str:
    if v is None:
        return "--"
    return f"{v * 100:.1f}%"


def _mean_or_none(vals: Iterable[float]) -> float | None:
    lst = list(vals)
    if not lst:
        return None
    return sum(lst) / len(lst)


# ---------------------------------------------------------------------------
# Table builders
# ---------------------------------------------------------------------------

def _table_a(
    df: pd.DataFrame,
    *,
    bootstrap_iters: int,
    seed: int,
) -> str:
    """Headline paired diff, stratified by is_expiry_day. Spec §11.1 Table A."""
    lines = ["## Table A - Headline Paired Diff (options_pnl_pct - futures_pnl_pct)\n"]
    lines.append("| is_expiry_day | mean diff | 95% CI | N |")
    lines.append("|---|---|---|---|")

    for expiry_flag in [True, False]:
        label = f"is_expiry_day={expiry_flag}"
        sub = df[df["is_expiry_day"] == expiry_flag] if not df.empty else pd.DataFrame()
        n = len(sub)
        if n == 0:
            lines.append(f"| {label} | -- | -- | N=0 |")
            continue

        diffs = sub["paired_diff"].tolist()
        m = sum(diffs) / n

        if n < 5:
            ci_str = "insufficient N"
        else:
            lo, hi = _bootstrap_ci(diffs, bootstrap_iters, seed)
            ci_str = f"[{_format_pct(lo)}, {_format_pct(hi)}]"

        lines.append(f"| {label} | {_format_pct(m)} | CI={ci_str} | N={n} |")

    return "\n".join(lines) + "\n"


def _table_b(df: pd.DataFrame) -> str:
    """Win rate by drift_vs_rent_tier, stratified by is_expiry_day. Spec §11.1 Table B."""
    lines = ["## Table B - Win Rate by drift_vs_rent_tier\n"]
    lines.append("| is_expiry_day | tier | win_rate | mean_pnl | N |")
    lines.append("|---|---|---|---|---|")

    all_tiers = ["HIGH-ALPHA SYNTHETIC", "EXPERIMENTAL", "NEGATIVE CARRY", "UNKNOWN"]
    # Include any tiers in the data not in the canonical list
    if not df.empty and "drift_vs_rent_tier" in df.columns:
        extra = [t for t in df["drift_vs_rent_tier"].dropna().unique() if t not in all_tiers]
        all_tiers = all_tiers + sorted(extra)

    for expiry_flag in [True, False]:
        label = f"is_expiry_day={expiry_flag}"
        sub_exp = df[df["is_expiry_day"] == expiry_flag] if not df.empty else pd.DataFrame()
        for tier in all_tiers:
            if not sub_exp.empty:
                sub = sub_exp[sub_exp["drift_vs_rent_tier"] == tier]
            else:
                sub = pd.DataFrame()
            n = len(sub)
            if n == 0:
                lines.append(f"| {label} | {tier} | -- | -- | 0 |")
            else:
                win_rate = (sub["options_pnl_pct"] > 0).sum() / n
                mean_pnl = sub["options_pnl_pct"].mean()
                lines.append(
                    f"| {label} | {tier} | {_format_win_rate(win_rate)} | {_format_pct(mean_pnl)} | {n} |"
                )

    return "\n".join(lines) + "\n"


def _table_c(df: pd.DataFrame) -> tuple[str, int]:
    """P&L by entry_iv bucket (terciles), stratified by is_expiry_day. Spec §11.1 Table C.

    Returns (markdown_str, iv_null_count).
    """
    lines = ["## Table C - P&L by entry_iv Bucket (terciles)\n"]
    lines.append("| is_expiry_day | iv_bucket | mean_pnl | N |")
    lines.append("|---|---|---|---|")

    null_count = 0
    footer_note = ""

    if df.empty:
        for expiry_flag in [True, False]:
            label = f"is_expiry_day={expiry_flag}"
            for bucket in ["low", "mid", "high"]:
                lines.append(f"| {label} | {bucket} | -- | 0 |")
        return "\n".join(lines) + "\n", 0

    # Compute null count before dropping
    null_mask = df["entry_iv"].isna()
    null_count = int(null_mask.sum())

    df_valid = df[~null_mask].copy()

    if df_valid.empty:
        for expiry_flag in [True, False]:
            label = f"is_expiry_day={expiry_flag}"
            for bucket in ["low", "mid", "high"]:
                lines.append(f"| {label} | {bucket} | -- | 0 |")
    else:
        # Compute tercile thresholds pooled across both strata (spec: IV is a market property)
        p33 = float(df_valid["entry_iv"].quantile(1 / 3))
        p66 = float(df_valid["entry_iv"].quantile(2 / 3))

        def _iv_bucket(iv: float) -> str:
            if iv < p33:
                return "low"
            elif iv < p66:
                return "mid"
            else:
                return "high"

        df_valid = df_valid.copy()
        df_valid["iv_bucket"] = df_valid["entry_iv"].apply(_iv_bucket)

        for expiry_flag in [True, False]:
            label = f"is_expiry_day={expiry_flag}"
            sub_exp = df_valid[df_valid["is_expiry_day"] == expiry_flag]
            for bucket in ["low", "mid", "high"]:
                sub = sub_exp[sub_exp["iv_bucket"] == bucket]
                n = len(sub)
                if n == 0:
                    lines.append(f"| {label} | {bucket} | -- | 0 |")
                else:
                    mean_pnl = sub["options_pnl_pct"].mean()
                    lines.append(f"| {label} | {bucket} | {_format_pct(mean_pnl)} | {n} |")

    return "\n".join(lines) + "\n", null_count


def _table_d(df: pd.DataFrame) -> str:
    """P&L by DTE bucket, stratified by is_expiry_day. Spec §11.1 Table D."""
    lines = ["## Table D - P&L by DTE Bucket\n"]
    lines.append("| is_expiry_day | dte_bucket | mean_pnl | N |")
    lines.append("|---|---|---|---|")

    def _dte_bucket(dte: int) -> str:
        if dte == 0:
            return "0d"
        elif dte <= 5:
            return "1-5d"
        elif dte <= 15:
            return "6-15d"
        elif dte <= 30:
            return "16-30d"
        else:
            return "31+d"

    dte_buckets = ["0d", "1-5d", "6-15d", "16-30d", "31+d"]

    if not df.empty and "days_to_expiry" in df.columns:
        df = df.copy()
        df["dte_bucket"] = df["days_to_expiry"].apply(
            lambda x: _dte_bucket(int(x)) if pd.notna(x) else "unknown"
        )

    for expiry_flag in [True, False]:
        label = f"is_expiry_day={expiry_flag}"
        if df.empty:
            for bucket in dte_buckets:
                lines.append(f"| {label} | {bucket} | -- | 0 |")
            continue

        sub_exp = df[df["is_expiry_day"] == expiry_flag]
        for bucket in dte_buckets:
            sub = sub_exp[sub_exp["dte_bucket"] == bucket] if not sub_exp.empty else pd.DataFrame()
            n = len(sub)
            if n == 0:
                lines.append(f"| {label} | {bucket} | -- | 0 |")
            else:
                mean_pnl = sub["options_pnl_pct"].mean()
                lines.append(f"| {label} | {bucket} | {_format_pct(mean_pnl)} | {n} |")

    return "\n".join(lines) + "\n"


def _table_e(options_rows: list[dict]) -> str:
    """Skip rate by ticker (full options ledger, not just CLOSED). Spec §11.1 Table E."""
    lines = ["## Table E - Skip Rate by Ticker (SKIPPED_LIQUIDITY / total)\n"]
    lines.append("| ticker | skip_rate | skipped | total |")
    lines.append("|---|---|---|---|")

    if not options_rows:
        lines.append("| -- | -- | 0 | 0 |")
        return "\n".join(lines) + "\n"

    terminal_statuses = {"OPEN", "CLOSED", "SKIPPED_LIQUIDITY", "ERROR", "TIME_STOP_FAIL_FETCH"}
    ticker_stats: dict[str, dict] = {}

    for row in options_rows:
        status = row.get("status", "")
        if status not in terminal_statuses:
            continue
        symbol = row.get("symbol", "UNKNOWN")
        if symbol not in ticker_stats:
            ticker_stats[symbol] = {"total": 0, "skipped": 0}
        ticker_stats[symbol]["total"] += 1
        if status == "SKIPPED_LIQUIDITY":
            ticker_stats[symbol]["skipped"] += 1

    # Build sorted list by skip_rate desc
    rows_sorted = sorted(
        ticker_stats.items(),
        key=lambda kv: (kv[1]["skipped"] / kv[1]["total"] if kv[1]["total"] else 0, kv[1]["skipped"]),
        reverse=True,
    )

    top10 = rows_sorted[:10]
    rest = rows_sorted[10:]

    for ticker, stats in top10:
        rate = stats["skipped"] / stats["total"] if stats["total"] else 0
        lines.append(
            f"| {ticker} | {_format_win_rate(rate)} | {stats['skipped']} | {stats['total']} |"
        )

    if rest:
        rest_total = sum(s["total"] for _, s in rest)
        rest_skipped = sum(s["skipped"] for _, s in rest)
        rest_rate = rest_skipped / rest_total if rest_total else 0
        n_others = len(rest)
        lines.append(
            f"| OTHERS ({n_others} tickers) | {_format_win_rate(rest_rate)} | {rest_skipped} | {rest_total} |"
        )

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Header + footer
# ---------------------------------------------------------------------------

def _render_header(
    *,
    futures_n: int,
    options_n: int,
    matched_n: int,
    unmatched_fut: int,
    unmatched_opt: int,
) -> str:
    now_ist = datetime.now(IST).strftime("%Y-%m-%d %H:%M IST")

    if matched_n < N_DESCRIPTIVE:
        verdict = "INSUFFICIENT_N -- accumulating forward-only OOS samples"
    elif matched_n < N_BOOTSTRAP:
        verdict = "DESCRIPTIVE -- see Table A; no statistical claim"
    else:
        verdict = "BOOTSTRAP_INFERENCE_PENDING -- see Table A footer for verdict"

    return (
        f"# Phase C Options Paired Shadow -- Forensic Readout\n\n"
        f"**As of:** {now_ist}\n"
        f"**Status:** descriptive only -- no edge claim, no kill-switch trigger\n"
        f"**Cadence:** N>={N_DESCRIPTIVE} descriptive, N>={N_BOOTSTRAP} bootstrap-inference\n\n"
        f"**Pair counts:** futures CLOSED N={futures_n} | options CLOSED N={options_n} "
        f"| matched N={matched_n} | unmatched-futures N={unmatched_fut} "
        f"| unmatched-options N={unmatched_opt}\n\n"
        f"**Verdict:** {verdict}\n\n"
        f"---\n\n"
    )


def _render_footer(
    *,
    iv_null_count: int,
    error_count: int,
    matched_n: int,
    df_matched: pd.DataFrame,
    bootstrap_iters: int,
    seed: int,
) -> str:
    lines = ["---\n", "**Footnotes**"]

    if iv_null_count:
        lines.append(
            f"- N={iv_null_count} rows with entry_iv=null excluded from Table C (IV solver non-convergence)"
        )
    if error_count:
        lines.append(
            f"- N={error_count} options rows with status=ERROR or TIME_STOP_FAIL_FETCH excluded from A-D"
        )
    lines.append(
        "- Drift-vs-rent tier=UNKNOWN reflects spec §13 risk #4: classifier adapter pending"
    )
    lines.append(
        "- This is a measurement layer. Phase C edge claim is unaffected by this report."
    )
    lines.append(
        "- Spec: docs/superpowers/specs/2026-04-27-phase-c-options-paired-shadow-design.md §11"
    )

    # Bootstrap-inference verdict at N>=100
    if matched_n >= N_BOOTSTRAP and not df_matched.empty:
        diffs = df_matched["paired_diff"].tolist()
        lo, hi = _bootstrap_ci(diffs, bootstrap_iters, seed)
        if lo <= 0.0 <= hi:
            verdict = "PAIRED_DIFF_ZERO_NOT_REJECTED"
        else:
            verdict = "PAIRED_DIFF_ZERO_REJECTED"
        lines.append(
            f"- **Bootstrap inference (N={matched_n}, all strata pooled):** "
            f"{verdict} | CI=[{_format_pct(lo)}, {_format_pct(hi)}]"
        )

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_report(
    *,
    futures_path: Path | None = None,
    options_path: Path | None = None,
    output_path: Path | None = None,
    bootstrap_iters: int = 5000,
    seed: int = 17,
) -> str:
    """Read both ledgers, join on signal_id, build all 5 tables, write
    Markdown to output_path. Returns the Markdown string.

    Spec: §11.1, §11.2
    """
    fp = futures_path or FUTURES_LEDGER_PATH
    op = options_path or OPTIONS_LEDGER_PATH
    out = output_path or REPORT_PATH

    futures_rows, options_rows = _load_ledgers(fp, op)

    # Count non-CLOSED options rows for footer
    error_count = sum(
        1 for r in options_rows
        if r.get("status") in ("ERROR", "TIME_STOP_FAIL_FETCH")
    )

    df_matched, fut_n, opt_n, matched_n, unmatched_fut, unmatched_opt = _join_on_signal_id(
        futures_rows, options_rows
    )

    header = _render_header(
        futures_n=fut_n,
        options_n=opt_n,
        matched_n=matched_n,
        unmatched_fut=unmatched_fut,
        unmatched_opt=unmatched_opt,
    )

    ta = _table_a(df_matched, bootstrap_iters=bootstrap_iters, seed=seed)
    tb = _table_b(df_matched)
    tc_str, iv_null_count = _table_c(df_matched)
    td = _table_d(df_matched)
    te = _table_e(options_rows)
    footer = _render_footer(
        iv_null_count=iv_null_count,
        error_count=error_count,
        matched_n=matched_n,
        df_matched=df_matched,
        bootstrap_iters=bootstrap_iters,
        seed=seed,
    )

    md = header + ta + "\n" + tb + "\n" + tc_str + "\n" + td + "\n" + te + "\n" + footer

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md, encoding="utf-8")
    log.info("phase_c_options_report: wrote %s (matched N=%d)", out, matched_n)

    return md


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO)
    md = build_report()
    print(REPORT_PATH)
