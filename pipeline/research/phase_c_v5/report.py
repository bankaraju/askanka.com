"""12-section V5 research report generator."""
from __future__ import annotations

from pathlib import Path
import pandas as pd


_SECTION_TITLES = {
    1:  "Executive summary",
    2:  "Strategy description (basket framing + MOAT rationale)",
    3:  "Methodology",
    4:  "Results — V5.0 regime-ranker pair (the MOAT)",
    5:  "Results — V5.1 sector pair",
    6:  "Results — V5.2 stock vs sector index",
    7:  "Results — V5.3 NIFTY overlay",
    8:  "Results — V5.4 BANKNIFTY dispersion",
    9:  "Results — V5.5 leader routing",
    10: "Results — V5.6 horizon sweep",
    11: "Results — V5.7 options overlay",
    12: "Verdict + production recommendation",
}


def _section_header(n: int) -> str:
    return f"## {n}. {_SECTION_TITLES[n]}"


def _verdict_line(row: pd.Series) -> str:
    icon = "✅ PASS" if row["passes"] else "❌ FAIL"
    return (f"- **{row['variant']}** — {icon} · n={int(row['n_trades'])} · "
            f"hit={row['hit_rate']:.1%} · Sharpe CI "
            f"[{row['sharpe_lo']:.2f}, {row['sharpe_hi']:.2f}] · "
            f"p={row['binomial_p']:.4f} (α={row['alpha_per_test']:.4f})")


def _executive_summary(ablation: pd.DataFrame) -> str:
    lines = [_section_header(1), ""]
    lines += [_verdict_line(r) for _, r in ablation.iterrows()]
    lines.append("")
    return "\n".join(lines)


def _strategy_section() -> str:
    return (f"{_section_header(2)}\n\n"
            "V5 tests 8 framings of the Phase C OPPORTUNITY signal plus the "
            "regime-ranker pair engine (V5.0, the MOAT). V5.0 derives trades "
            "from ETF-regime-conditional leader/laggard ranks; V5.1-V5.7 wrap "
            "single-stock Phase C signals in baskets, index hedges, and "
            "options structures. Bonferroni-corrected at α=0.01 / 12 tests.\n")


def _methodology_section() -> str:
    return (f"{_section_header(3)}\n\n"
            "- 4-year daily in-sample + 60-day 1-min forward window\n"
            "- Cost model: Zerodha intraday rates + per-instrument slippage\n"
            "  (stock 5 bps, NIFTY 2 bps, sectoral 8 bps, options 15 bps)\n"
            "- Sharpe CI: 10,000 IID bootstrap, seed=7, α=0.01\n"
            "- Hit rate: two-sided binomial vs 50% null\n"
            "- Pass gate: Sharpe CI lower bound > 0 AND p < α/12\n")


def _variant_section(n: int, variant_keys: list[str], ablation: pd.DataFrame,
                       ledger_map: dict[str, pd.DataFrame]) -> str:
    lines = [_section_header(n), ""]
    for vk in variant_keys:
        row = ablation[ablation["variant"] == vk]
        if row.empty:
            lines.append(f"- {vk}: no ledger emitted")
            continue
        lines.append(_verdict_line(row.iloc[0]))
        if vk in ledger_map and not ledger_map[vk].empty:
            ledger = ledger_map[vk]
            mean_pnl = ledger["pnl_net_inr"].mean()
            lines.append(f"  - mean net P&L per trade: ₹{mean_pnl:.2f}")
    lines.append("")
    return "\n".join(lines)


def _verdict_section(ablation: pd.DataFrame) -> str:
    lines = [_section_header(12), ""]
    passes = ablation[ablation["passes"]]
    if passes.empty:
        lines.append("**Production recommendation: retire Phase C V5.** "
                     "No variant cleared the Bonferroni-corrected gate. "
                     "Phase C as a signal generator has insufficient edge "
                     "at publication-grade rigor.")
    else:
        winners = ", ".join(passes["variant"].tolist())
        lines.append(f"**Production recommendation: advance {winners} to paper-"
                     "forward validation.** Other variants should be retired.")
    lines.append("")
    return "\n".join(lines)


def build_markdown(ablation: pd.DataFrame,
                    ledger_map: dict[str, pd.DataFrame]) -> str:
    header = "# Phase C V5 — Basket, Index Hedge & Options Validation\n\n"
    parts = [
        header,
        _executive_summary(ablation),
        _strategy_section(),
        _methodology_section(),
        _variant_section(4, [k for k in ledger_map if k.startswith("v50")],
                          ablation, ledger_map),
        _variant_section(5, ["v51"], ablation, ledger_map),
        _variant_section(6, ["v52"], ablation, ledger_map),
        _variant_section(7, ["v53"], ablation, ledger_map),
        _variant_section(8, ["v54"], ablation, ledger_map),
        _variant_section(9, ["v55"], ablation, ledger_map),
        _variant_section(10, ["v56"], ablation, ledger_map),
        _variant_section(11, ["v57"], ablation, ledger_map),
        _verdict_section(ablation),
    ]
    return "\n".join(parts)


def write_report(path: Path, ablation: pd.DataFrame,
                  ledger_map: dict[str, pd.DataFrame]) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(build_markdown(ablation, ledger_map), encoding="utf-8")
