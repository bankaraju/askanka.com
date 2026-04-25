"""Forensic card v3 — subdivide the unexplained 4σ residual.

Reads the v2 CSV and slices the "neither + no-insider" residual along 5 axes
to look for clusters that hint at a missing channel:

    1. Sector (which sector indices over-cluster the residual?)
    2. Year (is the residual concentrated in a window — regime change, vol regime?)
    3. Regime (does RISK-OFF leak more unexplained breaks than RISK-ON?)
    4. |z| magnitude bucket (do extreme breaks concentrate elsewhere?)
    5. Direction (UP vs DOWN — asymmetric leaks?)

This is descriptive forensics — no edge claim. The point is to find where the
55-60% unexplained share is unevenly distributed, which tells us which missing
channel (news? bulk deals? F&O ban-list?) is most likely the dominant driver.

Usage:
    python -m pipeline.autoresearch.forensics.forensic_card_v3

Outputs:
    output/correlation_break_4sigma_v3_stratified.csv
    output/correlation_break_4sigma_v3_report.md
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[3]
OUT_DIR = REPO / "pipeline" / "autoresearch" / "forensics" / "output"
V2_CSV = OUT_DIR / "correlation_break_4sigma_v2.csv"


def _load_v2() -> pd.DataFrame:
    df = pd.read_csv(V2_CSV)
    df["date"] = pd.to_datetime(df["date"])
    df["year"] = df["date"].dt.year
    df["abs_z"] = df["z"].abs()
    return df


def _classify_residual(df: pd.DataFrame) -> pd.DataFrame:
    """Tag each event with explanation status.

    explained_by_earnings: earnings_in_window True
    explained_by_sector: |sector_z| ≥ 1.5 same-sign
    co_occurs_insider: insider_trade_window True (descriptive, not causal)
    unexplained: none of the above (the residual we want to subdivide)
    """
    sec_spike = (df["sector_index_z"].abs() >= 1.5).fillna(False)
    sec_sign = np.sign(df["sector_index_ret_T"].fillna(0))
    dir_sign = df["direction"].map({"UP": 1, "DOWN": -1})
    sec_explained = sec_spike & (sec_sign == dir_sign)

    earnings = df["earnings_in_window"].fillna(False).astype(bool)
    insider = df["insider_trade_window"].fillna(False).astype(bool)

    out = df.copy()
    out["explained_earnings"] = earnings
    out["explained_sector"] = sec_explained
    out["explained_any_pub"] = earnings | sec_explained
    out["co_occurs_insider"] = insider
    # "Unexplained" = no earnings, no sector spike, no insider co-occurrence
    # (we're being charitable to the insider channel even though it's null —
    #  if we drop insider we get a slightly larger residual, but cleaner story
    #  is "even with the insider lottery, X% remain unexplained").
    out["unexplained"] = (~earnings) & (~sec_explained) & (~insider)
    out["explained_or_co"] = (~out["unexplained"])
    return out


def _stratify(df: pd.DataFrame, dim: str, *, min_n: int = 20) -> pd.DataFrame:
    """For each value of `dim`, compute n, n_unexplained, share_unexplained.

    Filters out cells with < min_n events to avoid spurious extremes.
    """
    grp = df.groupby(dim, dropna=False)
    out = grp.agg(
        n_events=("unexplained", "size"),
        n_unexplained=("unexplained", "sum"),
        n_earnings=("explained_earnings", "sum"),
        n_sector=("explained_sector", "sum"),
        n_insider=("co_occurs_insider", "sum"),
    ).reset_index()
    out["share_unexplained"] = out["n_unexplained"] / out["n_events"]
    out["share_earnings"] = out["n_earnings"] / out["n_events"]
    out["share_sector"] = out["n_sector"] / out["n_events"]
    out["share_insider"] = out["n_insider"] / out["n_events"]
    out = out[out["n_events"] >= min_n].copy()
    return out.sort_values("share_unexplained", ascending=False)


def _zbucket(z: float) -> str:
    if z < 4.5:
        return "[4.0, 4.5)"
    if z < 5.0:
        return "[4.5, 5.0)"
    if z < 6.0:
        return "[5.0, 6.0)"
    if z < 8.0:
        return "[6.0, 8.0)"
    return "[8.0, ∞)"


def build_v3(df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Compute all 5 stratifications. Returns dict keyed by axis name."""
    df["abs_z_bucket"] = df["abs_z"].map(_zbucket)
    return {
        "sector": _stratify(df, "sector_index", min_n=30),
        "year": _stratify(df, "year", min_n=20),
        "regime": _stratify(df, "regime", min_n=20),
        "abs_z_bucket": _stratify(df, "abs_z_bucket", min_n=20),
        "direction": _stratify(df, "direction", min_n=20),
    }


