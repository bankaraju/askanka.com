# Daily Regime-Stock Ranker (Phase B) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a daily script that detects regime transitions, ranks stocks by historical drift from Phase A, and sends a morning recommendation via Telegram.

**Architecture:** Read today's regime from ETF composite, compare to stored yesterday's regime, look up Phase A profile on transition, rank and format output. Single script, state in JSON file, Telegram via existing `send_message()`.

**Tech Stack:** Python, pandas, numpy. Existing: `eodhd_client.py`, `telegram_bot.py`. Data: `reverse_regime_profile.json` (Phase A).

**Spec:** `docs/superpowers/specs/2026-04-14-daily-regime-stock-ranker-design.md`

---

### Task 1: Transition Detection + State Management

**Files:**
- Create: `C:/Users/Claude_Anka/Documents/askanka.com/pipeline/autoresearch/reverse_regime_ranker.py`
- Create: `C:/Users/Claude_Anka/Documents/askanka.com/pipeline/autoresearch/tests/test_reverse_ranker.py`

- [ ] **Step 1: Write the failing test — transition detection**

```python
# C:/Users/Claude_Anka/Documents/askanka.com/pipeline/autoresearch/tests/test_reverse_ranker.py

import json
import pytest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


class TestTransitionDetection:

    def test_detect_transition_new_state(self, tmp_path):
        from reverse_regime_ranker import detect_transition, load_state, save_state
        state_path = tmp_path / "state.json"
        
        # No prior state → first run, no transition
        transition = detect_transition("NEUTRAL", state_path)
        assert transition is None  # first run, no previous zone to compare
        
        # State should now be saved
        state = load_state(state_path)
        assert state["last_zone"] == "NEUTRAL"

    def test_detect_transition_same_zone(self, tmp_path):
        from reverse_regime_ranker import detect_transition, save_state
        state_path = tmp_path / "state.json"
        save_state(state_path, last_zone="NEUTRAL")
        
        transition = detect_transition("NEUTRAL", state_path)
        assert transition is None  # no change

    def test_detect_transition_zone_change(self, tmp_path):
        from reverse_regime_ranker import detect_transition, save_state
        state_path = tmp_path / "state.json"
        save_state(state_path, last_zone="NEUTRAL")
        
        transition = detect_transition("RISK-OFF", state_path)
        assert transition is not None
        assert transition["from"] == "NEUTRAL"
        assert transition["to"] == "RISK-OFF"
        assert transition["key"] == "NEUTRAL→RISK-OFF"

    def test_save_load_state_roundtrip(self, tmp_path):
        from reverse_regime_ranker import save_state, load_state
        state_path = tmp_path / "state.json"
        
        save_state(state_path, last_zone="CAUTION", active_recommendations=[
            {"symbol": "HAL", "expiry": "2026-04-19"}
        ])
        state = load_state(state_path)
        assert state["last_zone"] == "CAUTION"
        assert len(state["active_recommendations"]) == 1
        assert state["active_recommendations"][0]["symbol"] == "HAL"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd C:/Users/Claude_Anka/Documents/askanka.com/pipeline/autoresearch && C:/Python313/python.exe -m pytest tests/test_reverse_ranker.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'reverse_regime_ranker'`

- [ ] **Step 3: Implement transition detection and state management**

```python
# C:/Users/Claude_Anka/Documents/askanka.com/pipeline/autoresearch/reverse_regime_ranker.py
"""
Daily Regime-Stock Ranker (Phase B)

Detects regime transitions, ranks stocks by historical drift from Phase A,
and sends morning recommendation via Telegram.

Designed to run at 09:25 IST alongside the existing morning brief.
On most days (NEUTRAL, 77%), this script exits silently.
On transition days, it fires a ranked recommendation.
"""

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))

DATA_DIR = Path(__file__).parent.parent / "data"
PROFILE_PATH = Path(__file__).parent / "reverse_regime_profile.json"
STATE_PATH = DATA_DIR / "regime_ranker_state.json"
HISTORY_PATH = DATA_DIR / "regime_ranker_history.json"


def load_state(state_path: Path = STATE_PATH) -> dict:
    """Load ranker state from JSON. Returns empty dict if missing."""
    if state_path.exists():
        return json.loads(state_path.read_text(encoding="utf-8"))
    return {}


def save_state(
    state_path: Path = STATE_PATH,
    last_zone: str = "",
    active_recommendations: list = None,
):
    """Save ranker state to JSON."""
    state = load_state(state_path)
    if last_zone:
        state["last_zone"] = last_zone
    if active_recommendations is not None:
        state["active_recommendations"] = active_recommendations
    state["updated"] = datetime.now().isoformat()
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")


def detect_transition(today_zone: str, state_path: Path = STATE_PATH) -> dict | None:
    """Compare today's zone to stored previous zone.
    Returns transition dict if changed, None if same or first run.
    Always updates stored state.
    """
    state = load_state(state_path)
    prev_zone = state.get("last_zone")

    # Save current zone for next run
    save_state(state_path, last_zone=today_zone)

    if prev_zone is None:
        return None  # first run, no baseline

    if today_zone == prev_zone:
        return None  # no transition

    return {
        "from": prev_zone,
        "to": today_zone,
        "key": f"{prev_zone}→{today_zone}",
        "date": datetime.now().strftime("%Y-%m-%d"),
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd C:/Users/Claude_Anka/Documents/askanka.com/pipeline/autoresearch && C:/Python313/python.exe -m pytest tests/test_reverse_ranker.py -v`

