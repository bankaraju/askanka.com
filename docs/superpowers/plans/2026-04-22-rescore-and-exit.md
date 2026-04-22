# Live Rescore + Conviction-Decay Exit

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Every intraday cycle, re-run the entry scorecard on each open signal using today's live data. Store `current_score` alongside the frozen `entry_score`. When the thesis has measurably decayed, auto-close the trade via a new 4th exit rule (alongside trail/daily/2-day stops).

**Architecture:**
A new `pipeline/signal_rescorer.py` script runs every 15 min inside `intraday_scan.bat`. For each open signal, it calls the existing `signal_enrichment.enrich_signal()` + `gate_signal()` with today's fresh trust/breaks/profile/OI inputs and attaches `signal["rescore"] = {current_score, score_delta, rescored_at, gate_reason_current}` to the signal dict in `open_signals.json`. `signal_tracker.check_signal_status()` gains two new exit branches: **CONVICTION_DECAY** (conviction score drops below absolute 45 AND relative drop > 20 points) and **Z_CROSS** (for `CORRELATION_BREAK` trades, the symbol's signed break direction has flipped — thesis has closed). UI shows `85 → 52` live.

**Exit thresholds (approved 2026-04-22):**
- CONVICTION_DECAY: `current_score < 45` AND `(entry_score - current_score) > 20` (both required)
- Z_CROSS: for `source == "CORRELATION_BREAK"` only — symbol no longer appears as the same-direction break in today's `correlation_breaks.json`

**Tech Stack:** Python 3.11, pytest, vanilla JS.

---

## File Structure

- **Modify** `pipeline/signal_enrichment.py` — extract `rescore_signal(signal, trust, breaks, profile, oi) -> dict` that returns the rescore-payload dict without mutating the signal.
- **Create** `pipeline/signal_rescorer.py` — standalone 15-min script that loads open signals, calls `rescore_signal` per entry, writes back to `open_signals.json` atomically.
- **Create** `pipeline/tests/test_signal_rescorer.py`
- **Modify** `pipeline/tests/test_signal_enrichment.py` — add test for the new `rescore_signal` function.
- **Modify** `pipeline/signal_tracker.py::check_signal_status()` — add CONVICTION_DECAY + Z_CROSS exits AFTER existing trail/daily/2-day logic.
- **Modify** `pipeline/tests/test_signal_tracker_atr.py` — extend with conviction-decay + z-cross tests.
- **Modify** `pipeline/scripts/intraday_scan.bat` — add `python -X utf8 signal_rescorer.py` after `msi_refresh.py` (msi_refresh landed earlier today as part of the MSI plan).
- **Modify** `pipeline/config/anka_inventory.json` — add `pipeline/data/signals/open_signals.json` to intraday task outputs (if not already there).
- **Modify** `pipeline/website_exporter.py::_build_live_status()` — lift `rescore.current_score` and `score_delta` into the per-position public JSON.
- **Modify** `pipeline/terminal/static/js/components/positions-table.js` — render `85 → 52` next to the position name or in a new column.
- **Modify** `docs/SYSTEM_OPERATIONS_MANUAL.md` — paragraph describing the rescore + new exits.
- **Create** memory `project_rescore_and_exit.md` + MEMORY.md pointer.

---

## Task 1: Extract pure `rescore_signal()` function

**Files:** `pipeline/signal_enrichment.py`, `pipeline/tests/test_signal_enrichment.py`.

- [ ] **Step 1: Failing test**

Append to `pipeline/tests/test_signal_enrichment.py`:

```python
def test_rescore_signal_returns_current_score_without_mutating_input(isolated_trust_dir):
    """rescore_signal must return a dict with current_score / score_delta /
    rescored_at / gate_reason_current, and must NOT mutate the input signal."""
    from pipeline.signal_enrichment import rescore_signal
    sig = {
        "signal_id": "BRK-TEST",
        "source": "CORRELATION_BREAK",
        "spread_name": "Phase C: BHEL REGIME_LAG",
        "long_legs": [{"ticker": "BHEL", "yf": "BHEL.NS", "price": 318.5, "weight": 1.0}],
        "short_legs": [],
        "conviction_score": 78,
        "entry_score": 78,
    }
    frozen_before = dict(sig)
    result = rescore_signal(sig, trust={}, breaks={}, profile={}, oi={})
    # Contract
    assert "current_score" in result
    assert "score_delta" in result
    assert "rescored_at" in result
    assert "gate_reason_current" in result
    # Non-mutation
    assert sig == frozen_before, "rescore_signal must not mutate its input"
    # score_delta sign convention: entry - current. Positive means thesis decayed.
    assert result["score_delta"] == 78 - result["current_score"]
```

Run: `pytest pipeline/tests/test_signal_enrichment.py::test_rescore_signal_returns_current_score_without_mutating_input -v` → FAIL (ImportError).

- [ ] **Step 2: Implement `rescore_signal`**

Read `pipeline/signal_enrichment.py` around the existing `enrich_signal` (~line 293) and `gate_signal` function to understand their signatures. Then add (alphabetically near `gate_signal`, or at the bottom):

```python
def rescore_signal(
    signal: Dict[str, Any],
    trust: Dict,
    breaks: Dict,
    profile: Dict,
    oi: Dict,
) -> Dict[str, Any]:
    """Recompute the conviction score for an already-open signal using
    today's enrichment inputs. Returns a rescore payload without mutating
    the input signal.

    Use case: every 15 min intraday, compare the live score to the frozen
    entry score to detect thesis decay (conviction-decay auto-exit).
    """
    from datetime import datetime, timezone, timedelta
    ist = timezone(timedelta(hours=5, minutes=30))
    # Work on a copy so no mutation leaks back
    working = {**signal}
    working.pop("rescore", None)  # drop any prior rescore so enrich sees a clean slate
    enriched = enrich_signal(working, trust, breaks, profile, oi)
    blocked, reason, score = gate_signal(enriched)
    entry_score = signal.get("entry_score") or signal.get("conviction_score") or 0
    return {
        "current_score": int(round(score)),
        "score_delta": int(round(entry_score - score)),
        "gate_reason_current": reason,
        "gate_blocked_current": blocked,
        "rescored_at": datetime.now(ist).isoformat(),
    }
```

If `enrich_signal` or `gate_signal` expect keys that aren't on the incoming signal, catch and return a safe fallback:

```python
    try:
        enriched = enrich_signal(working, trust, breaks, profile, oi)
        blocked, reason, score = gate_signal(enriched)
    except Exception as exc:
        return {
            "current_score": None,
            "score_delta": None,
            "gate_reason_current": f"rescore_failed: {exc.__class__.__name__}",
            "gate_blocked_current": False,
            "rescored_at": datetime.now(ist).isoformat(),
        }
```

(Wrap the two enrich/gate calls together.)

Run the test → PASS.

- [ ] **Step 3: Commit**

```bash
git add pipeline/signal_enrichment.py pipeline/tests/test_signal_enrichment.py
git commit -m "feat(signal_enrichment): add rescore_signal() returning live current_score"
```

---

## Task 2: `pipeline/signal_rescorer.py` + scheduler wire-up

**Files:** `pipeline/signal_rescorer.py`, `pipeline/tests/test_signal_rescorer.py`, `pipeline/scripts/intraday_scan.bat`.

- [ ] **Step 1: Failing tests**

Create `pipeline/tests/test_signal_rescorer.py`:

```python
import json
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import signal_rescorer


def _make_open_signals(path: Path, signals: list):
    path.write_text(json.dumps(signals, indent=2), encoding="utf-8")


def test_happy_path_attaches_rescore_to_each_signal(tmp_path, monkeypatch):
    open_file = tmp_path / "open_signals.json"
    _make_open_signals(open_file, [
        {"signal_id": "S1", "conviction_score": 80, "source": "SPREAD",
         "spread_name": "Defence vs IT", "long_legs": [], "short_legs": []},
        {"signal_id": "S2", "conviction_score": 70, "source": "CORRELATION_BREAK",
         "spread_name": "Phase C: BHEL", "long_legs": [], "short_legs": []},
    ])
    monkeypatch.setattr(signal_rescorer, "OPEN_SIGNALS_FILE", open_file)
    # Mock enrichment loads so nothing touches the real data dir
    monkeypatch.setattr(signal_rescorer, "_load_enrichment_inputs",
                        lambda: ({}, {}, {}, {}))
    # Mock rescore_signal so scores are deterministic
    def fake_rescore(sig, trust, breaks, profile, oi):
        return {"current_score": 55, "score_delta": 15 if sig["signal_id"] == "S1" else -5,
                "gate_reason_current": "ok", "gate_blocked_current": False,
                "rescored_at": "2026-04-22T11:30:00+05:30"}
    monkeypatch.setattr(signal_rescorer, "rescore_signal", fake_rescore)

    rc = signal_rescorer.main()
    assert rc == 0

    written = json.loads(open_file.read_text())
    assert written[0]["rescore"]["current_score"] == 55
    assert written[0]["rescore"]["score_delta"] == 15  # entry 80 - current 55
    assert written[1]["rescore"]["current_score"] == 55


def test_empty_open_signals_is_noop(tmp_path, monkeypatch):
    open_file = tmp_path / "open_signals.json"
    _make_open_signals(open_file, [])
    monkeypatch.setattr(signal_rescorer, "OPEN_SIGNALS_FILE", open_file)
    monkeypatch.setattr(signal_rescorer, "_load_enrichment_inputs", lambda: ({}, {}, {}, {}))
    rc = signal_rescorer.main()
    assert rc == 0
    assert json.loads(open_file.read_text()) == []


def test_missing_file_exits_quietly(tmp_path, monkeypatch):
    open_file = tmp_path / "does_not_exist.json"
    monkeypatch.setattr(signal_rescorer, "OPEN_SIGNALS_FILE", open_file)
    assert signal_rescorer.main() == 2


def test_rescore_failure_leaves_prior_rescore_intact(tmp_path, monkeypatch):
    """If rescore raises for one signal, that signal keeps its previous rescore;
    other signals still get fresh scores."""
    open_file = tmp_path / "open_signals.json"
    _make_open_signals(open_file, [
        {"signal_id": "S1", "conviction_score": 80, "source": "SPREAD",
         "long_legs": [], "short_legs": [], "rescore": {"current_score": 60}},
        {"signal_id": "S2", "conviction_score": 70, "source": "SPREAD",
         "long_legs": [], "short_legs": []},
    ])
    monkeypatch.setattr(signal_rescorer, "OPEN_SIGNALS_FILE", open_file)
    monkeypatch.setattr(signal_rescorer, "_load_enrichment_inputs", lambda: ({}, {}, {}, {}))

    def flaky_rescore(sig, *a, **kw):
        if sig["signal_id"] == "S1":
            raise RuntimeError("boom")
        return {"current_score": 55, "score_delta": 15,
                "gate_reason_current": "ok", "gate_blocked_current": False,
                "rescored_at": "2026-04-22T11:30:00+05:30"}
    monkeypatch.setattr(signal_rescorer, "rescore_signal", flaky_rescore)

    rc = signal_rescorer.main()
    assert rc == 0  # script still succeeds; one-signal failure is soft

    written = json.loads(open_file.read_text())
    assert written[0]["rescore"]["current_score"] == 60  # untouched from prior
    assert written[1]["rescore"]["current_score"] == 55  # freshly written
```

- [ ] **Step 2: Implement `pipeline/signal_rescorer.py`**

