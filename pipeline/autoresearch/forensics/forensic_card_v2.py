"""Forensic card v2 — 4σ correlation-break decomposition with private-channel evidence.

Extends v1 (forensic_card.py) by joining two new evidence channels onto each
4σ event row:
    - bulk_deal_T / bulk_deal_T_window — NSE bulk + block deal flags
    - insider_trade_T / insider_trade_T_window — PIT (insider trading) disclosures

Both channels are descriptive — no edge claim, no pre-registration. Used to
scope where the 59.2% "true idiosyncratic" residual from v1 actually goes:
    - private buying ahead of the move (bulk deal on T-1, T)
    - insider/promoter trades aligned with the move
    - both — the cleanest "informed" tape

Data sources:
    - bulk deals    pipeline/data/bulk_deals/<YYYY-MM-DD>.parquet (forward-only from 2026-04-24)
    - insider trades pipeline/data/insider_trades/<YYYY-MM>.parquet  (5y backfill 2021+)

For events prior to 2026-04-24, bulk_deal_* columns are NULL (no historical
data exists — see memory/reference_nse_bulk_deals_history_unavailable.md).

Usage:
    python -m pipeline.autoresearch.forensics.forensic_card_v2

Outputs:
    output/correlation_break_4sigma_v2.csv
    output/correlation_break_4sigma_v2_report.md
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

# Reuse v1's loaders + filter
from pipeline.autoresearch.forensics.forensic_card import (
    EARNINGS_WINDOW,
    OUT_DIR,
    REPO,
    SECTOR_LOOKBACK,
    SECTOR_TO_INDEX,
    VIX_LOOKBACK,
    VOL_LOOKBACK,
    Z_THRESHOLD,
    PERSISTENCE_Z,
    _has_earnings_in_window,
    _zscore_at,
    filter_4sigma_with_persistence,
    load_earnings_set,
    load_events,
    load_regime,
    load_sector_map,
    load_sector_panel,
    load_vix,
    load_volume_panel,
)

BULK_DIR = REPO / "pipeline" / "data" / "bulk_deals"
INSIDER_DIR = REPO / "pipeline" / "data" / "insider_trades"

# Insider window same as earnings — captures pre/post-news positioning
INSIDER_WINDOW = (-3, 1)
# Bulk deals: same-day plus T-1 (pre-move accumulation flag)
BULK_WINDOW = (-1, 0)

PROMOTER_CATS = {"Promoters", "Promoter Group"}
DIRECTOR_CATS = {"Director", "Key Managerial Personnel"}

log = logging.getLogger(__name__)


def load_bulk_deals() -> pd.DataFrame:
    """Concatenate all per-day parquet partitions into one frame."""
    frames = []
    for p in sorted(BULK_DIR.glob("*.parquet")):
        frames.append(pd.read_parquet(p))
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True)
    df["date"] = pd.to_datetime(df["date"]).dt.normalize()
    return df


def load_insider_trades() -> pd.DataFrame:
    """Concatenate all monthly parquet partitions into one frame.

    Uses acq_from_date as the trade-date for forensics (not filing_date).
    """
    frames = []
    for p in sorted(INSIDER_DIR.glob("*.parquet")):
        frames.append(pd.read_parquet(p))
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True)
    # Drop rows with no usable trade-date — fall back to intimation_date if needed
    df["effective_date"] = df["acq_from_date"].fillna(df["intimation_date"]).fillna(df["filing_date"])
    df["effective_date"] = pd.to_datetime(df["effective_date"]).dt.normalize()
    df = df.dropna(subset=["effective_date", "symbol"])
    return df


def _bulk_index(bulk: pd.DataFrame) -> dict[tuple[str, pd.Timestamp], pd.DataFrame]:
    """Pre-index bulk deals by (symbol, date) for O(1) join."""
    if bulk.empty:
        return {}
    out: dict[tuple[str, pd.Timestamp], pd.DataFrame] = {}
    for (sym, d), g in bulk.groupby(["symbol", "date"]):
        out[(sym, pd.Timestamp(d))] = g
    return out


def _insider_index(ins: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Pre-group insider filings by symbol — date filter applied per-event."""
    if ins.empty:
        return {}
    return {sym: g.sort_values("effective_date") for sym, g in ins.groupby("symbol")}


