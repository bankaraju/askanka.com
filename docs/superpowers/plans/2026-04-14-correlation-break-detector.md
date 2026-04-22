# Correlation Break Detector (Phase C) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Detect stocks deviating from expected regime behavior intraday, cross-reference with OI/PCR data, classify as opportunity or warning, and output action recommendations via Telegram.

**Architecture:** Load Phase A profile for current regime's expected returns, fetch realtime prices, compute z-score deviation, read OI positioning for context, classify using a decision matrix, format and send alerts. Single script, reads state from Phase B ranker.

**Tech Stack:** Python, numpy. Existing: `eodhd_client.py` (realtime prices), `oi_scanner.py` (PCR/OI), `telegram_bot.py` (alerts). Data: `reverse_regime_profile.json` (Phase A), `regime_ranker_state.json` (Phase B), `positioning.json` (OI scanner).

**Spec:** `docs/superpowers/specs/2026-04-14-correlation-break-detector-design.md`

---

### Task 1: Deviation Calculator

**Files:**
- Create: `C:/Users/Claude_Anka/Documents/askanka.com/pipeline/autoresearch/reverse_regime_breaks.py`
- Create: `C:/Users/Claude_Anka/Documents/askanka.com/pipeline/autoresearch/tests/test_reverse_breaks.py`

- [ ] **Step 1: Write the failing tests**

```python
# C:/Users/Claude_Anka/Documents/askanka.com/pipeline/autoresearch/tests/test_reverse_breaks.py

import json
import pytest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


class TestDeviationCalculator:

    def test_compute_deviation_normal(self):
        from reverse_regime_breaks import compute_deviation
        result = compute_deviation(
            actual_return=1.5,
            expected_return=1.2,
            expected_std=0.8,
        )
        assert result["deviation"] == pytest.approx(0.3, abs=0.01)
        assert result["z_score"] == pytest.approx(0.375, abs=0.01)
        assert result["is_break"] is False  # |0.375| < 1.5

    def test_compute_deviation_break(self):
        from reverse_regime_breaks import compute_deviation
        result = compute_deviation(
            actual_return=-0.3,
            expected_return=1.5,
            expected_std=0.8,
        )
        assert result["deviation"] == pytest.approx(-1.8, abs=0.01)
        assert result["z_score"] == pytest.approx(-2.25, abs=0.01)
        assert result["is_break"] is True  # |2.25| > 1.5

    def test_compute_deviation_zero_std(self):
        from reverse_regime_breaks import compute_deviation
        result = compute_deviation(
            actual_return=1.0,
            expected_return=1.0,
            expected_std=0.0,
        )
        assert result["is_break"] is False
        assert result["z_score"] == 0.0

    def test_get_expected_returns_for_regime(self):
        from reverse_regime_breaks import get_expected_returns

        profile = {
            "stocks": {
                "HAL": {
                    "NEUTRAL→RISK-OFF": {
                        "drift_1d_mean": -0.5, "drift_5d_mean": -2.0,
                        "drift_5d_std": 1.8, "hit_rate": 71.4,
                        "persistence": 60.0, "tradeable": True, "episodes": 14,
                        "gap_mean": -0.03,
                    },
                },
                "TCS": {
                    "NEUTRAL→EUPHORIA": {
                        "drift_1d_mean": 1.0, "drift_5d_mean": 3.0,
                        "drift_5d_std": 2.0, "hit_rate": 65.0,
                        "persistence": 55.0, "tradeable": True, "episodes": 8,
                        "gap_mean": 0.5,
                    },
                },
            },
            "baskets": {},
        }

        # Current regime transition is NEUTRAL→RISK-OFF
        expected = get_expected_returns(profile, "NEUTRAL→RISK-OFF")
        assert "HAL" in expected
        assert "TCS" not in expected  # TCS has no signal for this transition
        assert expected["HAL"]["drift_1d_mean"] == -0.5
        assert expected["HAL"]["daily_std"] == pytest.approx(1.8 / 2.236, abs=0.01)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd C:/Users/Claude_Anka/Documents/askanka.com/pipeline/autoresearch && C:/Python313/python.exe -m pytest tests/test_reverse_breaks.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'reverse_regime_breaks'`

