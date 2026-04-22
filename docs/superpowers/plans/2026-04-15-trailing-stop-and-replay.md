# Trailing Stop + Historical Replay Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a peak-relative trailing stop to signal_tracker using each spread's historical favorable-move distribution, then replay closed signals through the new logic to produce a subscriber-facing comparison of actual vs simulated exits.

**Architecture:** Extend the existing `check_signal_status()` exit cascade with a third rule — `TRAIL_STOP` — that fires when `cumulative_spread <= peak_spread_pnl_pct - trail_budget`, where `trail_budget = avg_favorable_move × 0.50 × sqrt(days_since_last_check)`. Existing daily_stop and two_day_stop stay as safety nets for flat trades. A separate replay script walks closed signals day-by-day with yfinance OHLC and produces `data/trail_stop_replay.json`.

**Tech Stack:** Python 3.11 · pytest · yfinance · existing spread_statistics.get_levels_for_spread() · intraday_scan.bat (already runs every 15 min)

---

## File Structure

**Modify:**
- `pipeline/signal_tracker.py` — add trail_stop exit rule inside `check_signal_status()`, surface trail fields in `_data_levels`
- `pipeline/website_exporter.py` — extend `_derive_close_reason()` to render new `STOPPED_OUT_TRAIL` status

**Create:**
- `pipeline/autoresearch/replay_trail_stop.py` — standalone replay driver
- `pipeline/tests/test_trail_stop.py` — unit tests for trail_stop logic
- `pipeline/tests/test_replay_trail_stop.py` — tests for replay walker
- `data/trail_stop_replay.json` — replay output (committed once verified)

---

## Task 1: Trail stop helper — pure function

**Files:**
- Modify: `pipeline/signal_tracker.py` (add helper above `check_signal_status`, around line 390)
- Test: `pipeline/tests/test_trail_stop.py`

- [ ] **Step 1: Write failing tests**

Create `pipeline/tests/test_trail_stop.py`:

```python
"""Tests for trail_stop budget and breach logic in signal_tracker."""
import math
import pytest

from signal_tracker import compute_trail_budget, trail_stop_triggered


class TestComputeTrailBudget:
    def test_single_day_returns_half_favorable(self):
        # 1 day gap: budget = favorable * 0.5 * sqrt(1) = favorable * 0.5
        assert compute_trail_budget(avg_favorable=2.38, days_since_check=1) == pytest.approx(1.19)

    def test_three_day_gap_widens_budget(self):
        # 3 day gap: budget = 2.38 * 0.5 * sqrt(3) ~= 2.06
        result = compute_trail_budget(avg_favorable=2.38, days_since_check=3)
        assert result == pytest.approx(2.38 * 0.5 * math.sqrt(3), rel=1e-6)

    def test_zero_days_clamped_to_one(self):
        # Edge: same-day re-check shouldn't produce 0 budget
        assert compute_trail_budget(avg_favorable=2.0, days_since_check=0) == pytest.approx(1.0)

    def test_zero_favorable_returns_zero(self):
        # Defensive: if no historical favorable data, no budget
        assert compute_trail_budget(avg_favorable=0.0, days_since_check=1) == 0.0


class TestTrailStopTriggered:
    def test_fires_when_cum_below_peak_minus_budget(self):
        # Peak +7%, budget 1.19%, cum +5.5% -> trail_stop = +5.81, cum < stop -> FIRE
        assert trail_stop_triggered(cumulative=5.5, peak=7.0, trail_budget=1.19) is True

    def test_no_fire_when_cum_above_trail(self):
        # Peak +7%, budget 1.19%, cum +6.5% -> trail_stop = +5.81, cum > stop -> HOLD
        assert trail_stop_triggered(cumulative=6.5, peak=7.0, trail_budget=1.19) is False

    def test_guard_no_fire_before_peak_exceeds_budget(self):
        # Peak +0.5% < budget 1.19% -> guard prevents fire, daily_stop handles it
        assert trail_stop_triggered(cumulative=-2.0, peak=0.5, trail_budget=1.19) is False

    def test_fires_exactly_at_trail_boundary(self):
        # Peak +3%, budget 1%, cum +2% -> trail_stop = +2, cum <= stop -> FIRE
        assert trail_stop_triggered(cumulative=2.0, peak=3.0, trail_budget=1.0) is True

    def test_zero_budget_never_fires(self):
        # Defensive: zero budget = no historical data, don't fire
        assert trail_stop_triggered(cumulative=-50.0, peak=10.0, trail_budget=0.0) is False
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd C:/Users/Claude_Anka/askanka.com
python -m pytest pipeline/tests/test_trail_stop.py -v
```

Expected: FAIL with `ImportError: cannot import name 'compute_trail_budget' from 'signal_tracker'`

- [ ] **Step 3: Implement the helpers**

Add to `pipeline/signal_tracker.py`, just above `def check_signal_status` (around line 389):