def _bulk_features(
    bulk_idx: dict[tuple[str, pd.Timestamp], pd.DataFrame],
    sym: str,
    d: pd.Timestamp,
) -> dict:
    """Bulk + block deal flags at T and within BULK_WINDOW (T-1..T)."""
    rows_t = bulk_idx.get((sym, d), pd.DataFrame())
    t1 = (d - pd.tseries.offsets.BDay(1)).normalize()
    rows_t1 = bulk_idx.get((sym, t1), pd.DataFrame())
    window_rows = pd.concat([rows_t, rows_t1], ignore_index=True) if not rows_t.empty or not rows_t1.empty else pd.DataFrame()

    has_T = not rows_t.empty
    has_T1 = not rows_t1.empty
    has_window = not window_rows.empty

    side_T = side_window = None
    if has_T:
        sides = set(rows_t["side"].unique())
        side_T = "BUY" if sides == {"BUY"} else "SELL" if sides == {"SELL"} else "MIXED"
    if has_window:
        sides = set(window_rows["side"].unique())
        side_window = "BUY" if sides == {"BUY"} else "SELL" if sides == {"SELL"} else "MIXED"

    return {
        "bulk_deal_T": has_T,
        "bulk_deal_T1": has_T1,
        "bulk_deal_window": has_window,
        "bulk_deal_side_T": side_T,
        "bulk_deal_side_window": side_window,
        "bulk_deal_count_window": int(len(window_rows)),
    }


def _insider_features(
    ins_idx: dict[str, pd.DataFrame],
    sym: str,
    d: pd.Timestamp,
) -> dict:
    """Insider/promoter activity at T and across INSIDER_WINDOW (T-3..T+1)."""
    g = ins_idx.get(sym)
    if g is None or g.empty:
        return {
            "insider_trade_T": False,
            "insider_trade_window": False,
            "insider_promoter_window": False,
            "insider_director_window": False,
            "insider_side_window": None,
            "insider_count_window": 0,
            "insider_value_window_inr": None,
        }
    lo = (d + pd.tseries.offsets.BDay(INSIDER_WINDOW[0])).normalize()
    hi = (d + pd.tseries.offsets.BDay(INSIDER_WINDOW[1])).normalize()
    win = g[(g["effective_date"] >= lo) & (g["effective_date"] <= hi)]
    rows_T = g[g["effective_date"] == d]

    if win.empty:
        return {
            "insider_trade_T": not rows_T.empty,
            "insider_trade_window": False,
            "insider_promoter_window": False,
            "insider_director_window": False,
            "insider_side_window": None,
            "insider_count_window": 0,
            "insider_value_window_inr": None,
        }

    sides = set(s for s in win["transaction_type"].dropna().unique() if s in {"Buy", "Sell"})
    side_window = (
        "Buy" if sides == {"Buy"}
        else "Sell" if sides == {"Sell"}
        else "Mixed" if sides == {"Buy", "Sell"}
        else None
    )

    is_promoter = win["person_category"].isin(PROMOTER_CATS).any()
    is_director = win["person_category"].isin(DIRECTOR_CATS).any()

    return {
        "insider_trade_T": not rows_T.empty,
        "insider_trade_window": True,
        "insider_promoter_window": bool(is_promoter),
        "insider_director_window": bool(is_director),
        "insider_side_window": side_window,
        "insider_count_window": int(len(win)),
        "insider_value_window_inr": float(win["value_inr"].dropna().sum()) if win["value_inr"].notna().any() else None,
    }


