"""Markdown + chart emitter for the Phase C validation research document.

Each public function is self-contained and idempotent — given structured input,
it writes one file (markdown or PNG). Output lives under
``docs/research/phase-c-validation/`` when wired into the top-level runner.
"""
from __future__ import annotations

import logging
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # headless backend; MUST precede pyplot import
import matplotlib.pyplot as plt  # noqa: E402  (deliberate post-backend import)
import pandas as pd  # noqa: E402

log = logging.getLogger(__name__)


def render_pnl_table(
    ledger: pd.DataFrame,
    out_path: Path | str,
    title: str = "Trade Ledger",
) -> None:
    """Write a markdown summary + per-trade P&L table.

    Summary includes N trades, total net P&L (INR), and win rate. Per-trade
    rows follow. Empty ledgers emit the summary with zero counts and an empty
    table body (header only).
    """
    out_path = Path(out_path)
    n = int(len(ledger))
    total = float(ledger["pnl_net_inr"].sum()) if n else 0.0
    n_win = int((ledger["pnl_net_inr"] > 0).sum()) if n else 0
    win_rate = (n_win / n) if n else 0.0
    md = [
        f"## {title}\n",
        f"- N trades: **{n}**",
        f"- Total net P&L: **\u20b9{total:,.2f}**",
        f"- Win rate: **{win_rate:.1%}** ({n_win}/{n})",
        "",
        "| entry_date | symbol | side | pnl_net_inr |",
        "|---|---|---|---:|",
    ]
    for _, r in ledger.iterrows():
        md.append(
            f"| {r['entry_date']} | {r['symbol']} | {r['side']} | {r['pnl_net_inr']:.2f} |"
        )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(md), encoding="utf-8")


def render_equity_curve(
    ledger: pd.DataFrame,
    out_path: Path | str,
    title: str = "Equity Curve",
) -> None:
    """Render cumulative net P&L as a PNG equity curve.

    Empty ledgers produce an empty-axis chart (no data points) rather than
    crashing — the caller gets a valid PNG it can still embed.
    """
    out_path = Path(out_path)
    df = ledger.sort_values("entry_date").copy() if len(ledger) else ledger.copy()
    if len(df):
        df["cum_pnl"] = df["pnl_net_inr"].cumsum()

    fig, ax = plt.subplots(figsize=(8, 4))
    if len(df):
        ax.plot(df["entry_date"], df["cum_pnl"], marker="o")
    ax.set_title(title)
    ax.set_xlabel("Date")
    ax.set_ylabel("Cumulative net P&L (INR)")
    ax.grid(True, alpha=0.3)
    fig.autofmt_xdate()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)  # prevent matplotlib figure leak


def render_verdict_section(
    verdicts: dict[str, dict],
    out_path: Path | str,
) -> None:
    """Render the per-hypothesis PASS/FAIL verdict markdown."""
    out_path = Path(out_path)
    md = [
        "# Verdict\n",
        "| Hypothesis | Outcome | Reason |",
        "|---|:---:|---|",
    ]
    for hname, v in verdicts.items():
        outcome = "PASS" if v.get("passes") else "FAIL"
        md.append(f"| {hname} | **{outcome}** | {v.get('reason', '')} |")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(md), encoding="utf-8")


def render_regime_breakdown(
    ledger: pd.DataFrame,
    regime_by_date: dict[str, str],
    out_path: Path | str,
) -> None:
    """Render per-regime hit rate and net P&L breakdown table."""
    out_path = Path(out_path)
    df = ledger.copy()
    df["regime"] = df["entry_date"].map(regime_by_date)
    df = df.dropna(subset=["regime"])

    rows = []
    for reg, g in df.groupby("regime"):
        rows.append(
            {
                "regime": reg,
                "n_trades": int(len(g)),
                "win_rate": float((g["pnl_net_inr"] > 0).mean()),
                "total_pnl_inr": float(g["pnl_net_inr"].sum()),
                "avg_pnl_inr": float(g["pnl_net_inr"].mean()) if len(g) else 0.0,
            }
        )

    md = [
        "## Per-regime breakdown\n",
        "| regime | n_trades | win_rate | total_pnl_inr | avg_pnl_inr |",
        "|---|---:|---:|---:|---:|",
    ]
    for r in rows:
        md.append(
            f"| {r['regime']} | {r['n_trades']} | {r['win_rate']:.1%} | "
            f"{r['total_pnl_inr']:.2f} | {r['avg_pnl_inr']:.2f} |"
        )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(md), encoding="utf-8")
