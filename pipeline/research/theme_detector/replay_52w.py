"""Theme Detector v1 — 52-week PIT replay basket evaluator.

Bharat 2026-05-02: take the existing 156-week retro trajectory, slice to last
52 Sundays (2025-05-04 → 2026-04-26), and for every weekly stage transition
evaluate forward basket returns on top-3 members. Compare to random/naive
baselines and cost-stress.

**Frozen-thresholds rule:** This script does NOT re-optimize lifecycle.py
thresholds based on result. It is a supplementary read on the retro window;
the forward 45-day shadow remains the actual Gate 2 closure path.

Inputs:
- pipeline/data/research/theme_detector/retro/lifecycle_trajectory.csv (156w retro)
- pipeline/research/theme_detector/themes_frozen.json (member lists)
- pipeline/data/fno_historical/<TICKER>.csv (daily OHLCV per member)
- pipeline/data/fno_historical/NIFTY.csv (benchmark)

Outputs (all under pipeline/data/research/theme_detector/replay_52w/):
- transitions.csv — every transition + basket members + forward returns
- baseline_random_date.csv — random-date null
- baseline_random_member.csv — random-member null
- baseline_nifty.csv — always-long-Nifty
- transition_quality.csv — per-stage outcome rates
- summary.json — top-line numbers at 0/20/40 bps cost
"""
from __future__ import annotations

import csv
import json
import math
import random
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[3]
TRAJ = REPO / "pipeline/data/research/theme_detector/retro/lifecycle_trajectory.csv"
THEMES = REPO / "pipeline/research/theme_detector/themes_frozen.json"
PRICE_DIR = REPO / "pipeline/data/fno_historical"
OUT_DIR = REPO / "pipeline/data/research/theme_detector/replay_52w"

WINDOW_START = date(2025, 5, 4)   # 52 Sundays back from 2026-04-26
WINDOW_END = date(2026, 4, 26)
TOP_N = 3
HORIZONS = [5, 21, 45]            # trading-day forward windows
COST_BPS_TIERS = [0, 20, 40]
RNG_SEED = 42


def load_prices() -> dict[str, pd.DataFrame]:
    """Return {ticker: DataFrame indexed by date with Close column}."""
    out = {}
    for csv_path in PRICE_DIR.glob("*.csv"):
        try:
            df = pd.read_csv(csv_path, parse_dates=["Date"]).set_index("Date").sort_index()
            df = df[["Close"]].dropna()
            out[csv_path.stem] = df
        except Exception:
            continue
    return out


def trading_calendar(prices: dict[str, pd.DataFrame]) -> pd.DatetimeIndex:
    """Use NIFTY's index as the canonical trading calendar."""
    return prices["NIFTY"].index


def fwd_return(price_df: pd.DataFrame, anchor: pd.Timestamp, horizon_td: int) -> float | None:
    """Close-to-close log return over `horizon_td` trading days starting AFTER anchor.

    Returns None if either the entry-bar or exit-bar is not present in the
    series (cap at 2026-04-26 last bar).
    """
    idx = price_df.index
    if anchor not in idx:
        # snap to next trading day
        future = idx[idx > anchor]
        if len(future) == 0:
            return None
        anchor = future[0]
    pos = idx.get_loc(anchor)
    if pos + horizon_td >= len(idx):
        return None
    p0 = float(price_df["Close"].iloc[pos])
    p1 = float(price_df["Close"].iloc[pos + horizon_td])
    if p0 <= 0:
        return None
    return math.log(p1 / p0)


def rs_21d(member_df: pd.DataFrame, nifty_df: pd.DataFrame, anchor: pd.Timestamp) -> float | None:
    """21-trading-day log RS (member - nifty) ending AT anchor (point-in-time)."""
    if anchor not in member_df.index or anchor not in nifty_df.index:
        # snap back to prior trading day common to both
        common = member_df.index.intersection(nifty_df.index)
        common = common[common <= anchor]
        if len(common) == 0:
            return None
        anchor = common[-1]
    m_idx = member_df.index
    n_idx = nifty_df.index
    m_pos = m_idx.get_loc(anchor)
    n_pos = n_idx.get_loc(anchor)
    if m_pos < 21 or n_pos < 21:
        return None
    m0 = float(member_df["Close"].iloc[m_pos - 21])
    m1 = float(member_df["Close"].iloc[m_pos])
    n0 = float(nifty_df["Close"].iloc[n_pos - 21])
    n1 = float(nifty_df["Close"].iloc[n_pos])
    if m0 <= 0 or n0 <= 0:
        return None
    return math.log(m1 / m0) - math.log(n1 / n0)