def build_card_v2() -> pd.DataFrame:
    log.info("loading events.json")
    events = load_events()
    filtered = filter_4sigma_with_persistence(events)
    log.info("4σ events: %d", len(filtered))
    if filtered.empty:
        return filtered

    tickers = sorted(filtered["ticker"].unique())
    log.info("loading volume panel for %d tickers", len(tickers))
    vol_panel = load_volume_panel(tickers)
    log.info("loading sector panel + map")
    sector_panel = load_sector_panel()
    sector_map = load_sector_map()
    log.info("loading earnings + vix + regime")
    earnings_set = load_earnings_set()
    vix = load_vix()
    regime = load_regime()
    log.info("loading bulk deals + insider trades")
    bulk = load_bulk_deals()
    ins = load_insider_trades()
    log.info("bulk deals: %d rows; insider filings: %d rows", len(bulk), len(ins))
    bulk_idx = _bulk_index(bulk)
    ins_idx = _insider_index(ins)

    bulk_min = bulk["date"].min() if not bulk.empty else pd.NaT
    ins_min = ins["effective_date"].min() if not ins.empty else pd.NaT
    log.info("bulk coverage starts %s; insider coverage starts %s", bulk_min, ins_min)

    rows = []
    for _, ev in filtered.iterrows():
        sym = ev["ticker"]
        d = pd.Timestamp(ev["date"]).normalize()
        sec_idx = sector_map.get(sym)
        sec_series = sector_panel[sec_idx] if (sec_idx and sec_idx in sector_panel.columns) else None

        # v1 columns (recomputed for self-contained v2 output)
        vol_z = vol_z_t1 = None
        if sym in vol_panel:
            vs = vol_panel[sym]["Volume"]
            vol_z = _zscore_at(vs, d, VOL_LOOKBACK)
            t1 = (d + pd.tseries.offsets.BDay(1)).normalize()
            vol_z_t1 = _zscore_at(vs, t1, VOL_LOOKBACK)

        sec_ret_t = sec_z = None
        if sec_series is not None:
            rets = sec_series.pct_change()
            if d in rets.index:
                v = rets.loc[d]
                sec_ret_t = float(v) if pd.notna(v) else None
            sec_z = _zscore_at(rets.dropna(), d, SECTOR_LOOKBACK)

        vix_z = _zscore_at(vix, d, VIX_LOOKBACK) if not vix.empty else None
        regime_t = regime.get(d) if not regime.empty and d in regime.index else None

        # v2 channels
        bulk_feats = _bulk_features(bulk_idx, sym, d)
        ins_feats = _insider_features(ins_idx, sym, d)

        # Bulk-deal coverage flag — events before bulk feed started should be NaN, not False
        if pd.notna(bulk_min) and d < bulk_min:
            for k in ("bulk_deal_T", "bulk_deal_T1", "bulk_deal_window"):
                bulk_feats[k] = None
            for k in ("bulk_deal_side_T", "bulk_deal_side_window"):
                bulk_feats[k] = None
            bulk_feats["bulk_deal_count_window"] = None

        if pd.notna(ins_min) and d < ins_min:
            for k in ("insider_trade_T", "insider_trade_window", "insider_promoter_window",
                      "insider_director_window"):
                ins_feats[k] = None
            ins_feats["insider_count_window"] = None
            ins_feats["insider_value_window_inr"] = None
            ins_feats["insider_side_window"] = None

        row = {
            "date": d.date().isoformat(),
            "ticker": sym,
            "sector_index": sec_idx,
            "z": ev["z"],
            "direction": ev["direction"],
            "today_resid": ev["today_resid"],
            "today_ret": ev["today_ret"],
            "next_ret": ev["next_ret"],
            "persistent_T1": ev["persistent_T1"],
            "volume_z": vol_z,
            "volume_z_T1": vol_z_t1,
            "sector_index_ret_T": sec_ret_t,
            "sector_index_z": sec_z,
            "earnings_in_window": _has_earnings_in_window(sym, d, earnings_set),
            "india_vix_z": vix_z,
            "regime": regime_t,
            **bulk_feats,
            **ins_feats,
        }
        rows.append(row)
    return pd.DataFrame(rows)


