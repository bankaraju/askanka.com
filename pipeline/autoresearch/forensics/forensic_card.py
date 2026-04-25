"""Forensic card v1 — 4σ correlation-break decomposition.

Descriptive only. For each |z|>=4 event in the H-2026-04-23-001 parent panel,
join the available "fast" evidence channels (volume z, sector index move,
earnings proximity, India VIX z, regime, persistence) into a single row.

v1 deliberately omits news/bulk-deal/promoter/FII channels — those need
new fetches (see runbook).

Usage:
    python -m pipeline.autoresearch.forensics.forensic_card

Outputs:
    pipeline/autoresearch/forensics/output/correlation_break_4sigma_v1.csv
    pipeline/autoresearch/forensics/output/correlation_break_4sigma_v1_report.md
"""
from __future__ import annotations

import json
import logging
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[3]
EVENTS_PATH = REPO / "pipeline" / "autoresearch" / "results" / "compliance_H-2026-04-23-001_20260423-150125" / "events.json"
FNO_DIR = REPO / "pipeline" / "data" / "fno_historical"
SECTOR_DIR = REPO / "pipeline" / "data" / "sectoral_indices"
EARNINGS_PARQUET = REPO / "pipeline" / "data" / "earnings_calendar" / "history.parquet"
VIX_CSV = REPO / "pipeline" / "data" / "alpha_test_cache" / "INDIAVIX.csv"
REGIME_CSV = REPO / "pipeline" / "data" / "regime_history.csv"
OUT_DIR = REPO / "pipeline" / "autoresearch" / "forensics" / "output"

Z_THRESHOLD = 4.0
PERSISTENCE_Z = 3.0
VOL_LOOKBACK = 60
SECTOR_LOOKBACK = 60
VIX_LOOKBACK = 60
EARNINGS_WINDOW = (-3, 1)

SECTOR_TO_INDEX = {
    "Banks": "BANKNIFTY",
    "IT_Services": "NIFTYIT",
    "Pharma": "NIFTYPHARMA",
    "Hospitals_Diagnostics": "NIFTYPHARMA",
    "Autos": "NIFTYAUTO",
    "Auto_Ancillaries": "NIFTYAUTO",
    "FMCG": "NIFTYFMCG",
    "Metals_Mining": "NIFTYMETAL",
    "Oil_Gas": "NIFTYENERGY",
    "Power_Utilities": "NIFTYENERGY",
    "Real_Estate_Hotels": "NIFTYREALTY",
}

log = logging.getLogger(__name__)


def load_events() -> pd.DataFrame:
    rows = json.loads(EVENTS_PATH.read_text())
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    df["sign"] = np.sign(df["z"])
    return df


def filter_4sigma_with_persistence(events: pd.DataFrame) -> pd.DataFrame:
    """|z| >= 4 on T AND a same-sign |z| >= 3 row at T-1 (in events.json).

    Note: stricter than the H-2026-04-24-003 spec's |z|>=2 at T-1, because
    events.json only carries |z|>=3 rows. Sub-threshold T-1 z's are not
    recoverable without recomputing the full residual panel — deferred to v2.
    """
    out_rows = []
    for ticker, g in events.groupby("ticker"):
        g = g.sort_values("date").reset_index(drop=True)
        dates = g["date"].dt.normalize().tolist()
        z_arr = g["z"].to_numpy()
        sign_arr = g["sign"].to_numpy()
        for i, d in enumerate(dates):
            if abs(z_arr[i]) < Z_THRESHOLD:
                continue
            t1 = pd.Timestamp(d - pd.tseries.offsets.BDay(1)).normalize()
            persistent = any(
                dates[j] == t1 and abs(z_arr[j]) >= PERSISTENCE_Z and sign_arr[j] == sign_arr[i]
                for j in range(i)
            )
            row = g.iloc[i].to_dict()
            row["persistent_T1"] = persistent
            out_rows.append(row)
    out = pd.DataFrame(out_rows)
    if not out.empty:
        out["date"] = pd.to_datetime(out["date"])
    return out


def load_sector_map() -> dict[str, str]:
    from pipeline.scorecard_v2.sector_mapper import SectorMapper
    raw = SectorMapper().map_all()
    return {s: SECTOR_TO_INDEX.get(meta["sector"]) for s, meta in raw.items()}


def load_volume_panel(tickers: list[str]) -> dict[str, pd.DataFrame]:
    panel = {}
    for t in tickers:
        p = FNO_DIR / f"{t}.csv"
        if not p.exists():
            continue
        df = pd.read_csv(p, parse_dates=["Date"]).sort_values("Date").set_index("Date")
        df = df[["Close", "Volume"]].astype(float)
        panel[t] = df
    return panel


def load_sector_panel() -> pd.DataFrame:
    frames = {}
    for csv in SECTOR_DIR.glob("*_daily.csv"):
        sym = csv.stem.replace("_daily", "")
        df = pd.read_csv(csv, parse_dates=["date"]).sort_values("date").set_index("date")
        frames[sym] = df["close"].astype(float)
    return pd.concat(frames, axis=1).sort_index() if frames else pd.DataFrame()