- [ ] **Step 3: Implement deviation calculator**

```python
# C:/Users/Claude_Anka/Documents/askanka.com/pipeline/autoresearch/reverse_regime_breaks.py
"""
Correlation Break Detector (Phase C)

Detects stocks deviating from expected regime behavior intraday,
cross-references with OI/PCR data, classifies as opportunity or warning.

Runs every 15 min during market hours (09:30-15:30 IST).
Reads from Phase A profile and Phase B state. Does NOT modify spreads.
ADD recommendations are standalone directional trades.
"""

import json
import math
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))

DATA_DIR = Path(__file__).parent.parent / "data"
PROFILE_PATH = Path(__file__).parent / "reverse_regime_profile.json"
STATE_PATH = DATA_DIR / "regime_ranker_state.json"
POSITIONING_PATH = DATA_DIR / "positioning.json"
BREAKS_PATH = DATA_DIR / "correlation_breaks.json"
BREAK_HISTORY_PATH = DATA_DIR / "correlation_break_history.json"

IST = timezone(timedelta(hours=5, minutes=30))
BREAK_THRESHOLD = 1.5  # z-score threshold for correlation break


def compute_deviation(
    actual_return: float,
    expected_return: float,
    expected_std: float,
) -> dict:
    """Compute deviation of actual return from expected.
    Returns dict with deviation, z_score, is_break.
    """
    deviation = actual_return - expected_return

    if expected_std <= 0:
        return {"deviation": deviation, "z_score": 0.0, "is_break": False}

    z_score = deviation / expected_std
    is_break = abs(z_score) > BREAK_THRESHOLD

    return {
        "deviation": round(deviation, 4),
        "z_score": round(z_score, 4),
        "is_break": is_break,
    }


def get_expected_returns(profile: dict, transition_key: str) -> dict:
    """Get expected returns for all stocks with signals for this transition.
    Returns dict[symbol, {drift_1d_mean, daily_std, drift_5d_mean, hit_rate, ...}].
    """
    expected = {}

    for source_key in ["stocks", "baskets"]:
        for symbol, transitions in profile.get(source_key, {}).items():
            if transition_key not in transitions:
                continue
            data = transitions[transition_key]
            if not data.get("tradeable"):
                continue

            drift_5d_std = data.get("drift_5d_std", 0)
            daily_std = drift_5d_std / math.sqrt(5) if drift_5d_std > 0 else 0

            expected[symbol] = {
                "drift_1d_mean": data["drift_1d_mean"],
                "drift_5d_mean": data["drift_5d_mean"],
                "daily_std": daily_std,
                "hit_rate": data.get("hit_rate", 0),
                "persistence": data.get("persistence", 0),
                "episodes": data.get("episodes", 0),
                "gap_mean": data.get("gap_mean", 0),
                "type": "stock" if source_key == "stocks" else "basket",
            }

    return expected
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd C:/Users/Claude_Anka/Documents/askanka.com/pipeline/autoresearch && C:/Python313/python.exe -m pytest tests/test_reverse_breaks.py -v`

Expected: 4 tests PASS

- [ ] **Step 5: Commit**

```bash
cd C:/Users/Claude_Anka/Documents/askanka.com/pipeline
git add -f autoresearch/reverse_regime_breaks.py autoresearch/tests/test_reverse_breaks.py
git commit -m "feat: deviation calculator for correlation break detection (Phase C)"
```

---

### Task 2: Break Classification with OI Cross-Reference

**Files:**
- Modify: `C:/Users/Claude_Anka/Documents/askanka.com/pipeline/autoresearch/reverse_regime_breaks.py`
- Modify: `C:/Users/Claude_Anka/Documents/askanka.com/pipeline/autoresearch/tests/test_reverse_breaks.py`

- [ ] **Step 1: Write the failing tests**

Append to test file:

```python
class TestBreakClassification:

    def test_opportunity_stock_lagging_oi_confirms(self):
        from reverse_regime_breaks import classify_break
        result = classify_break(
            actual_return=0.1,
            expected_return=1.5,
            z_score=-1.75,
            pcr_sentiment="BULLISH",
            oi_anomaly=False,
        )
        assert result["classification"] == "OPPORTUNITY"
        assert result["action"] == "ADD"

    def test_warning_stock_opposite_oi_confirms(self):
        from reverse_regime_breaks import classify_break
        result = classify_break(
            actual_return=-1.0,
            expected_return=1.5,
            z_score=-3.1,
            pcr_sentiment="BEARISH",
            oi_anomaly=True,
        )
        assert result["classification"] == "CONFIRMED_WARNING"
        assert result["action"] == "EXIT"

    def test_hold_stock_lagging_oi_neutral(self):
        from reverse_regime_breaks import classify_break
        result = classify_break(
            actual_return=0.1,
            expected_return=1.5,
            z_score=-1.75,
            pcr_sentiment="NEUTRAL",
            oi_anomaly=False,
        )
        assert result["classification"] == "POSSIBLE_OPPORTUNITY"
        assert result["action"] == "HOLD"

    def test_reduce_stock_lagging_oi_disagrees(self):
        from reverse_regime_breaks import classify_break
        result = classify_break(
            actual_return=0.1,
            expected_return=1.5,
            z_score=-1.75,
            pcr_sentiment="BEARISH",
            oi_anomaly=True,
        )
        assert result["classification"] == "WARNING"
        assert result["action"] == "REDUCE"

    def test_uncertain_opposite_but_oi_disagrees(self):
        from reverse_regime_breaks import classify_break
        result = classify_break(
            actual_return=-1.0,
            expected_return=1.5,
            z_score=-3.1,
            pcr_sentiment="BULLISH",
            oi_anomaly=False,
        )
        assert result["classification"] == "UNCERTAIN"
        assert result["action"] == "HOLD"

    def test_read_oi_for_symbol(self):
        from reverse_regime_breaks import read_oi_context
        positioning = {
            "HAL": {
                "pcr": 1.4, "sentiment": "BULLISH",
                "oi_anomaly": False, "oi_change": 100,
                "call_oi": 500000, "put_oi": 700000,
            },
        }
        ctx = read_oi_context("HAL", positioning)
        assert ctx["pcr"] == 1.4
        assert ctx["pcr_sentiment"] == "BULLISH"
        assert ctx["oi_anomaly"] is False

    def test_read_oi_missing_symbol(self):
        from reverse_regime_breaks import read_oi_context
        ctx = read_oi_context("UNKNOWN", {})
        assert ctx["pcr_sentiment"] == "NEUTRAL"
        assert ctx["oi_anomaly"] is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd C:/Users/Claude_Anka/Documents/askanka.com/pipeline/autoresearch && C:/Python313/python.exe -m pytest tests/test_reverse_breaks.py -v -k "BreakClassification"`

Expected: FAIL with `ImportError: cannot import name 'classify_break'`

- [ ] **Step 3: Implement classification and OI reader**

Add to `reverse_regime_breaks.py`:

```python
def _pcr_agrees_with_direction(pcr_sentiment: str, expected_direction: str) -> bool:
    """Check if PCR sentiment agrees with expected stock direction.
    expected_direction: 'UP' (expected positive return) or 'DOWN' (expected negative).
    """
    bullish_sentiments = {"BULLISH", "MILD_BULL"}
    bearish_sentiments = {"BEARISH", "MILD_BEAR"}

    if expected_direction == "UP":
        return pcr_sentiment in bullish_sentiments
    else:
        return pcr_sentiment in bearish_sentiments


def _pcr_agrees_with_break(pcr_sentiment: str, break_direction: str) -> bool:
    """Check if PCR sentiment agrees with the break direction (actual move)."""
    bullish_sentiments = {"BULLISH", "MILD_BULL"}
    bearish_sentiments = {"BEARISH", "MILD_BEAR"}

    if break_direction == "UP":
        return pcr_sentiment in bullish_sentiments
    else:
        return pcr_sentiment in bearish_sentiments


def classify_break(
    actual_return: float,
    expected_return: float,
    z_score: float,
    pcr_sentiment: str,
    oi_anomaly: bool,
) -> dict:
    """Classify a correlation break using price deviation + OI context.

    Returns dict with classification and action.
    """
    expected_direction = "UP" if expected_return > 0 else "DOWN"

    # Is stock lagging (near zero) or moving opposite?
    stock_lagging = abs(actual_return) < abs(expected_return) * 0.5
    stock_opposite = (
        (expected_return > 0 and actual_return < -abs(expected_return) * 0.3)
        or (expected_return < 0 and actual_return > abs(expected_return) * 0.3)
    )

    pcr_agrees_expected = _pcr_agrees_with_direction(pcr_sentiment, expected_direction)
    pcr_neutral = pcr_sentiment == "NEUTRAL"

    if stock_lagging:
        if pcr_agrees_expected and not oi_anomaly:
            return {"classification": "OPPORTUNITY", "action": "ADD"}
        elif pcr_neutral and not oi_anomaly:
            return {"classification": "POSSIBLE_OPPORTUNITY", "action": "HOLD"}
        else:
            return {"classification": "WARNING", "action": "REDUCE"}

    if stock_opposite:
        break_direction = "UP" if actual_return > 0 else "DOWN"
        pcr_agrees_break = _pcr_agrees_with_break(pcr_sentiment, break_direction)

        if pcr_agrees_break or oi_anomaly:
            return {"classification": "CONFIRMED_WARNING", "action": "EXIT"}
        else:
            return {"classification": "UNCERTAIN", "action": "HOLD"}

    # Stock moving in expected direction but weaker/stronger than expected
    return {"classification": "DIVERGING", "action": "HOLD"}


def read_oi_context(symbol: str, positioning: dict) -> dict:
    """Read OI context for a symbol from positioning data.
    Returns dict with pcr, pcr_sentiment, oi_anomaly, oi_change.
    """
    if symbol not in positioning:
        return {
            "pcr": 0.0,
            "pcr_sentiment": "NEUTRAL",
            "oi_anomaly": False,
            "oi_change": 0,
            "call_oi": 0,
            "put_oi": 0,
        }

    data = positioning[symbol]
    return {
        "pcr": data.get("pcr", 0.0),
        "pcr_sentiment": data.get("sentiment", "NEUTRAL"),
        "oi_anomaly": data.get("oi_anomaly", False),
        "oi_change": data.get("oi_change", 0),
        "call_oi": data.get("call_oi", 0),
        "put_oi": data.get("put_oi", 0),
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd C:/Users/Claude_Anka/Documents/askanka.com/pipeline/autoresearch && C:/Python313/python.exe -m pytest tests/test_reverse_breaks.py -v`

Expected: 11 tests PASS

- [ ] **Step 5: Commit**

```bash
cd C:/Users/Claude_Anka/Documents/askanka.com/pipeline
git add -f autoresearch/reverse_regime_breaks.py autoresearch/tests/test_reverse_breaks.py
git commit -m "feat: break classification matrix with OI cross-reference"
```

---

### Task 3: Alert Formatter + Phase B Cross-Reference

**Files:**
- Modify: `C:/Users/Claude_Anka/Documents/askanka.com/pipeline/autoresearch/reverse_regime_breaks.py`
- Modify: `C:/Users/Claude_Anka/Documents/askanka.com/pipeline/autoresearch/tests/test_reverse_breaks.py`

- [ ] **Step 1: Write the failing tests**

Append to test file:

```python
class TestAlertFormatter:

    def test_format_break_alert(self):
        from reverse_regime_breaks import format_break_alert
        break_data = {
            "symbol": "HAL",
            "regime": "RISK-OFF",
            "regime_day": 2,
            "expected_return": 1.5,
            "actual_return": -0.3,
            "z_score": -2.1,
            "classification": "WARNING",
            "action": "REDUCE",
            "pcr": 1.4,
            "pcr_sentiment": "BULLISH",
            "oi_anomaly": True,
            "oi_change": 150000,
            "phase_b_active": None,
        }
        msg = format_break_alert(break_data)
        assert "HAL" in msg
        assert "RISK-OFF" in msg
        assert "WARNING" in msg
        assert "REDUCE" in msg
        assert "PCR: 1.40" in msg

    def test_format_with_phase_b_active(self):
        from reverse_regime_breaks import format_break_alert
        break_data = {
            "symbol": "HAL",
            "regime": "RISK-OFF",
            "regime_day": 1,
            "expected_return": 1.5,
            "actual_return": -0.3,
            "z_score": -2.1,
            "classification": "WARNING",
            "action": "REDUCE",
            "pcr": 0.6,
            "pcr_sentiment": "MILD_BEAR",
            "oi_anomaly": False,
            "oi_change": 0,
            "phase_b_active": {
                "direction": "LONG",
                "entry_date": "2026-04-14",
                "expiry_date": "2026-04-21",
            },
        }
        msg = format_break_alert(break_data)
        assert "Phase B" in msg
        assert "LONG" in msg

    def test_format_add_recommendation(self):
        from reverse_regime_breaks import format_break_alert
        break_data = {
            "symbol": "BDL",
            "regime": "EUPHORIA",
            "regime_day": 1,
            "expected_return": 2.0,
            "actual_return": 0.1,
            "z_score": -2.3,
            "classification": "OPPORTUNITY",
            "action": "ADD",
            "pcr": 1.2,
            "pcr_sentiment": "MILD_BULL",
            "oi_anomaly": False,
            "oi_change": 0,
            "phase_b_active": None,
            "daily_std": 0.9,
            "drift_5d_mean": 5.87,
        }
        msg = format_break_alert(break_data)
        assert "ADD" in msg
        assert "Standalone" in msg
        assert "BDL" in msg

    def test_check_phase_b_active(self):
        from reverse_regime_breaks import check_phase_b_active
        state = {
            "active_recommendations": [
                {"symbol": "HAL", "direction": "LONG", "entry_date": "2026-04-14", "expiry_date": "2026-04-21"},
                {"symbol": "TCS", "direction": "SHORT", "entry_date": "2026-04-14", "expiry_date": "2026-04-21"},
            ],
        }
        result = check_phase_b_active("HAL", state)
        assert result is not None
        assert result["direction"] == "LONG"

        result2 = check_phase_b_active("INFY", state)
        assert result2 is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd C:/Users/Claude_Anka/Documents/askanka.com/pipeline/autoresearch && C:/Python313/python.exe -m pytest tests/test_reverse_breaks.py -v -k "AlertFormatter"`

Expected: FAIL with `ImportError: cannot import name 'format_break_alert'`

- [ ] **Step 3: Implement formatter and Phase B cross-reference**

Add to `reverse_regime_breaks.py`:

```python
def check_phase_b_active(symbol: str, ranker_state: dict) -> dict | None:
    """Check if symbol has an active Phase B recommendation."""
    for rec in ranker_state.get("active_recommendations", []):
        if rec.get("symbol") == symbol:
            return rec
    return None


def format_break_alert(break_data: dict) -> str:
    """Format a Telegram-ready correlation break alert."""
    symbol = break_data["symbol"]
    classification = break_data["classification"]
    action = break_data["action"]

    icon = {
        "OPPORTUNITY": "\u2705",       # green check
        "POSSIBLE_OPPORTUNITY": "\u2754",  # question
        "WARNING": "\u26a0\ufe0f",     # warning
        "CONFIRMED_WARNING": "\U0001f6a8",  # red siren
        "UNCERTAIN": "\u2753",         # question
        "DIVERGING": "\U0001f504",     # arrows
    }.get(classification, "\u26a0\ufe0f")

    lines = [
        f"{icon} CORRELATION BREAK: {symbol}",
        f"Regime: {break_data['regime']} (day {break_data['regime_day']})",
        f"Expected: {break_data['expected_return']:+.1f}% | "
        f"Actual: {break_data['actual_return']:+.1f}% | "
        f"Z-score: {break_data['z_score']:.1f}\u03c3",
        f"Classification: {classification}",
        "",
        "Options context:",
        f"  PCR: {break_data['pcr']:.2f} ({break_data['pcr_sentiment']}) | "
        f"OI anomaly: {'YES' if break_data['oi_anomaly'] else 'No'}",
        "",
        f"Action: {action}",
    ]

    if action == "ADD":
        daily_std = break_data.get("daily_std", 1.0)
        drift_5d = break_data.get("drift_5d_mean", 0)
        stop = round(1.5 * daily_std, 2)
        direction = "LONG" if drift_5d > 0 else "SHORT"
        lines.append(
            f"  -> Standalone {direction} {symbol} @ market, "
            f"stop {stop:.1f}%, target {abs(drift_5d):.1f}%, 3d hold"
        )

    phase_b = break_data.get("phase_b_active")
    if phase_b:
        lines.append("")
        lines.append(
            f"Phase B: {phase_b['direction']} {symbol}, "
            f"entry {phase_b['entry_date']}, expires {phase_b['expiry_date']}"
        )

    return "\n".join(lines)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd C:/Users/Claude_Anka/Documents/askanka.com/pipeline/autoresearch && C:/Python313/python.exe -m pytest tests/test_reverse_breaks.py -v`