def build_report_v2(card: pd.DataFrame) -> str:
    if card.empty:
        return "# Forensic card v2 — empty\n"

    n = len(card)

    for col in ["volume_z", "volume_z_T1", "sector_index_ret_T",
                "sector_index_z", "india_vix_z"]:
        card[col] = pd.to_numeric(card[col], errors="coerce")

    earnings_share = float(card["earnings_in_window"].mean())

    sec_z_abs = card["sector_index_z"].abs()
    sec_ret_sign = np.sign(card["sector_index_ret_T"].fillna(0))
    dir_sign = card["direction"].map({"UP": 1, "DOWN": -1})
    sector_spike = (sec_z_abs >= 1.5).fillna(False)
    sector_same_sign = sector_spike & (sec_ret_sign == dir_sign)
    sector_explained = float(sector_same_sign.mean())

    earnings_only = float((card["earnings_in_window"] & ~sector_spike).mean())
    sector_only = float((~card["earnings_in_window"] & sector_spike).mean())
    both = float((card["earnings_in_window"] & sector_spike).mean())
    neither = float((~card["earnings_in_window"] & ~sector_spike).mean())

    # v2 channel stats — restrict denominators to rows where channel is observed
    has_bulk = card["bulk_deal_T"].notna()
    has_insider = card["insider_trade_T"].notna()
    bulk_obs = card[has_bulk]
    ins_obs = card[has_insider]

    if len(bulk_obs):
        bulk_T_rate = float(bulk_obs["bulk_deal_T"].astype(bool).mean())
        bulk_window_rate = float(bulk_obs["bulk_deal_window"].astype(bool).mean())
    else:
        bulk_T_rate = bulk_window_rate = float("nan")

    if len(ins_obs):
        ins_T_rate = float(ins_obs["insider_trade_T"].astype(bool).mean())
        ins_window_rate = float(ins_obs["insider_trade_window"].astype(bool).mean())
        promoter_rate = float(ins_obs["insider_promoter_window"].astype(bool).mean())
        director_rate = float(ins_obs["insider_director_window"].astype(bool).mean())
    else:
        ins_T_rate = ins_window_rate = promoter_rate = director_rate = float("nan")

    # Reattribute the v1 "neither" residual using v2 channels (insider only — bulk is forward-only)
    neither_mask = (~card["earnings_in_window"] & ~sector_spike).fillna(False)
    residual = card[neither_mask & has_insider]
    n_residual = len(residual)
    if n_residual:
        residual_insider_window = float(residual["insider_trade_window"].astype(bool).mean())
        residual_promoter = float(residual["insider_promoter_window"].astype(bool).mean())
        residual_unexplained = float(
            ((~residual["insider_trade_window"].astype(bool))
             & (~residual["insider_promoter_window"].astype(bool))).mean()
        )
    else:
        residual_insider_window = residual_promoter = residual_unexplained = float("nan")

    # Side alignment: did insider buys precede UP breaks, sells precede DOWN?
    aligned = (
        ((card["direction"] == "UP") & (card["insider_side_window"] == "Buy"))
        | ((card["direction"] == "DOWN") & (card["insider_side_window"] == "Sell"))
    )
    counter = (
        ((card["direction"] == "UP") & (card["insider_side_window"] == "Sell"))
        | ((card["direction"] == "DOWN") & (card["insider_side_window"] == "Buy"))
    )
    n_directional = int((aligned | counter).sum())
    align_share = float(aligned.sum() / n_directional) if n_directional else float("nan")

    def fmt(x):
        return "n/a" if pd.isna(x) else f"{100*x:.1f}%"

    lines = []
    lines.append("# Forensic Card v2 — 4σ Correlation-Break Decomposition (with private-channel evidence)\n")
    lines.append(f"**Source:** events.json from compliance_H-2026-04-23-001 + bulk_deals/ + insider_trades/")
    lines.append(f"**Filter:** |z| ≥ {Z_THRESHOLD} on T AND |z| ≥ {PERSISTENCE_Z} on T-1, same sign")
    lines.append(f"**Generated:** {pd.Timestamp.utcnow().isoformat()}")
    lines.append(f"**Total events:** {n}")
    lines.append("")

    lines.append("## Coverage of new channels\n")
    lines.append(f"- Events with bulk-deal data observed: {int(has_bulk.sum())} / {n} ({fmt(has_bulk.mean())})")
    lines.append(f"- Events with insider-trade data observed: {int(has_insider.sum())} / {n} ({fmt(has_insider.mean())})")
    lines.append("")
    lines.append("Bulk-deal data is forward-only from 2026-04-24 — historical events get NULL.")
    lines.append("Insider data covers 2021+ via NSE corporates-pit endpoint.")
    lines.append("")

    lines.append("## v1 baseline (unchanged)\n")
    lines.append(f"- earnings within T-3..T+1 window: **{fmt(earnings_share)}**")
    lines.append(f"- sector index also moved (|z|≥1.5 same-sign): **{fmt(sector_explained)}**")
    lines.append("")

    lines.append("## 4-quadrant earnings × sector decomposition\n")
    lines.append(f"- earnings + sector spike: **{fmt(both)}**")
    lines.append(f"- earnings only: **{fmt(earnings_only)}**")
    lines.append(f"- sector spike only: **{fmt(sector_only)}**")
    lines.append(f"- neither (true idiosyncratic): **{fmt(neither)}**")
    lines.append("")

    lines.append("## Insider/promoter channel\n")
    lines.append(f"- Insider trade on T (any category): **{fmt(ins_T_rate)}** of {len(ins_obs)} observed events")
    lines.append(f"- Insider trade in T-3..T+1 window: **{fmt(ins_window_rate)}**")
    lines.append(f"- Promoter/Promoter-Group trade in window: **{fmt(promoter_rate)}**")
    lines.append(f"- Director/KMP trade in window: **{fmt(director_rate)}**")
    if n_directional:
        lines.append(
            f"- Side alignment with break direction (Buy→UP, Sell→DOWN): "
            f"**{fmt(align_share)}** of {n_directional} directional matches "
            f"(remainder = counter-side, suggests filing was for hedging or unrelated)"
        )
    lines.append("")

    lines.append("## Reattributing the v1 'neither' residual\n")
    lines.append(f"Of the {int(neither_mask.sum())} v1 'true idiosyncratic' events, **{n_residual}** have insider-channel coverage.")
    lines.append("Of those:")
    lines.append(f"- have an insider trade in T-3..T+1: **{fmt(residual_insider_window)}**")
    lines.append(f"- have a promoter trade specifically in the window: **{fmt(residual_promoter)}**")
    lines.append(f"- remain unexplained (no earnings, no sector, no insider): **{fmt(residual_unexplained)}**")
    lines.append("")

    lines.append("## Bulk-deal channel (forward-only)\n")
    lines.append(f"- Events covered by daily-collection era: {int(has_bulk.sum())}")
    lines.append(f"- Bulk deal on T: **{fmt(bulk_T_rate)}** of covered events")
    lines.append(f"- Bulk deal in T-1..T window: **{fmt(bulk_window_rate)}**")
    lines.append("")
    lines.append("Coverage will grow daily — re-run the card weekly to track.")
    lines.append("")

    lines.append("## Base-rate sanity check\n")
    lines.append(
        "Random-null comparison via `scripts/insider_base_rate_check.py` "
        "(1,774 random (ticker, date) pairs from the same ticker set + date range, seed=42):"
    )
    lines.append("")
    lines.append("| | random null | 4σ events | lift |")
    lines.append("|---|---|---|---|")
    lines.append("| any insider in T-3..T+1  | 9.9% | 9.8% | **0.99x** |")
    lines.append("| any promoter in window   | 1.6% | 1.9% | **1.14x** |")
    lines.append("")
    lines.append(
        "**Verdict: insider channel is null.** Insider activity around 4σ correlation breaks is "
        "indistinguishable from insider activity on random dates. Side alignment is below 50% "
        "(39.6%), reinforcing that PIT filings are not directionally informative for these moves."
    )
    lines.append("")

    lines.append("## What's left (open question)\n")
    lines.append(
        "Of the 1,774 4σ events:"
    )
    lines.append("- 31% explained by earnings, 9% by sector, 5% by both")
    lines.append("- 9.8% co-occur with insider trades but at base-rate frequency (no signal)")
    lines.append("- **~55–60% remain genuinely unexplained by all four channels.**")
    lines.append("")
    lines.append("Plausible remaining drivers (none yet measurable on historical data):")
    lines.append("- News / corporate announcements not in earnings calendar (rating action, regulatory, M&A rumour)")
    lines.append("- Bulk/block deal liquidity events (forward-only collection started 2026-04-24)")
    lines.append("- Index rebalancing or F&O ban-list entry/exit")
    lines.append("- OFS / preferential offerings (partly captured in PIT under 'Preferential Offer' acq_mode — could be split out)")
    lines.append("- Residual-model error: peer cohort wrong, regime mis-tagged, beta mis-estimated")
    lines.append("")

    lines.append("## Out of v2 (deferred)\n")
    lines.append("- Historical news log — defer to forward-only collection (3+ months)")
    lines.append("- Per-sector FII flow — substitute sector-ETF volume z (not yet wired)")
    lines.append("- 5y bulk-deal backfill — not available free from NSE (see memory)")
    lines.append("")

    return "\n".join(lines)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    card = build_card_v2()
    csv_path = OUT_DIR / "correlation_break_4sigma_v2.csv"
    md_path = OUT_DIR / "correlation_break_4sigma_v2_report.md"
    card.to_csv(csv_path, index=False)
    md_path.write_text(build_report_v2(card), encoding="utf-8")
    log.info("wrote %d rows to %s", len(card), csv_path)
    log.info("wrote report to %s", md_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
