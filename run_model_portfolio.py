"""
OPUS ANKA — Model Portfolio Engine

Builds and maintains a live model portfolio based on:
1. Regime Engine (askanka.com) → sector direction
2. ANKA Trust Score → stock selection within sector
3. Intraday narrative shifts → position adjustment alerts

Three modes:
  python run_model_portfolio.py morning    # 4:30 AM — full rescore + portfolio rebalance
  python run_model_portfolio.py intraday   # Every 30 min — OI shifts, news, regime check
  python run_model_portfolio.py eod        # 4:30 PM — P&L, scorecard, next-day outlook

Output: model_portfolio.json + Telegram messages
"""

import json
import sys
import time
import os
import requests
from pathlib import Path
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / "config" / ".env")

from pipeline.retrieval.screener_client import ScreenerClient
from run_spread_ranker import fetch_stock_snapshot, score_for_long, score_for_short, parse_num

IST = timezone(timedelta(hours=5, minutes=30))
ARTIFACTS = Path(__file__).parent / "artifacts"
PORTFOLIO_FILE = ARTIFACTS / "model_portfolio.json"
UNIVERSE_FILE = Path(__file__).parent / "config" / "universe.json"


def load_universe() -> dict:
    return json.loads(UNIVERSE_FILE.read_text(encoding="utf-8"))


def load_portfolio() -> dict:
    if PORTFOLIO_FILE.exists():
        return json.loads(PORTFOLIO_FILE.read_text(encoding="utf-8"))
    return {"positions": [], "cash_pct": 100, "created": datetime.now(IST).isoformat()}


def save_portfolio(portfolio: dict):
    portfolio["updated_at"] = datetime.now(IST).isoformat()
    PORTFOLIO_FILE.write_text(json.dumps(portfolio, indent=2, default=str), encoding="utf-8")


# ── Morning Mode: Full Rescore + Rebalance ───────────────────────────

def morning_rebalance():
    """Run at 4:30 AM. Full Trust Score proxy scan, regime check, portfolio construction."""
    universe = load_universe()
    screener = ScreenerClient()
    now = datetime.now(IST)

    print(f"{'='*70}")
    print(f"  ANKA MODEL PORTFOLIO — Morning Rebalance")
    print(f"  {now.strftime('%B %d, %Y %H:%M IST')}")
    print(f"{'='*70}")

    # Get current regime from askanka.com data
    regime = _get_current_regime()
    print(f"\n  Current Regime: {regime}")

    # Score all stocks in universe
    from run_basket import fast_trust_proxy
    all_scores = {}
    total = sum(len(s["stocks"]) for s in universe["sectors"].values())
    done = 0

    for sector_name, sector in universe["sectors"].items():
        for sym in sector["stocks"]:
            done += 1
            print(f"  [{done}/{total}] {sym}...", end=" ", flush=True)
            snap = fetch_stock_snapshot(sym, screener)
            if not snap or not snap.get("price"):
                print("SKIP")
                continue
            trust = fast_trust_proxy(snap)
            snap.update(trust)
            snap["sector"] = sector_name
            snap["direction"] = sector["direction"]
            snap["thesis"] = sector["thesis"]
            all_scores[sym] = snap
            print(f"{trust['grade']} ({trust['score']})")
            time.sleep(0.3)

    # Build portfolio
    portfolio = _construct_portfolio(all_scores, regime, universe)
    save_portfolio(portfolio)

    # Print summary
    _print_portfolio(portfolio)

    # Send Telegram morning call
    _send_morning_telegram(portfolio, regime)

    return portfolio


def _get_current_regime() -> str:
    """Read current regime from askanka.com live data."""
    try:
        data = json.loads(Path("C:/Users/Claude_Anka/askanka.com/data/live_status.json").read_text())
        regime_raw = data.get("msi", {}).get("regime", "MACRO_NEUTRAL")
        score = data.get("msi", {}).get("score", 50)
        # Map old MSI regimes to URE zones
        if score < 20:
            return "RISK-ON"
        elif score < 35:
            return "RISK-ON"
        elif score < 65:
            return "NEUTRAL"
        elif score < 80:
            return "CAUTION"
        else:
            return "RISK-OFF"
    except Exception:
        return "NEUTRAL"


