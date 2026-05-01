"""Stage A widen #74 — sector spillover (event-day peer drift, multi-horizon).

Forensic only. NOT a hypothesis. NO holdout consumption. NO registry row.

QUESTION
--------
When a NIFTY Bank or NIFTY IT name prints earnings (e.g., SBIN, HDFCBANK, INFY,
TCS), do its sector peers drift in the same direction over the next 1, 3, 5
trading days? If yes, that's a separate v2 hypothesis (peer-momentum spillover
LONG) — distinct from the on-the-name LONG drift already pre-registered as
H-2026-05-01-EARNINGS-DRIFT-LONG-v1.

DATA
----
- pipeline/research/h_2026_05_01_earnings_drift/event_factors.csv (314 events,
  with direction_proxy = BEAT_LIKE | MISS_LIKE | NEUTRAL based on event-day
  excess return)
- pipeline/data/fno_historical/<SYMBOL>.csv for peer daily bars

METHOD
------
For each event (symbol_E, event_date_E, sector_E, direction_proxy_E):
  - peer cohort = all OTHER names in sector_E (from frozen 40-name universe)
  - for each peer P:
      * find T+0_P = first trading day strictly > event_date_E in P's daily bars
      * compute log returns at h ∈ {1, 3, 5}: ret_h_bps = ln(C[T+h-1] / C[T+0-1]) * 10000
      * NOTE T+0 is the event day for the printing name; for peers the comparable
        anchor is "the close strictly before event_date_E" so we measure peer
        movement AFTER the event hits the tape. Use peer's last close <= event_date_E
        as the entry reference; first close > event_date_E starts h=1.
  - aggregate per event: median peer h_ret_bps across the cohort
  - aggregate across events stratified by direction_proxy_E

WRITES
------
- peer_drift_per_event.csv: one row per (event, peer, horizon)
- peer_drift_summary.json: aggregated statistics
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
EVENT_FACTORS_PATH = ROOT / "pipeline" / "research" / "h_2026_05_01_earnings_drift" / "event_factors.csv"
DAILY_DIR = ROOT / "pipeline" / "data" / "fno_historical"
UNIVERSE_FROZEN = ROOT / "pipeline" / "research" / "h_2026_05_01_earnings_drift_long" / "universe_frozen.json"

OUT_PER_EVENT_CSV = ROOT / "pipeline" / "research" / "h_2026_05_01_earnings_drift" / "peer_drift_per_event.csv"
OUT_SUMMARY_JSON = ROOT / "pipeline" / "research" / "h_2026_05_01_earnings_drift" / "peer_drift_summary.json"


def _read_daily_close(symbol: str) -> pd.DataFrame | None:
    path = DAILY_DIR / f"{symbol}.csv"
    if not path.exists():
        return None
    df = pd.read_csv(path)
    df.columns = [c.strip().capitalize() for c in df.columns]
    if "Date" not in df.columns or "Close" not in df.columns:
        return None
    df["Date"] = pd.to_datetime(df["Date"])
    df = df[["Date", "Close"]].sort_values("Date").reset_index(drop=True)
    return df


def _peer_returns_at_horizons(peer_daily: pd.DataFrame, event_date: pd.Timestamp,
                                horizons: list[int]) -> dict[int, float] | None:
    """For peer P, compute log return from last close <= event_date to close at T+h.

    Returns None if any required bar is missing.
    """
    pre = peer_daily[peer_daily["Date"] <= event_date]
    post = peer_daily[peer_daily["Date"] > event_date].reset_index(drop=True)
    if pre.empty or len(post) < max(horizons):
        return None
    p_anchor = float(pre["Close"].iloc[-1])
    if p_anchor <= 0:
        return None
    out = {}
    for h in horizons:
        if h - 1 >= len(post):
            return None
        p_h = float(post["Close"].iloc[h - 1])
        if p_h <= 0:
            return None
        out[h] = float(np.log(p_h / p_anchor) * 10_000.0)
    return out


def main() -> None:
    universe = json.load(open(UNIVERSE_FROZEN))["universe"]  # {"Banks": [...], "IT_Services": [...]}
    sec_to_syms = {sec: list(syms) for sec, syms in universe.items()}

    ev = pd.read_csv(EVENT_FACTORS_PATH)
    ev["event_date"] = pd.to_datetime(ev["event_date"])
    print(f"events: {len(ev)}  (Banks={(ev['sector']=='Banks').sum()}, "
          f"IT_Services={(ev['sector']=='IT_Services').sum()})")

    # cache peer dailies
    cache = {}
    for sec, syms in sec_to_syms.items():
        for s in syms:
            cache[s] = _read_daily_close(s)

    horizons = [1, 3, 5]
    rows = []
    n_skipped = 0

    for _, e in ev.iterrows():
        sym_e = e["symbol"]
        sec_e = e["sector"]
        dir_e = e["direction_proxy"]
        regime_e = e["regime"]
        event_date = e["event_date"]
        peers = [p for p in sec_to_syms.get(sec_e, []) if p != sym_e]

        for p in peers:
            pd_p = cache.get(p)
            if pd_p is None or pd_p.empty:
                continue
            rets = _peer_returns_at_horizons(pd_p, event_date, horizons)
            if rets is None:
                n_skipped += 1
                continue
            row = {
                "event_symbol": sym_e,
                "event_date": event_date.date(),
                "sector": sec_e,
                "event_direction": dir_e,
                "event_regime": regime_e,
                "peer_symbol": p,
            }
            for h in horizons:
                row[f"peer_ret_h{h}_bps"] = rets[h]
            rows.append(row)

    if not rows:
        print("no peer-drift rows assembled")
        return

    df = pd.DataFrame(rows)
    OUT_PER_EVENT_CSV.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT_PER_EVENT_CSV, index=False)
    print(f"per-event-peer rows: {len(df)} (skipped {n_skipped})")
    print(f"-> {OUT_PER_EVENT_CSV}")

    summary = {
        "meta": {
            "n_events": int(ev["event_date"].nunique() * len(ev) // max(1, ev["event_date"].nunique())),  # approx
            "n_event_peer_rows": int(len(df)),
            "horizons": horizons,
            "universe_breakdown": {sec: len(syms) for sec, syms in sec_to_syms.items()},
            "method": "peer = all other names in same sector; anchor = peer last close <= event_date; ret_h = ln(close[T+h-1]/anchor)*10000",
            "data_validation_policy": "PIT (anchor uses last close strictly <= event_date; T+h are forward-only post-event bars)",
        },
        "by_direction": {},
        "by_sector_direction": {},
        "by_regime_direction": {},
    }

    # Aggregate: median per-event-peer drift by direction
    for direction in ["BEAT_LIKE", "MISS_LIKE", "NEUTRAL"]:
        sub = df[df["event_direction"] == direction]
        if len(sub) == 0:
            continue
        summary["by_direction"][direction] = {
            "n_event_peer_rows": int(len(sub)),
            "n_unique_events": int(sub.groupby(["event_symbol", "event_date"]).ngroups),
            **{
                f"peer_ret_h{h}_bps": {
                    "median": round(float(sub[f"peer_ret_h{h}_bps"].median()), 2),
                    "mean": round(float(sub[f"peer_ret_h{h}_bps"].mean()), 2),
                    "std": round(float(sub[f"peer_ret_h{h}_bps"].std(ddof=1)), 2),
                    "hit_pos_pct": round(float((sub[f"peer_ret_h{h}_bps"] > 0).mean() * 100), 2),
                }
                for h in horizons
            },
        }

    # By sector x direction
    for sec in sec_to_syms.keys():
        for direction in ["BEAT_LIKE", "MISS_LIKE"]:
            sub = df[(df["sector"] == sec) & (df["event_direction"] == direction)]
            if len(sub) < 5:
                continue
            key = f"{sec}_{direction}"
            summary["by_sector_direction"][key] = {
                "n_event_peer_rows": int(len(sub)),
                "n_unique_events": int(sub.groupby(["event_symbol", "event_date"]).ngroups),
                **{
                    f"peer_ret_h{h}_bps_mean": round(float(sub[f"peer_ret_h{h}_bps"].mean()), 2)
                    for h in horizons
                },
                **{
                    f"peer_ret_h{h}_bps_median": round(float(sub[f"peer_ret_h{h}_bps"].median()), 2)
                    for h in horizons
                },
            }

    # By regime x direction (focus on NEUTRAL + RISK-ON which are the live-traded regimes)
    for regime in ["NEUTRAL", "RISK-ON", "CAUTION", "RISK-OFF", "EUPHORIA"]:
        for direction in ["BEAT_LIKE", "MISS_LIKE"]:
            sub = df[(df["event_regime"] == regime) & (df["event_direction"] == direction)]
            if len(sub) < 5:
                continue
            key = f"{regime}_{direction}"
            summary["by_regime_direction"][key] = {
                "n_event_peer_rows": int(len(sub)),
                "n_unique_events": int(sub.groupby(["event_symbol", "event_date"]).ngroups),
                **{
                    f"peer_ret_h{h}_bps_mean": round(float(sub[f"peer_ret_h{h}_bps"].mean()), 2)
                    for h in horizons
                },
                **{
                    f"peer_ret_h{h}_bps_hit_pos_pct": round(float((sub[f"peer_ret_h{h}_bps"] > 0).mean() * 100), 2)
                    for h in horizons
                },
            }

    OUT_SUMMARY_JSON.write_text(json.dumps(summary, indent=2, default=str))
    print(f"-> {OUT_SUMMARY_JSON}\n")
    print(json.dumps(summary["by_direction"], indent=2))


if __name__ == "__main__":
    main()