Expected: 4 tests PASS

- [ ] **Step 5: Commit**

```bash
cd C:/Users/Claude_Anka/Documents/askanka.com/pipeline
git add -f autoresearch/reverse_regime_ranker.py autoresearch/tests/test_reverse_ranker.py
git commit -m "feat: regime transition detection + state management (Phase B)"
```

---

### Task 2: Profile Lookup + Stock Ranking

**Files:**
- Modify: `C:/Users/Claude_Anka/Documents/askanka.com/pipeline/autoresearch/reverse_regime_ranker.py`
- Modify: `C:/Users/Claude_Anka/Documents/askanka.com/pipeline/autoresearch/tests/test_reverse_ranker.py`

- [ ] **Step 1: Write the failing test — profile lookup and ranking**

Append to test file:

```python
class TestProfileLookup:

    @pytest.fixture
    def sample_profile(self, tmp_path):
        """Create a minimal Phase A profile for testing."""
        profile = {
            "stocks": {
                "HAL": {
                    "NEUTRAL→EUPHORIA": {
                        "episodes": 8, "gap_mean": 0.87, "drift_5d_mean": 5.87,
                        "hit_rate": 71.4, "persistence": 71.4, "tradeable": True,
                        "drift_1d_mean": 1.2, "drift_3d_mean": 3.5,
                        "gap_std": 0.5, "drift_5d_std": 2.1,
                    },
                },
                "SIEMENS": {
                    "NEUTRAL→RISK-OFF": {
                        "episodes": 14, "gap_mean": -0.03, "drift_5d_mean": -3.30,
                        "hit_rate": 71.4, "persistence": 53.8, "tradeable": True,
                        "drift_1d_mean": -0.8, "drift_3d_mean": -2.1,
                        "gap_std": 0.4, "drift_5d_std": 1.8,
                    },
                },
                "TCS": {
                    "NEUTRAL→RISK-OFF": {
                        "episodes": 14, "gap_mean": -0.5, "drift_5d_mean": -1.2,
                        "hit_rate": 57.1, "persistence": 50.0, "tradeable": True,
                        "drift_1d_mean": -0.3, "drift_3d_mean": -0.8,
                        "gap_std": 0.3, "drift_5d_std": 1.0,
                    },
                },
                "SUNPHARMA": {
                    "NEUTRAL→RISK-OFF": {
                        "episodes": 14, "gap_mean": 0.1, "drift_5d_mean": 0.57,
                        "hit_rate": 57.1, "persistence": 50.0, "tradeable": True,
                        "drift_1d_mean": 0.2, "drift_3d_mean": 0.4,
                        "gap_std": 0.2, "drift_5d_std": 0.8,
                    },
                },
            },
            "baskets": {
                "Pharma": {
                    "NEUTRAL→RISK-OFF": {
                        "episodes": 14, "gap_mean": 0.08, "drift_5d_mean": 0.57,
                        "hit_rate": 57.1, "persistence": 50.0, "tradeable": True,
                        "drift_1d_mean": 0.2, "drift_3d_mean": 0.3,
                        "gap_std": 0.1, "drift_5d_std": 0.6,
                    },
                },
                "Conglomerate": {
                    "NEUTRAL→RISK-OFF": {
                        "episodes": 14, "gap_mean": -0.08, "drift_5d_mean": -2.08,
                        "hit_rate": 78.6, "persistence": 50.0, "tradeable": True,
                        "drift_1d_mean": -0.5, "drift_3d_mean": -1.3,
                        "gap_std": 0.3, "drift_5d_std": 1.5,
                    },
                },
            },
            "tradeable_signals": [],
            "meta": {"regime_episodes": {"RISK-OFF": 17, "NEUTRAL": 120}},
            "gate_pass": True,
        }
        path = tmp_path / "profile.json"
        path.write_text(json.dumps(profile, indent=2))
        return path

    def test_lookup_transition_signals(self, sample_profile):
        from reverse_regime_ranker import lookup_transition_signals
        
        signals = lookup_transition_signals("NEUTRAL→RISK-OFF", sample_profile)
        assert len(signals) >= 3  # SIEMENS, TCS, SUNPHARMA + baskets
        
        # Should be sorted by abs(drift_5d_mean) descending
        drifts = [abs(s["drift_5d_mean"]) for s in signals]
        assert drifts == sorted(drifts, reverse=True)

    def test_lookup_returns_longs_and_shorts(self, sample_profile):
        from reverse_regime_ranker import lookup_transition_signals
        
        signals = lookup_transition_signals("NEUTRAL→RISK-OFF", sample_profile)
        longs = [s for s in signals if s["drift_5d_mean"] > 0]
        shorts = [s for s in signals if s["drift_5d_mean"] < 0]
        assert len(longs) > 0, "Expected at least one long"
        assert len(shorts) > 0, "Expected at least one short"

    def test_lookup_unknown_transition(self, sample_profile):
        from reverse_regime_ranker import lookup_transition_signals
        
        signals = lookup_transition_signals("EUPHORIA→RISK-OFF", sample_profile)
        assert signals == []

    def test_confidence_level(self):
        from reverse_regime_ranker import compute_confidence
        
        assert compute_confidence(episodes=25, hit_rate=70.0) == "HIGH"
        assert compute_confidence(episodes=14, hit_rate=60.0) == "MEDIUM"
        assert compute_confidence(episodes=4, hit_rate=55.0) == "LOW"
        assert compute_confidence(episodes=20, hit_rate=50.0) == "LOW"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd C:/Users/Claude_Anka/Documents/askanka.com/pipeline/autoresearch && C:/Python313/python.exe -m pytest tests/test_reverse_ranker.py -v -k "ProfileLookup"`