```python
import math


def compute_trail_budget(avg_favorable: float, days_since_check: int) -> float:
    """Historic-basis trailing budget scaled for elapsed days.

    Budget = avg_favorable_move * 0.50 * sqrt(max(1, days_since_check)).
    The sqrt scaler accounts for variance accumulating across holiday gaps:
    on a 3-day re-open, the spread has had 3 days of action to cover, so
    the single-day budget is widened accordingly.

    Returns 0.0 when avg_favorable is 0 (no historical data -> no trail).
    """
    if avg_favorable <= 0:
        return 0.0
    days = max(1, days_since_check)
    return avg_favorable * 0.50 * math.sqrt(days)


def trail_stop_triggered(cumulative: float, peak: float, trail_budget: float) -> bool:
    """Peak-relative trailing stop check.

    Fires when cumulative P&L has given back more than ``trail_budget`` from
    the running peak. Guard: does not fire until peak has exceeded the budget
    (otherwise fresh trades with noisy early moves would trip instantly —
    daily_stop handles that regime).

    Returns False when trail_budget is 0 (no historical basis -> skip).
    """
    if trail_budget <= 0:
        return False
    if peak < trail_budget:
        return False
    return cumulative <= (peak - trail_budget)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd C:/Users/Claude_Anka/askanka.com
python -m pytest pipeline/tests/test_trail_stop.py -v
```

Expected: 9 tests PASS.

- [ ] **Step 5: Commit**

```bash
cd C:/Users/Claude_Anka/askanka.com
git add pipeline/signal_tracker.py pipeline/tests/test_trail_stop.py
git commit -m "feat(stops): add compute_trail_budget + trail_stop_triggered helpers

Historic-basis trailing budget = avg_favorable * 0.5 * sqrt(days_since).
Peak-relative breach with guard against firing before peak > budget.
9 tests covering normal, holiday scaling, guards, and zero-favorable fallback."
```

---

## Task 2: Wire trail stop into check_signal_status

**Files:**
- Modify: `pipeline/signal_tracker.py:391-483` (the `check_signal_status` function)
- Test: `pipeline/tests/test_trail_stop.py` (add integration tests)

- [ ] **Step 1: Write failing integration tests**

Append to `pipeline/tests/test_trail_stop.py`:

```python
from signal_tracker import check_signal_status


def _signal_with_prices(entry_long, entry_short, peak_pnl, prev_long=None, prev_short=None):
    """Build a minimal signal dict for check_signal_status."""
    sig = {
        "signal_id": "TEST-1",
        "spread_name": "Defence vs IT",  # must exist in spread_stats.json
        "long_legs":  [{"ticker": "HAL",  "price": entry_long}],
        "short_legs": [{"ticker": "TCS",  "price": entry_short}],
        "peak_spread_pnl_pct": peak_pnl,
    }
    if prev_long:
        sig["_prev_close_long"] = {"HAL": prev_long}
    if prev_short:
        sig["_prev_close_short"] = {"TCS": prev_short}
    return sig


class TestTrailStopIntegration:
    def test_trail_stop_fires_when_giving_back_from_peak(self, monkeypatch):
        # Force known historical levels
        monkeypatch.setattr(
            "signal_tracker.get_levels_for_spread",
            lambda name: {"daily_std": 2.0, "avg_favorable_move": 2.38},
        )
        # Peak at +7%, now at +5% (gave back 2%). Budget = 1.19%.
        # Trail stop = 7 - 1.19 = 5.81. Cum 5.0 < 5.81 -> FIRE.
        sig = _signal_with_prices(
            entry_long=100.0, entry_short=100.0,
            peak_pnl=7.0,
            prev_long=104.0, prev_short=101.0,  # today's move small
        )
        # current spread level: long +3% (103-100), short -2% (100 vs 102)
        # cumulative should be well below peak
        prices = {"HAL": 103.0, "TCS": 102.0}  # cum long +3%, short -2%, spread +1% -> below peak 7
        status, _ = check_signal_status(sig, prices)
        assert status == "STOPPED_OUT_TRAIL"

    def test_trail_stop_holds_near_peak(self, monkeypatch):
        # Cum at +6.5%, peak +7%, budget 1.19 -> trail = 5.81 -> HOLD
        monkeypatch.setattr(
            "signal_tracker.get_levels_for_spread",
            lambda name: {"daily_std": 2.0, "avg_favorable_move": 2.38},
        )
        sig = _signal_with_prices(
            entry_long=100.0, entry_short=100.0,
            peak_pnl=7.0,
            prev_long=106.0, prev_short=99.5,
        )
        prices = {"HAL": 106.5, "TCS": 100.0}  # long +6.5, short 0 -> spread +6.5
        status, _ = check_signal_status(sig, prices)
        assert status == "OPEN"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd C:/Users/Claude_Anka/askanka.com
python -m pytest pipeline/tests/test_trail_stop.py::TestTrailStopIntegration -v
```

Expected: FAIL because `check_signal_status` never returns `STOPPED_OUT_TRAIL`.

