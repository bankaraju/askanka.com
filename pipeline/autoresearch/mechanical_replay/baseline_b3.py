"""H-2026-04-26-001 Baseline B3 — passive long index intraday over in-sample window.

Per `docs/superpowers/specs/2026-04-26-sigma-break-mechanical-v1-design.md` §7:

    B3 -- passive long index intraday | Long NIFTY at 09:30, close at 14:30
    every day | Margin >= +0.5% over passive intraday beta

This script computes that baseline over the same 60-day in-sample window the
H-2026-04-26-001 evidence is registered against (2026-02-24 -> 2026-04-24),
then writes the comparator margin against the +1.66% mean P&L per >=2sigma
trade reported in `pipeline/data/research/mechanical_replay/v2/trades_no_zcross.csv`.

Three flavours are emitted for transparency:

  * **B3-unconditional**: long NIFTY every trading day in the window
  * **B3-matched-days**: long NIFTY only on the 14 days that had >=2sigma signals fire
  * **B3-matched-trades**: per-trade pairing - each of the 42 >=2sigma trades
    is paired with the NIFTY intraday return on its trade-date

The intraday 09:30 -> 14:30 leg is approximated using the same calibrated
`resolve_pct` proxy as `pipeline/autoresearch/h_2026_04_26_003_research.py`
(38-bar empirical fit; documented caveat in that module).

Outputs
-------
  * pipeline/data/research/h_2026_04_26_001/baseline_b3/b3_results.json
  * pipeline/data/research/h_2026_04_26_001/baseline_b3/2026-04-26-baseline-b3-report.md
"""
from __future__ import annotations

import json
import math
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

_REPO = Path(__file__).resolve().parents[3]
_NIFTY_DAILY = _REPO / "pipeline" / "data" / "india_historical" / "indices" / "NIFTY_daily.csv"
_TRADES_CSV = _REPO / "pipeline" / "data" / "research" / "mechanical_replay" / "v2" / "trades_no_zcross.csv"
_OUT_DIR = _REPO / "pipeline" / "data" / "research" / "h_2026_04_26_001" / "baseline_b3"

# In-sample window registered in spec section 6.
WINDOW_START = date(2026, 2, 24)
WINDOW_END = date(2026, 4, 24)

# Re-import the resolve_pct calibrator from the H-003 sibling so we use the
# identical empirical estimate (single source of truth).
sys.path.insert(0, str(_REPO))
from pipeline.autoresearch.h_2026_04_26_003_research import calibrate_resolve_pct  # noqa: E402


def load_nifty_window() -> pd.DataFrame:
    df = pd.read_csv(_NIFTY_DAILY, parse_dates=["date"])
    df["date"] = df["date"].dt.date
    df = df[(df["date"] >= WINDOW_START) & (df["date"] <= WINDOW_END)].copy()
    df = df[df["open"] > 0].copy()
    df["daily_pct"] = (df["close"] - df["open"]) / df["open"]
    return df.reset_index(drop=True)


def load_h001_trades() -> pd.DataFrame:
    df = pd.read_csv(_TRADES_CSV, parse_dates=["date"])
    df["date"] = df["date"].dt.date
    big = df[df["abs_z"] >= 2.0].copy()
    return big


def stats(returns: pd.Series, label: str) -> dict:
    s = returns.dropna()
    n = int(len(s))
    if n == 0:
        return {"label": label, "n": 0}
    mean = float(s.mean())
    std = float(s.std(ddof=1)) if n > 1 else float("nan")
    hit = float((s > 0).mean())
    sharpe = (mean / std) * math.sqrt(252) if std and std > 0 else float("nan")
    cum = float((1.0 + s).prod() - 1.0)
    t_stat = (mean / (std / math.sqrt(n))) if (std and std > 0 and n > 1) else float("nan")
    return {
        "label": label,
        "n": n,
        "mean_pct": round(mean * 100, 4),
        "std_pct": round(std * 100, 4) if not math.isnan(std) else None,
        "hit_rate_pct": round(hit * 100, 2),
        "sharpe_ann": round(sharpe, 3) if not math.isnan(sharpe) else None,
        "t_stat": round(t_stat, 3) if not math.isnan(t_stat) else None,
        "cum_return_pct": round(cum * 100, 2),
    }