Expected: FAIL with `ImportError: cannot import name 'lookup_transition_signals'`

- [ ] **Step 3: Implement profile lookup and ranking**

Add to `reverse_regime_ranker.py`:

```python
def lookup_transition_signals(
    transition_key: str,
    profile_path: Path = PROFILE_PATH,
    min_hit_rate: float = 55.0,
    min_persistence: float = 50.0,
    min_episodes: int = 5,
) -> list[dict]:
    """Look up tradeable signals for a given transition from Phase A profile.
    Returns list sorted by abs(drift_5d_mean) descending.
    """
    if not profile_path.exists():
        return []

    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    signals = []

    for source_key, source_type in [("stocks", "stock"), ("baskets", "basket")]:
        source_data = profile.get(source_key, {})
        for symbol, transitions in source_data.items():
            if transition_key not in transitions:
                continue
            data = transitions[transition_key]
            if (
                data.get("tradeable")
                and data.get("hit_rate", 0) >= min_hit_rate
                and data.get("persistence", 0) >= min_persistence
                and data.get("episodes", 0) >= min_episodes
            ):
                signals.append({
                    "symbol": symbol,
                    "type": source_type,
                    **data,
                })

    signals.sort(key=lambda x: abs(x["drift_5d_mean"]), reverse=True)
    return signals


def compute_confidence(episodes: int, hit_rate: float) -> str:
    """Compute confidence level based on episode count and hit rate."""
    if episodes >= 20 and hit_rate >= 65.0:
        return "HIGH"
    if episodes >= 10 and hit_rate >= 55.0:
        return "MEDIUM"
    return "LOW"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd C:/Users/Claude_Anka/Documents/askanka.com/pipeline/autoresearch && C:/Python313/python.exe -m pytest tests/test_reverse_ranker.py -v`

Expected: 8 tests PASS

- [ ] **Step 5: Commit**