- [ ] **Step 3: Modify check_signal_status to include trail stop**

In `pipeline/signal_tracker.py`, replace the block starting at line 442 through line 483 with:

```python
    # Update peak cumulative (for reporting AND trail stop)
    peak_pnl = signal.get("peak_spread_pnl_pct", 0.0)
    if cumulative_spread > peak_pnl:
        signal["peak_spread_pnl_pct"] = cumulative_spread
        peak_pnl = cumulative_spread

    # Trail stop: peak-relative, historic-basis, holiday-scaled
    last_check_iso = signal.get("_last_trail_check")
    days_since = 1
    if last_check_iso:
        try:
            from datetime import datetime as _dt
            last_check = _dt.fromisoformat(last_check_iso.replace("Z", "+00:00"))
            now = _dt.now(last_check.tzinfo) if last_check.tzinfo else _dt.now()
            delta_days = (now - last_check).days
            days_since = max(1, delta_days)
        except Exception:
            days_since = 1
    trail_budget = compute_trail_budget(avg_favorable, days_since)
    trail_stop = peak_pnl - trail_budget if trail_budget > 0 else None

    # Store levels on the signal for Telegram display + replay
    signal["_data_levels"] = {
        "daily_stop": round(daily_stop, 2),
        "two_day_stop": round(two_day_stop, 2),
        "trail_stop": round(trail_stop, 2) if trail_stop is not None else None,
        "trail_budget": round(trail_budget, 2),
        "todays_move": round(todays_move, 2),
        "cumulative": round(cumulative_spread, 2),
        "peak": round(peak_pnl, 2),
        "daily_std": round(daily_std, 2),
        "avg_favorable": round(avg_favorable, 2),
        "consecutive_losses": 2 if (is_today_loss and was_yesterday_loss) else (1 if is_today_loss else 0),
        "two_day_combined": round(two_day_combined, 2) if two_day_combined is not None else None,
    }

    # Stamp the trail-check timestamp for the next invocation
    from datetime import datetime as _dt2
    signal["_last_trail_check"] = _dt2.now().isoformat()

    # ── EXIT 0: TRAIL STOP ─────────────────────────────────
    # Peak-relative give-back using historic favorable-move distribution.
    # Checked FIRST so it protects accumulated gains before the daily stop
    # (which is insensitive to peak) can let profit slip back to negative.
    if trail_stop_triggered(cumulative_spread, peak_pnl, trail_budget):
        log.info(
            f"Signal {signal.get('signal_id')}: TRAIL STOP "
            f"(cum {cumulative_spread:+.2f}% <= trail {trail_stop:+.2f}%, "
            f"peak {peak_pnl:+.2f}% - budget {trail_budget:.2f}%)"
        )
        return ("STOPPED_OUT_TRAIL", pnl)

    # ── EXIT 1: DAILY STOP ──────────────────────────────────
    # Today's spread move breaches 50% of avg daily favorable move.
    # Flat-trade safety net — fires when peak hasn't accumulated yet.
    if todays_move <= daily_stop:
        log.info(
            f"Signal {signal.get('signal_id')}: DAILY STOP "
            f"(today {todays_move:+.2f}% <= stop {daily_stop:+.2f}%, "
            f"cumulative {cumulative_spread:+.2f}%)"
        )
        return ("STOPPED_OUT", pnl)

    # ── EXIT 2: 2-DAY RUNNING STOP ──────────────────────────
    if is_today_loss and was_yesterday_loss and two_day_combined is not None:
        if two_day_combined <= two_day_stop:
            log.info(
                f"Signal {signal.get('signal_id')}: 2-DAY RUNNING STOP "
                f"(day1 {prev_day_move:+.2f}% + day2 {todays_move:+.2f}% "
                f"= {two_day_combined:+.2f}% <= stop {two_day_stop:+.2f}%, "
                f"cumulative {cumulative_spread:+.2f}%)"
            )
            return ("STOPPED_OUT_2DAY", pnl)

    return ("OPEN", None)
```

Also update the docstring of `check_signal_status` (around line 395) to describe three exits instead of two:

```python
    """Determine whether an open signal should be closed.

    STOPS-ONLY PHILOSOPHY: Winners run until stopped. We never voluntarily
    take profits — the only exits are stops. This keeps winning positions
    compounding. Losses are cut short by data-driven daily thresholds.

    Three exit conditions (all data-driven from 1-month spread statistics):

      0. TRAIL STOP: Peak-relative give-back. Budget =
         avg_favorable_move * 0.50 * sqrt(days_since_last_check).
         Locks in profit as cumulative P&L ratchets up. Checked first so
         it protects gains before the static daily stop allows flat-day
         slippage. Has a guard: doesn't fire until peak exceeds budget
         (daily stop handles the fresh-trade regime).

      1. DAILY STOP: Today's spread move breaches -(avg_favorable × 50%).
         Flat-trade safety net — catches bad days when trail stop hasn't
         armed yet.

      2. 2-DAY RUNNING STOP: Two consecutive losing days AND combined
         2-day loss exceeds 2 × daily_stop. Catches persistent
         deterioration that individual daily stops might miss.

    Returns ``("OPEN", None)`` or ``(reason, pnl_dict)``.
    """
```