def pick_top_n(theme_members: list[str], anchor: pd.Timestamp,
               prices: dict[str, pd.DataFrame], nifty: pd.DataFrame, n: int = TOP_N) -> list[str]:
    """Top-N theme members by 21d RS at anchor. Filters out members with no
    price data."""
    scored: list[tuple[str, float]] = []
    for m in theme_members:
        if m not in prices:
            continue
        rs = rs_21d(prices[m], nifty, anchor)
        if rs is None:
            continue
        scored.append((m, rs))
    scored.sort(key=lambda x: x[1], reverse=True)
    return [s[0] for s in scored[:n]]


def basket_return(members: list[str], anchor: pd.Timestamp, horizon: int,
                  prices: dict[str, pd.DataFrame]) -> float | None:
    """Equal-weight basket forward log return. Returns None if no members
    have a valid forward window."""
    rs = []
    for m in members:
        if m not in prices:
            continue
        r = fwd_return(prices[m], anchor, horizon)
        if r is not None:
            rs.append(r)
    if not rs:
        return None
    return sum(rs) / len(rs)


def apply_cost(gross: float, cost_bps: int) -> float:
    """Round-trip cost per basket leg = cost_bps / 10000."""
    return gross - (cost_bps / 10000.0)


def find_transitions(traj: pd.DataFrame, window_start: date, window_end: date) -> pd.DataFrame:
    """Return rows where lifecycle_stage differs from the prior week within the
    window. Stage at `week=window_start - 7d` (last pre-window) is loaded so
    week-1 transitions are detectable."""
    real = traj[traj["label"] == "real"].copy()
    real["week"] = pd.to_datetime(real["week"]).dt.date
    real = real.sort_values(["theme_id", "week"])
    real["prev_stage"] = real.groupby("theme_id")["lifecycle_stage"].shift(1)
    in_window = (real["week"] >= window_start) & (real["week"] <= window_end)
    transitions = real[in_window & real["prev_stage"].notna() &
                       (real["lifecycle_stage"] != real["prev_stage"])].copy()
    transitions["transition"] = transitions["prev_stage"] + "->" + transitions["lifecycle_stage"]
    return transitions[["week", "theme_id", "prev_stage", "lifecycle_stage", "transition",
                        "belief_score", "confirmation_score", "current_strength"]]