Expected: 15 tests PASS

- [ ] **Step 5: Commit**

```bash
cd C:/Users/Claude_Anka/Documents/askanka.com/pipeline
git add -f autoresearch/reverse_regime_breaks.py autoresearch/tests/test_reverse_breaks.py
git commit -m "feat: break alert formatter with Phase B cross-reference"
```

---

### Task 4: Main Scanner + History Logging + CLI

**Files:**
- Modify: `C:/Users/Claude_Anka/Documents/askanka.com/pipeline/autoresearch/reverse_regime_breaks.py`
- Modify: `C:/Users/Claude_Anka/Documents/askanka.com/pipeline/autoresearch/tests/test_reverse_breaks.py`

- [ ] **Step 1: Write the failing tests**

Append to test file:

```python
class TestScanner:

    @pytest.fixture
    def full_setup(self, tmp_path):
        """Create all required files for a full scan test."""
        profile = {
            "stocks": {
                "HAL": {
                    "NEUTRAL->RISK-OFF": {
                        "drift_1d_mean": 1.5, "drift_5d_mean": 5.0,
                        "drift_5d_std": 2.0, "hit_rate": 71.0,
                        "persistence": 60.0, "tradeable": True,
                        "episodes": 14, "gap_mean": 0.5,
                        "drift_3d_mean": 3.0, "gap_std": 0.3,
                    },
                },
            },
            "baskets": {},
        }
        profile_path = tmp_path / "profile.json"
        profile_path.write_text(json.dumps(profile))

        state = {
            "last_zone": "RISK-OFF",
            "active_recommendations": [
                {"symbol": "HAL", "direction": "LONG",
                 "entry_date": "2026-04-14", "expiry_date": "2026-04-21"},
            ],
            "updated": "2026-04-14",
        }
        state_path = tmp_path / "state.json"
        state_path.write_text(json.dumps(state))

        positioning = {
            "HAL": {
                "pcr": 0.5, "sentiment": "BEARISH",
                "oi_anomaly": True, "oi_change": 200000,
                "call_oi": 300000, "put_oi": 150000,
            },
        }
        pos_path = tmp_path / "positioning.json"
        pos_path.write_text(json.dumps(positioning))

        return {
            "profile_path": profile_path,
            "state_path": state_path,
            "positioning_path": pos_path,
            "breaks_path": tmp_path / "breaks.json",
            "history_path": tmp_path / "history.json",
        }

    def test_scan_finds_breaks(self, full_setup):
        from reverse_regime_breaks import run_break_scan

        # Mock prices: HAL actual return = -0.5% (expected +1.5%)
        mock_prices = {"HAL": {"open": 100.0, "current": 99.5}}

        breaks = run_break_scan(
            transition_key="NEUTRAL->RISK-OFF",
            regime_day=2,
            current_regime="RISK-OFF",
            mock_prices=mock_prices,
            send_telegram=False,
            **full_setup,
        )
        assert len(breaks) >= 1
        hal_break = [b for b in breaks if b["symbol"] == "HAL"][0]
        assert hal_break["is_break"] is True
        assert hal_break["classification"] in ("WARNING", "CONFIRMED_WARNING")
        assert hal_break["phase_b_active"] is not None

    def test_scan_no_breaks(self, full_setup):
        from reverse_regime_breaks import run_break_scan

        # Mock prices: HAL actual return = +1.4% (expected +1.5%, within tolerance)
        mock_prices = {"HAL": {"open": 100.0, "current": 101.4}}

        breaks = run_break_scan(
            transition_key="NEUTRAL->RISK-OFF",
            regime_day=1,
            current_regime="RISK-OFF",
            mock_prices=mock_prices,
            send_telegram=False,
            **full_setup,
        )
        assert len(breaks) == 0

    def test_history_logged(self, full_setup):
        from reverse_regime_breaks import run_break_scan

        mock_prices = {"HAL": {"open": 100.0, "current": 99.5}}
        run_break_scan(
            transition_key="NEUTRAL->RISK-OFF",
            regime_day=2,
            current_regime="RISK-OFF",
            mock_prices=mock_prices,
            send_telegram=False,
            **full_setup,
        )
        history_path = full_setup["history_path"]
        assert history_path.exists()
        history = json.loads(history_path.read_text())
        assert len(history) >= 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd C:/Users/Claude_Anka/Documents/askanka.com/pipeline/autoresearch && C:/Python313/python.exe -m pytest tests/test_reverse_breaks.py -v -k "Scanner"`