def load_earnings_set() -> set[tuple[str, pd.Timestamp]]:
    df = pd.read_parquet(EARNINGS_PARQUET)
    df = df[df["kind"].astype(str).str.contains("EARNINGS")]
    df["event_date"] = pd.to_datetime(df["event_date"]).dt.normalize()
    return set(zip(df["symbol"], df["event_date"]))


def load_vix() -> pd.Series:
    if not VIX_CSV.exists():
        return pd.Series(dtype=float)
    df = pd.read_csv(VIX_CSV, parse_dates=["Date"]).sort_values("Date").set_index("Date")
    return df["Close"].astype(float)


def load_regime() -> pd.Series:
    if not REGIME_CSV.exists():
        return pd.Series(dtype=str)
    df = pd.read_csv(REGIME_CSV, parse_dates=["date"]).set_index("date")
    return df["regime_zone"]


def _zscore_at(series: pd.Series, ts: pd.Timestamp, lookback: int) -> float | None:
    ts = pd.Timestamp(ts).normalize()
    if ts not in series.index:
        return None
    pos = series.index.get_loc(ts)
    if pos < lookback:
        return None
    window = series.iloc[pos - lookback:pos]
    mu, sd = float(window.mean()), float(window.std(ddof=1))
    if sd <= 0:
        return None
    return (float(series.iloc[pos]) - mu) / sd


def _has_earnings_in_window(symbol: str, ts: pd.Timestamp, earnings: set) -> bool:
    base = pd.Timestamp(ts).normalize()
    for offset in range(EARNINGS_WINDOW[0], EARNINGS_WINDOW[1] + 1):
        cand = (base + pd.tseries.offsets.BDay(offset)).normalize()
        if (symbol, pd.Timestamp(cand)) in earnings:
            return True
    return False


def build_card() -> pd.DataFrame:
    log.info("loading events.json")
    events = load_events()
    log.info("filtering to |z|>=%.1f with same-sign T-1 persistence (|z|>=%.1f)", Z_THRESHOLD, PERSISTENCE_Z)
    filtered = filter_4sigma_with_persistence(events)
    log.info("4σ events: %d (of which %d persistent)",
             len(filtered), int(filtered["persistent_T1"].sum()) if not filtered.empty else 0)

    if filtered.empty:
        return filtered

    tickers = sorted(filtered["ticker"].unique())
    log.info("loading volume panel for %d tickers", len(tickers))
    vol_panel = load_volume_panel(tickers)
    log.info("loading sector panel")
    sector_panel = load_sector_panel()
    sector_map = load_sector_map()
    log.info("loading earnings calendar")
    earnings_set = load_earnings_set()
    vix = load_vix()
    regime = load_regime()

    rows = []
    for _, ev in filtered.iterrows():
        sym = ev["ticker"]
        d = pd.Timestamp(ev["date"]).normalize()
        sec_idx = sector_map.get(sym)
        sector_idx_series = sector_panel[sec_idx] if (sec_idx and sec_idx in sector_panel.columns) else None

        vol_z = vol_z_t1 = None
        if sym in vol_panel:
            vol_series = vol_panel[sym]["Volume"]
            vol_z = _zscore_at(vol_series, d, VOL_LOOKBACK)
            t1 = (d + pd.tseries.offsets.BDay(1)).normalize()
            vol_z_t1 = _zscore_at(vol_series, t1, VOL_LOOKBACK)

        sec_ret_t = sec_ret_t1 = sec_z = None
        if sector_idx_series is not None:
            rets = sector_idx_series.pct_change()
            if d in rets.index:
                v = rets.loc[d]
                sec_ret_t = float(v) if pd.notna(v) else None
            t1 = (d + pd.tseries.offsets.BDay(1)).normalize()
            if t1 in rets.index:
                v = rets.loc[t1]
                sec_ret_t1 = float(v) if pd.notna(v) else None
            sec_z = _zscore_at(rets.dropna(), d, SECTOR_LOOKBACK)

        vix_z = _zscore_at(vix, d, VIX_LOOKBACK) if not vix.empty else None
        regime_t = regime.get(d) if not regime.empty and d in regime.index else None

        rows.append({
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
            "sector_index_ret_T1": sec_ret_t1,
            "sector_index_z": sec_z,
            "earnings_in_window": _has_earnings_in_window(sym, d, earnings_set),
            "india_vix_z": vix_z,
            "regime": regime_t,
        })
    return pd.DataFrame(rows)