```python
"""Live rescore — runs every 15 min during market hours.

Recomputes the conviction score for every open signal using today's fresh
trust/breaks/profile/OI enrichment inputs, and stores the result on the
signal dict as `rescore = {current_score, score_delta, gate_reason_current,
rescored_at}`.

The signal tracker's check_signal_status() consumes this field to trigger
the CONVICTION_DECAY exit (score < 45 AND score_delta > 20) and, for
CORRELATION_BREAK signals, the Z_CROSS exit.

Exit codes:
    0 — success (even if some signals failed to rescore)
    2 — soft failure: open_signals.json missing / unreadable
"""
from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from signal_enrichment import (  # noqa: E402
    load_trust_scores, load_correlation_breaks, load_regime_profile,
    load_oi_anomalies, rescore_signal,
)

IST = timezone(timedelta(hours=5, minutes=30))
OPEN_SIGNALS_FILE = _HERE / "data" / "signals" / "open_signals.json"

log = logging.getLogger("anka.signal_rescorer")
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s %(message)s")


def _load_enrichment_inputs():
    """Load the four enrichment inputs — factored out for test monkeypatching."""
    return (load_trust_scores(), load_correlation_breaks(),
            load_regime_profile(), load_oi_anomalies())


def _atomic_write(path: Path, data) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def main() -> int:
    if not OPEN_SIGNALS_FILE.exists():
        log.warning("open_signals.json not found — nothing to rescore")
        return 2

    try:
        signals = json.loads(OPEN_SIGNALS_FILE.read_text(encoding="utf-8"))
    except Exception as exc:
        log.warning("failed to read open_signals.json: %s", exc)
        return 2

    if not signals:
        log.info("no open signals — nothing to rescore")
        return 0

    trust, breaks, profile, oi = _load_enrichment_inputs()

    rescored_count = 0
    failed_count = 0
    for sig in signals:
        try:
            sig["rescore"] = rescore_signal(sig, trust, breaks, profile, oi)
            rescored_count += 1
        except Exception as exc:
            log.warning("rescore failed for signal %s: %s — keeping prior rescore",
                        sig.get("signal_id"), exc)
            failed_count += 1
            # Do NOT overwrite sig["rescore"] on failure — prior value sticks

    try:
        _atomic_write(OPEN_SIGNALS_FILE, signals)
    except Exception as exc:
        log.error("atomic write failed: %s", exc)
        return 2

    log.info("rescore complete: %d ok, %d failed", rescored_count, failed_count)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

Run tests → 4 PASS.

- [ ] **Step 3: Wire into `intraday_scan.bat`**

Insert one line right after the msi_refresh line (added earlier today):

```bat
python -X utf8 msi_refresh.py >> logs\intraday_scan.log 2>&1
python -X utf8 signal_rescorer.py >> logs\intraday_scan.log 2>&1
REM Phase C: Correlation break scanner ...
```

Like msi_refresh, the exit code 2 on soft failure is NOT wired to `goto error` — the scheduler tolerates rescore-misses.

- [ ] **Step 4: Inventory update**

If `pipeline/data/signals/open_signals.json` isn't already in every `AnkaIntraday####` entry's `outputs[]`, add it via the same helper pattern used for `today_regime.json` earlier today:

```bash
python - <<'PY'
import json
from pathlib import Path
p = Path("pipeline/config/anka_inventory.json")
inv = json.loads(p.read_text(encoding="utf-8"))
tasks = inv["tasks"] if isinstance(inv, dict) else inv
changed = 0
for t in tasks:
    if t.get("task_name", "").startswith("AnkaIntraday"):
        outs = t.setdefault("outputs", [])
        if "pipeline/data/signals/open_signals.json" not in outs:
            outs.append("pipeline/data/signals/open_signals.json")
            changed += 1
p.write_text(json.dumps(inv, indent=2, ensure_ascii=False), encoding="utf-8")
print(f"updated {changed} intraday tasks")
PY
```

- [ ] **Step 5: Commit**