- [ ] **Step 4: Run test to verify passes**

```bash
cd C:/Users/Claude_Anka/askanka.com
python -m pytest pipeline/tests/test_trail_stop.py -v
```

Expected: all 11 tests PASS.

Also run the full existing tracker test file to confirm no regressions:

```bash
python -m pytest pipeline/tests/ -k "tracker or signal" -v
```

Expected: no new failures vs baseline.

- [ ] **Step 5: Commit**

```bash
cd C:/Users/Claude_Anka/askanka.com
git add pipeline/signal_tracker.py pipeline/tests/test_trail_stop.py
git commit -m "feat(stops): wire trail stop into check_signal_status cascade

Trail stop checked first (protects gains), then daily_stop, then 2-day.
Emits new status STOPPED_OUT_TRAIL. Stamps _last_trail_check per signal
so the holiday scaler widens the budget on re-open after gap days.
_data_levels now surfaces trail_stop + trail_budget + peak for telegram
and replay consumption."
```

---

## Task 3: Render trail-stop close reason for track record

**Files:**
- Modify: `pipeline/website_exporter.py:317-331` (the `_derive_close_reason` function)
- Test: `pipeline/tests/test_website_exporter.py` (new file)

- [ ] **Step 1: Write failing test**

Create `pipeline/tests/test_website_exporter.py`:

```python
"""Tests for website_exporter close-reason rendering."""
from website_exporter import _derive_close_reason


def test_trail_stop_reason_renders_peak_and_budget():
    sig = {
        "status": "STOPPED_OUT_TRAIL",
        "_data_levels": {
            "cumulative": 5.50,
            "trail_stop": 5.81,
            "peak": 7.00,
            "trail_budget": 1.19,
        },
    }
    reason = _derive_close_reason(sig)
    assert "Trail stop" in reason
    assert "5.50" in reason
    assert "5.81" in reason
    assert "7.00" in reason


def test_daily_stop_reason_unchanged():
    sig = {
        "status": "STOPPED_OUT",
        "_data_levels": {"todays_move": -1.10, "daily_stop": -0.98},
    }
    reason = _derive_close_reason(sig)
    assert "Trailing stop:" in reason or "Trailing stop" in reason
    assert "-1.10" in reason
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd C:/Users/Claude_Anka/askanka.com
python -m pytest pipeline/tests/test_website_exporter.py -v
```

Expected: FAIL on `test_trail_stop_reason_renders_peak_and_budget` — current function doesn't recognise `STOPPED_OUT_TRAIL`.

- [ ] **Step 3: Extend _derive_close_reason**

In `pipeline/website_exporter.py`, replace the `_derive_close_reason` function (line 317) with:

```python
def _derive_close_reason(sig: dict) -> str:
    """Human-readable close reason from the signal's final state."""
    status = sig.get("status", "")
    dl = sig.get("_data_levels", {}) or {}
    if status == "STOPPED_OUT_TRAIL":
        cum = dl.get("cumulative")
        ts = dl.get("trail_stop")
        peak = dl.get("peak")
        budget = dl.get("trail_budget")
        if all(v is not None for v in (cum, ts, peak, budget)):
            return (f"Trail stop: cum {cum:+.2f}% <= trail {ts:+.2f}% "
                    f"(peak {peak:+.2f}% - budget {budget:.2f}%)")
        return "Trail stop hit"
    if status == "STOPPED_OUT":
        tm = dl.get("todays_move")
        ds = dl.get("daily_stop")
        if tm is not None and ds is not None:
            return f"Trailing stop: today {tm:+.2f}% <= stop {ds:+.2f}%"
        return "Trailing stop hit"
    if status == "STOPPED_OUT_2DAY":
        return "2-day running stop hit (two consecutive losing days)"
    if status == "EXPIRED":
        return "Holding period expired"
    return status or "Closed"
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd C:/Users/Claude_Anka/askanka.com
python -m pytest pipeline/tests/test_website_exporter.py -v
```

Expected: both tests PASS.

- [ ] **Step 5: Commit**

```bash
cd C:/Users/Claude_Anka/askanka.com
git add pipeline/website_exporter.py pipeline/tests/test_website_exporter.py
git commit -m "feat(site): render trail-stop close reason in track record"
```

---

## Task 4: Replay walker — core logic

**Files:**
- Create: `pipeline/autoresearch/replay_trail_stop.py`
- Test: `pipeline/tests/test_replay_trail_stop.py`

- [ ] **Step 1: Write failing test**

Create `pipeline/tests/test_replay_trail_stop.py`:

```python
"""Tests for replay_trail_stop.simulate_signal."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "autoresearch"))

from replay_trail_stop import simulate_signal


def _mk_signal():
    return {
        "signal_id": "SIG-TEST-001",
        "spread_name": "Coal vs OMCs",
        "open_timestamp": "2026-04-01T04:29:29",
        "close_timestamp": "2026-04-08T04:14:51",
        "long_legs":  [{"ticker": "COALINDIA", "price": 464.0}],
        "short_legs": [{"ticker": "BPCL",      "price": 292.0},
                       {"ticker": "HPCL",      "price": 350.0}],
        "status": "STOPPED_OUT",
        "final_pnl": {"spread_pnl_pct": -4.04},
        "peak_spread_pnl_pct": 7.07,
    }


def test_simulate_returns_earlier_exit_when_trail_breached():
    # Daily OHLC: peak on day 3, then slow give-back crossing trail_stop on day 5
    daily_prices = {
        "COALINDIA": [
            ("2026-04-01", 464.0),
            ("2026-04-02", 475.0),
            ("2026-04-03", 490.0),   # peak
            ("2026-04-04", 488.0),
            ("2026-04-07", 478.0),   # breach
            ("2026-04-08", 450.9),
        ],
        "BPCL": [
            ("2026-04-01", 292.0),
            ("2026-04-02", 290.0),
            ("2026-04-03", 285.0),
            ("2026-04-04", 286.0),
            ("2026-04-07", 292.0),
            ("2026-04-08", 295.05),
        ],
        "HPCL": [
            ("2026-04-01", 350.0),
            ("2026-04-02", 348.0),
            ("2026-04-03", 343.0),
            ("2026-04-04", 344.0),
            ("2026-04-07", 352.0),
            ("2026-04-08", 354.85),
        ],
    }
    levels = {"avg_favorable_move": 2.38, "daily_std": 3.57}
    result = simulate_signal(_mk_signal(), daily_prices, levels)

    assert result["signal_id"] == "SIG-TEST-001"
    assert result["simulated_exit"]["reason"] == "TRAIL_STOP"
    # Simulated exit date must precede the actual Apr 8 close
    assert result["simulated_exit"]["date"] < "2026-04-08"
    # Simulated P&L must be better than actual -4.04
    assert result["simulated_exit"]["pnl_pct"] > result["actual_exit"]["pnl_pct"]
    assert result["delta_pct"] > 0


def test_simulate_keeps_actual_when_no_trail_breach():
    # Monotonically improving trade — trail should never fire, actual kept
    daily_prices = {
        "COALINDIA": [("2026-04-01", 464.0), ("2026-04-02", 470.0), ("2026-04-03", 480.0)],
        "BPCL":      [("2026-04-01", 292.0), ("2026-04-02", 290.0), ("2026-04-03", 285.0)],
        "HPCL":      [("2026-04-01", 350.0), ("2026-04-02", 348.0), ("2026-04-03", 345.0)],
    }
    sig = _mk_signal()
    sig["close_timestamp"] = "2026-04-03T16:00:00"
    sig["final_pnl"] = {"spread_pnl_pct": 3.5}
    sig["peak_spread_pnl_pct"] = 3.5
    levels = {"avg_favorable_move": 2.38, "daily_std": 3.57}
    result = simulate_signal(sig, daily_prices, levels)

    assert result["simulated_exit"]["reason"] in ("ACTUAL_CLOSE", None)
    assert result["delta_pct"] == 0 or result["delta_pct"] is None
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd C:/Users/Claude_Anka/askanka.com
python -m pytest pipeline/tests/test_replay_trail_stop.py -v
```

Expected: FAIL — `replay_trail_stop` module does not exist yet.

- [ ] **Step 3: Implement the replay simulator**

Create `pipeline/autoresearch/replay_trail_stop.py`:

```python
"""Historical replay: re-run closed signals through the trail-stop logic.

For each closed signal we have entry prices, the close date, and the final
P&L. This module walks each trading day between open and close using daily
OHLC (close prices) for every leg, updates a synthetic running peak and
trail_stop, and reports what date/P&L the trade would have exited at if the
trail stop had been live.

Output: list of {signal_id, actual_exit, simulated_exit, delta_pct} dicts.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Allow imports from pipeline/ root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from signal_tracker import compute_trail_budget, trail_stop_triggered  # type: ignore


def _spread_pnl_pct(
    long_legs: List[Dict[str, Any]],
    short_legs: List[Dict[str, Any]],
    prices_on_day: Dict[str, float],
) -> Optional[float]:
    """Cumulative spread P&L from entry for a given day's closes.

    Returns None when any leg is missing a price for that day.
    """
    long_moves = []
    for leg in long_legs:
        curr = prices_on_day.get(leg["ticker"])
        entry = leg["price"]
        if curr is None or not entry:
            return None
        long_moves.append((curr / entry - 1) * 100)

    short_moves = []
    for leg in short_legs:
        curr = prices_on_day.get(leg["ticker"])
        entry = leg["price"]
        if curr is None or not entry:
            return None
        short_moves.append((1 - curr / entry) * 100)

    avg_long = sum(long_moves) / len(long_moves) if long_moves else 0.0
    avg_short = sum(short_moves) / len(short_moves) if short_moves else 0.0
    return round(avg_long + avg_short, 4)


def _dates_in_window(
    daily_prices: Dict[str, List[Tuple[str, float]]],
) -> List[str]:
    """Return the sorted union of all dates that appear in every leg."""
    common: Optional[set] = None
    for series in daily_prices.values():
        ds = {d for d, _ in series}
        common = ds if common is None else (common & ds)
    return sorted(common or [])


def simulate_signal(
    signal: Dict[str, Any],
    daily_prices: Dict[str, List[Tuple[str, float]]],
    levels: Dict[str, Any],
) -> Dict[str, Any]:
    """Replay one closed signal with trail-stop logic.

    Args:
        signal: Closed signal dict (needs long_legs, short_legs, open/close
            timestamps, final_pnl, peak_spread_pnl_pct).
        daily_prices: {ticker: [(YYYY-MM-DD, close_price), ...]} covering
            at least open_date..close_date for every leg ticker.
        levels: {"avg_favorable_move": float, "daily_std": float} for this
            spread (from spread_stats.json).

    Returns:
        {signal_id, actual_exit, simulated_exit, delta_pct}
    """
    long_legs  = signal.get("long_legs", [])
    short_legs = signal.get("short_legs", [])
    actual_close = (signal.get("close_timestamp") or "")[:10]
    actual_pnl  = (signal.get("final_pnl") or {}).get("spread_pnl_pct", 0) or 0
    actual_status = signal.get("status", "")

    avg_fav = levels.get("avg_favorable_move", 0.0) or 0.0

    # Build {date: {ticker: price}} for iteration
    by_date: Dict[str, Dict[str, float]] = {}
    for ticker, series in daily_prices.items():
        for date, price in series:
            by_date.setdefault(date, {})[ticker] = price

    dates = _dates_in_window(daily_prices)

    peak = 0.0
    sim_exit_date: Optional[str] = None
    sim_exit_pnl: Optional[float] = None
    prev_date: Optional[str] = None

    for date in dates:
        if date > actual_close:
            break
        prices_today = by_date.get(date, {})
        cum = _spread_pnl_pct(long_legs, short_legs, prices_today)
        if cum is None:
            continue

        if cum > peak:
            peak = cum

        # Days since previous observation (1 on consecutive days, >1 across holidays)
        if prev_date is None:
            days_since = 1
        else:
            from datetime import datetime as _dt
            a = _dt.strptime(prev_date, "%Y-%m-%d")
            b = _dt.strptime(date, "%Y-%m-%d")
            days_since = max(1, (b - a).days)
        prev_date = date

        budget = compute_trail_budget(avg_fav, days_since)
        if trail_stop_triggered(cum, peak, budget):
            sim_exit_date = date
            sim_exit_pnl = cum
            break

    # If trail never fired, simulated exit = actual exit
    if sim_exit_date is None:
        sim_exit = {
            "date": actual_close,
            "reason": "ACTUAL_CLOSE",
            "pnl_pct": round(actual_pnl, 2),
        }
        delta = 0.0
    else:
        sim_exit = {
            "date": sim_exit_date,
            "reason": "TRAIL_STOP",
            "pnl_pct": round(sim_exit_pnl, 2),
        }
        delta = round(sim_exit_pnl - actual_pnl, 2)

    return {
        "signal_id": signal.get("signal_id", ""),
        "spread_name": signal.get("spread_name", ""),
        "open_date": (signal.get("open_timestamp") or "")[:10],
        "actual_exit": {
            "date": actual_close,
            "reason": actual_status,
            "pnl_pct": round(actual_pnl, 2),
        },
        "simulated_exit": sim_exit,
        "delta_pct": delta,
    }
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd C:/Users/Claude_Anka/askanka.com
python -m pytest pipeline/tests/test_replay_trail_stop.py -v
```

Expected: both tests PASS.

- [ ] **Step 5: Commit**

```bash
cd C:/Users/Claude_Anka/askanka.com
git add pipeline/autoresearch/replay_trail_stop.py pipeline/tests/test_replay_trail_stop.py
git commit -m "feat(replay): add simulate_signal for historical trail-stop replay"
```

---

## Task 5: Replay driver — fetch prices, write artifact

**Files:**
- Modify: `pipeline/autoresearch/replay_trail_stop.py` (add `run_replay` + CLI)

- [ ] **Step 1: Implement the driver**

Append to `pipeline/autoresearch/replay_trail_stop.py`:

```python
import json
from datetime import datetime, timedelta


PIPELINE_ROOT = Path(__file__).resolve().parent.parent
CLOSED_SIGS_PATH = PIPELINE_ROOT / "data" / "signals" / "closed_signals.json"
SPREAD_STATS_PATH = PIPELINE_ROOT / "data" / "spread_stats.json"
OUTPUT_PATH = PIPELINE_ROOT.parent / "data" / "trail_stop_replay.json"


def _fetch_daily_closes(
    tickers: List[str],
    start_date: str,
    end_date: str,
) -> Dict[str, List[Tuple[str, float]]]:
    """Fetch daily closes for each ticker via yfinance.

    Tickers are passed as-is — caller must append `.NS` for NSE names if
    needed. start_date and end_date are YYYY-MM-DD strings (inclusive).
    """
    import yfinance as yf  # noqa: WPS433

    result: Dict[str, List[Tuple[str, float]]] = {}
    # Pad end by +2 days to ensure yfinance includes the close_date row
    end_dt = (datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=2)).strftime("%Y-%m-%d")

    for tk in tickers:
        yf_symbol = tk if "." in tk or "^" in tk else f"{tk}.NS"
        hist = yf.Ticker(yf_symbol).history(start=start_date, end=end_dt)
        if hist.empty:
            result[tk] = []
            continue
        series = []
        for idx, row in hist.iterrows():
            date_str = idx.strftime("%Y-%m-%d")
            close = float(row["Close"])
            series.append((date_str, close))
        result[tk] = series
    return result


def _load_levels_for(spread_name: str, stats_all: dict) -> Dict[str, float]:
    """Pull avg_favorable + daily_std from spread_stats.json for one spread."""
    entry = stats_all.get(spread_name) or stats_all.get("spreads", {}).get(spread_name, {})
    # spread_stats.json uses nested shape: spread -> overall -> {...}
    overall = entry.get("overall") if isinstance(entry, dict) and "overall" in entry else entry
    return {
        "avg_favorable_move": float(overall.get("avg_favorable_move", 0.0) or 0.0),
        "daily_std": float(overall.get("daily_std", 0.0) or 0.0),
    }


def run_replay() -> Dict[str, Any]:
    """Replay every closed signal; write result to data/trail_stop_replay.json."""
    closed = json.loads(CLOSED_SIGS_PATH.read_text(encoding="utf-8"))
    stats_all = json.loads(SPREAD_STATS_PATH.read_text(encoding="utf-8")) if SPREAD_STATS_PATH.exists() else {}

    trades: List[Dict[str, Any]] = []
    actual_sum = 0.0
    sim_sum = 0.0
    improved = 0
    worse = 0

    for sig in closed:
        tickers = [l["ticker"] for l in sig.get("long_legs", []) + sig.get("short_legs", [])]
        open_date = (sig.get("open_timestamp") or "")[:10]
        close_date = (sig.get("close_timestamp") or "")[:10]
        if not (open_date and close_date and tickers):
            continue

        try:
            prices = _fetch_daily_closes(tickers, open_date, close_date)
        except Exception as e:
            print(f"  skip {sig.get('signal_id')}: fetch failed ({e})")
            continue

        levels = _load_levels_for(sig.get("spread_name", ""), stats_all)
        if levels["avg_favorable_move"] == 0:
            print(f"  skip {sig.get('signal_id')}: no stats for {sig.get('spread_name')}")
            continue

        result = simulate_signal(sig, prices, levels)
        trades.append(result)

        actual_sum += result["actual_exit"]["pnl_pct"]
        sim_sum    += result["simulated_exit"]["pnl_pct"]
        if result["delta_pct"] > 0:
            improved += 1
        elif result["delta_pct"] < 0:
            worse += 1

    out = {
        "updated_at": datetime.now().isoformat(),
        "total_trades": len(trades),
        "trades_improved": improved,
        "trades_worse": worse,
        "actual_pnl_sum_pct": round(actual_sum, 2),
        "simulated_pnl_sum_pct": round(sim_sum, 2),
        "delta_sum_pct": round(sim_sum - actual_sum, 2),
        "trades": trades,
    }

    OUTPUT_PATH.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(f"Wrote {OUTPUT_PATH}")
    print(f"  Trades: {len(trades)}  improved: {improved}  worse: {worse}")
    print(f"  Actual sum: {actual_sum:+.2f}%  Simulated: {sim_sum:+.2f}%  Delta: {sim_sum - actual_sum:+.2f}%")
    return out


if __name__ == "__main__":
    run_replay()
```

- [ ] **Step 2: Run the driver against real closed signals**

```bash
cd C:/Users/Claude_Anka/askanka.com
python pipeline/autoresearch/replay_trail_stop.py
```

Expected output: writes `data/trail_stop_replay.json`, prints one line per closed signal and an aggregate summary. Defence vs IT and Coal vs OMCs should each show a simulated exit earlier than actual with positive delta_pct.

- [ ] **Step 3: Eyeball the output**

```bash
cd C:/Users/Claude_Anka/askanka.com
python -c "import json; d=json.loads(open('data/trail_stop_replay.json').read()); print(json.dumps({k:v for k,v in d.items() if k!='trades'}, indent=2)); [print(f\"  {t['signal_id']}: actual {t['actual_exit']['pnl_pct']:+.2f}% -> sim {t['simulated_exit']['pnl_pct']:+.2f}% ({t['simulated_exit']['reason']})\") for t in d['trades']]"
```

