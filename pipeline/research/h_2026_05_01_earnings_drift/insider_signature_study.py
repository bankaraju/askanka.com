"""Stage A widen #75 — pre-event insider trading signature.

Forensic only. NOT a hypothesis. NO holdout consumption. NO registry row.

QUESTION
--------
Does insider buying / selling in the 30 days BEFORE a Banks/IT earnings event
predict the direction (BEAT_LIKE vs MISS_LIKE)? If yes, that's a v2 feature
candidate to add to the entry rule.

(Substitute for the originally-mentioned "INDUSIND / Goldman large-print"
bulk-deals pattern, which cannot be backtested because NSE bulk-deals history
is unavailable per `reference_nse_bulk_deals_history_unavailable.md` — only
forward-only collection from 2026-04-24, ~6 days as of 2026-05-01. Insider
trade disclosures, by contrast, span 2021-01 onward.)

DATA
----
- 314 events in event_factors.csv (40-name Banks+IT, 2021-05 → 2024-04)
- pipeline/data/insider_trades/<YYYY-MM>.parquet (88,863 rows, 2021-01 → 2024-12)

METHOD (PIT-clean)
------------------
For each event (symbol_E, event_date_E, direction_proxy_E):
  - WINDOW = [event_date_E - 30 days, event_date_E - 1 day]
  - Filter insider_trades where:
      * symbol == symbol_E
      * acq_to_date in WINDOW (the trade was executed in that window)
      * filing_date <= event_date_E - 1 day (PIT — must have been filed before
        T-1; otherwise the signal isn't observable at the entry moment)
      * person_category in {Promoters, Promoter Group, Director,
        Key Managerial Personnel, Immediate relative}
        (operative insiders, not designated/employee SARs)
      * transaction_type in {Buy, Sell}
  - Aggregate:
      * insider_buy_inr = sum of value_inr where Buy
      * insider_sell_inr = sum of value_inr where Sell
      * insider_net_inr = buy - sell

Stratify by direction_proxy and report mean / median / hit-direction.

WRITES
------
- insider_signature_per_event.csv: one row per event (symbol_E, event_date_E,
  insider_buy_inr, insider_sell_inr, insider_net_inr, direction_proxy)
- insider_signature_summary.json: aggregated stats
"""
from __future__ import annotations

import glob
import json
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
EVENT_FACTORS_PATH = ROOT / "pipeline" / "research" / "h_2026_05_01_earnings_drift" / "event_factors.csv"
INSIDER_DIR = ROOT / "pipeline" / "data" / "insider_trades"

OUT_PER_EVENT_CSV = ROOT / "pipeline" / "research" / "h_2026_05_01_earnings_drift" / "insider_signature_per_event.csv"
OUT_SUMMARY_JSON = ROOT / "pipeline" / "research" / "h_2026_05_01_earnings_drift" / "insider_signature_summary.json"

WINDOW_DAYS = 30
INSIDER_CATEGORIES = {"Promoters", "Promoter Group", "Director",
                      "Key Managerial Personnel", "Immediate relative"}
INSIDER_TXN_TYPES = {"Buy", "Sell"}


def _load_insider_history() -> pd.DataFrame:
    files = sorted(glob.glob(str(INSIDER_DIR / "20[12]*.parquet")))
    files = [f for f in files if "2021" in f or "2022" in f or "2023" in f or "2024" in f]
    if not files:
        raise FileNotFoundError("no insider_trades files found")
    dfs = [pd.read_parquet(f) for f in files]
    df = pd.concat(dfs, ignore_index=True)
    # parse dates
    for col in ("acq_from_date", "acq_to_date", "intimation_date", "filing_date"):
        df[col] = pd.to_datetime(df[col], errors="coerce")
    # numeric coerce
    df["value_inr"] = pd.to_numeric(df["value_inr"], errors="coerce")
    df = df[df["value_inr"].notna()].copy()
    return df