```bash
git add pipeline/signal_rescorer.py pipeline/tests/test_signal_rescorer.py pipeline/scripts/intraday_scan.bat pipeline/config/anka_inventory.json
git commit -m "feat(rescorer): intraday rescore writes current_score to each open signal"
```

---

## Task 3: CONVICTION_DECAY + Z_CROSS exits in `check_signal_status`

**Files:** `pipeline/signal_tracker.py`, `pipeline/tests/test_signal_tracker_atr.py`.

- [ ] **Step 1: Failing tests**

Append to `pipeline/tests/test_signal_tracker_atr.py`:

```python
def test_conviction_decay_closes_spread_signal(monkeypatch):
    """If current_score < 45 AND score_delta > 20, close with CONVICTION_DECAY."""
    from unittest.mock import patch
    sig = _mk_signal(stop_pct=-1.0, source="SPREAD")
    sig["entry_score"] = 75
    sig["conviction_score"] = 75
    sig["rescore"] = {"current_score": 40, "score_delta": 35,
                      "gate_reason_current": "regime misaligned",
                      "rescored_at": "2026-04-22T11:30:00+05:30"}
    with patch.object(signal_tracker, "compute_signal_pnl",
                      return_value={"spread_pnl_pct": 3.0}), \
         patch.object(signal_tracker, "_compute_todays_spread_move", return_value=0.5), \
         patch.object(signal_tracker, "get_levels_for_spread",
                      return_value={"daily_std": 2.0, "avg_favorable_move": 2.0,
                                    "entry_level": 0.0, "stop_level": -1.5,
                                    "cum_percentile": 50.0, "cum_peak": 5.0, "cum_trough": -2.0}):
        status, _ = signal_tracker.check_signal_status(sig, current_prices={"BHEL": 330.0})
    assert status == "STOPPED_OUT_CONVICTION"


def test_conviction_decay_requires_both_absolute_and_relative():
    """Only absolute trigger (score < 45) without enough relative drop → stay OPEN.
    Only relative trigger (drop > 20) without absolute crossing → stay OPEN."""
    from unittest.mock import patch
    # Case A: absolute met, relative NOT — score dropped 44→40 (delta 4)
    sig = _mk_signal(stop_pct=-1.0, source="SPREAD")
    sig["entry_score"] = 44
    sig["rescore"] = {"current_score": 40, "score_delta": 4,
                      "gate_reason_current": "ok", "rescored_at": "x"}
    with patch.object(signal_tracker, "compute_signal_pnl",
                      return_value={"spread_pnl_pct": 2.0}), \
         patch.object(signal_tracker, "_compute_todays_spread_move", return_value=0.5), \
         patch.object(signal_tracker, "get_levels_for_spread",
                      return_value={"daily_std": 2.0, "avg_favorable_move": 2.0,
                                    "entry_level": 0.0, "stop_level": -1.5,
                                    "cum_percentile": 50.0, "cum_peak": 5.0, "cum_trough": -2.0}):
        status, _ = signal_tracker.check_signal_status(sig, current_prices={"BHEL": 330.0})
    assert status == "OPEN"

    # Case B: relative met, absolute NOT — 85 → 60 (delta 25, but 60 >= 45)
    sig = _mk_signal(stop_pct=-1.0, source="SPREAD")
    sig["entry_score"] = 85
    sig["rescore"] = {"current_score": 60, "score_delta": 25,
                      "gate_reason_current": "ok", "rescored_at": "x"}
    with patch.object(signal_tracker, "compute_signal_pnl",
                      return_value={"spread_pnl_pct": 2.0}), \
         patch.object(signal_tracker, "_compute_todays_spread_move", return_value=0.5), \
         patch.object(signal_tracker, "get_levels_for_spread",
                      return_value={"daily_std": 2.0, "avg_favorable_move": 2.0,
                                    "entry_level": 0.0, "stop_level": -1.5,
                                    "cum_percentile": 50.0, "cum_peak": 5.0, "cum_trough": -2.0}):
        status, _ = signal_tracker.check_signal_status(sig, current_prices={"BHEL": 330.0})
    assert status == "OPEN"


def test_z_cross_closes_correlation_break():
    """CORRELATION_BREAK signal: symbol absent from today's correlation_breaks.json
    → the break has closed → Z_CROSS exit."""
    from unittest.mock import patch
    sig = _mk_signal(stop_pct=-2.3, source="CORRELATION_BREAK")
    sig["entry_score"] = 80
    sig["long_legs"] = [{"ticker": "BHEL", "yf": "BHEL.NS", "price": 318.5, "weight": 1.0}]
    sig["short_legs"] = []
    sig["rescore"] = {"current_score": 70, "score_delta": 10,
                      "gate_reason_current": "ok", "rescored_at": "x"}
    # Breaks file now shows BHEL appearing with opposite direction (SHORT, not LONG)
    # OR not appearing at all — both mean the break has closed.
    def fake_current_breaks():
        return {"breaks": [
            # BHEL no longer an actionable LONG break — thesis done
            {"symbol": "OTHER", "trade_rec": "SHORT"},
        ]}
    with patch.object(signal_tracker, "compute_signal_pnl",
                      return_value={"spread_pnl_pct": 2.0}), \
         patch.object(signal_tracker, "_compute_todays_spread_move", return_value=0.5), \
         patch.object(signal_tracker, "get_levels_for_spread",
                      return_value={"daily_std": 2.0, "avg_favorable_move": 2.0,
                                    "entry_level": 0.0, "stop_level": -1.5,
                                    "cum_percentile": 50.0, "cum_peak": 5.0, "cum_trough": -2.0}), \
         patch.object(signal_tracker, "_load_current_breaks_for_zcross",
                      side_effect=fake_current_breaks):
        status, _ = signal_tracker.check_signal_status(sig, current_prices={"BHEL": 320.0})
    assert status == "STOPPED_OUT_ZCROSS"


def test_z_cross_only_applies_to_correlation_break():
    """A SPREAD signal whose symbols aren't in correlation_breaks.json must NOT z-cross-exit."""
    from unittest.mock import patch
    sig = _mk_signal(stop_pct=-1.0, source="SPREAD")
    sig["entry_score"] = 80
    sig["rescore"] = {"current_score": 70, "score_delta": 10,
                      "gate_reason_current": "ok", "rescored_at": "x"}
    with patch.object(signal_tracker, "compute_signal_pnl",
                      return_value={"spread_pnl_pct": 2.0}), \
         patch.object(signal_tracker, "_compute_todays_spread_move", return_value=0.5), \
         patch.object(signal_tracker, "get_levels_for_spread",
                      return_value={"daily_std": 2.0, "avg_favorable_move": 2.0,
                                    "entry_level": 0.0, "stop_level": -1.5,
                                    "cum_percentile": 50.0, "cum_peak": 5.0, "cum_trough": -2.0}):
        # No patch on _load_current_breaks_for_zcross — it won't be called
        status, _ = signal_tracker.check_signal_status(sig, current_prices={"BHEL": 320.0})
    assert status == "OPEN"
```

