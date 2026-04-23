"""Per-ticker fade-edge scan across the full 211-ticker universe.

For each ticker, compute historical fade-edge stats at |z|>=2 and |z|>=3:
  * fade-UP: short after UP-overshoot, edge = -mean(next_ret)
  * fade-DOWN: long after DOWN-overshoot, edge = +mean(next_ret)
Hit rate = fraction where next-day return moves in the fade direction.
Random-null p-value per direction via 500 permutations of (event -> next_ret)
drawn from the same ticker's return distribution.

Then intersect with today's live correlation_breaks.json and print a
ranked "today's actionable" table: for each live break, does the
ticker have historical edge in the required fade direction?

Output:
  * stdout ranked table
  * pipeline/autoresearch/results/per_ticker_fade_<stamp>.json
"""
from __future__ import annotations

import json
import random
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from pipeline.autoresearch.overshoot_reversion_backtest import (
    classify_events,
    compute_residuals,
    load_price_panel,
    load_sector_map,
)

_REPO = Path(__file__).resolve().parents[2]
_RESULTS_DIR = _REPO / "pipeline" / "autoresearch" / "results"
_BREAKS_PATH = _REPO / "pipeline" / "data" / "correlation_breaks.json"


def per_ticker_fade_stats(
    events: list[dict],
    ticker_returns: dict[str, list[float]],
    min_z: float,
    n_shuffles: int = 1000,
    seed: int = 42,
) -> list[dict]:
    """One row per (ticker, direction) with hit rate, mean edge, and null p-value.

    Null hypothesis: the mean next-day return on overshoot days is drawn from the
    ticker's unconditional daily-return distribution. We draw n random days from
    that distribution per shuffle and check how often the bootstrapped edge
    meets/exceeds the observed edge. One-sided p-value.
    """
    rng = random.Random(seed)
    by_ticker = defaultdict(list)
    for e in events:
        if abs(e["z"]) >= min_z:
            by_ticker[e["ticker"]].append(e)

    rows = []
    for ticker, evs in by_ticker.items():
        ups = [e for e in evs if e["z"] > 0]
        downs = [e for e in evs if e["z"] < 0]
        unconditional = ticker_returns.get(ticker, [])
        if len(unconditional) < 100:
            continue  # too little price history for a meaningful null

        for direction, subset in [("UP", ups), ("DOWN", downs)]:
            if len(subset) < 5:
                continue
            next_rets = [e["next_ret"] for e in subset]
            n = len(subset)
            mean_next = sum(next_rets) / n
            if direction == "UP":
                hits = sum(1 for r in next_rets if r < 0)
                edge = -mean_next  # positive edge = SHORT next day pays
            else:
                hits = sum(1 for r in next_rets if r > 0)
                edge = mean_next   # positive edge = LONG next day pays
            hit_rate = hits / n

            # Bootstrap null from unconditional return distribution
            exceed = 0
            for _ in range(n_shuffles):
                sample = [unconditional[rng.randrange(len(unconditional))]
                          for _ in range(n)]
                boot_mean = sum(sample) / n
                boot_edge = -boot_mean if direction == "UP" else boot_mean
                if boot_edge >= edge:
                    exceed += 1
            p_val = exceed / n_shuffles

            rows.append({
                "ticker": ticker,
                "direction": direction,
                "n_events": n,
                "hit_rate": round(hit_rate, 3),
                "mean_next_pct": round(mean_next, 3),
                "edge_pct": round(edge, 3),
                "p_value": round(p_val, 4),
                "min_z": min_z,
            })
    return rows


def _today_breaks() -> list[dict]:
    if not _BREAKS_PATH.exists():
        return []
    try:
        d = json.load(open(_BREAKS_PATH, encoding="utf-8"))
    except Exception:
        return []
    return d.get("breaks", []) if isinstance(d, dict) else d


def intersect_with_today(
    ranked: list[dict],
    today_breaks: list[dict],
    sector_of: dict[str, str],
) -> list[dict]:
    """For each live break today with |z|>=3, attach the matching historical
    (ticker, direction) row so we can see what the 5-yr data says about it.
    """
    # index historicals by (ticker, direction)
    hist_idx = {(r["ticker"], r["direction"]): r for r in ranked}
    out = []
    for b in today_breaks:
        z = b.get("z_score") or 0
        if abs(z) < 3.0:
            continue
        ticker = b.get("symbol")
        direction = "UP" if z > 0 else "DOWN"
        # fade direction is OPPOSITE the overshoot — but per-ticker stats
        # use direction of the OVERSHOOT (UP means fade-UP i.e. SHORT).
        row = hist_idx.get((ticker, direction))
        actionable_trade = "SHORT" if direction == "UP" else "LONG"
        out.append({
            "symbol": ticker,
            "sector": sector_of.get(ticker, "Unmapped"),
            "today_z": round(z, 2),
            "today_return_pct": round(b.get("actual_return") or 0, 2),
            "classification": b.get("classification"),
            "engine_action": b.get("action"),
            "trade_under_fade": actionable_trade,
            "hist_n": row["n_events"] if row else None,
            "hist_hit_rate": row["hit_rate"] if row else None,
            "hist_edge_pct": row["edge_pct"] if row else None,
            "hist_p_value": row["p_value"] if row else None,
            "hist_verdict": _verdict(row),
        })
    # sort: best historical edge first among those with real data
    out.sort(key=lambda r: (
        0 if r["hist_edge_pct"] is None else -r["hist_edge_pct"],
    ))
    return out