def main() -> None:
    print("loading insider_trades 2021-2024 ...")
    insider = _load_insider_history()
    insider = insider[insider["person_category"].isin(INSIDER_CATEGORIES) &
                      insider["transaction_type"].isin(INSIDER_TXN_TYPES)].copy()
    print(f"  filtered insider rows (operative + Buy/Sell): {len(insider)}")

    ev = pd.read_csv(EVENT_FACTORS_PATH)
    ev["event_date"] = pd.to_datetime(ev["event_date"])
    print(f"events: {len(ev)}")

    rows = []
    for _, e in ev.iterrows():
        sym_e = e["symbol"]
        event_date = e["event_date"]
        dir_e = e["direction_proxy"]
        regime_e = e["regime"]
        sector_e = e["sector"]

        window_start = event_date - timedelta(days=WINDOW_DAYS)
        window_end = event_date - timedelta(days=1)

        sub = insider[
            (insider["symbol"] == sym_e) &
            (insider["acq_to_date"] >= window_start) &
            (insider["acq_to_date"] <= window_end) &
            (insider["filing_date"] <= window_end)  # PIT: must be filed before T-1
        ]

        buy_v = float(sub.loc[sub["transaction_type"] == "Buy", "value_inr"].sum())
        sell_v = float(sub.loc[sub["transaction_type"] == "Sell", "value_inr"].sum())
        n_buy = int((sub["transaction_type"] == "Buy").sum())
        n_sell = int((sub["transaction_type"] == "Sell").sum())

        rows.append({
            "symbol": sym_e,
            "event_date": event_date.date(),
            "sector": sector_e,
            "direction_proxy": dir_e,
            "regime": regime_e,
            "insider_buy_inr": buy_v,
            "insider_sell_inr": sell_v,
            "insider_net_inr": buy_v - sell_v,
            "n_buy": n_buy,
            "n_sell": n_sell,
            "any_insider": int((n_buy + n_sell) > 0),
        })

    df = pd.DataFrame(rows)
    OUT_PER_EVENT_CSV.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT_PER_EVENT_CSV, index=False)
    print(f"per-event rows: {len(df)} (with any insider activity: "
          f"{int(df['any_insider'].sum())} / {len(df)})")

    # Cross-tab: direction x insider net sign
    df["insider_sign"] = np.where(df["insider_net_inr"] > 0, "POS",
                          np.where(df["insider_net_inr"] < 0, "NEG", "ZERO"))

    summary = {
        "meta": {
            "n_events": int(len(df)),
            "n_with_any_insider_activity": int(df["any_insider"].sum()),
            "window_days": WINDOW_DAYS,
            "insider_categories": sorted(INSIDER_CATEGORIES),
            "method": "PIT-clean: filing_date <= event_date - 1 day",
            "data_source": "pipeline/data/insider_trades/<YYYY-MM>.parquet",
        },
        "by_direction": {},
        "cross_tab_direction_x_insider_sign": {},
        "by_sector_direction": {},
    }

    for direction in ["BEAT_LIKE", "MISS_LIKE", "NEUTRAL"]:
        sub = df[df["direction_proxy"] == direction]
        if len(sub) == 0:
            continue
        summary["by_direction"][direction] = {
            "n": int(len(sub)),
            "n_with_insider": int((sub["any_insider"] == 1).sum()),
            "insider_buy_inr_mean_lakhs": round(float(sub["insider_buy_inr"].mean()) / 1e5, 1),
            "insider_sell_inr_mean_lakhs": round(float(sub["insider_sell_inr"].mean()) / 1e5, 1),
            "insider_net_inr_mean_lakhs": round(float(sub["insider_net_inr"].mean()) / 1e5, 1),
            "insider_net_inr_median_lakhs": round(float(sub["insider_net_inr"].median()) / 1e5, 1),
            "share_pos_net_pct": round(float((sub["insider_net_inr"] > 0).mean() * 100), 2),
            "share_neg_net_pct": round(float((sub["insider_net_inr"] < 0).mean() * 100), 2),
        }

    # Cross-tab: direction x insider sign
    for direction in ["BEAT_LIKE", "MISS_LIKE"]:
        for sign in ["POS", "NEG", "ZERO"]:
            sub = df[(df["direction_proxy"] == direction) & (df["insider_sign"] == sign)]
            summary["cross_tab_direction_x_insider_sign"][f"{direction}_{sign}"] = int(len(sub))

    # By sector
    for sec in ["Banks", "IT_Services"]:
        for direction in ["BEAT_LIKE", "MISS_LIKE"]:
            sub = df[(df["sector"] == sec) & (df["direction_proxy"] == direction)]
            if len(sub) < 5:
                continue
            summary["by_sector_direction"][f"{sec}_{direction}"] = {
                "n": int(len(sub)),
                "n_with_insider": int((sub["any_insider"] == 1).sum()),
                "insider_net_inr_mean_lakhs": round(float(sub["insider_net_inr"].mean()) / 1e5, 1),
                "share_pos_net_pct": round(float((sub["insider_net_inr"] > 0).mean() * 100), 2),
            }

    # KEY TEST: does insider_net SIGN predict direction_proxy?
    # Build 2x2 contingency table: pos_insider_net x BEAT_LIKE
    pos = df[df["insider_net_inr"] > 0]
    neg = df[df["insider_net_inr"] < 0]
    if len(pos) >= 5 and len(neg) >= 5:
        beat_among_pos = (pos["direction_proxy"] == "BEAT_LIKE").mean()
        beat_among_neg = (neg["direction_proxy"] == "BEAT_LIKE").mean()
        beat_unconditional = (df["direction_proxy"] == "BEAT_LIKE").mean()
        summary["pit_signal_strength"] = {
            "n_pos_insider_net": int(len(pos)),
            "n_neg_insider_net": int(len(neg)),
            "p(BEAT | insider_net>0)": round(float(beat_among_pos), 4),
            "p(BEAT | insider_net<0)": round(float(beat_among_neg), 4),
            "p(BEAT | unconditional)": round(float(beat_unconditional), 4),
            "lift_pos_minus_unconditional_pct": round(float((beat_among_pos - beat_unconditional) * 100), 2),
            "lift_neg_minus_unconditional_pct": round(float((beat_among_neg - beat_unconditional) * 100), 2),
        }

    OUT_SUMMARY_JSON.write_text(json.dumps(summary, indent=2, default=str))
    print(f"-> {OUT_SUMMARY_JSON}\n")
    print(json.dumps(summary["by_direction"], indent=2))
    if "pit_signal_strength" in summary:
        print()
        print("PIT signal strength:")
        print(json.dumps(summary["pit_signal_strength"], indent=2))


if __name__ == "__main__":
    main()
