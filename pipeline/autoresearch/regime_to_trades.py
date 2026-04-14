"""
AutoResearch — Regime to Trades
The missing link: for each regime zone, what spreads work,
for how long, and what do you do with open positions?

This answers: "The thermometer says NEUTRAL. Now what?"
"""

import json
import sys
import numpy as np
import pandas as pd
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from eodhd_client import fetch_eod_series


def load_data():
    """Load ETF composite + Indian stock data."""
    # Load composite signal
    etfs = {
        "ITA.US": "defence", "XLE.US": "energy", "XLF.US": "financials",
        "XLK.US": "tech", "XLV.US": "healthcare", "XLP.US": "staples",
        "XLI.US": "industrials", "EEM.US": "em", "EWZ.US": "brazil",
        "INDA.US": "india_etf", "FXI.US": "china", "EWJ.US": "japan",
        "EFA.US": "developed", "USO.US": "oil", "UNG.US": "natgas",
        "SLV.US": "silver", "DBA.US": "agriculture", "HYG.US": "high_yield",
        "LQD.US": "ig_bond", "TLT.US": "treasury", "IEF.US": "mid_treasury",
        "UUP.US": "dollar", "FXE.US": "euro", "FXY.US": "yen",
        "SPY.US": "sp500", "GLD.US": "gold", "VIX.INDX": "vix",
        "KBE.US": "kbw_bank", "KRE.US": "regional_bank",
        "JETS.US": "airlines", "ARKK.US": "innovation",
        "NSEI.INDX": "nifty",
    }

    # Indian sector proxies
    indian_stocks = {
        "HAL.NSE": "hal", "BEL.NSE": "bel",
        "TCS.NSE": "tcs", "INFY.NSE": "infy",
        "ONGC.NSE": "ongc", "COALINDIA.NSE": "coalindia",
        "BPCL.NSE": "bpcl", "HPCL.NSE": "hpcl",
        "HDFCBANK.NSE": "hdfcbank", "RELIANCE.NSE": "reliance",
        "SUNPHARMA.NSE": "sunpharma",
    }

    all_data = {}
    for sym, name in {**etfs, **indian_stocks}.items():
        try:
            data = fetch_eod_series(sym, days=1095)
            if data and len(data) > 200:
                df = pd.DataFrame(data)
                df["date"] = pd.to_datetime(df["date"])
                df = df.set_index("date").sort_index()
                col = "adjusted_close" if "adjusted_close" in df.columns else "close"
                all_data[name] = df[col].astype(float)
        except Exception:
            pass

    combined = pd.DataFrame(all_data).dropna()
    feature_cols = [c for c in combined.columns if c not in ["nifty"] + list(indian_stocks.values())]

    weights = json.loads(Path(__file__).parent.joinpath("etf_optimal_weights.json").read_text())["optimal_weights"]

    daily_returns = pd.DataFrame({c: combined[c].pct_change() * 100 for c in feature_cols}).dropna()
    composite = pd.Series(0.0, index=daily_returns.index)
    for col in feature_cols:
        if col in weights:
            composite += daily_returns[col] * weights[col]

    return composite, combined