def transition_outcomes(traj: pd.DataFrame, window_start: date, window_end: date) -> list[dict]:
    """For each PRE_IGNITION entry in the window, classify outcome at the
    earliest of: 12 weeks elapsed, IGNITION reached, DORMANT reached,
    FALSE_POSITIVE reached, OR end of trajectory."""
    real = traj[traj["label"] == "real"].copy()
    real["week"] = pd.to_datetime(real["week"]).dt.date
    real = real.sort_values(["theme_id", "week"])
    real["prev_stage"] = real.groupby("theme_id")["lifecycle_stage"].shift(1)
    in_window = (real["week"] >= window_start) & (real["week"] <= window_end)

    pre_ig_entries = real[in_window & (real["lifecycle_stage"] == "PRE_IGNITION") &
                          (real["prev_stage"] != "PRE_IGNITION")]

    out: list[dict] = []
    for _, entry in pre_ig_entries.iterrows():
        theme_id = entry["theme_id"]
        entry_week = entry["week"]
        cutoff = entry_week + timedelta(weeks=12)
        future = real[(real["theme_id"] == theme_id) &
                      (real["week"] > entry_week) &
                      (real["week"] <= cutoff)].sort_values("week")
        outcome = "STILL_PRE_IGNITION_AT_12W"
        outcome_week = None
        for _, fr in future.iterrows():
            if fr["lifecycle_stage"] == "IGNITION":
                outcome = "ESCALATED_TO_IGNITION"
                outcome_week = fr["week"]
                break
            if fr["lifecycle_stage"] == "DORMANT":
                outcome = "INVERTED_TO_DORMANT"
                outcome_week = fr["week"]
                break
            if fr["lifecycle_stage"] == "FALSE_POSITIVE":
                outcome = "FALSE_POSITIVE"
                outcome_week = fr["week"]
                break
        if not future.shape[0]:
            outcome = "INSUFFICIENT_FORWARD_DATA"
        out.append({
            "theme_id": theme_id,
            "entry_week": entry_week.isoformat(),
            "outcome": outcome,
            "outcome_week": outcome_week.isoformat() if outcome_week else None,
        })
    return out


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rng = random.Random(RNG_SEED)

    print("[replay52w] loading themes + prices ...")
    themes = json.loads(THEMES.read_text(encoding="utf-8"))["themes"]
    members_by_theme = {
        t["theme_id"]: t.get("rule_definition", {}).get("members", [])
        for t in themes if t.get("rule_kind") == "A"
    }
    prices = load_prices()
    nifty = prices["NIFTY"]
    print(f"[replay52w] {len(prices)} ticker price files loaded")

    print("[replay52w] loading 156w trajectory + finding 52w transitions ...")
    traj = pd.read_csv(TRAJ)
    transitions = find_transitions(traj, WINDOW_START, WINDOW_END)
    print(f"[replay52w] {len(transitions)} transitions in 2025-05-04..2026-04-26")
    print(transitions["transition"].value_counts().to_string())

    # ===========================================================
    # PHASE 1: Real basket forward returns
    # ===========================================================
    rows: list[dict] = []
    for _, t in transitions.iterrows():
        theme_id = t["theme_id"]
        if theme_id not in members_by_theme or len(members_by_theme[theme_id]) < TOP_N:
            continue
        anchor = pd.Timestamp(t["week"])
        members = members_by_theme[theme_id]
        top = pick_top_n(members, anchor, prices, nifty, TOP_N)
        if len(top) < TOP_N:
            continue
        row = {
            "week": t["week"].isoformat(),
            "theme_id": theme_id,
            "transition": t["transition"],
            "members": "|".join(top),
            "belief": round(t["belief_score"], 4),
            "confirmation": round(t["confirmation_score"], 4),
            "strength": round(t["current_strength"], 4),
        }
        for h in HORIZONS:
            br = basket_return(top, anchor, h, prices)
            row[f"ret_{h}d"] = round(br, 6) if br is not None else None
        rows.append(row)

    real_df = pd.DataFrame(rows)
    real_df.to_csv(OUT_DIR / "transitions.csv", index=False)

    # ===========================================================
    # PHASE 2: Random-date null (same theme, random Sunday in window)
    # ===========================================================
    sundays = sorted({pd.Timestamp(t["week"]) for _, t in transitions.iterrows()})
    null_dates = []
    for _, t in transitions.iterrows():
        theme_id = t["theme_id"]
        if theme_id not in members_by_theme or len(members_by_theme[theme_id]) < TOP_N:
            continue
        random_anchor = rng.choice(sundays)
        members = members_by_theme[theme_id]
        top = pick_top_n(members, random_anchor, prices, nifty, TOP_N)
        if len(top) < TOP_N:
            continue
        row = {
            "real_week": t["week"].isoformat(),
            "random_week": random_anchor.date().isoformat(),
            "theme_id": theme_id,
            "members": "|".join(top),
        }
        for h in HORIZONS:
            br = basket_return(top, random_anchor, h, prices)
            row[f"ret_{h}d"] = round(br, 6) if br is not None else None
        null_dates.append(row)
    null_date_df = pd.DataFrame(null_dates)
    null_date_df.to_csv(OUT_DIR / "baseline_random_date.csv", index=False)

    # ===========================================================
    # PHASE 3: Random-member null (same date + theme, random N members)
    # ===========================================================
    null_members = []
    for _, t in transitions.iterrows():
        theme_id = t["theme_id"]
        if theme_id not in members_by_theme or len(members_by_theme[theme_id]) < TOP_N:
            continue
        anchor = pd.Timestamp(t["week"])
        members = [m for m in members_by_theme[theme_id] if m in prices]
        if len(members) < TOP_N:
            continue
        random_top = rng.sample(members, TOP_N)
        row = {
            "week": t["week"].isoformat(),
            "theme_id": theme_id,
            "members": "|".join(random_top),
        }
        for h in HORIZONS:
            br = basket_return(random_top, anchor, h, prices)
            row[f"ret_{h}d"] = round(br, 6) if br is not None else None
        null_members.append(row)
    null_member_df = pd.DataFrame(null_members)
    null_member_df.to_csv(OUT_DIR / "baseline_random_member.csv", index=False)

    # ===========================================================
    # PHASE 4: Always-long-Nifty naive baseline (one basket return per transition date)
    # ===========================================================
    nifty_baseline = []
    for _, t in transitions.iterrows():
        anchor = pd.Timestamp(t["week"])
        row = {"week": t["week"].isoformat(), "theme_id": t["theme_id"]}
        for h in HORIZONS:
            br = fwd_return(nifty, anchor, h)
            row[f"ret_{h}d"] = round(br, 6) if br is not None else None
        nifty_baseline.append(row)
    nifty_df = pd.DataFrame(nifty_baseline)
    nifty_df.to_csv(OUT_DIR / "baseline_nifty.csv", index=False)

    # ===========================================================
    # PHASE 5: Transition quality (PRE_IGNITION outcomes within 12w)
    # ===========================================================
    outcomes = transition_outcomes(traj, WINDOW_START, WINDOW_END)
    outcomes_df = pd.DataFrame(outcomes)
    outcomes_df.to_csv(OUT_DIR / "transition_quality.csv", index=False)

    outcome_counts = Counter(o["outcome"] for o in outcomes)
    n_pre = len(outcomes)

    # ===========================================================
    # PHASE 6: Cost-stressed summary
    # ===========================================================
    def stats(df: pd.DataFrame, col: str) -> dict:
        s = df[col].dropna()
        if len(s) == 0:
            return {"n": 0, "mean": None, "hit": None, "median": None, "std": None}
        return {
            "n": int(len(s)),
            "mean": float(s.mean()),
            "median": float(s.median()),
            "std": float(s.std()) if len(s) > 1 else 0.0,
            "hit": float((s > 0).sum() / len(s)),
        }

    summary = {
        "window_start": WINDOW_START.isoformat(),
        "window_end": WINDOW_END.isoformat(),
        "n_transitions_total": int(len(transitions)),
        "transition_breakdown": dict(transitions["transition"].value_counts()),
        "n_with_basket_eval": int(len(real_df)),
        "horizons_td": HORIZONS,
        "raw_returns": {
            f"{h}d": {
                "real_basket": stats(real_df, f"ret_{h}d"),
                "random_date_null": stats(null_date_df, f"ret_{h}d"),
                "random_member_null": stats(null_member_df, f"ret_{h}d"),
                "nifty_naive": stats(nifty_df, f"ret_{h}d"),
            }
            for h in HORIZONS
        },
        "cost_stressed_mean": {
            f"{h}d": {
                f"{c}bps": {
                    "real_minus_cost": (
                        stats(real_df, f"ret_{h}d")["mean"] - c / 10000.0
                        if stats(real_df, f"ret_{h}d")["mean"] is not None else None
                    ),
                    "real_minus_random_member": (
                        (stats(real_df, f"ret_{h}d")["mean"] or 0) -
                        (stats(null_member_df, f"ret_{h}d")["mean"] or 0)
                        - c / 10000.0
                    ),
                    "real_minus_nifty": (
                        (stats(real_df, f"ret_{h}d")["mean"] or 0) -
                        (stats(nifty_df, f"ret_{h}d")["mean"] or 0)
                        - c / 10000.0
                    ),
                }
                for c in COST_BPS_TIERS
            }
            for h in HORIZONS
        },
        "transition_quality_pre_ignition_12w": {
            "n_pre_ignition_entries": n_pre,
            "outcomes": dict(outcome_counts),
            "rates": (
                {k: round(v / n_pre, 3) for k, v in outcome_counts.items()}
                if n_pre else {}
            ),
        },
        "by_transition_type_mean_21d": {
            tt: stats(real_df[real_df["transition"] == tt], "ret_21d")
            for tt in real_df["transition"].unique()
        },
    }
    (OUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")

    # ===========================================================
    # PHASE 7: Console summary
    # ===========================================================
    print("\n=== 52-WEEK PIT REPLAY VERDICT ===")
    print(f"window: {WINDOW_START} -> {WINDOW_END}")
    print(f"transitions: {len(transitions)}  |  basket-evaluable: {len(real_df)}")
    print(f"transitions by type:\n{transitions['transition'].value_counts().to_string()}")
    print()
    for h in HORIZONS:
        s_real = stats(real_df, f"ret_{h}d")
        s_rdate = stats(null_date_df, f"ret_{h}d")
        s_rmem = stats(null_member_df, f"ret_{h}d")
        s_nifty = stats(nifty_df, f"ret_{h}d")
        print(f"--- horizon {h} trading days ---")
        for label, s in [("REAL", s_real), ("rand-date null", s_rdate),
                         ("rand-member null", s_rmem), ("Nifty naive", s_nifty)]:
            if s["n"] == 0:
                print(f"  {label:18}  n=0")
            else:
                print(f"  {label:18}  n={s['n']:3}  mean={s['mean']:+.4%}  hit={s['hit']:.2%}  med={s['median']:+.4%}")
        if s_real["n"] and s_rmem["n"]:
            edge = s_real["mean"] - s_rmem["mean"]
            print(f"  EDGE vs rand-member: {edge:+.4%}  (cost-stressed @20bps: {edge - 0.0020:+.4%})")
        print()

    print("--- transition quality (PRE_IGNITION outcomes within 12w) ---")
    for k, v in outcome_counts.items():
        rate = v / n_pre if n_pre else 0
        print(f"  {k:30}  n={v:3}  rate={rate:.2%}")

    print(f"\nartefacts: {OUT_DIR}")


if __name__ == "__main__":
    main()