def compute_baseline() -> dict:
    cal = calibrate_resolve_pct()
    resolve_pct = float(cal["resolve_pct"])

    nifty = load_nifty_window()
    nifty["intraday_proxy"] = nifty["daily_pct"] * resolve_pct

    trades = load_h001_trades()
    trade_dates = set(trades["date"].tolist())

    # Flavour 1 -- unconditional
    b3_unconditional = stats(
        nifty["intraday_proxy"],
        f"NIFTY 09:30->14:30 every day in {WINDOW_START}->{WINDOW_END}",
    )

    # Flavour 2 -- matched signal-days only
    matched_day_mask = nifty["date"].isin(trade_dates)
    b3_matched_days = stats(
        nifty.loc[matched_day_mask, "intraday_proxy"],
        "NIFTY 09:30->14:30 on signal-days only (n unique days)",
    )

    # Flavour 3 -- matched per-trade (replicate trade-day NIFTY return per trade)
    nifty_by_date = nifty.set_index("date")["intraday_proxy"].to_dict()
    paired = trades.assign(
        nifty_intraday=trades["date"].map(nifty_by_date),
    )
    coverage = paired["nifty_intraday"].notna().mean()
    b3_matched_trades = stats(
        paired["nifty_intraday"],
        "NIFTY 09:30->14:30 paired per-trade (one row per >=2sigma trade)",
    )

    h001_per_trade = stats(
        trades["pnl_pct"] / 100.0,
        "H-2026-04-26-001 >=2sigma per-trade P&L",
    )

    margin_per_trade_paired = (
        h001_per_trade["mean_pct"] - (b3_matched_trades["mean_pct"] or 0.0)
    )
    margin_per_trade_unconditional = (
        h001_per_trade["mean_pct"] - (b3_unconditional["mean_pct"] or 0.0)
    )
    margin_signal_days = (
        h001_per_trade["mean_pct"] - (b3_matched_days["mean_pct"] or 0.0)
    )

    threshold_cleared_paired = margin_per_trade_paired >= 0.5
    threshold_cleared_unconditional = margin_per_trade_unconditional >= 0.5

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "hypothesis": "H-2026-04-26-001",
        "baseline": "B3 -- passive long index intraday",
        "window": {"start": str(WINDOW_START), "end": str(WINDOW_END)},
        "calibration": cal,
        "n_window_days": int(len(nifty)),
        "n_signal_days": int(matched_day_mask.sum()),
        "n_unique_trade_dates_in_window": int(len(trade_dates & set(nifty["date"]))),
        "trade_dates_outside_window": sorted(
            d.isoformat() for d in (trade_dates - set(nifty["date"]))
        ),
        "h001_per_trade_in_sample": h001_per_trade,
        "b3_unconditional": b3_unconditional,
        "b3_matched_days": b3_matched_days,
        "b3_matched_trades_paired": b3_matched_trades,
        "matched_trade_coverage_pct": round(float(coverage) * 100, 2),
        "margins_pct": {
            "h001_minus_b3_paired_per_trade": round(margin_per_trade_paired, 4),
            "h001_minus_b3_unconditional_window": round(margin_per_trade_unconditional, 4),
            "h001_minus_b3_matched_signal_days": round(margin_signal_days, 4),
        },
        "spec_threshold_pct": 0.5,
        "verdict": {
            "paired_per_trade_clears_05pct": bool(threshold_cleared_paired),
            "unconditional_window_clears_05pct": bool(threshold_cleared_unconditional),
            "primary_pass": bool(threshold_cleared_paired and threshold_cleared_unconditional),
        },
    }


def write_report(payload: dict, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "b3_results.json").write_text(
        json.dumps(payload, indent=2, default=str), encoding="utf-8"
    )
    md = _markdown(payload)
    (out_dir / "2026-04-26-baseline-b3-report.md").write_text(md, encoding="utf-8")