def _verdict(row: dict | None) -> str:
    if row is None:
        return "NO_HISTORY"
    n = row["n_events"]
    p = row["p_value"]
    edge = row["edge_pct"]
    hit = row["hit_rate"]
    if n < 8:
        return "THIN_DATA"
    if edge <= 0:
        return "NO_EDGE"
    if p <= 0.05 and edge >= 0.2:
        return "STRONG"
    if p <= 0.15 and edge >= 0.1:
        return "MODEST"
    return "WEAK"


def main() -> int:
    print("loading sector map + price panel...", flush=True)
    sector_of = load_sector_map()
    closes = load_price_panel(sector_of.keys())
    rets, resids, zs = compute_residuals(closes, sector_of)
    events = classify_events(rets, resids, zs)
    print(f"panel: {closes.shape[0]} days x {closes.shape[1]} tickers; "
          f"events >=2sigma with next-day: {len(events)}")

    # Unconditional return distributions for the bootstrap null
    ticker_returns: dict[str, list[float]] = {}
    for col in rets.columns:
        vals = rets[col].dropna().tolist()
        ticker_returns[col] = vals

    for min_z in [3.0, 2.0]:
        print(f"\n=== PER-TICKER FADE STATS (|z|>={min_z}) ===")
        rows = per_ticker_fade_stats(events, ticker_returns, min_z=min_z, n_shuffles=1000)
        if not rows:
            print("  (none)")
            continue
        # show top 25 by edge with p<=0.1
        robust = [r for r in rows if r["n_events"] >= 8]
        ranked = sorted(robust, key=lambda r: -r["edge_pct"])
        print(f"{'ticker':<12}{'dir':<5}{'n':>4} {'hit%':>6} {'edge%':>7} {'p':>7}")
        for r in ranked[:25]:
            print(f"  {r['ticker']:<10}{r['direction']:<5}{r['n_events']:>4}"
                  f" {r['hit_rate']*100:>5.1f} {r['edge_pct']:>7.3f}"
                  f" {r['p_value']:>7.4f}")

        # persist full table for this min_z
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        out_path = _RESULTS_DIR / f"per_ticker_fade_z{int(min_z)}_{stamp}.json"
        _RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps({
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "min_z": min_z,
            "n_tickers_with_data": len({r["ticker"] for r in rows}),
            "rows": ranked,
        }, indent=2, default=str))
        print(f"  saved: {out_path.relative_to(_REPO)}")

    # intersect with TODAY
    print("\n=== TODAY'S BREAKS x HISTORICAL EDGE ===")
    rows_z3 = per_ticker_fade_stats(events, ticker_returns, min_z=3.0, n_shuffles=1000)
    today_breaks = _today_breaks()
    print(f"today's breaks (all): {len(today_breaks)}")
    cross = intersect_with_today(rows_z3, today_breaks, sector_of)
    print(f"live |z|>=3 breaks: {len(cross)}")
    hdr = (f"  {'sym':<11} {'sec':<14} {'z':>6} {'act%':>6} "
           f"{'trade':<6} {'n':>4} {'hit%':>6} {'edge%':>7} {'p':>7}  verdict")
    print(hdr)
    for c in cross:
        n = c["hist_n"]
        hit = c["hist_hit_rate"]
        edge = c["hist_edge_pct"]
        p = c["hist_p_value"]
        n_s = f"{n:>4}" if n is not None else "   -"
        hit_s = f"{hit*100:>5.1f}" if hit is not None else "    -"
        edge_s = f"{edge:>7.3f}" if edge is not None else "      -"
        p_s = f"{p:>7.4f}" if p is not None else "      -"
        print(f"  {c['symbol']:<11} {c['sector']:<14} "
              f"{c['today_z']:>6.2f} {c['today_return_pct']:>6.2f} "
              f"{c['trade_under_fade']:<6} {n_s} {hit_s} {edge_s} {p_s}  "
              f"{c['hist_verdict']}")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    out_cross = _RESULTS_DIR / f"today_fade_candidates_{stamp}.json"
    out_cross.write_text(json.dumps({
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "today_regime": "RISK-OFF",
        "rows": cross,
    }, indent=2, default=str))
    print(f"\nsaved: {out_cross.relative_to(_REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