```bash
cd C:/Users/Claude_Anka/Documents/askanka.com/pipeline
git add -f autoresearch/reverse_regime_ranker.py autoresearch/tests/test_reverse_ranker.py
git commit -m "feat: Phase A profile lookup + stock ranking + confidence levels"
```

---

### Task 3: Recommendation Formatter + Telegram Output

**Files:**
- Modify: `C:/Users/Claude_Anka/Documents/askanka.com/pipeline/autoresearch/reverse_regime_ranker.py`
- Modify: `C:/Users/Claude_Anka/Documents/askanka.com/pipeline/autoresearch/tests/test_reverse_ranker.py`

- [ ] **Step 1: Write the failing test — format recommendation**

Append to test file:

```python
class TestFormatRecommendation:

    def test_format_telegram_message(self):
        from reverse_regime_ranker import format_recommendation
        
        transition = {"from": "NEUTRAL", "to": "RISK-OFF", "key": "NEUTRAL→RISK-OFF", "date": "2026-04-14"}
        signals = [
            {"symbol": "SIEMENS", "type": "stock", "drift_5d_mean": -3.30, "gap_mean": -0.03,
             "hit_rate": 71.4, "persistence": 53.8, "episodes": 14,
             "drift_1d_mean": -0.8, "drift_3d_mean": -2.1, "tradeable": True,
             "gap_std": 0.4, "drift_5d_std": 1.8},
            {"symbol": "SUNPHARMA", "type": "stock", "drift_5d_mean": 0.57, "gap_mean": 0.1,
             "hit_rate": 57.1, "persistence": 50.0, "episodes": 14,
             "drift_1d_mean": 0.2, "drift_3d_mean": 0.4, "tradeable": True,
             "gap_std": 0.2, "drift_5d_std": 0.8},
        ]
        
        msg = format_recommendation(transition, signals)
        assert "NEUTRAL → RISK-OFF" in msg
        assert "SIEMENS" in msg
        assert "SUNPHARMA" in msg
        assert "Hold period: 5 trading days" in msg

    def test_format_empty_signals(self):
        from reverse_regime_ranker import format_recommendation
        
        transition = {"from": "NEUTRAL", "to": "RISK-OFF", "key": "NEUTRAL→RISK-OFF", "date": "2026-04-14"}
        msg = format_recommendation(transition, [])
        assert "No tradeable signals" in msg

    def test_build_active_recommendation(self):
        from reverse_regime_ranker import build_active_recommendations
        
        signals = [
            {"symbol": "HAL", "type": "stock", "drift_5d_mean": 5.87, "hit_rate": 71.4,
             "episodes": 8, "gap_mean": 0.87, "persistence": 71.4,
             "drift_1d_mean": 1.2, "drift_3d_mean": 3.5, "tradeable": True,
             "gap_std": 0.5, "drift_5d_std": 2.1},
        ]
        recs = build_active_recommendations(signals, "2026-04-14")
        assert len(recs) == 1
        assert recs[0]["symbol"] == "HAL"
        assert recs[0]["entry_date"] == "2026-04-14"
        assert recs[0]["expiry_date"] == "2026-04-21"  # +7 calendar days ≈ 5 trading days
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd C:/Users/Claude_Anka/Documents/askanka.com/pipeline/autoresearch && C:/Python313/python.exe -m pytest tests/test_reverse_ranker.py -v -k "FormatRecommendation"`

Expected: FAIL with `ImportError: cannot import name 'format_recommendation'`

- [ ] **Step 3: Implement formatter and recommendation builder**

Add to `reverse_regime_ranker.py`:

```python
def format_recommendation(transition: dict, signals: list[dict]) -> str:
    """Format a Telegram-ready recommendation message."""
    if not signals:
        return (
            f"REGIME TRANSITION: {transition['from']} → {transition['to']}\n"
            f"Date: {transition['date']}\n\n"
            f"No tradeable signals found for this transition type."
        )

    longs = [s for s in signals if s["drift_5d_mean"] > 0]
    shorts = [s for s in signals if s["drift_5d_mean"] < 0]

    lines = [
        f"🔄 REGIME TRANSITION: {transition['from']} → {transition['to']}",
        f"Detected: {transition['date']}",
        "",
    ]

    if longs:
        lines.append("📈 TOP LONGS (historical drift > gap, persistent):")
        for i, s in enumerate(longs[:5], 1):
            conf = compute_confidence(s["episodes"], s["hit_rate"])
            lines.append(
                f"  {i}. {s['symbol']} — "
                f"{s['drift_5d_mean']:+.2f}% drift 5d, "
                f"{s['hit_rate']:.0f}% hit, "
                f"{s['episodes']} eps [{conf}]"
            )
        lines.append("")

    if shorts:
        lines.append("📉 TOP SHORTS:")
        for i, s in enumerate(shorts[:5], 1):
            conf = compute_confidence(s["episodes"], s["hit_rate"])
            lines.append(
                f"  {i}. {s['symbol']} — "
                f"{s['drift_5d_mean']:+.2f}% drift 5d, "
                f"{s['hit_rate']:.0f}% hit, "
                f"{s['episodes']} eps [{conf}]"
            )
        lines.append("")

    # Best spread opportunity
    if longs and shorts:
        best_long = longs[0]
        best_short = shorts[0]
        spread_drift = best_long["drift_5d_mean"] - best_short["drift_5d_mean"]
        min_hit = min(best_long["hit_rate"], best_short["hit_rate"])
        lines.append(
            f"📊 SPREAD: Long {best_long['symbol']} / Short {best_short['symbol']}"
        )
        lines.append(
            f"  Expected: {spread_drift:+.2f}% net, {min_hit:.0f}% min hit"
        )
        lines.append("")

    lines.append(f"Hold period: 5 trading days | Stop: 2x gap")
    return "\n".join(lines)


def build_active_recommendations(signals: list[dict], date_str: str) -> list[dict]:
    """Build list of active recommendations with expiry dates."""
    entry_date = datetime.strptime(date_str, "%Y-%m-%d")
    expiry_date = entry_date + timedelta(days=7)  # 7 calendar ≈ 5 trading days

    recs = []
    for s in signals[:10]:  # cap at 10 active
        recs.append({
            "symbol": s["symbol"],
            "type": s["type"],
            "drift_5d_expected": s["drift_5d_mean"],
            "hit_rate": s["hit_rate"],
            "episodes": s["episodes"],
            "entry_date": date_str,
            "expiry_date": expiry_date.strftime("%Y-%m-%d"),
            "direction": "LONG" if s["drift_5d_mean"] > 0 else "SHORT",
        })
    return recs
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd C:/Users/Claude_Anka/Documents/askanka.com/pipeline/autoresearch && C:/Python313/python.exe -m pytest tests/test_reverse_ranker.py -v`

Expected: 11 tests PASS

- [ ] **Step 5: Commit**

```bash
cd C:/Users/Claude_Anka/Documents/askanka.com/pipeline
git add -f autoresearch/reverse_regime_ranker.py autoresearch/tests/test_reverse_ranker.py
git commit -m "feat: recommendation formatter + Telegram output + active rec builder"
```

---

### Task 4: Main Orchestrator + History Logging

**Files:**
- Modify: `C:/Users/Claude_Anka/Documents/askanka.com/pipeline/autoresearch/reverse_regime_ranker.py`
- Modify: `C:/Users/Claude_Anka/Documents/askanka.com/pipeline/autoresearch/tests/test_reverse_ranker.py`

- [ ] **Step 1: Write the failing test — main orchestrator**

Append to test file:

```python
class TestOrchestrator:

    def test_run_ranker_no_transition(self, tmp_path):
        from reverse_regime_ranker import run_ranker
        
        state_path = tmp_path / "state.json"
        # Pre-seed state with NEUTRAL
        state_path.write_text(json.dumps({"last_zone": "NEUTRAL"}))
        
        result = run_ranker(
            today_zone="NEUTRAL",
            state_path=state_path,
            profile_path=tmp_path / "dummy.json",  # doesn't matter, no transition
            send_telegram=False,
        )
        assert result["transition"] is None
        assert result["signals_count"] == 0

    def test_run_ranker_with_transition(self, tmp_path):
        from reverse_regime_ranker import run_ranker
        
        state_path = tmp_path / "state.json"
        state_path.write_text(json.dumps({"last_zone": "NEUTRAL"}))
        
        # Create minimal profile
        profile = {
            "stocks": {
                "HAL": {
                    "NEUTRAL→EUPHORIA": {
                        "episodes": 8, "gap_mean": 0.87, "drift_5d_mean": 5.87,
                        "hit_rate": 71.4, "persistence": 71.4, "tradeable": True,
                        "drift_1d_mean": 1.2, "drift_3d_mean": 3.5,
                        "gap_std": 0.5, "drift_5d_std": 2.1,
                    },
                },
            },
            "baskets": {},
            "meta": {},
            "tradeable_signals": [],
            "gate_pass": True,
        }
        profile_path = tmp_path / "profile.json"
        profile_path.write_text(json.dumps(profile))
        
        history_path = tmp_path / "history.json"
        
        result = run_ranker(
            today_zone="EUPHORIA",
            state_path=state_path,
            profile_path=profile_path,
            history_path=history_path,
            send_telegram=False,
        )
        assert result["transition"]["key"] == "NEUTRAL→EUPHORIA"
        assert result["signals_count"] >= 1
        assert result["message"] is not None
        assert "HAL" in result["message"]
        
        # History should be logged
        assert history_path.exists()
        history = json.loads(history_path.read_text())
        assert len(history) == 1

    def test_expire_old_recommendations(self, tmp_path):
        from reverse_regime_ranker import expire_recommendations
        
        recs = [
            {"symbol": "HAL", "expiry_date": "2026-04-10"},  # expired
            {"symbol": "BEL", "expiry_date": "2026-04-20"},  # active
        ]
        active = expire_recommendations(recs, today="2026-04-14")
        assert len(active) == 1
        assert active[0]["symbol"] == "BEL"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd C:/Users/Claude_Anka/Documents/askanka.com/pipeline/autoresearch && C:/Python313/python.exe -m pytest tests/test_reverse_ranker.py -v -k "Orchestrator"`

Expected: FAIL with `ImportError: cannot import name 'run_ranker'`

- [ ] **Step 3: Implement orchestrator, history logging, and expiry**

Add to `reverse_regime_ranker.py`:

```python
def expire_recommendations(recs: list[dict], today: str = None) -> list[dict]:
    """Remove expired recommendations."""
    if today is None:
        today = datetime.now().strftime("%Y-%m-%d")
    return [r for r in recs if r.get("expiry_date", "") >= today]


def log_history(
    transition: dict,
    signals: list[dict],
    message: str,
    history_path: Path = HISTORY_PATH,
):
    """Append this recommendation to history log."""
    history = []
    if history_path.exists():
        history = json.loads(history_path.read_text(encoding="utf-8"))

    history.append({
        "date": transition["date"],
        "transition": transition["key"],
        "signals_count": len(signals),
        "top_longs": [s["symbol"] for s in signals if s["drift_5d_mean"] > 0][:5],
        "top_shorts": [s["symbol"] for s in signals if s["drift_5d_mean"] < 0][:5],
        "timestamp": datetime.now().isoformat(),
    })

    history_path.parent.mkdir(parents=True, exist_ok=True)
    history_path.write_text(json.dumps(history, indent=2), encoding="utf-8")


def run_ranker(
    today_zone: str,
    state_path: Path = STATE_PATH,
    profile_path: Path = PROFILE_PATH,
    history_path: Path = HISTORY_PATH,
    send_telegram: bool = True,
) -> dict:
    """Main orchestrator. Returns result dict."""
    today_str = datetime.now().strftime("%Y-%m-%d")

    # Step 1: Detect transition
    transition = detect_transition(today_zone, state_path)

    if transition is None:
        # Expire old recommendations
        state = load_state(state_path)
        active = expire_recommendations(
            state.get("active_recommendations", []), today_str
        )
        if active != state.get("active_recommendations", []):
            save_state(state_path, active_recommendations=active)

        return {"transition": None, "signals_count": 0, "message": None}

    # Step 2: Look up signals
    signals = lookup_transition_signals(transition["key"], profile_path)

    # Step 3: Format message
    message = format_recommendation(transition, signals)

    # Step 4: Build active recommendations
    new_recs = build_active_recommendations(signals, today_str)
    state = load_state(state_path)
    existing = expire_recommendations(
        state.get("active_recommendations", []), today_str
    )
    save_state(state_path, active_recommendations=existing + new_recs)

    # Step 5: Log history
    log_history(transition, signals, message, history_path)

    # Step 6: Send Telegram
    if send_telegram and signals:
        try:
            from telegram_bot import send_message
            send_message(message)
            print(f"Telegram sent: {transition['key']} ({len(signals)} signals)")
        except Exception as e:
            print(f"Telegram failed: {e}")

    # Step 7: Print to console
    print(message)

    return {
        "transition": transition,
        "signals_count": len(signals),
        "message": message,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd C:/Users/Claude_Anka/Documents/askanka.com/pipeline/autoresearch && C:/Python313/python.exe -m pytest tests/test_reverse_ranker.py -v`