def build_report(card: pd.DataFrame) -> str:
    if card.empty:
        return "# Forensic card v1 — empty (no 4σ events with persistence)\n"

    n = len(card)
    n_persistent = int(card["persistent_T1"].sum())

    for col in ["volume_z", "volume_z_T1", "sector_index_ret_T", "sector_index_ret_T1",
                "sector_index_z", "india_vix_z"]:
        card[col] = pd.to_numeric(card[col], errors="coerce")

    by_year = card.assign(year=pd.to_datetime(card["date"]).dt.year).groupby("year").size()
    by_sector = card["sector_index"].fillna("UNMAPPED").value_counts()
    by_ticker_top = card["ticker"].value_counts().head(20)

    earnings_share = float(card["earnings_in_window"].mean())

    sec_z_abs = card["sector_index_z"].abs()
    sec_ret_sign = np.sign(card["sector_index_ret_T"].fillna(0))
    dir_sign = card["direction"].map({"UP": 1, "DOWN": -1})
    sector_spike = (sec_z_abs >= 1.5).fillna(False)
    sector_same_sign = sector_spike & (sec_ret_sign == dir_sign)
    sector_explained = float(sector_same_sign.mean())

    high_vol = float((card["volume_z"] >= 2.0).fillna(False).mean())

    earnings_only = float((card["earnings_in_window"] & ~sector_spike).mean())
    sector_only = float((~card["earnings_in_window"] & sector_spike).mean())
    both = float((card["earnings_in_window"] & sector_spike).mean())
    neither = float((~card["earnings_in_window"] & ~sector_spike).mean())

    by_regime = card["regime"].fillna("UNKNOWN").value_counts(normalize=True).round(3) if "regime" in card else pd.Series(dtype=float)

    def fmt_pct(x):
        return f"{100*x:.1f}%"

    lines = []
    lines.append("# Forensic Card v1 — 4σ Correlation-Break Decomposition\n")
    lines.append(f"**Source:** events.json from compliance_H-2026-04-23-001_20260423-150125\n")
    lines.append(f"**Filter:** |z| ≥ {Z_THRESHOLD} on T AND |z| ≥ {PERSISTENCE_Z} on T-1, same sign")
    lines.append(f"**Note:** T-1 persistence is stricter than spec (|z|≥3 vs intended |z|≥2) — events.json"
                 f" only carries |z|≥3 rows, sub-threshold T-1 z's not recoverable without a panel rebuild.")
    lines.append(f"**Generated:** {pd.Timestamp.utcnow().isoformat()}")
    lines.append("")

    lines.append("## Counts\n")
    lines.append(f"- Total 4σ events with persistence: **{n}**")
    lines.append(f"- Of these, persistent at T-1: **{n_persistent}** ({fmt_pct(n_persistent/n)})")
    lines.append("")

    lines.append("### By year")
    for y, c in by_year.items():
        lines.append(f"- {y}: {c}")
    lines.append("")

    lines.append("### By sector")
    for s, c in by_sector.items():
        lines.append(f"- {s}: {c}")
    lines.append("")

    lines.append("### Top 20 tickers")
    for t, c in by_ticker_top.items():
        lines.append(f"- {t}: {c}")
    lines.append("")

    lines.append("## Cause-channel headline rates\n")
    lines.append(f"- earnings within T-3..T+1 window: **{fmt_pct(earnings_share)}**")
    lines.append(f"- sector index also moved (|z|≥1.5 same-sign): **{fmt_pct(sector_explained)}**")
    lines.append(f"- volume z ≥ 2 on T: **{fmt_pct(high_vol)}**")
    lines.append("")

    lines.append("## 4-quadrant earnings × sector decomposition\n")
    lines.append(f"- earnings + sector spike: **{fmt_pct(both)}**")
    lines.append(f"- earnings only (no sector spike): **{fmt_pct(earnings_only)}**")
    lines.append(f"- sector spike only (no earnings): **{fmt_pct(sector_only)}**")
    lines.append(f"- neither (true idiosyncratic): **{fmt_pct(neither)}**")
    lines.append("")

    lines.append("## By regime\n")
    for r, p in by_regime.items():
        lines.append(f"- {r}: {fmt_pct(p)}")
    lines.append("")

    lines.append("## Channel availability (NULL share)\n")
    for col in ["volume_z", "volume_z_T1", "sector_index_ret_T", "sector_index_z",
                "india_vix_z", "regime"]:
        null_share = card[col].isna().mean()
        lines.append(f"- {col}: NULL {fmt_pct(null_share)}")
    lines.append("")

    lines.append("## Out of v1 (deferred to v2)\n")
    lines.append("- news_tagged / news_kind / news_sentiment — historical news log < 5y")
    lines.append("- bulk_deal_T / bulk_deal_side — IndianAPI endpoint not yet integrated")
    lines.append("- promoter_trade_T / promoter_side — SAST/PIT not yet pulled")
    lines.append("- fii_sector_net_T — daily_dump per-sector breakdown TBD")
    lines.append("- |z|≥2 (vs ≥3) T-1 persistence — needs full residual-panel rebuild")
    lines.append("")

    return "\n".join(lines)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    card = build_card()
    csv_path = OUT_DIR / "correlation_break_4sigma_v1.csv"
    md_path = OUT_DIR / "correlation_break_4sigma_v1_report.md"
    card.to_csv(csv_path, index=False)
    md_path.write_text(build_report(card), encoding="utf-8")
    log.info("wrote %d rows to %s", len(card), csv_path)
    log.info("wrote report to %s", md_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