Run → FAIL (STOPPED_OUT_CONVICTION + STOPPED_OUT_ZCROSS don't exist yet; `_load_current_breaks_for_zcross` helper doesn't exist).

- [ ] **Step 2: Add `_load_current_breaks_for_zcross` helper + exit branches in `signal_tracker.py`**

Near the top of signal_tracker.py (after the existing imports), add:

```python
def _load_current_breaks_for_zcross() -> dict:
    """Load today's correlation_breaks.json for the Z_CROSS exit check.
    Factored into a named helper so tests can monkeypatch at module level."""
    try:
        from signal_enrichment import BREAKS_PATH
        import json
        if not BREAKS_PATH.exists():
            return {"breaks": []}
        return json.loads(BREAKS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"breaks": []}
```

Then in `check_signal_status()`, AFTER the existing "EXIT 2: 2-DAY RUNNING STOP" block (around line 634) and BEFORE the final `return ("OPEN", None)`, add:

```python
    # ── EXIT 3: CONVICTION DECAY ────────────────────────────
    # Thesis has measurably degraded. Requires BOTH absolute (score<45)
    # AND relative (drop>20pts) to fire — prevents noise flicker.
    rescore = signal.get("rescore") or {}
    current_score = rescore.get("current_score")
    score_delta = rescore.get("score_delta")
    entry_score = signal.get("entry_score") or signal.get("conviction_score") or 0
    if (current_score is not None and score_delta is not None
            and current_score < 45 and score_delta > 20 and entry_score > 0):
        log.info(
            f"Signal {signal.get('signal_id')}: CONVICTION DECAY "
            f"(entry {entry_score} → current {current_score}, delta {score_delta})"
        )
        return ("STOPPED_OUT_CONVICTION", pnl)

    # ── EXIT 4: Z_CROSS (CORRELATION_BREAK only) ────────────
    # The thesis for a correlation-break trade is "the regime-stock gap
    # will close." If the symbol no longer appears as a same-direction
    # actionable break in today's correlation_breaks.json, the thesis has
    # closed — exit.
    if signal.get("source") == "CORRELATION_BREAK":
        direction = "LONG" if signal.get("long_legs") else "SHORT"
        symbol = (signal.get("long_legs") or signal.get("short_legs") or [{}])[0].get("ticker")
        if symbol:
            current_breaks = _load_current_breaks_for_zcross()
            still_active = any(
                b.get("symbol") == symbol and _same_direction(b.get("trade_rec"), direction)
                for b in current_breaks.get("breaks", [])
            )
            if not still_active:
                log.info(
                    f"Signal {signal.get('signal_id')}: Z_CROSS "
                    f"({symbol} no longer an actionable {direction} break)"
                )
                return ("STOPPED_OUT_ZCROSS", pnl)
```