def _fmt_table(df: pd.DataFrame, label_col: str) -> list[str]:
    rows = ["| {} | n | unexplained | earnings | sector | insider |".format(label_col),
            "|---|---:|---:|---:|---:|---:|"]
    for _, r in df.iterrows():
        rows.append(
            f"| {r[label_col]} | {int(r['n_events'])} "
            f"| {100*r['share_unexplained']:.1f}% ({int(r['n_unexplained'])}) "
            f"| {100*r['share_earnings']:.1f}% "
            f"| {100*r['share_sector']:.1f}% "
            f"| {100*r['share_insider']:.1f}% |"
        )
    return rows


def build_report(df: pd.DataFrame, strat: dict[str, pd.DataFrame]) -> str:
    n = len(df)
    n_unex = int(df["unexplained"].sum())
    overall_unex = n_unex / n

    lines = []
    lines.append("# Forensic Card v3 — Stratifying the Unexplained 4σ Residual\n")
    lines.append(f"**Source:** correlation_break_4sigma_v2.csv ({n} events, 2021-05-10 → 2026-04-21)")
    lines.append(f"**Generated:** {pd.Timestamp.utcnow().isoformat()}")
    lines.append("")
    lines.append("## Definitions\n")
    lines.append("- **explained_earnings:** earnings within T-3..T+1")
    lines.append("- **explained_sector:** |sector_index_z| ≥ 1.5 AND same direction as the break")
    lines.append("- **co_occurs_insider:** PIT filing in T-3..T+1 (note: 0.99x lift vs random null — co-occurrence ≠ cause)")
    lines.append("- **unexplained:** none of the above")
    lines.append("")
    lines.append(f"**Overall unexplained: {100*overall_unex:.1f}% ({n_unex} of {n} events)**")
    lines.append("")
    lines.append("Cells below n<min are suppressed; tables sorted by share_unexplained desc.")
    lines.append("")

    lines.append("## 1. By sector (where do the unexplained breaks pile up?)\n")
    lines += _fmt_table(strat["sector"], "sector_index")
    lines.append("")

    lines.append("## 2. By year (is the residual time-concentrated?)\n")
    lines += _fmt_table(strat["year"].sort_values("year"), "year")
    lines.append("")

    lines.append("## 3. By regime (does any regime leak more?)\n")
    lines += _fmt_table(strat["regime"], "regime")
    lines.append("")

    lines.append("## 4. By |z| magnitude bucket (do extreme breaks differ?)\n")
    order = ["[4.0, 4.5)", "[4.5, 5.0)", "[5.0, 6.0)", "[6.0, 8.0)", "[8.0, ∞)"]
    z_tab = strat["abs_z_bucket"].set_index("abs_z_bucket").reindex(order).reset_index()
    z_tab = z_tab.dropna(subset=["n_events"])
    lines += _fmt_table(z_tab, "abs_z_bucket")
    lines.append("")

    lines.append("## 5. By direction (UP vs DOWN asymmetry?)\n")
    lines += _fmt_table(strat["direction"], "direction")
    lines.append("")

    # Headline observations — pull a few automated takeaways
    lines.append("## Observations (auto-generated)\n")
    sec = strat["sector"]
    if not sec.empty:
        worst_sec = sec.iloc[0]
        best_sec = sec.iloc[-1]
        lines.append(
            f"- **Sector spread:** {worst_sec['sector_index']} has {100*worst_sec['share_unexplained']:.1f}% "
            f"unexplained vs {best_sec['sector_index']} at {100*best_sec['share_unexplained']:.1f}% "
            f"(Δ {100*(worst_sec['share_unexplained']-best_sec['share_unexplained']):.1f} pp)"
        )

    yr = strat["year"]
    if not yr.empty and len(yr) >= 2:
        worst_yr = yr.iloc[0]
        best_yr = yr.iloc[-1]
        lines.append(
            f"- **Year spread:** {int(worst_yr['year'])} has {100*worst_yr['share_unexplained']:.1f}% "
            f"unexplained vs {int(best_yr['year'])} at {100*best_yr['share_unexplained']:.1f}%"
        )

    rg = strat["regime"]
    if not rg.empty:
        worst_rg = rg.iloc[0]
        best_rg = rg.iloc[-1]
        lines.append(
            f"- **Regime spread:** {worst_rg['regime']} {100*worst_rg['share_unexplained']:.1f}% "
            f"vs {best_rg['regime']} {100*best_rg['share_unexplained']:.1f}%"
        )

    di = strat["direction"]
    if not di.empty and len(di) == 2:
        up = di[di["direction"] == "UP"].iloc[0] if (di["direction"] == "UP").any() else None
        dn = di[di["direction"] == "DOWN"].iloc[0] if (di["direction"] == "DOWN").any() else None
        if up is not None and dn is not None:
            lines.append(
                f"- **Direction:** UP unexplained {100*up['share_unexplained']:.1f}% "
                f"vs DOWN {100*dn['share_unexplained']:.1f}% "
                f"(Δ {100*(up['share_unexplained']-dn['share_unexplained']):.1f} pp)"
            )

    zb = strat["abs_z_bucket"]
    if not zb.empty:
        # Sort by bucket order to show monotone or non-monotone trend
        zb2 = zb.set_index("abs_z_bucket").reindex(order).dropna(subset=["n_events"])
        if len(zb2) >= 2:
            low = zb2.iloc[0]
            high = zb2.iloc[-1]
            lines.append(
                f"- **|z| trend:** smallest bucket ({zb2.index[0]}) {100*low['share_unexplained']:.1f}% "
                f"unexplained vs extreme bucket ({zb2.index[-1]}) {100*high['share_unexplained']:.1f}%"
            )

    lines.append("")
    lines.append("## Reading the tables\n")
    lines.append(
        "A high share_unexplained cell means: this slice has many breaks that earnings/sector/insider "
        "do NOT explain — so a missing channel (likely news, bulk deals, OFS, or model error) dominates "
        "there. Look for cells that are >5 pp above the overall mean and ask: what is unique about that "
        "slice that the four observed channels miss?"
    )
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df = _load_v2()
    df = _classify_residual(df)
    strat = build_v3(df)

    # Concatenate all strats into one CSV with axis label
    parts = []
    for axis, t in strat.items():
        tt = t.copy()
        tt.insert(0, "axis", axis)
        # rename label col to common name
        label_col = tt.columns[1]
        tt = tt.rename(columns={label_col: "value"})
        tt["value"] = tt["value"].astype(str)
        parts.append(tt)
    combined = pd.concat(parts, ignore_index=True)
    combined.to_csv(OUT_DIR / "correlation_break_4sigma_v3_stratified.csv", index=False)

    report = build_report(df, strat)
    (OUT_DIR / "correlation_break_4sigma_v3_report.md").write_text(report, encoding="utf-8")

    print(f"Wrote {OUT_DIR / 'correlation_break_4sigma_v3_stratified.csv'}")
    print(f"Wrote {OUT_DIR / 'correlation_break_4sigma_v3_report.md'}")
    print(f"\nOverall unexplained: {100*df['unexplained'].mean():.1f}% ({int(df['unexplained'].sum())} of {len(df)})")


if __name__ == "__main__":
    main()