Expected: 14 tests PASS

- [ ] **Step 5: Commit**

```bash
cd C:/Users/Claude_Anka/Documents/askanka.com/pipeline
git add -f autoresearch/reverse_regime_ranker.py autoresearch/tests/test_reverse_ranker.py
git commit -m "feat: ranker orchestrator + history logging + recommendation expiry"
```

---

### Task 5: CLI Entry Point + Today's Regime Fetch

**Files:**
- Modify: `C:/Users/Claude_Anka/Documents/askanka.com/pipeline/autoresearch/reverse_regime_ranker.py`

- [ ] **Step 1: Write the failing test — get today's regime**

Append to test file:

```python
class TestCLI:

    def test_get_today_regime_from_file(self, tmp_path):
        from reverse_regime_ranker import get_today_regime
        
        regime_file = tmp_path / "today_regime.json"
        regime_file.write_text(json.dumps({
            "zone": "RISK-OFF",
            "score": -8.5,
            "confidence": 45,
        }))
        
        zone = get_today_regime(regime_file=regime_file)
        assert zone == "RISK-OFF"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd C:/Users/Claude_Anka/Documents/askanka.com/pipeline/autoresearch && C:/Python313/python.exe -m pytest tests/test_reverse_ranker.py::TestCLI -v`

Expected: FAIL with `ImportError: cannot import name 'get_today_regime'`

- [ ] **Step 3: Implement get_today_regime and __main__ block**

Add to `reverse_regime_ranker.py`:

```python
REGIME_FILE = Path(__file__).parent / "today_regime.json"


def get_today_regime(regime_file: Path = REGIME_FILE) -> str:
    """Get today's regime zone. Reads from today_regime.json if available,
    otherwise reconstructs from ETF composite (slow, ~60s).
    """
    # Try reading cached regime first
    if regime_file.exists():
        data = json.loads(regime_file.read_text(encoding="utf-8"))
        zone = data.get("zone", data.get("today_zone"))
        if zone:
            print(f"Regime from cache: {zone}")
            return zone

    # Fallback: reconstruct from ETF composite
    print("No cached regime found, reconstructing from ETFs (slow)...")
    from reverse_regime_analysis import reconstruct_regime_labels
    zones, _ = reconstruct_regime_labels()
    zone = str(zones.iloc[-1])
    print(f"Regime from ETF composite: {zone}")
    return zone


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Daily Regime-Stock Ranker (Phase B)")
    parser.add_argument("--zone", type=str, help="Override today's regime zone (for testing)")
    parser.add_argument("--no-telegram", action="store_true", help="Skip Telegram send")
    args = parser.parse_args()

    if args.zone:
        today_zone = args.zone.upper()
        print(f"Using override zone: {today_zone}")
    else:
        today_zone = get_today_regime()

    result = run_ranker(
        today_zone=today_zone,
        send_telegram=not args.no_telegram,
    )

    if result["transition"] is None:
        print(f"No transition detected. Current zone: {today_zone}. Exiting.")
    else:
        print(f"\nDone. {result['signals_count']} signals for {result['transition']['key']}")
```

- [ ] **Step 4: Run all tests**

Run: `cd C:/Users/Claude_Anka/Documents/askanka.com/pipeline/autoresearch && C:/Python313/python.exe -m pytest tests/test_reverse_ranker.py -v`

Expected: 15 tests PASS

- [ ] **Step 5: Test CLI with a simulated transition**

Run: `cd C:/Users/Claude_Anka/Documents/askanka.com/pipeline/autoresearch && PYTHONIOENCODING=utf-8 C:/Python313/python.exe reverse_regime_ranker.py --zone EUPHORIA --no-telegram`

Expected: First run saves EUPHORIA as state. No transition (first run). Run again:

Run: `PYTHONIOENCODING=utf-8 C:/Python313/python.exe reverse_regime_ranker.py --zone RISK-OFF --no-telegram`

Expected: Detects EUPHORIA→RISK-OFF transition, prints ranked recommendation.

- [ ] **Step 6: Commit**

```bash
cd C:/Users/Claude_Anka/Documents/askanka.com/pipeline
git add -f autoresearch/reverse_regime_ranker.py autoresearch/tests/test_reverse_ranker.py
git commit -m "feat: CLI entry point + today's regime fetch — Phase B complete"
```