def _construct_portfolio(scores: dict, regime: str, universe: dict) -> dict:
    """Build model portfolio from scored stocks + regime."""

    # Regime determines max exposure and sector weights
    regime_config = {
        "RISK-OFF":  {"max_positions": 4, "long_pct": 20, "short_pct": 30, "cash_pct": 50},
        "CAUTION":   {"max_positions": 6, "long_pct": 30, "short_pct": 30, "cash_pct": 40},
        "NEUTRAL":   {"max_positions": 8, "long_pct": 40, "short_pct": 30, "cash_pct": 30},
        "RISK-ON":   {"max_positions": 10, "long_pct": 55, "short_pct": 25, "cash_pct": 20},
        "EUPHORIA":  {"max_positions": 10, "long_pct": 65, "short_pct": 20, "cash_pct": 15},
    }
    config = regime_config.get(regime, regime_config["NEUTRAL"])

    # Rank all stocks
    ranked = sorted(scores.values(), key=lambda x: x.get("score", 0), reverse=True)

    # Longs: highest trust scores in long-biased sectors
    long_sectors = {"defence", "upstream_energy", "infra_capital_goods", "pharma"}
    if regime in ("RISK-ON", "EUPHORIA"):
        long_sectors.update({"auto", "metals", "banks_private"})

    longs = [s for s in ranked if s["sector"] in long_sectors and s.get("score", 0) >= 65]
    max_longs = config["max_positions"] // 2 + 1
    longs = longs[:max_longs]

    # Shorts: lowest trust scores in short-biased or overvalued sectors
    short_sectors = {"omcs"}
    if regime in ("RISK-OFF", "CAUTION"):
        short_sectors.update({"banks_private", "auto", "metals"})

    # Also short any stock with Trust D or F regardless of sector
    shorts = [s for s in ranked if (s["sector"] in short_sectors and s.get("score", 0) < 70)]
    shorts += [s for s in ranked if s.get("score", 0) < 40 and s["symbol"] not in [l["symbol"] for l in longs]]
    # Deduplicate
    seen = set()
    unique_shorts = []
    for s in shorts:
        if s["symbol"] not in seen:
            seen.add(s["symbol"])
            unique_shorts.append(s)
    max_shorts = config["max_positions"] // 2
    shorts = unique_shorts[:max_shorts]

    # Gate: only allow stocks with deep Trust Score into final portfolio
    from pipeline.risk_manager import has_deep_trust_score, get_stop_loss, get_position_size

    longs_verified = [s for s in longs if has_deep_trust_score(s["symbol"])]
    longs_unverified = [s for s in longs if not has_deep_trust_score(s["symbol"])]
    shorts_verified = [s for s in shorts if has_deep_trust_score(s["symbol"])]
    shorts_unverified = [s for s in shorts if not has_deep_trust_score(s["symbol"])]

    if longs_unverified:
        print(f"\n  [!] BLOCKED from portfolio (no deep Trust Score):")
        for s in longs_unverified:
            print(f"      {s['symbol']} — run: python run_research.py {s['symbol']} && python run_trust_score.py {s['symbol']}")

    longs = longs_verified
    shorts = shorts_verified

    # Size by conviction (now uses risk manager)
    total_long_conviction = sum(s.get("score", 50) for s in longs) or 1
    total_short_conviction = sum(100 - s.get("score", 50) for s in shorts) or 1

    positions = []
    for s in longs:
        grade = s.get("grade", "B")
        price = s.get("price", 0)
        weight = min(
            round(s.get("score", 50) / total_long_conviction * config["long_pct"], 1),
            get_position_size(grade, regime),
        )
        stop = get_stop_loss(grade, "LONG", price) if price else {}
        positions.append({
            "symbol": s["symbol"], "side": "LONG", "sector": s["sector"],
            "trust_grade": grade, "trust_score": s.get("score", 0),
            "price": price, "pe": s.get("pe"), "roe": s.get("roe"),
            "weight_pct": weight,
            "stop_pct": stop.get("stop_pct", 5),
            "stop_price": stop.get("stop_price", 0),
            "entry_price": price,
            "thesis": s.get("thesis", ""),
        })

    for s in shorts:
        grade = s.get("grade", "B")
        price = s.get("price", 0)
        inverse_score = 100 - s.get("score", 50)
        weight = min(
            round(inverse_score / total_short_conviction * config["short_pct"], 1),
            get_position_size(grade, regime),
        )
        stop = get_stop_loss(grade, "SHORT", price) if price else {}
        positions.append({
            "symbol": s["symbol"], "side": "SHORT", "sector": s["sector"],
            "trust_grade": grade, "trust_score": s.get("score", 0),
            "price": price, "pe": s.get("pe"), "roe": s.get("roe"),
            "weight_pct": weight,
            "stop_pct": stop.get("stop_pct", 5),
            "stop_price": stop.get("stop_price", 0),
            "entry_price": price,
            "thesis": s.get("thesis", ""),
        })

    return {
        "regime": regime,
        "regime_config": config,
        "positions": positions,
        "total_positions": len(positions),
        "long_count": len(longs),
        "short_count": len(shorts),
        "cash_pct": config["cash_pct"],
        "generated_at": datetime.now(IST).isoformat(),
    }


