"""
Anka Research — Pinning Strategy Forward Tester
Paper-trades the pinning straddle strategy on expiry days.
Logs every signal, entry, intraday path, exit, and costs.

Runs automatically on Thursdays. Does NOT send to subscribers yet.
Results accumulate in data/forward_test_pinning.json.
After 15+ trades, review to decide if strategy goes live.

Failure thresholds (auto-pause):
  - 3 consecutive losses
  - Single loss > 2%
  - Win rate < 50% over rolling 10
"""

import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

log = logging.getLogger("anka.pinning_fwd_test")

IST = timezone(timedelta(hours=5, minutes=30))
DATA_DIR = Path(__file__).parent / "data"
FWD_TEST_FILE = DATA_DIR / "forward_test_pinning.json"

# Transaction cost model (per lot)
COSTS = {
    "brokerage_per_order": 40,   # ₹40 per order, 4 orders per straddle
    "stt_pct": 0.05,             # STT on sell-side
    "exchange_pct": 0.053,       # Exchange charges
    "slippage_pts": 3,           # Per leg, both entry and exit
    "lot_size_nifty": 75,
    "lot_size_banknifty": 30,
}


def load_forward_tests() -> list:
    if FWD_TEST_FILE.exists():
        return json.loads(FWD_TEST_FILE.read_text(encoding="utf-8"))
    return []


def save_forward_tests(tests: list):
    FWD_TEST_FILE.write_text(json.dumps(tests, indent=2), encoding="utf-8")


def check_failure_thresholds(tests: list) -> dict:
    """Check if strategy should be paused."""
    if len(tests) < 3:
        return {"pause": False, "reason": ""}

    recent = tests[-10:]
    consecutive_losses = 0
    for t in reversed(tests):
        if t.get("net_pnl_pct", 0) < 0:
            consecutive_losses += 1
        else:
            break

    win_rate = sum(1 for t in recent if t.get("net_pnl_pct", 0) > 0) / len(recent) * 100
    max_loss = min(t.get("net_pnl_pct", 0) for t in tests)

    pause = False
    reasons = []

    if consecutive_losses >= 3:
        pause = True
        reasons.append(f"3+ consecutive losses ({consecutive_losses})")
    if max_loss < -2.0:
        pause = True
        reasons.append(f"Single loss exceeded 2% ({max_loss:.2f}%)")
    if len(recent) >= 10 and win_rate < 50:
        pause = True
        reasons.append(f"Win rate below 50% ({win_rate:.0f}% over last 10)")

    return {
        "pause": pause,
        "reason": "; ".join(reasons) if reasons else "OK",
        "consecutive_losses": consecutive_losses,
        "rolling_win_rate": round(win_rate, 1),
        "max_single_loss": round(max_loss, 2),
        "total_trades": len(tests),
    }


def estimate_costs(premium_pts: float, index: str = "NIFTY") -> dict:
    """Estimate transaction costs for a straddle trade."""
    lot = COSTS["lot_size_nifty"] if "NIFTY" == index else COSTS["lot_size_banknifty"]

    brokerage = COSTS["brokerage_per_order"] * 4  # 4 orders
    stt = premium_pts * lot * COSTS["stt_pct"] / 100
    exchange = premium_pts * lot * COSTS["exchange_pct"] / 100
    slippage = COSTS["slippage_pts"] * 4 * lot  # 4 legs, both sides

    total = brokerage + stt + exchange + slippage
    total_pct = total / (premium_pts * lot) * 100 if premium_pts > 0 else 0

    return {
        "brokerage": round(brokerage),
        "stt": round(stt),
        "exchange": round(exchange),
        "slippage": round(slippage),
        "total_inr": round(total),
        "total_pct": round(total_pct, 2),
    }