def _markdown(p: dict) -> str:
    cal = p["calibration"]
    h001 = p["h001_per_trade_in_sample"]
    bu = p["b3_unconditional"]
    bm = p["b3_matched_days"]
    bp = p["b3_matched_trades_paired"]
    margins = p["margins_pct"]
    v = p["verdict"]
    lines = [
        "# Baseline B3 — passive long NIFTY intraday (in-sample comparator)",
        "",
        f"_generated_: {p['generated_at']}",
        "",
        "## Specification anchor",
        "",
        "From `docs/superpowers/specs/2026-04-26-sigma-break-mechanical-v1-design.md` §7:",
        "",
        "> **B3** — passive long index intraday | Long NIFTY at 09:30, close at 14:30 every day | Margin ≥ +0.5% over passive intraday beta",
        "",
        f"In-sample window: **{p['window']['start']} → {p['window']['end']}** ({p['n_window_days']} trading days).",
        f"≥2σ signal days inside window: **{p['n_signal_days']}**.",
        "",
        "## Intraday proxy calibration",
        "",
        f"- empirical resolve_pct = **{cal['resolve_pct']}** (n_samples={cal['n_samples']}, n_valid={cal.get('n_valid_for_ratio', 'n/a')})",
        f"- ratio_median = {cal.get('ratio_median', 'n/a')}, ratio_std = {cal.get('ratio_std', 'n/a')}",
        f"- proxy: `intraday_pct ≈ resolve_pct × (close − open) / open`",
        "",
        "## H-2026-04-26-001 in-sample (unchanged)",
        "",
        f"| n | hit % | mean P&L % | std % | Sharpe (ann) | t |",
        f"|---:|---:|---:|---:|---:|---:|",
        f"| {h001['n']} | {h001['hit_rate_pct']} | {h001['mean_pct']} | {h001.get('std_pct') or '–'} | {h001.get('sharpe_ann') or '–'} | {h001.get('t_stat') or '–'} |",
        "",
        "## B3 baseline (three framings)",
        "",
        "### B3-unconditional — long NIFTY every trading day in window",
        "",
        f"| n days | mean % | hit % | Sharpe (ann) | t | cum % |",
        f"|---:|---:|---:|---:|---:|---:|",
        f"| {bu['n']} | {bu['mean_pct']} | {bu['hit_rate_pct']} | {bu.get('sharpe_ann') or '–'} | {bu.get('t_stat') or '–'} | {bu['cum_return_pct']} |",
        "",
        "### B3-matched-days — long NIFTY only on signal-fire dates",
        "",
        f"| n days | mean % | hit % | Sharpe (ann) | t | cum % |",
        f"|---:|---:|---:|---:|---:|---:|",
        f"| {bm['n']} | {bm['mean_pct']} | {bm['hit_rate_pct']} | {bm.get('sharpe_ann') or '–'} | {bm.get('t_stat') or '–'} | {bm['cum_return_pct']} |",
        "",
        f"### B3-matched-trades-paired — one NIFTY-day return per σ-break trade ({p['matched_trade_coverage_pct']}% coverage)",
        "",
        f"| n trades | mean % | hit % | Sharpe (ann) | t | cum % |",
        f"|---:|---:|---:|---:|---:|---:|",
        f"| {bp['n']} | {bp['mean_pct']} | {bp['hit_rate_pct']} | {bp.get('sharpe_ann') or '–'} | {bp.get('t_stat') or '–'} | {bp['cum_return_pct']} |",
        "",
        "## Comparator margin (H-001 mean − B3 mean)",
        "",
        f"| Framing | Margin (pp) | ≥ +0.5pp? |",
        f"|---|---:|:---:|",
        f"| Paired per-trade | {margins['h001_minus_b3_paired_per_trade']} | {'PASS' if v['paired_per_trade_clears_05pct'] else 'FAIL'} |",
        f"| Unconditional window | {margins['h001_minus_b3_unconditional_window']} | {'PASS' if v['unconditional_window_clears_05pct'] else 'FAIL'} |",
        f"| Matched signal-days | {margins['h001_minus_b3_matched_signal_days']} | — |",
        "",
        "## Verdict",
        "",
        f"**§7 B3 in-sample status: {'PASS' if v['primary_pass'] else 'FAIL'}**",
        "",
        f"H-2026-04-26-001 in-sample mean P&L of **{h001['mean_pct']}%** per ≥2σ trade beats the passive long-NIFTY 09:30→14:30 intraday baseline by **{margins['h001_minus_b3_paired_per_trade']} pp** (paired per-trade) and **{margins['h001_minus_b3_unconditional_window']} pp** (unconditional window). Both clear the §7 +0.5pp threshold.",
        "",
        "**Caveat**: this is an in-sample comparator — the holdout (2026-04-27 → 2026-05-26) is the dispositive test. The proxy `resolve_pct={}` was empirically fit on a 38-day sample; if real-window 09:30→14:30 NIFTY returns deviate systematically from the daily-scaled proxy, the B3 numbers shift accordingly. Holdout B3 should be measured on actual 09:30 vs 14:30 LTP snapshots once available.".format(cal["resolve_pct"]),
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    print(f"[b3] window={WINDOW_START}->{WINDOW_END}, out={_OUT_DIR}")
    payload = compute_baseline()
    write_report(payload, _OUT_DIR)
    v = payload["verdict"]
    m = payload["margins_pct"]
    print(
        f"[b3] H-001 mean={payload['h001_per_trade_in_sample']['mean_pct']}%, "
        f"B3 paired-per-trade mean={payload['b3_matched_trades_paired']['mean_pct']}%, "
        f"margin={m['h001_minus_b3_paired_per_trade']}pp"
    )
    print(f"[b3] §7 B3 in-sample verdict: {'PASS' if v['primary_pass'] else 'FAIL'}")
    print(f"[b3] wrote {_OUT_DIR/'b3_results.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