def _print_portfolio(p: dict):
    print(f"\n{'='*70}")
    print(f"  ANKA MODEL PORTFOLIO — {p['regime']}")
    print(f"  {p['long_count']} longs | {p['short_count']} shorts | {p['cash_pct']}% cash")
    print(f"{'='*70}")

    longs = [pos for pos in p["positions"] if pos["side"] == "LONG"]
    shorts = [pos for pos in p["positions"] if pos["side"] == "SHORT"]

    if longs:
        print(f"\n  LONG:")
        print(f"  {'Symbol':12s} {'Trust':6s} {'Sector':18s} {'Price':>8s} {'PE':>6s} {'Wt%':>6s}")
        print(f"  {'─'*58}")
        for pos in sorted(longs, key=lambda x: x["weight_pct"], reverse=True):
            print(f"  {pos['symbol']:12s} {pos['trust_grade']:>4s}   {pos['sector']:18s} {(pos.get('price') or 0):>8,.0f} {(pos.get('pe') or 0):>6.1f} {pos['weight_pct']:>5.1f}%")

    if shorts:
        print(f"\n  SHORT:")
        print(f"  {'Symbol':12s} {'Trust':6s} {'Sector':18s} {'Price':>8s} {'PE':>6s} {'Wt%':>6s}")
        print(f"  {'─'*58}")
        for pos in sorted(shorts, key=lambda x: x["weight_pct"], reverse=True):
            print(f"  {pos['symbol']:12s} {pos['trust_grade']:>4s}   {pos['sector']:18s} {(pos.get('price') or 0):>8,.0f} {(pos.get('pe') or 0):>6.1f} {pos['weight_pct']:>5.1f}%")

    print(f"\n  CASH: {p['cash_pct']}%")


# ── Intraday Mode: Narrative Monitor ─────────────────────────────────

def intraday_monitor():
    """Run every 30 min during market hours. Check for narrative shifts."""
    now = datetime.now(IST)
    print(f"\n  INTRADAY MONITOR — {now.strftime('%H:%M IST')}")

    portfolio = load_portfolio()
    if not portfolio.get("positions"):
        print("  No active portfolio. Run morning mode first.")
        return

    alerts = []

    # 1. Check regime shift
    current_regime = _get_current_regime()
    portfolio_regime = portfolio.get("regime", "NEUTRAL")
    if current_regime != portfolio_regime:
        alert = f"REGIME SHIFT: {portfolio_regime} -> {current_regime}. Portfolio was built for {portfolio_regime}."
        alerts.append({"type": "REGIME_SHIFT", "message": alert, "severity": "HIGH"})
        print(f"  [!] {alert}")

    # 2. Check stop-losses
    stop_alerts = _check_stops(portfolio)
    alerts.extend(stop_alerts)

    # 3. Check re-entry opportunities for stopped-out positions
    reentry_alerts = _check_reentries(portfolio, current_regime)
    alerts.extend(reentry_alerts)

    # 4. Check OI shifts for portfolio stocks
    oi_alerts = _check_oi_shifts(portfolio)
    alerts.extend(oi_alerts)

    # 5. Check for major price moves in portfolio stocks
    price_alerts = _check_price_moves(portfolio)
    alerts.extend(price_alerts)

    # 4. Check VIX spike
    vix_alert = _check_vix()
    if vix_alert:
        alerts.append(vix_alert)

    if alerts:
        _send_intraday_telegram(alerts, portfolio)
        # Save alerts to portfolio
        portfolio.setdefault("intraday_alerts", []).extend([
            {**a, "time": now.isoformat()} for a in alerts
        ])
        save_portfolio(portfolio)
    else:
        print("  No alerts. Positions holding.")

    return alerts


