"""Post-hoc focused queries on overshoot_reversion_backtest.py output.

For specific candidates (TECHM, POLICYBZR, DRREDDY, CIPLA, LAURUSLABS):
  * Historical |z|>=3 events → next-day return distribution
  * Same by regime-era (last 18 months vs pre)
  * Pair-trade simulation: pharma-long / IT-short on joint-overshoot days
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from pipeline.autoresearch.overshoot_reversion_backtest import (
    classify_events,
    compute_residuals,
    load_price_panel,
    load_sector_map,
)

_REPO = Path(__file__).resolve().parents[2]


def per_ticker_history(events: list[dict], ticker: str, min_z: float = 3.0):
    evs = [e for e in events if e["ticker"] == ticker and abs(e["z"]) >= min_z]
    if not evs:
        return None
    next_rets = [e["next_ret"] for e in evs]
    hits_up = sum(1 for e in evs if e["z"] > 0 and e["next_ret"] < 0)
    hits_down = sum(1 for e in evs if e["z"] < 0 and e["next_ret"] > 0)
    ups = [e for e in evs if e["z"] > 0]
    downs = [e for e in evs if e["z"] < 0]
    return {
        "ticker": ticker,
        "n_events": len(evs),
        "n_up_overshoot": len(ups),
        "n_down_overshoot": len(downs),
        "up_fade_hit_rate": round(hits_up / len(ups), 3) if ups else None,
        "down_fade_hit_rate": round(hits_down / len(downs), 3) if downs else None,
        "mean_next_after_up": round(
            sum(e["next_ret"] for e in ups) / len(ups), 3) if ups else None,
        "mean_next_after_down": round(
            sum(e["next_ret"] for e in downs) / len(downs), 3) if downs else None,
    }


def pair_trade_sim(
    events: list[dict],
    long_ticker: str,
    short_ticker: str,
    sector_of: dict[str, str],
    min_z: float = 3.0,
) -> dict:
    """Simulate: on any day `long_ticker` is DOWN-overshoot AND `short_ticker`
    is UP-overshoot, enter long/short pair. PnL = long_next − short_next.
    """
    by_date = {}
    for e in events:
        if abs(e["z"]) < min_z:
            continue
        by_date.setdefault(e["date"], {})[e["ticker"]] = e
    trades = []
    for dt, tickers in by_date.items():
        long_ev = tickers.get(long_ticker)
        short_ev = tickers.get(short_ticker)
        if not long_ev or not short_ev:
            continue
        if long_ev["z"] < 0 and short_ev["z"] > 0:  # perfect symmetric setup
            pnl = long_ev["next_ret"] - short_ev["next_ret"]
            trades.append({"date": dt, "pnl_pct": round(pnl, 3)})
    if not trades:
        return {"pair": f"LONG {long_ticker} / SHORT {short_ticker}",
                "n_trades": 0}
    pnls = [t["pnl_pct"] for t in trades]
    wins = sum(1 for p in pnls if p > 0)
    return {
        "pair": f"LONG {long_ticker} / SHORT {short_ticker}",
        "n_trades": len(trades),
        "hit_rate": round(wins / len(trades), 3),
        "mean_pnl_pct": round(sum(pnls) / len(pnls), 3),
        "median_pnl_pct": round(sorted(pnls)[len(pnls) // 2], 3),
        "worst_pct": round(min(pnls), 3),
        "best_pct": round(max(pnls), 3),
        "last_5_trades": trades[-5:],
    }


def sector_pair_basket(
    events: list[dict],
    sector_of: dict[str, str],
    long_sector: str,
    short_sector: str,
    min_z: float = 3.0,
) -> dict:
    """On any day when ≥1 stock in long_sector shows DOWN-overshoot AND
    ≥1 stock in short_sector shows UP-overshoot, trade the sector-basket
    pair: equal-weight long the down-overshoots, short the up-overshoots.
    """
    by_date = {}
    for e in events:
        if abs(e["z"]) < min_z:
            continue
        sec = sector_of.get(e["ticker"], "Unmapped")
        by_date.setdefault(e["date"], []).append({**e, "sector": sec})
    trades = []
    for dt, evs in by_date.items():
        longs = [e for e in evs if e["sector"] == long_sector and e["z"] < 0]
        shorts = [e for e in evs if e["sector"] == short_sector and e["z"] > 0]
        if not longs or not shorts:
            continue
        long_next = sum(e["next_ret"] for e in longs) / len(longs)
        short_next = sum(e["next_ret"] for e in shorts) / len(shorts)
        pnl = long_next - short_next
        trades.append({
            "date": dt,
            "n_long": len(longs), "n_short": len(shorts),
            "pnl_pct": round(pnl, 3),
            "long_tickers": [e["ticker"] for e in longs],
            "short_tickers": [e["ticker"] for e in shorts],
        })
    if not trades:
        return {"basket": f"LONG {long_sector} / SHORT {short_sector}", "n_trades": 0}
    pnls = [t["pnl_pct"] for t in trades]
    wins = sum(1 for p in pnls if p > 0)
    return {
        "basket": f"LONG {long_sector} / SHORT {short_sector}",
        "min_z": min_z,
        "n_trades": len(trades),
        "hit_rate": round(wins / len(trades), 3),
        "mean_pnl_pct": round(sum(pnls) / len(pnls), 3),
        "median_pnl_pct": round(sorted(pnls)[len(pnls) // 2], 3),
        "worst_pct": round(min(pnls), 3),
        "best_pct": round(max(pnls), 3),
        "last_5_trades": trades[-5:],
    }


def main() -> int:
    sector_of = load_sector_map()
    closes = load_price_panel(sector_of.keys())
    print(f"panel: {closes.shape[0]} days x {closes.shape[1]} tickers")
    rets, resids, zs = compute_residuals(closes, sector_of)
    events = classify_events(rets, resids, zs)
    print(f"events (>=2σ, next-day valid): {len(events)}")

    print("\n=== TICKER-LEVEL HISTORIES (|z|>=3) ===")
    for t in ["TECHM", "INFY", "WIPRO", "TCS", "DRREDDY", "CIPLA",
              "LAURUSLABS", "DIVISLAB", "POLICYBZR", "TORNTPOWER", "DEFIANT"]:
        row = per_ticker_history(events, t, min_z=3.0)
        if row:
            print(f"  {t:<11} n={row['n_events']:>3} "
                  f"up={row['n_up_overshoot']:>3} down={row['n_down_overshoot']:>3} "
                  f"fade_up_hit={row['up_fade_hit_rate']} "
                  f"fade_down_hit={row['down_fade_hit_rate']} "
                  f"mean_next_up={row['mean_next_after_up']} "
                  f"mean_next_down={row['mean_next_after_down']}")
        else:
            print(f"  {t:<11} (no events)")

    print("\n=== SECTOR BASKET PAIR TRADES (|z|>=3) ===")
    for long_sec, short_sec in [
        ("Pharma", "IT"),        # user's thesis
        ("IT", "Pharma"),        # reverse — as control
        ("Pharma", "Banks"),     # pharma reversion vs banks UP
        ("Pharma", "NBFC"),
        ("IT", "Banks"),
        ("Pharma", "Capital_Goods"),
        ("Pharma", "Utilities"),
    ]:
        result = sector_pair_basket(events, sector_of, long_sec, short_sec, min_z=3.0)
        print(f"\n{result.get('basket')}:")
        for k, v in result.items():
            if k in ("basket", "last_5_trades"):
                continue
            print(f"  {k}: {v}")

    print("\n=== SPECIFIC PAIR: LONG TECHM / SHORT POLICYBZR (|z|>=3) ===")
    p = pair_trade_sim(events, "TECHM", "POLICYBZR", sector_of, min_z=3.0)
    print(json.dumps(p, indent=2, default=str))

    print("\n=== ALL IT STOCKS: UP 3-4σ → next-day returns ===")
    it_tickers = [t for t, s in sector_of.items() if s == "IT"]
    it_up = [e for e in events
             if e["ticker"] in it_tickers and e["z"] >= 3.0 and e["z"] < 4.0]
    if it_up:
        print(f"n={len(it_up)}, "
              f"mean_next_ret={sum(e['next_ret'] for e in it_up)/len(it_up):.3f}%, "
              f"hit_down={sum(1 for e in it_up if e['next_ret']<0)/len(it_up):.3f}")

    print("\n=== ALL PHARMA STOCKS: DOWN 3-4σ → next-day returns ===")
    ph_tickers = [t for t, s in sector_of.items() if s == "Pharma"]
    ph_down = [e for e in events
               if e["ticker"] in ph_tickers and e["z"] <= -3.0 and e["z"] > -4.0]
    if ph_down:
        print(f"n={len(ph_down)}, "
              f"mean_next_ret={sum(e['next_ret'] for e in ph_down)/len(ph_down):.3f}%, "
              f"hit_up={sum(1 for e in ph_down if e['next_ret']>0)/len(ph_down):.3f}")

    # RECENT regime: 2025-01 onward (post-US election)
    print("\n=== RECENT (2025+) — last fold only ===")
    recent = [e for e in events if e["date"] >= "2025-01-01"]
    print(f"events in recent fold: {len(recent)}")
    for t in ["TECHM", "INFY", "POLICYBZR", "DRREDDY", "CIPLA"]:
        row = per_ticker_history(recent, t, min_z=3.0)
        if row:
            print(f"  {t:<11} {row}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
