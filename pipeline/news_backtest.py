"""
Anka Research — Overnight News Backtest
Takes today's news events, looks up historical price reactions,
generates verdicts: NO_IMPACT / MODERATE / HIGH_IMPACT -> ADD / CUT / EXIT

Usage:
    python news_backtest.py                    # process today's events
    python news_backtest.py --date 2026-04-13  # process specific date
"""

import argparse
import json
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

_HERE = Path(__file__).parent
sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(_HERE / "lib"))

from config import NEWS_CATEGORIES

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("anka.news_backtest")

IST = timezone(timedelta(hours=5, minutes=30))
DATA_DIR = _HERE / "data"
FNO_HIST = DATA_DIR / "fno_historical"
EVENTS_TODAY = DATA_DIR / "news_events_today.json"
EVENTS_HISTORY = DATA_DIR / "news_events_history.json"
VERDICTS_FILE = DATA_DIR / "news_verdicts.json"


def load_stock_prices(symbol: str) -> pd.DataFrame | None:
    csv_path = FNO_HIST / f"{symbol}.csv"
    if not csv_path.exists():
        return None
    try:
        df = pd.read_csv(csv_path, index_col=0, parse_dates=True)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        return df
    except Exception:
        return None


def compute_forward_returns(df: pd.DataFrame, event_date: str) -> dict | None:
    try:
        event_dt = pd.Timestamp(event_date)
        future = df.index[df.index >= event_dt]
        if len(future) == 0:
            return None
        t0 = future[0]
        t0_loc = df.index.get_loc(t0)
        close_0 = df.iloc[t0_loc]["Close"]
        result = {"date": t0.strftime("%Y-%m-%d"), "close_0": float(close_0)}
        for days, label in [(1, "ret_1d"), (3, "ret_3d"), (5, "ret_5d")]:
            if t0_loc + days < len(df):
                close_n = df.iloc[t0_loc + days]["Close"]
                result[label] = round(float((close_n / close_0 - 1) * 100), 3)
            else:
                result[label] = None
        return result
    except Exception:
        return None


def lookup_historical_precedent(symbol: str, category: str, history: list[dict]) -> dict:
    past_events = [
        e for e in history
        if symbol in e.get("matched_stocks", [])
        and category in e.get("categories", [])
        and e.get("outcome")
    ]
    if len(past_events) < 2:
        return {"precedent_count": len(past_events), "verdict": "INSUFFICIENT_DATA"}
    returns_5d = [e["outcome"]["ret_5d"] for e in past_events
                  if e.get("outcome", {}).get("ret_5d") is not None]
    if not returns_5d:
        return {"precedent_count": len(past_events), "verdict": "INSUFFICIENT_DATA"}
    avg_5d = np.mean(returns_5d)
    hit_rate = len([r for r in returns_5d if r > 0]) / len(returns_5d)
    return {
        "precedent_count": len(past_events),
        "avg_5d_return": round(float(avg_5d), 3),
        "hit_rate": round(float(hit_rate), 3),
    }