And add this helper just above (or next to) `_load_current_breaks_for_zcross`:

```python
def _same_direction(trade_rec, direction: str) -> bool:
    """trade_rec may be 'LONG' / 'SHORT' / dict{'direction': ...}."""
    if isinstance(trade_rec, dict):
        return trade_rec.get("direction") == direction
    return trade_rec == direction
```

Run tests → all PASS. Run existing `pipeline/tests/test_signal_tracker*.py` → no regressions.

- [ ] **Step 3: Commit**

```bash
git add pipeline/signal_tracker.py pipeline/tests/test_signal_tracker_atr.py
git commit -m "feat(signal_tracker): CONVICTION_DECAY + Z_CROSS exit branches"
```

---

## Task 4: Surface live score in UI

**Files:** `pipeline/website_exporter.py`, `pipeline/terminal/static/js/components/positions-table.js`.

- [ ] **Step 1: Lift `rescore.current_score` + `score_delta` into public JSON**

In `pipeline/website_exporter.py::_build_live_status()`, find where per-position dict is constructed (you touched this file in the ATR plan Task 4 already — same function). Add:

```python
rescore = signal.get("rescore") or {}
pos["current_score"] = rescore.get("current_score")
pos["score_delta"] = rescore.get("score_delta")
pos["entry_score"] = signal.get("entry_score") or signal.get("conviction_score")
```

- [ ] **Step 2: Render in positions-table.js**

Find the Name / Source cell. Add inline:

```javascript
const scoreBadge = (p.entry_score != null && p.current_score != null)
    ? ` <span class="score-badge" title="entry → current conviction" style="font-size:0.7em;opacity:0.7;">${p.entry_score} → ${p.current_score}</span>`
    : '';
// Append to the name/label cell
```

- [ ] **Step 3: Node smoke-check**

Same pattern as ATR Task 4 — verify the rendered string for `{entry:80, current:45}` vs `{entry:80, current:null}` behaves correctly.

- [ ] **Step 4: Commit**