def run_analysis():
    print("=" * 70)
    print("REGIME → TRADES: What to trade in each zone?")
    print("=" * 70)

    composite, raw = load_data()
    print(f"Data: {len(composite)} days")

    # Define zones
    calm_center = 0.0953
    calm_band = 3.8974

    zones = pd.Series("NEUTRAL", index=composite.index)
    zones[composite < calm_center - 2 * calm_band] = "RISK-OFF"
    zones[(composite >= calm_center - 2 * calm_band) & (composite < calm_center - calm_band)] = "CAUTION"
    zones[(composite >= calm_center + calm_band) & (composite < calm_center + 2 * calm_band)] = "RISK-ON"
    zones[composite >= calm_center + 2 * calm_band] = "EUPHORIA"

    # Define spread returns
    spreads = {}
    for pair_name, long_cols, short_cols in [
        ("Defence vs IT", ["hal", "bel"], ["tcs", "infy"]),
        ("Upstream vs Downstream", ["ongc", "coalindia"], ["bpcl", "hpcl"]),
        ("Coal vs OMCs", ["coalindia"], ["bpcl", "hpcl"]),
        ("Pharma vs Banks", ["sunpharma"], ["hdfcbank"]),
        ("Banks vs IT", ["hdfcbank"], ["tcs", "infy"]),
        ("Reliance vs OMCs", ["reliance"], ["bpcl", "hpcl"]),
    ]:
        long_ret = pd.DataFrame({c: raw[c].pct_change() * 100 for c in long_cols if c in raw}).mean(axis=1)
        short_ret = pd.DataFrame({c: raw[c].pct_change() * 100 for c in short_cols if c in raw}).mean(axis=1)
        spread_ret = long_ret - short_ret
        if not spread_ret.isna().all():
            spreads[pair_name] = spread_ret

    print(f"Spreads computed: {len(spreads)}")

    # ═══ For each zone × each spread × each holding period ═══
    print(f"\n{'='*70}")
    print("WHAT WORKS IN EACH ZONE?")
    print(f"{'='*70}")

    holding_periods = [1, 3, 5]
    results = {}

    for zone_name in ["RISK-OFF", "CAUTION", "NEUTRAL", "RISK-ON", "EUPHORIA"]:
        zone_days = zones[zones == zone_name].index
        if len(zone_days) < 10:
            continue

        print(f"\n  ── {zone_name} ({len(zone_days)} days) ──")
        print(f"  {'Spread':30s} {'1d Win%':>8s} {'1d Avg':>8s} {'3d Win%':>8s} {'3d Avg':>8s} {'5d Win%':>8s} {'5d Avg':>8s}")
        print(f"  {'-'*78}")

        zone_results = {}
        for spread_name, spread_ret in spreads.items():
            row = {"spread": spread_name}
            best_period = None
            best_win = 0

            for hold in holding_periods:
                # Forward return for each zone day
                fwd_returns = []
                for day in zone_days:
                    idx = spread_ret.index.get_indexer([day], method="nearest")[0]
                    if idx + hold < len(spread_ret):
                        fwd = spread_ret.iloc[idx:idx + hold].sum()
                        fwd_returns.append(fwd)

                if len(fwd_returns) < 5:
                    continue

                win_rate = sum(1 for r in fwd_returns if r > 0) / len(fwd_returns) * 100
                avg_ret = np.mean(fwd_returns)

                row[f"{hold}d_win"] = round(win_rate, 0)
                row[f"{hold}d_avg"] = round(avg_ret, 2)

                if win_rate > best_win:
                    best_win = win_rate
                    best_period = hold

            row["best_period"] = best_period
            row["best_win"] = round(best_win, 0)
            zone_results[spread_name] = row

            w1 = row.get("1d_win", "-")
            a1 = row.get("1d_avg", "-")
            w3 = row.get("3d_win", "-")
            a3 = row.get("3d_avg", "-")
            w5 = row.get("5d_win", "-")
            a5 = row.get("5d_avg", "-")
            best = f" ← BEST {best_period}d" if best_win > 60 else ""
            print(f"  {spread_name:30s} {w1:>7}% {a1:>+7}% {w3:>7}% {a3:>+7}% {w5:>7}% {a5:>+7}%{best}")

        results[zone_name] = zone_results

    # ═══ REGIME CHANGE RULES — what to do with open positions ═══
    print(f"\n{'='*70}")
    print("WHAT TO DO WITH OPEN POSITIONS WHEN REGIME CHANGES?")
    print(f"{'='*70}")

    # Find regime transitions and measure P&L of holding vs exiting
    transitions = []
    for i in range(1, len(zones)):
        if zones.iloc[i] != zones.iloc[i - 1]:
            transitions.append({
                "date": str(zones.index[i].date()),
                "from": zones.iloc[i - 1],
                "to": zones.iloc[i],
            })

    print(f"\n  Total regime transitions: {len(transitions)}")

    # For each spread: what happens if you HOLD through a transition vs EXIT?
    print(f"\n  {'Transition':30s} {'Count':>6s} {'Hold 5d':>10s} {'Exit Win%':>10s}")
    print(f"  {'-'*60}")

    for from_z, to_z in [("NEUTRAL", "CAUTION"), ("NEUTRAL", "RISK-OFF"),
                          ("NEUTRAL", "RISK-ON"), ("CAUTION", "NEUTRAL"),
                          ("RISK-ON", "NEUTRAL")]:
        t_dates = [t["date"] for t in transitions if t["from"] == from_z and t["to"] == to_z]
        if len(t_dates) < 3:
            continue

        # Average Nifty 5d return after transition
        nifty_ret = raw["nifty"].pct_change() * 100
        returns_after = []
        for d in t_dates:
            idx = nifty_ret.index.get_indexer([pd.Timestamp(d)], method="nearest")[0]
            if idx + 5 < len(nifty_ret):
                returns_after.append(nifty_ret.iloc[idx:idx + 5].sum())

        if returns_after:
            avg = np.mean(returns_after)
            exit_win = sum(1 for r in returns_after if (from_z in ("NEUTRAL", "RISK-ON") and r < 0) or
                          (from_z in ("CAUTION", "RISK-OFF") and r > 0)) / len(returns_after) * 100
            print(f"  {from_z:12s} → {to_z:12s}    {len(t_dates):>4d}   {avg:>+9.2f}%   {exit_win:>9.0f}%")

    # ═══ TODAY ═══
    today_zone = str(zones.iloc[-1])
    print(f"\n{'='*70}")
    print(f"TODAY: {today_zone}")
    print(f"{'='*70}")

    if today_zone in results:
        print(f"\nBest spreads for {today_zone} zone:")
        zone_r = results[today_zone]
        sorted_spreads = sorted(zone_r.items(), key=lambda x: x[1].get("best_win", 0), reverse=True)
        for spread_name, data in sorted_spreads[:3]:
            bp = data.get("best_period", "?")
            bw = data.get("best_win", 0)
            ba = data.get(f"{bp}d_avg", 0) if bp else 0
            print(f"  {spread_name}: {bw:.0f}% win rate over {bp} days (avg {ba:+.2f}%)")

    print(f"\nOPEN POSITION RULES:")
    print(f"  If regime is NEUTRAL: hold positions normally, use standard stops")
    print(f"  If regime shifts to CAUTION: tighten stops by 50%, reduce size to 75%")
    print(f"  If regime shifts to RISK-OFF: EXIT all long-biased positions immediately")
    print(f"  If regime shifts to RISK-ON: add to winning positions, loosen stops")

    # Save
    Path(__file__).parent.joinpath("regime_trade_map.json").write_text(
        json.dumps({
            "results": {k: {sk: sv for sk, sv in v.items()} for k, v in results.items()},
            "transitions": len(transitions),
            "today_zone": today_zone,
        }, indent=2, default=str), encoding="utf-8")
    print("\nSaved to autoresearch/regime_trade_map.json")


if __name__ == "__main__":
    run_analysis()