def classify_verdict(event: dict, price_reaction: dict, precedent: dict) -> dict:
    ret_1d = price_reaction.get("ret_1d") if price_reaction else None
    avg_5d = precedent.get("avg_5d_return")
    hit_rate = precedent.get("hit_rate", 0)

    if ret_1d is not None and abs(ret_1d) > 3.0:
        impact = "HIGH_IMPACT"
    elif ret_1d is not None and abs(ret_1d) > 1.5:
        impact = "MODERATE"
    elif avg_5d is not None and abs(avg_5d) > 2.0 and hit_rate > 0.6:
        impact = "HIGH_IMPACT"
    elif avg_5d is not None and abs(avg_5d) > 1.0:
        impact = "MODERATE"
    else:
        impact = "NO_IMPACT"

    if impact == "HIGH_IMPACT":
        if (avg_5d or 0) > 0 or (ret_1d or 0) > 0:
            recommendation = "ADD"
            direction = "LONG"
        else:
            recommendation = "CUT"
            direction = "SHORT"
    elif impact == "MODERATE":
        recommendation = "MONITOR"
        direction = "LONG" if (avg_5d or ret_1d or 0) > 0 else "SHORT"
    else:
        recommendation = "NO_ACTION"
        direction = None

    category = event.get("categories", [""])[0] if event.get("categories") else ""
    shelf_cfg = NEWS_CATEGORIES.get(category, {})
    shelf_days = shelf_cfg.get("default_shelf_life_days", 3)

    if ret_1d is not None and avg_5d is not None and abs(ret_1d) > abs(avg_5d) * 0.7:
        shelf_life = "EXPIRED"
    elif ret_1d is not None and abs(ret_1d) < 0.5:
        shelf_life = "EMERGING"
    else:
        shelf_life = "ACTIVE"

    return {
        "impact": impact, "recommendation": recommendation,
        "direction": direction, "shelf_life": shelf_life,
        "shelf_days": shelf_days, "price_reaction_1d": ret_1d,
        "historical_avg_5d": avg_5d, "historical_hit_rate": hit_rate,
        "precedent_count": precedent.get("precedent_count", 0),
    }


def run_backtest(target_date: str = None):
    if target_date is None:
        target_date = datetime.now(IST).strftime("%Y-%m-%d")
    log.info(f"=== News Backtest for {target_date} ===")

    if not EVENTS_TODAY.exists():
        log.info("No events file found. Run news_intelligence.py first.")
        return
    today_data = json.loads(EVENTS_TODAY.read_text(encoding="utf-8"))
    events = today_data.get("events", [])
    log.info(f"Events to process: {len(events)}")

    history = []
    if EVENTS_HISTORY.exists():
        try:
            history = json.loads(EVENTS_HISTORY.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, KeyError):
            pass

    verdicts = []
    for event in events:
        stocks = event.get("matched_stocks", [])
        categories = event.get("categories", [])
        if not stocks:
            continue
        for symbol in stocks[:3]:
            df = load_stock_prices(symbol)
            price_reaction = compute_forward_returns(df, target_date) if df is not None else None
            category = categories[0] if categories else ""
            precedent = lookup_historical_precedent(symbol, category, history)
            verdict = classify_verdict(event, price_reaction, precedent)
            verdict["symbol"] = symbol
            verdict["event_title"] = event["title"][:100]
            verdict["event_date"] = target_date
            verdict["category"] = category
            verdicts.append(verdict)
            log.info(f"  {symbol}: {verdict['impact']} -> {verdict['recommendation']} "
                     f"(1d: {verdict['price_reaction_1d']}, hist: {verdict['historical_avg_5d']})")

    VERDICTS_FILE.write_text(json.dumps(verdicts, indent=2, ensure_ascii=False), encoding="utf-8")
    log.info(f"Saved {len(verdicts)} verdicts to {VERDICTS_FILE}")

    high = [v for v in verdicts if v["impact"] == "HIGH_IMPACT"]
    moderate = [v for v in verdicts if v["impact"] == "MODERATE"]
    adds = [v for v in verdicts if v["recommendation"] == "ADD"]
    cuts = [v for v in verdicts if v["recommendation"] == "CUT"]

    print(f"\n{'='*60}")
    print(f"  NEWS BACKTEST VERDICTS -- {target_date}")
    print(f"{'='*60}")
    print(f"  HIGH_IMPACT: {len(high)} | MODERATE: {len(moderate)} | NO_IMPACT: {len(verdicts) - len(high) - len(moderate)}")
    print(f"  ADD: {len(adds)} | CUT: {len(cuts)}")
    for v in high:
        print(f"\n  {v['recommendation']} {v['symbol']} ({v['direction']})")
        print(f"    Event: {v['event_title']}")
        print(f"    1d reaction: {v['price_reaction_1d']}% | Historical avg 5d: {v['historical_avg_5d']}%")
        print(f"    Shelf life: {v['shelf_life']} ({v['shelf_days']} days)")
    print(f"{'='*60}\n")
    return verdicts


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", type=str, default=None)
    args = parser.parse_args()
    run_backtest(target_date=args.date)