```bash
git add pipeline/website_exporter.py pipeline/terminal/static/js/components/positions-table.js
git commit -m "feat(ui): show entry → current conviction score on positions table"
```

---

## Task 5: Docs + memory

- [ ] **Step 1:** Append to `docs/SYSTEM_OPERATIONS_MANUAL.md` near the MSI intraday / Phase C section:

> **Live rescore + conviction-decay exit (added 2026-04-22)** — `pipeline/signal_rescorer.py` runs every 15 min inside `intraday_scan.bat` and writes `rescore = {current_score, score_delta, gate_reason_current, rescored_at}` onto each open signal. `signal_tracker.check_signal_status()` now has two additional exit rules: **CONVICTION_DECAY** fires when `current_score < 45` AND `entry_score - current_score > 20`; **Z_CROSS** (CORRELATION_BREAK only) fires when the signal's symbol is no longer an actionable same-direction break in today's `correlation_breaks.json`. The terminal and public site both show `entry → current` next to each open position. Exit sequence now: TRAIL → DAILY → 2-DAY → CONVICTION → Z_CROSS.

- [ ] **Step 2:** Create memory file `C:\Users\Claude_Anka\.claude\projects\C--Users-Claude-Anka-askanka-com\memory\project_rescore_and_exit.md`:

```markdown
---
name: Live rescore + conviction-decay exit
description: Every 15 min intraday, re-run scorecard on open signals; auto-close when thesis has decayed (current_score<45 AND drop>20pts), plus Z_CROSS for correlation breaks (2026-04-22)
type: project
---
Before 2026-04-22 the conviction_score was frozen at signal creation and never
re-evaluated. A trade with deteriorating underlying thesis (regime shift, trust
downgrade, break closed) had NO way to tell the trader the rationale was gone —
the only exits were trail/daily/2-day price stops. Fix: `pipeline/signal_rescorer.py`
runs every 15 min via intraday_scan.bat, calls `signal_enrichment.rescore_signal()`
per open signal, writes `rescore = {current_score, score_delta, gate_reason_current,
rescored_at}`. `signal_tracker.check_signal_status()` adds two exit rules:
- CONVICTION_DECAY: current<45 AND (entry-current)>20. Both required, avoids noise flicker.
- Z_CROSS (CORRELATION_BREAK only): symbol no longer appears as same-direction
  actionable break in today's correlation_breaks.json.

**Why:** User flagged: "would we know what is the current conviction on those
trades with respect to what we entered in as?" — no we wouldn't. Blind spot for
days-long trades where underlying thesis decays silently.

**How to apply:** When adding a new signal source, make sure it populates
`entry_score` at creation. If score semantics differ (like CORRELATION_BREAK's
z-score), add a source-specific exit branch — don't force-fit the 0-100 scorecard.
Exit sequence order matters: TRAIL → DAILY → 2-DAY → CONVICTION → Z_CROSS.
```

- [ ] **Step 3:** Add MEMORY.md pointer near the ATR stops entry:

```markdown
- [Live rescore + conviction-decay exit](project_rescore_and_exit.md) — 15-min rescore + auto-close on thesis decay or Z_CROSS
```

- [ ] **Step 4:** Commit manual change:

```bash
git add docs/SYSTEM_OPERATIONS_MANUAL.md
git commit -m "docs: live rescore + CONVICTION_DECAY / Z_CROSS exits"
```

---

## Self-review checklist

- All 5 tasks committed?
- `pytest pipeline/tests/test_signal_enrichment.py pipeline/tests/test_signal_rescorer.py pipeline/tests/test_signal_tracker_atr.py` — green?
- The 3 open positions (YESBANK/IEX/BHEL, Sovereign Shield) have `rescore.current_score` populated after the next intraday cycle?
- CONVICTION_DECAY fires only when BOTH absolute (<45) AND relative (>20) are true?
- Z_CROSS fires ONLY for `source == "CORRELATION_BREAK"`?
- Terminal + public site both show `85 → 52`-style badge?