def _check_stops(portfolio: dict) -> list:
    """Check if any position has hit its stop-loss."""
    from pipeline.risk_manager import check_stop_hit
    alerts = []
    screener = ScreenerClient()

    for pos in portfolio.get("positions", []):
        if pos.get("status") == "stopped_out":
            continue
        sym = pos["symbol"]
        snap = fetch_stock_snapshot(sym, screener)
        if not snap or not snap.get("price"):
            continue

        result = check_stop_hit(pos, snap["price"])
        if result:
            alerts.append(result)
            pos["status"] = "stopped_out"
            pos["stopped_at"] = datetime.now(IST).isoformat()
            pos["stopped_price"] = snap["price"]
            print(f"  [STOP] {result['action']}")

    return alerts


def _check_reentries(portfolio: dict, current_regime: str) -> list:
    """Check if any stopped-out positions are eligible for re-entry."""
    from pipeline.risk_manager import check_reentry_eligible
    alerts = []
    screener = ScreenerClient()

    for pos in portfolio.get("positions", []):
        if pos.get("status") != "stopped_out":
            continue

        sym = pos["symbol"]
        stopped_at = pos.get("stopped_at", "")
        if not stopped_at:
            continue

        # Calculate days since stop
        try:
            stop_date = datetime.fromisoformat(stopped_at).date()
            days_since = (datetime.now(IST).date() - stop_date).days
        except Exception:
            continue

        snap = fetch_stock_snapshot(sym, screener)
        if not snap or not snap.get("price"):
            continue

        result = check_reentry_eligible(pos, snap["price"], current_regime, days_since)
        if result:
            alerts.append(result)
            print(f"  [RE-ENTRY] {result['action']}")

    return alerts


def _check_oi_shifts(portfolio: dict) -> list:
    """Check for significant OI changes in portfolio stocks."""
    alerts = []
    try:
        from pipeline.retrieval.nse_client import NSEClient
        nse = NSEClient()

        for pos in portfolio.get("positions", []):
            sym = pos["symbol"]
            side = pos["side"]
            # Check if there's unusual OI buildup against our position
            try:
                data = nse._get(f"/api/option-chain-equities?symbol={sym}")
                if data and "records" in data:
                    total_ce_oi = sum(r.get("CE", {}).get("openInterest", 0) for r in data["records"].get("data", []) if "CE" in r)
                    total_pe_oi = sum(r.get("PE", {}).get("openInterest", 0) for r in data["records"].get("data", []) if "PE" in r)
                    pcr = total_pe_oi / total_ce_oi if total_ce_oi > 0 else 1.0

                    if side == "LONG" and pcr < 0.7:
                        alerts.append({
                            "type": "OI_BEARISH",
                            "symbol": sym,
                            "message": f"{sym}: PCR {pcr:.2f} — bearish OI buildup against our LONG. Watch for breakdown.",
                            "severity": "MEDIUM",
                        })
                    elif side == "SHORT" and pcr > 1.5:
                        alerts.append({
                            "type": "OI_BULLISH",
                            "symbol": sym,
                            "message": f"{sym}: PCR {pcr:.2f} — bullish OI buildup against our SHORT. Watch for squeeze.",
                            "severity": "MEDIUM",
                        })
                time.sleep(0.5)
            except Exception:
                pass
    except ImportError:
        pass
    return alerts


def _check_price_moves(portfolio: dict) -> list:
    """Check for significant intraday price moves (>3% from entry)."""
    alerts = []
    screener = ScreenerClient()

    for pos in portfolio.get("positions", []):
        sym = pos["symbol"]
        entry_price = pos.get("price")
        if not entry_price:
            continue

        snap = fetch_stock_snapshot(sym, screener)
        if not snap or not snap.get("price"):
            continue

        current = snap["price"]
        move_pct = (current / entry_price - 1) * 100

        if pos["side"] == "LONG" and move_pct < -3:
            alerts.append({
                "type": "PRICE_DROP",
                "symbol": sym,
                "message": f"{sym} LONG down {move_pct:.1f}% from portfolio entry. Review stop.",
                "severity": "HIGH" if move_pct < -5 else "MEDIUM",
            })
        elif pos["side"] == "SHORT" and move_pct > 3:
            alerts.append({
                "type": "PRICE_SPIKE",
                "symbol": sym,
                "message": f"{sym} SHORT up {move_pct:.1f}% against us. Review cover.",
                "severity": "HIGH" if move_pct > 5 else "MEDIUM",
            })

    return alerts


def _check_vix() -> dict | None:
    """Check for VIX spike."""
    try:
        data = json.loads(Path("C:/Users/Claude_Anka/askanka.com/data/live_status.json").read_text())
        score = data.get("msi", {}).get("score", 50)
        if score > 75:
            return {
                "type": "VIX_SPIKE",
                "message": f"Regime score {score}/100 — HIGH STRESS. Consider reducing all positions.",
                "severity": "HIGH",
            }
    except Exception:
        pass
    return None