Expected: Coal vs OMCs and Defence vs IT show clear improvement; print matches sanity check (Coal actual -4.04 → sim positive; Defence actual +8.66 → sim between +9 and +11).

- [ ] **Step 4: Commit the driver and the first replay artifact**

```bash
cd C:/Users/Claude_Anka/askanka.com
git add pipeline/autoresearch/replay_trail_stop.py data/trail_stop_replay.json
git commit -m "feat(replay): add replay driver + first trail-stop replay artifact

Driver fetches yfinance daily closes for every leg of every closed signal,
calls simulate_signal with that spread's historical avg_favorable_move,
and writes data/trail_stop_replay.json with actual vs simulated exits
and an aggregate portfolio delta. First run baseline committed."
```

---

## Task 6: Smoke test the live cascade + verify telemetry

**Files:**
- Run: `pipeline/website_exporter.py` (existing entry point)

- [ ] **Step 1: Force the exporter to reprocess open signals**

```bash
cd C:/Users/Claude_Anka/askanka.com
python pipeline/website_exporter.py
```

Expected: prints "Exported live_status.json" plus others; no crash.

- [ ] **Step 2: Inspect live_status.json for new telemetry keys**

```bash
cd C:/Users/Claude_Anka/askanka.com
python -c "import json; d=json.loads(open('data/live_status.json').read()); print(json.dumps(d['positions'][0] if d.get('positions') else {}, indent=2, default=str))"
```

Expected: output should include the existing fields (`spread_pnl_pct`, `todays_move`, `peak_pnl`, `daily_stop`). No regression. (trail_stop fields will only appear after the 15-min tracker has run once with the new code; this step just confirms we haven't broken the read.)

- [ ] **Step 3: Manually invoke the monitor cycle once**

```bash
cd C:/Users/Claude_Anka/askanka.com
python -c "import sys; sys.path.insert(0, 'pipeline'); from signal_tracker import monitor_cycle; r = monitor_cycle(); print(f'cycle ran: closed={len(r)} signals')"
```

Expected: prints `cycle ran: closed=N` (N=0 likely — today's trades haven't armed the trail yet). No exception.

- [ ] **Step 4: Re-export and confirm trail fields now present for open signals**

```bash
cd C:/Users/Claude_Anka/askanka.com
python pipeline/website_exporter.py
python -c "import json; sigs = json.loads(open('pipeline/data/signals/open_signals.json').read()); [print(s.get('signal_id'), s.get('_data_levels', {}).get('trail_stop'), s.get('_data_levels', {}).get('trail_budget')) for s in sigs]"
```

Expected: each open signal prints its signal_id and non-null trail_stop + trail_budget values.

- [ ] **Step 5: Commit the state file updates**

```bash
cd C:/Users/Claude_Anka/askanka.com
git add pipeline/data/signals/open_signals.json data/live_status.json
git commit -m "chore(state): first live tracker cycle under trail-stop logic

State snapshot confirms trail_stop + trail_budget now populated on each
open signal; no signals stopped out during the smoke run."
```

---

## Task 7: Push

**Files:** none (git push only)

- [ ] **Step 1: Push to origin**

```bash
cd C:/Users/Claude_Anka/askanka.com
git push origin master
```

Expected: six commits land on origin/master.

---

## Out of scope (follow-ups, not in this plan)

- Subscriber-facing UI card on index.html showing the aggregate delta from `trail_stop_replay.json`. Design after eyeballing the numbers.
- Converting `_prev_day_move` holiday handling in `snapshot_eod_prices` to match the trail stop's √N scaling.
- Alternative trail_budget formulas (e.g., `p10` of favorable distribution instead of `0.5 * avg_favorable`) — deferred until replay baseline is on record.

---

## Self-review

**Spec coverage:**
- ✅ Peak-relative trail — Tasks 1, 2
- ✅ Historic basis (avg_favorable per spread) — Task 1 `compute_trail_budget`
- ✅ 15-min cadence — piggybacks existing `monitor_cycle` called by `intraday_scan.bat`, verified Task 6
- ✅ Holiday √N scaling — Task 1 helper, Task 4 simulator uses same helper
- ✅ Kept existing daily_stop + 2-day_stop — Task 2 keeps both below the new trail check
- ✅ Replay artifact — Tasks 4, 5
- ✅ Track Record renders new reason — Task 3
- ⏳ Subscriber UI — intentionally deferred, listed in Out of scope

**Placeholder scan:** None present. Every code step has complete code; every test has real assertions.

**Type consistency:** `compute_trail_budget(avg_favorable, days_since_check)` and `trail_stop_triggered(cumulative, peak, trail_budget)` are called with the same argument names in Task 2's cascade and Task 4's simulator. `_data_levels` key names (`trail_stop`, `trail_budget`, `peak`) are consistent across Tasks 2, 3, 4.