def log_trade_open(index: str, pin_strike: int, spot: float,
                   premium_pts: float, vix: float, gex: float = 0) -> dict:
    """Log a paper trade entry."""
    costs = estimate_costs(premium_pts, index)

    trade = {
        "date": datetime.now(IST).strftime("%Y-%m-%d"),
        "time_opened": datetime.now(IST).strftime("%H:%M"),
        "index": index,
        "pin_strike": pin_strike,
        "spot_at_entry": round(spot, 1),
        "premium_collected_pts": round(premium_pts, 1),
        "vix_at_entry": round(vix, 1),
        "gex_at_pin": round(gex),
        "costs": costs,
        "status": "OPEN",
        "max_adverse_pts": 0,
        "close_price": None,
        "close_distance_pts": None,
        "gross_pnl_pct": None,
        "net_pnl_pct": None,
    }

    tests = load_forward_tests()
    tests.append(trade)
    save_forward_tests(tests)

    log.info("FWD TEST OPEN: %s straddle at %d, premium %.1f, VIX %.1f",
             index, pin_strike, premium_pts, vix)
    return trade


def log_trade_close(close_price: float, max_adverse: float = 0):
    """Log paper trade close at end of day."""
    tests = load_forward_tests()
    if not tests:
        return

    trade = tests[-1]
    if trade["status"] != "OPEN":
        return

    pin = trade["pin_strike"]
    premium = trade["premium_collected_pts"]
    close_dist = abs(close_price - pin)

    gross_pnl_pts = premium - close_dist
    gross_pnl_pct = gross_pnl_pts / pin * 100
    net_pnl_pct = gross_pnl_pct - trade["costs"]["total_pct"]

    trade["status"] = "CLOSED"
    trade["time_closed"] = datetime.now(IST).strftime("%H:%M")
    trade["close_price"] = round(close_price, 1)
    trade["close_distance_pts"] = round(close_dist, 1)
    trade["max_adverse_pts"] = round(max_adverse, 1)
    trade["gross_pnl_pct"] = round(gross_pnl_pct, 3)
    trade["net_pnl_pct"] = round(net_pnl_pct, 3)
    trade["win"] = net_pnl_pct > 0

    save_forward_tests(tests)

    # Check thresholds
    status = check_failure_thresholds(tests)

    log.info("FWD TEST CLOSE: %s at %.1f, dist %.0f, gross %+.2f%%, net %+.2f%% | %s",
             trade["index"], close_price, close_dist,
             gross_pnl_pct, net_pnl_pct,
             "PAUSED" if status["pause"] else "OK")

    return trade, status


def get_forward_test_summary() -> str:
    """Get summary of forward testing results."""
    tests = load_forward_tests()
    closed = [t for t in tests if t["status"] == "CLOSED"]

    if not closed:
        return "No forward test trades completed yet."

    n = len(closed)
    wins = sum(1 for t in closed if t.get("win"))
    avg_gross = sum(t["gross_pnl_pct"] for t in closed) / n
    avg_net = sum(t["net_pnl_pct"] for t in closed) / n
    avg_cost = sum(t["costs"]["total_pct"] for t in closed) / n

    status = check_failure_thresholds(closed)

    lines = [
        f"Forward Test: {n} trades ({wins}W/{n - wins}L, {wins / n * 100:.0f}%)",
        f"Avg gross: {avg_gross:+.2f}% | Avg cost: -{avg_cost:.2f}% | Avg net: {avg_net:+.2f}%",
        f"Status: {'PAUSED — ' + status['reason'] if status['pause'] else 'ACTIVE'}",
    ]

    if n >= 15 and not status["pause"]:
        if avg_net > 0.3 and wins / n > 0.6:
            lines.append("✅ READY FOR SUBSCRIBER PROMOTION")
        else:
            lines.append("⚠️ Not yet meeting promotion criteria (need >60% win, >+0.3% net)")

    return "\n".join(lines)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    print(get_forward_test_summary())
    status = check_failure_thresholds(load_forward_tests())
    print(f"\nThreshold check: {json.dumps(status, indent=2)}")