# ── Telegram Integration ─────────────────────────────────────────────

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")


def _send_telegram(message: str):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print(f"  [Telegram] {message[:100]}...")
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"},
            timeout=10,
        )
    except Exception as e:
        print(f"  Telegram failed: {e}")


def _send_morning_telegram(portfolio: dict, regime: str):
    longs = [p for p in portfolio["positions"] if p["side"] == "LONG"]
    shorts = [p for p in portfolio["positions"] if p["side"] == "SHORT"]

    msg = f"*ANKA Model Portfolio* — {datetime.now(IST).strftime('%d %b %Y')}\n"
    msg += f"Regime: *{regime}* | {portfolio['long_count']}L / {portfolio['short_count']}S / {portfolio['cash_pct']}% cash\n\n"

    if longs:
        msg += "*LONG:*\n"
        for p in sorted(longs, key=lambda x: x["weight_pct"], reverse=True):
            msg += f"  {p['symbol']} ({p['trust_grade']}) {p['weight_pct']}% @ Rs {(p.get('price') or 0):,.0f}\n"

    if shorts:
        msg += "\n*SHORT:*\n"
        for p in sorted(shorts, key=lambda x: x["weight_pct"], reverse=True):
            msg += f"  {p['symbol']} ({p['trust_grade']}) {p['weight_pct']}% @ Rs {(p.get('price') or 0):,.0f}\n"

    msg += f"\n_Trust Score based on annual report forensics_"
    _send_telegram(msg)


def _send_intraday_telegram(alerts: list, portfolio: dict):
    if not alerts:
        return
    msg = f"*ANKA ALERT* — {datetime.now(IST).strftime('%H:%M IST')}\n\n"
    for a in alerts:
        icon = "🔴" if a["severity"] == "HIGH" else "🟡"
        msg += f"{icon} {a['message']}\n"
    _send_telegram(msg)


# ── EOD Mode ─────────────────────────────────────────────────────────

def eod_review():
    """Run at 4:30 PM. Score the day, update P&L, generate next-day outlook."""
    portfolio = load_portfolio()
    if not portfolio.get("positions"):
        print("  No active portfolio.")
        return

    print(f"\n{'='*70}")
    print(f"  ANKA EOD REVIEW — {datetime.now(IST).strftime('%B %d, %Y')}")
    print(f"{'='*70}")

    screener = ScreenerClient()
    total_pnl = 0
    position_count = 0

    for pos in portfolio["positions"]:
        sym = pos["symbol"]
        entry = pos.get("price", 0)
        if not entry:
            continue

        snap = fetch_stock_snapshot(sym, screener)
        current = snap.get("price", entry) if snap else entry
        pnl = (current / entry - 1) * 100 if pos["side"] == "LONG" else (1 - current / entry) * 100

        pos["current_price"] = current
        pos["pnl_pct"] = round(pnl, 2)
        total_pnl += pnl * pos.get("weight_pct", 0) / 100
        position_count += 1

        icon = "+" if pnl > 0 else ""
        print(f"  {pos['side']:5s} {sym:12s} Entry: {entry:>8,.0f} Current: {current:>8,.0f} P&L: {icon}{pnl:.2f}%")

    portfolio["eod_pnl_pct"] = round(total_pnl, 2)
    portfolio["eod_date"] = datetime.now(IST).strftime("%Y-%m-%d")
    save_portfolio(portfolio)

    print(f"\n  Portfolio P&L: {'+' if total_pnl > 0 else ''}{total_pnl:.2f}%")

    # Telegram EOD
    msg = f"*ANKA EOD* — {datetime.now(IST).strftime('%d %b')}\n"
    msg += f"Portfolio: {'+' if total_pnl > 0 else ''}{total_pnl:.2f}%\n\n"
    for pos in sorted(portfolio["positions"], key=lambda x: abs(x.get("pnl_pct", 0)), reverse=True):
        icon = "✅" if pos.get("pnl_pct", 0) > 0 else "❌"
        msg += f"{icon} {pos['side']} {pos['symbol']} {pos.get('pnl_pct', 0):+.1f}%\n"
    _send_telegram(msg)


# ── Main ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "morning"

    if mode == "morning":
        morning_rebalance()
    elif mode == "intraday":
        intraday_monitor()
    elif mode == "eod":
        eod_review()
    else:
        print(f"Unknown mode: {mode}. Use: morning | intraday | eod")