Expected: FAIL with `ImportError: cannot import name 'run_break_scan'`

- [ ] **Step 3: Implement the scanner, history logger, and CLI**

Add to `reverse_regime_breaks.py`:

```python
def _fetch_current_prices(symbols: list[str]) -> dict:
    """Fetch current prices from EODHD for a list of symbols.
    Returns dict[symbol, {open, current}].
    """
    from eodhd_client import fetch_realtime
    prices = {}
    for sym in symbols:
        try:
            data = fetch_realtime(f"{sym}.NSE")
            if data:
                prices[sym] = {
                    "open": float(data.get("open", 0)),
                    "current": float(data.get("close", 0)),
                }
        except Exception:
            pass
    return prices


def _load_positioning(positioning_path: Path = POSITIONING_PATH) -> dict:
    """Load latest OI positioning data."""
    if positioning_path.exists():
        return json.loads(positioning_path.read_text(encoding="utf-8"))
    return {}


def _load_ranker_state(state_path: Path = STATE_PATH) -> dict:
    """Load Phase B ranker state."""
    if state_path.exists():
        return json.loads(state_path.read_text(encoding="utf-8"))
    return {}


def _log_break_history(
    breaks: list[dict],
    history_path: Path = BREAK_HISTORY_PATH,
):
    """Append breaks to history log."""
    history = []
    if history_path.exists():
        history = json.loads(history_path.read_text(encoding="utf-8"))

    for b in breaks:
        history.append({
            "date": datetime.now(IST).strftime("%Y-%m-%d"),
            "time": datetime.now(IST).strftime("%H:%M"),
            "symbol": b["symbol"],
            "regime": b["regime"],
            "expected": b["expected_return"],
            "actual": b["actual_return"],
            "z_score": b["z_score"],
            "classification": b["classification"],
            "action": b["action"],
            "pcr": b["pcr"],
            "oi_anomaly": b["oi_anomaly"],
        })

    history_path.parent.mkdir(parents=True, exist_ok=True)
    history_path.write_text(json.dumps(history, indent=2), encoding="utf-8")


def run_break_scan(
    transition_key: str,
    regime_day: int,
    current_regime: str,
    profile_path: Path = PROFILE_PATH,
    state_path: Path = STATE_PATH,
    positioning_path: Path = POSITIONING_PATH,
    breaks_path: Path = BREAKS_PATH,
    history_path: Path = BREAK_HISTORY_PATH,
    mock_prices: dict = None,
    send_telegram: bool = True,
) -> list[dict]:
    """Run a full break scan. Returns list of detected breaks."""
    # Load profile
    if not profile_path.exists():
        print("No Phase A profile found. Run reverse_regime_analysis.py first.")
        return []

    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    expected = get_expected_returns(profile, transition_key)

    if not expected:
        print(f"No expected returns for transition {transition_key}")
        return []

    # Load prices
    if mock_prices is not None:
        prices = mock_prices
    else:
        prices = _fetch_current_prices(list(expected.keys()))

    # Load OI positioning
    positioning = _load_positioning(positioning_path)

    # Load Phase B state
    ranker_state = _load_ranker_state(state_path)

    # Scan each stock
    breaks = []
    for symbol, exp in expected.items():
        if symbol not in prices:
            continue

        price_data = prices[symbol]
        open_price = price_data["open"]
        current_price = price_data["current"]

        if open_price <= 0:
            continue

        actual_return = (current_price / open_price - 1) * 100
        dev = compute_deviation(actual_return, exp["drift_1d_mean"], exp["daily_std"])

        if not dev["is_break"]:
            continue

        # OI context
        oi_ctx = read_oi_context(symbol, positioning)

        # Classify
        cls = classify_break(
            actual_return=actual_return,
            expected_return=exp["drift_1d_mean"],
            z_score=dev["z_score"],
            pcr_sentiment=oi_ctx["pcr_sentiment"],
            oi_anomaly=oi_ctx["oi_anomaly"],
        )

        # Phase B cross-reference
        phase_b = check_phase_b_active(symbol, ranker_state)

        break_data = {
            "symbol": symbol,
            "regime": current_regime,
            "regime_day": regime_day,
            "expected_return": exp["drift_1d_mean"],
            "actual_return": round(actual_return, 3),
            "z_score": dev["z_score"],
            "deviation": dev["deviation"],
            "is_break": True,
            "classification": cls["classification"],
            "action": cls["action"],
            "pcr": oi_ctx["pcr"],
            "pcr_sentiment": oi_ctx["pcr_sentiment"],
            "oi_anomaly": oi_ctx["oi_anomaly"],
            "oi_change": oi_ctx["oi_change"],
            "phase_b_active": phase_b,
            "daily_std": exp["daily_std"],
            "drift_5d_mean": exp["drift_5d_mean"],
        }
        breaks.append(break_data)

    # Save today's breaks
    breaks_path.parent.mkdir(parents=True, exist_ok=True)
    breaks_path.write_text(json.dumps(breaks, indent=2, default=str), encoding="utf-8")

    # Log to history
    if breaks:
        _log_break_history(breaks, history_path)

    # Format and send alerts
    for b in breaks:
        msg = format_break_alert(b)
        print(msg)
        print()

        if send_telegram:
            try:
                from telegram_bot import send_message
                send_message(msg)
            except Exception as e:
                print(f"Telegram failed for {b['symbol']}: {e}")

    if not breaks:
        print(f"No correlation breaks detected. Regime: {current_regime} (day {regime_day})")

    return breaks


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Correlation Break Detector (Phase C)")
    parser.add_argument("--transition", type=str, help="Override transition key (e.g., NEUTRAL->RISK-OFF)")
    parser.add_argument("--regime", type=str, help="Current regime zone")
    parser.add_argument("--day", type=int, default=1, help="Day number in current regime")
    parser.add_argument("--no-telegram", action="store_true", help="Skip Telegram send")
    args = parser.parse_args()

    # Read regime from Phase B state if not overridden
    if args.transition and args.regime:
        transition_key = args.transition
        current_regime = args.regime
    else:
        state = _load_ranker_state()
        current_regime = state.get("last_zone", "NEUTRAL")
        # Infer transition from state — use last known transition
        # For live use, the transition key comes from ranker history
        if not args.transition:
            print(f"Current regime: {current_regime}")
            print("Use --transition and --regime for explicit control")
            print("Example: --transition NEUTRAL->RISK-OFF --regime RISK-OFF --day 2")
            sys.exit(0)
        transition_key = args.transition

    regime_day = args.day

    print(f"Scanning for correlation breaks: {transition_key} (day {regime_day})")
    print(f"{'=' * 60}")

    breaks = run_break_scan(
        transition_key=transition_key,
        regime_day=regime_day,
        current_regime=current_regime,
        send_telegram=not args.no_telegram,
    )

    print(f"\nDone. {len(breaks)} breaks detected.")
```

- [ ] **Step 4: Run all tests**

Run: `cd C:/Users/Claude_Anka/Documents/askanka.com/pipeline/autoresearch && C:/Python313/python.exe -m pytest tests/test_reverse_breaks.py -v`

Expected: 18 tests PASS

- [ ] **Step 5: Commit**

```bash
cd C:/Users/Claude_Anka/Documents/askanka.com/pipeline
git add -f autoresearch/reverse_regime_breaks.py autoresearch/tests/test_reverse_breaks.py
git commit -m "feat: correlation break scanner with OI context + CLI — Phase C complete"
```
