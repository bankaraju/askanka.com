# Wire Rigour into Signals (Reconciled Across Website + Telegram) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire 4 orphan JSONs (OPUS Trust, Phase C correlation breaks, Phase A reverse-regime profile, OI anomalies) into the signal engine so every signal carries trust/rank/break/OI enrichment, and reconcile the same badges across `index.html` and Telegram.

**Architecture:** New `signal_enrichment.py` module loads the 4 orphan JSONs and exposes lookup helpers. `signal_tracker.py` calls enrichment at signal open, persisting additive fields on each signal (`trust_scores`, `regime_rank`, `correlation_break`, `oi_anomaly`, `enrichment_score`, `gate_reason`). A gate function can block/warn signals based on the enrichment (behind `GATE_ENABLED` flag, default `False` until we verify a full day). New `break_signal_generator.py` converts Phase C `POSSIBLE_OPPORTUNITY` breaks into standalone signal candidates. Website and Telegram both consume the enriched `open_signals.json` — one source, two renderers, reconciled by a shared `render_signal_badges()` helper that emits the same trust/rank/break labels for both surfaces.

**Tech Stack:** Python 3.13, pytest, existing pipeline (signal_tracker.py, telegram_bot.py, website_exporter.py), vanilla JS in index.html.

**Rollback:** Enrichment is additive — old readers continue working. Gate is flagged off by default. `break_signal_generator.py` writes signals with `source: "CORRELATION_BREAK"` that can be filtered out by changing one config line.

---

## Shadow Trading Context (READ BEFORE IMPLEMENTING)

This is a **paper / shadow trading period**. Signals produced here are *not* sent to a broker — they are tracked, stopped, monitored, and retrospectively scored so we can:

1. Show investors a **real, auditable track record** of the rigour-driven strategy
2. Validate stop-loss discipline before committing real capital
3. Prove the regime → spread → signal → stop → exit → P&L loop is closed

This changes the bar for every field we persist. Specifically:

- **Every signal must carry its full decision provenance.** A future investor (or auditor) reading `open_signals.json` must be able to reconstruct *why* a signal was opened without re-running the pipeline. That means we persist not just `trust_scores` but also *which file* (path + mtime) supplied the score.
- **Every signal must carry stop discipline.** Spread signals have `spread_statistics.get_levels_for_spread()` providing entry/stop/target. Break signals need a comparable stop policy (see Task 6b below).
- **Every write is a permanent investor-facing record.** Don't let code that mutates historical signals land without a test. `closed_signals.json` is the investor-credible history; treat it as an append-only ledger.
- **Documentation is a deliverable, not an afterthought.** The lifecycle doc added in Task 13 is the document we hand to an investor alongside the track record.

All code comments, commit messages, and docs should use precise language: "shadow signal", "paper P&L", "stop policy" — never "trade" in a way that could mislead a reader into thinking this is live brokerage.

---

## File Structure

**NEW files:**
- `pipeline/signal_enrichment.py` — 4 lookup functions + `enrich_signal()` + `gate_signal()`
- `pipeline/break_signal_generator.py` — Phase C break → signal candidate
- `pipeline/tests/test_signal_enrichment.py` — unit tests for lookups + enrichment + gate
- `pipeline/tests/test_break_signal_generator.py` — unit tests for break → signal
- `pipeline/tests/test_signal_reconciliation.py` — fixture + assert website and telegram render same badges

**MODIFIED files:**
- `pipeline/config.py` — add `SIGNAL_ENRICHMENT_ENABLED = True`, `SIGNAL_GATE_ENABLED = False` flags
- `pipeline/signal_tracker.py` — call `enrich_signal()` when creating a new signal, persist fields
- `pipeline/run_signals.py` — call `break_signal_generator.generate_candidates()` as a new signal source
- `pipeline/website_exporter.py` — pass enrichment fields through to exported JSON
- `pipeline/telegram_bot.py` — render trust/break/rank badges in `format_multi_spread_card()`
- `index.html` — render trust/rank/break badges on result rows (vanilla JS, reads same enrichment fields)

**Shared renderer (used by both website and Telegram):**
- `pipeline/signal_badges.py` — new module exposing `badge_for_trust(grade) -> (emoji, label)`, `badge_for_break(classification) -> (emoji, label)`, `badge_for_rank(hit_rate) -> (emoji, label)` — single source of truth so Telegram text and HTML use identical labels.

---

## Input JSON schemas (reference — copy-paste into tests as needed)

**`opus/artifacts/model_portfolio.json`:**
```json
{
  "regime": "NEUTRAL",
  "positions": [
    {"symbol": "GAIL", "side": "LONG", "trust_grade": "A", "trust_score": 85,
     "price": 158.0, "pe": 12.0, "roe": 13.1, "weight_pct": 6.4, "thesis": "..."}
  ]
}
```

**`pipeline/data/correlation_breaks.json`:**
```json
{
  "date": "2026-04-16",
  "scan_time": "2026-04-16 15:32:15",
  "breaks": [
    {"symbol": "PIIND", "regime": "NEUTRAL", "expected_return": 1.52,
     "actual_return": 0.47, "z_score": -2.0,
     "classification": "POSSIBLE_OPPORTUNITY", "action": "HOLD",
     "oi_anomaly": false, "trade_rec": null}
  ]
}
```

**`pipeline/autoresearch/reverse_regime_profile.json`:**
```json
{
  "stock_profiles": {
    "HAL": {
      "summary": {"episode_count": 35, "tradeable_rate": 0.94,
                  "persistence_rate": 0.38, "hit_rate": 0.50, "avg_drift_1d": 0.00093}
    }
  }
}
```

**`pipeline/data/oi_anomalies.json`:** (list or dict) — will confirm shape in Task 1.

---

## Task 1: Create `signal_enrichment.py` with 4 lookup helpers

**Files:**
- Create: `pipeline/signal_enrichment.py`
- Test: `pipeline/tests/test_signal_enrichment.py`

- [ ] **Step 1.1: Confirm `oi_anomalies.json` shape**

```bash
cd C:/Users/Claude_Anka/askanka.com
python -c "import json; d = json.load(open('pipeline/data/oi_anomalies.json')); print(type(d).__name__, list(d.keys() if isinstance(d, dict) else [])[:5], 'len' if isinstance(d, list) else '', len(d) if hasattr(d, '__len__') else '')"
```

Record output in task comments. Assume `{"date", "scan_time", "anomalies": [{"symbol", "type", "pcr", "iv_change", ...}]}` pattern if it mirrors `correlation_breaks.json`. If shape differs, adapt Step 1.3.

- [ ] **Step 1.2: Write the failing test for `load_trust_scores`**

Create `pipeline/tests/test_signal_enrichment.py`:
```python
import json
import pytest
from pathlib import Path
from pipeline.signal_enrichment import (
    load_trust_scores, load_correlation_breaks, load_regime_profile,
    load_oi_anomalies, get_trust, get_break, get_rank, get_oi,
    enrich_signal, gate_signal,
)


@pytest.fixture
def trust_fixture(tmp_path):
    p = tmp_path / "model_portfolio.json"
    p.write_text(json.dumps({
        "regime": "NEUTRAL",
        "positions": [
            {"symbol": "GAIL", "side": "LONG", "trust_grade": "A", "trust_score": 85},
            {"symbol": "TCS", "side": "SHORT", "trust_grade": "A+", "trust_score": 92},
        ]
    }))
    return p


def test_load_trust_scores_returns_dict_by_symbol(trust_fixture):
    scores = load_trust_scores(trust_fixture)
    assert scores["GAIL"]["trust_grade"] == "A"
    assert scores["GAIL"]["trust_score"] == 85
    assert scores["GAIL"]["opus_side"] == "LONG"
    assert scores["TCS"]["trust_grade"] == "A+"
```

- [ ] **Step 1.3: Run test — expect ImportError**

```bash
cd C:/Users/Claude_Anka/askanka.com
python -m pytest pipeline/tests/test_signal_enrichment.py::test_load_trust_scores_returns_dict_by_symbol -v
```
Expected: `ModuleNotFoundError: No module named 'pipeline.signal_enrichment'`

- [ ] **Step 1.4: Create `signal_enrichment.py` with `load_trust_scores`**

`pipeline/signal_enrichment.py`:
```python
"""Loads the four rigour JSONs and exposes per-ticker lookups + signal enrichment.

Producers:
- OPUS Trust: opus/artifacts/model_portfolio.json
- Phase C breaks: pipeline/data/correlation_breaks.json
- Phase A regime profile: pipeline/autoresearch/reverse_regime_profile.json
- OI anomalies: pipeline/data/oi_anomalies.json

All loaders return a symbol->dict mapping (empty dict if the file is missing or empty)
so downstream callers never have to null-check paths.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

_REPO_ROOT = Path(__file__).resolve().parent.parent
TRUST_PATH = _REPO_ROOT / "opus" / "artifacts" / "model_portfolio.json"
BREAKS_PATH = _REPO_ROOT / "pipeline" / "data" / "correlation_breaks.json"
REGIME_PROFILE_PATH = _REPO_ROOT / "pipeline" / "autoresearch" / "reverse_regime_profile.json"
OI_ANOMALIES_PATH = _REPO_ROOT / "pipeline" / "data" / "oi_anomalies.json"


def _read_json(path: Path) -> Any:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def load_trust_scores(path: Path = TRUST_PATH) -> Dict[str, Dict[str, Any]]:
    data = _read_json(path) or {}
    out: Dict[str, Dict[str, Any]] = {}
    for pos in data.get("positions", []):
        sym = pos.get("symbol")
        if not sym:
            continue
        out[sym] = {
            "trust_grade": pos.get("trust_grade"),
            "trust_score": pos.get("trust_score"),
            "opus_side": pos.get("side"),
            "thesis": pos.get("thesis"),
        }
    return out
```

- [ ] **Step 1.5: Run test — expect PASS**

```bash
python -m pytest pipeline/tests/test_signal_enrichment.py::test_load_trust_scores_returns_dict_by_symbol -v
```
Expected: `PASSED`

- [ ] **Step 1.6: Write + run failing test for `load_correlation_breaks`**

Append to `test_signal_enrichment.py`:
```python
@pytest.fixture
def breaks_fixture(tmp_path):
    p = tmp_path / "correlation_breaks.json"
    p.write_text(json.dumps({
        "date": "2026-04-16",
        "scan_time": "2026-04-16 15:32:15",
        "breaks": [
            {"symbol": "PIIND", "z_score": -2.0,
             "classification": "POSSIBLE_OPPORTUNITY", "action": "HOLD",
             "expected_return": 1.52, "actual_return": 0.47,
             "oi_anomaly": False, "trade_rec": None},
            {"symbol": "HAL", "z_score": 2.3,
             "classification": "MOMENTUM_CONFIRM", "action": "HOLD",
             "expected_return": 0.5, "actual_return": 1.8,
             "oi_anomaly": True, "trade_rec": "LONG"},
        ]
    }))
    return p


def test_load_correlation_breaks(breaks_fixture):
    breaks = load_correlation_breaks(breaks_fixture)
    assert breaks["PIIND"]["classification"] == "POSSIBLE_OPPORTUNITY"
    assert breaks["PIIND"]["z_score"] == -2.0
    assert breaks["HAL"]["trade_rec"] == "LONG"
    assert breaks["HAL"]["oi_anomaly"] is True
```

Run: `python -m pytest pipeline/tests/test_signal_enrichment.py::test_load_correlation_breaks -v` — expect FAIL.

Add to `signal_enrichment.py`:
```python
def load_correlation_breaks(path: Path = BREAKS_PATH) -> Dict[str, Dict[str, Any]]:
    data = _read_json(path) or {}
    out: Dict[str, Dict[str, Any]] = {}
    for br in data.get("breaks", []):
        sym = br.get("symbol")
        if not sym:
            continue
        out[sym] = {
            "classification": br.get("classification"),
            "action": br.get("action"),
            "z_score": br.get("z_score"),
            "expected_return": br.get("expected_return"),
            "actual_return": br.get("actual_return"),
            "oi_anomaly": br.get("oi_anomaly"),
            "trade_rec": br.get("trade_rec"),
        }
    return out
```

Re-run test — expect PASS.

- [ ] **Step 1.7: Write + run failing test for `load_regime_profile`**

Append:
```python
@pytest.fixture
def regime_profile_fixture(tmp_path):
    p = tmp_path / "reverse_regime_profile.json"
    p.write_text(json.dumps({
        "stock_profiles": {
            "HAL": {
                "summary": {
                    "episode_count": 35,
                    "tradeable_rate": 0.94,
                    "persistence_rate": 0.38,
                    "hit_rate": 0.50,
                    "avg_drift_1d": 0.00093,
                }
            },
            "TCS": {
                "summary": {
                    "episode_count": 22,
                    "tradeable_rate": 0.77,
                    "persistence_rate": 0.45,
                    "hit_rate": 0.62,
                    "avg_drift_1d": -0.0012,
                }
            },
        }
    }))
    return p


def test_load_regime_profile(regime_profile_fixture):
    profile = load_regime_profile(regime_profile_fixture)
    assert profile["HAL"]["hit_rate"] == 0.50
    assert profile["HAL"]["tradeable_rate"] == 0.94
    assert profile["TCS"]["hit_rate"] == 0.62
```

Run — FAIL. Add to module:
```python
def load_regime_profile(path: Path = REGIME_PROFILE_PATH) -> Dict[str, Dict[str, Any]]:
    data = _read_json(path) or {}
    out: Dict[str, Dict[str, Any]] = {}
    for sym, prof in (data.get("stock_profiles") or {}).items():
        summary = prof.get("summary") or {}
        out[sym] = {
            "episode_count": summary.get("episode_count", 0),
            "tradeable_rate": summary.get("tradeable_rate", 0.0),
            "persistence_rate": summary.get("persistence_rate", 0.0),
            "hit_rate": summary.get("hit_rate", 0.0),
            "avg_drift_1d": summary.get("avg_drift_1d", 0.0),
        }
    return out
```

Re-run — PASS.

- [ ] **Step 1.8: Write + run failing test for `load_oi_anomalies`**

Append (adjust shape based on Step 1.1 output if the real file uses different keys):
```python
@pytest.fixture
def oi_fixture(tmp_path):
    p = tmp_path / "oi_anomalies.json"
    p.write_text(json.dumps({
        "date": "2026-04-16",
        "anomalies": [
            {"symbol": "HAL", "type": "CALL_BUILDUP", "pcr": 0.4, "severity": "HIGH"},
            {"symbol": "TCS", "type": "PUT_BUILDUP", "pcr": 1.8, "severity": "MEDIUM"},
        ]
    }))
    return p


def test_load_oi_anomalies(oi_fixture):
    oi = load_oi_anomalies(oi_fixture)
    assert oi["HAL"]["type"] == "CALL_BUILDUP"
    assert oi["HAL"]["severity"] == "HIGH"
    assert oi["TCS"]["pcr"] == 1.8
```

Run — FAIL. Add:
```python
def load_oi_anomalies(path: Path = OI_ANOMALIES_PATH) -> Dict[str, Dict[str, Any]]:
    data = _read_json(path) or {}
    entries = data.get("anomalies") if isinstance(data, dict) else data
    if not isinstance(entries, list):
        return {}
    out: Dict[str, Dict[str, Any]] = {}
    for a in entries:
        sym = a.get("symbol") or a.get("ticker")
        if not sym:
            continue
        out[sym] = {
            "type": a.get("type") or a.get("anomaly_type"),
            "pcr": a.get("pcr"),
            "severity": a.get("severity"),
            "iv_change": a.get("iv_change"),
        }
    return out
```

Re-run — PASS.

- [ ] **Step 1.9: Add the per-ticker `get_*` helpers**

Append to module (returns `None` when symbol not found, so callers can use short-circuits):
```python
def get_trust(symbol: str, cache: Dict[str, Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    return cache.get(symbol)


def get_break(symbol: str, cache: Dict[str, Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    return cache.get(symbol)


def get_rank(symbol: str, cache: Dict[str, Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    return cache.get(symbol)


def get_oi(symbol: str, cache: Dict[str, Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    return cache.get(symbol)
```

(Yes, they're all `cache.get(symbol)` — but naming them explicitly keeps call sites self-documenting. Small cost, big readability.)

- [ ] **Step 1.10: Test per-ticker getters**

Append:
```python
def test_get_trust_returns_none_for_missing(trust_fixture):
    scores = load_trust_scores(trust_fixture)
    assert get_trust("NOT_A_TICKER", scores) is None
    assert get_trust("GAIL", scores)["trust_grade"] == "A"
```

Run: `python -m pytest pipeline/tests/test_signal_enrichment.py -v` — all tests PASS.

- [ ] **Step 1.11: Commit**

```bash
git add pipeline/signal_enrichment.py pipeline/tests/test_signal_enrichment.py
git commit -m "feat(signal): add signal_enrichment module (Task 1)

Adds loaders for the 4 rigour JSONs (trust scores, correlation breaks,
regime profile, OI anomalies) and per-ticker getter helpers. Pure I/O
module — no signal-engine integration yet. 5 unit tests green.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: `enrich_signal()` — attach enrichment fields to a signal

**Files:**
- Modify: `pipeline/signal_enrichment.py`
- Modify: `pipeline/tests/test_signal_enrichment.py`

- [ ] **Step 2.1: Write failing test**

Append to test file:
```python
def test_enrich_signal_attaches_all_four_sources(trust_fixture, breaks_fixture, regime_profile_fixture, oi_fixture):
    trust = load_trust_scores(trust_fixture)
    breaks = load_correlation_breaks(breaks_fixture)
    profile = load_regime_profile(regime_profile_fixture)
    oi = load_oi_anomalies(oi_fixture)

    signal = {
        "signal_id": "SIG-TEST-001",
        "spread_name": "Defence vs IT",
        "long_legs": [{"ticker": "HAL", "price": 4284.80}],
        "short_legs": [{"ticker": "TCS", "price": 2572.00}],
    }
    enriched = enrich_signal(
        signal, trust, breaks, profile, oi,
        trust_path=trust_fixture,
        breaks_path=breaks_fixture,
        profile_path=regime_profile_fixture,
        oi_path=oi_fixture,
    )

    # trust per leg
    assert enriched["trust_scores"]["HAL"] is None  # HAL not in trust fixture
    assert enriched["trust_scores"]["TCS"]["trust_grade"] == "A+"

    # regime rank per leg
    assert enriched["regime_rank"]["HAL"]["hit_rate"] == 0.50
    assert enriched["regime_rank"]["TCS"]["hit_rate"] == 0.62

    # correlation break per leg
    assert enriched["correlation_breaks"]["HAL"]["classification"] == "MOMENTUM_CONFIRM"
    assert enriched["correlation_breaks"]["TCS"] is None

    # oi anomaly per leg
    assert enriched["oi_anomalies"]["HAL"]["type"] == "CALL_BUILDUP"
    assert enriched["oi_anomalies"]["TCS"]["type"] == "PUT_BUILDUP"

    # original fields untouched
    assert enriched["signal_id"] == "SIG-TEST-001"
    assert enriched["spread_name"] == "Defence vs IT"

    # Shadow-trading audit: rigour_trail records which files supplied the scores
    assert "rigour_trail" in enriched
    assert "enriched_at" in enriched["rigour_trail"]
    assert set(enriched["rigour_trail"]["sources"].keys()) == {"trust", "breaks", "regime_profile", "oi_anomalies"}
    assert enriched["rigour_trail"]["sources"]["trust"]["exists"] is True
```

Run: `python -m pytest pipeline/tests/test_signal_enrichment.py::test_enrich_signal_attaches_all_four_sources -v` — expect FAIL (`enrich_signal` not defined).

- [ ] **Step 2.2: Implement `enrich_signal`**

Append to `pipeline/signal_enrichment.py`:
```python
def _provenance(path: Path) -> Dict[str, Any]:
    """Shadow-trading audit: record which file + mtime supplied a field so a future
    investor or auditor can reconstruct the decision without re-running the pipeline."""
    if not path.exists():
        return {"path": str(path), "exists": False, "mtime": None}
    stat = path.stat()
    return {
        "path": str(path.relative_to(_REPO_ROOT)) if str(path).startswith(str(_REPO_ROOT)) else str(path),
        "exists": True,
        "mtime": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
        "size_bytes": stat.st_size,
    }


def enrich_signal(
    signal: Dict[str, Any],
    trust_cache: Dict[str, Dict[str, Any]],
    breaks_cache: Dict[str, Dict[str, Any]],
    profile_cache: Dict[str, Dict[str, Any]],
    oi_cache: Dict[str, Dict[str, Any]],
    trust_path: Path = TRUST_PATH,
    breaks_path: Path = BREAKS_PATH,
    profile_path: Path = REGIME_PROFILE_PATH,
    oi_path: Path = OI_ANOMALIES_PATH,
) -> Dict[str, Any]:
    """Attach per-leg enrichment to a signal. Returns a new dict (does not mutate input).

    Shadow-trading guarantee: enrichment includes a `rigour_trail` field recording
    exactly which JSONs (and their mtimes) supplied the scores — so the signal
    remains auditable after the files move on.
    """
    enriched = dict(signal)
    all_legs = []
    for leg in signal.get("long_legs", []) or []:
        all_legs.append(leg.get("ticker"))
    for leg in signal.get("short_legs", []) or []:
        all_legs.append(leg.get("ticker"))
    all_legs = [t for t in all_legs if t]

    enriched["trust_scores"] = {t: get_trust(t, trust_cache) for t in all_legs}
    enriched["regime_rank"] = {t: get_rank(t, profile_cache) for t in all_legs}
    enriched["correlation_breaks"] = {t: get_break(t, breaks_cache) for t in all_legs}
    enriched["oi_anomalies"] = {t: get_oi(t, oi_cache) for t in all_legs}
    enriched["rigour_trail"] = {
        "enriched_at": datetime.now(timezone.utc).isoformat(),
        "sources": {
            "trust": _provenance(trust_path),
            "breaks": _provenance(breaks_path),
            "regime_profile": _provenance(profile_path),
            "oi_anomalies": _provenance(oi_path),
        },
    }
    return enriched
```

- [ ] **Step 2.3: Re-run test**

```bash
python -m pytest pipeline/tests/test_signal_enrichment.py::test_enrich_signal_attaches_all_four_sources -v
```
Expected: PASS.

- [ ] **Step 2.4: Commit**

```bash
git add pipeline/signal_enrichment.py pipeline/tests/test_signal_enrichment.py
git commit -m "feat(signal): enrich_signal attaches trust/rank/break/OI per leg (Task 2)

Additive — original signal fields untouched. Unknown symbols resolve to
None so downstream renderers can show 'no data' without crashing.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: `gate_signal()` — compute conviction score + optional blocking reason

**Files:**
- Modify: `pipeline/signal_enrichment.py`
- Modify: `pipeline/tests/test_signal_enrichment.py`
- Modify: `pipeline/config.py`

- [ ] **Step 3.1: Add config flag**

Append to `pipeline/config.py`:
```python
# Signal enrichment + gating (Task 3, 2026-04-16)
# SIGNAL_ENRICHMENT_ENABLED: attach trust/rank/break/OI fields to new signals.
# SIGNAL_GATE_ENABLED: if True, block signals that fail the gate; if False, compute
#   gate_reason for display/logging but do not block. Keep False until a full
#   trading day of dry-run review.
SIGNAL_ENRICHMENT_ENABLED = True
SIGNAL_GATE_ENABLED = False
```

- [ ] **Step 3.2: Write failing test for gate logic**

Append to test file:
```python
@pytest.fixture
def enriched_signal():
    return {
        "signal_id": "SIG-TEST-002",
        "long_legs": [{"ticker": "HAL"}, {"ticker": "BEL"}],
        "short_legs": [{"ticker": "TCS"}],
        "trust_scores": {
            "HAL": {"trust_grade": "B+", "trust_score": 72, "opus_side": "LONG"},
            "BEL": {"trust_grade": "A", "trust_score": 80, "opus_side": "LONG"},
            "TCS": {"trust_grade": "A+", "trust_score": 92, "opus_side": "LONG"},
        },
        "regime_rank": {
            "HAL": {"hit_rate": 0.62, "tradeable_rate": 0.9},
            "BEL": {"hit_rate": 0.55, "tradeable_rate": 0.85},
            "TCS": {"hit_rate": 0.48, "tradeable_rate": 0.77},
        },
        "correlation_breaks": {
            "HAL": {"classification": "MOMENTUM_CONFIRM", "trade_rec": "LONG"},
            "BEL": None, "TCS": None,
        },
        "oi_anomalies": {"HAL": None, "BEL": None, "TCS": None},
    }


def test_gate_short_on_high_trust_name_blocks(enriched_signal):
    # TCS is A+ (trust_score 92, opus LONG) but we're shorting it — contrarian to OPUS
    blocked, reason, score = gate_signal(enriched_signal)
    assert blocked is True
    assert "TCS" in reason
    assert "high-trust" in reason.lower() or "opus long" in reason.lower()


def test_gate_passes_good_spread(enriched_signal):
    # Flip: don't short TCS; short a low-trust name instead
    sig = dict(enriched_signal)
    sig["trust_scores"] = dict(sig["trust_scores"])
    sig["trust_scores"]["TCS"] = {"trust_grade": "C", "trust_score": 35, "opus_side": "SHORT"}
    blocked, reason, score = gate_signal(sig)
    assert blocked is False
    assert reason is None
    assert score > 50  # conviction boosted by break + good trust alignment


def test_gate_missing_enrichment_does_not_block():
    # No trust/rank/break data for legs — must NOT block (fail-open)
    sig = {
        "long_legs": [{"ticker": "UNKNOWN1"}],
        "short_legs": [{"ticker": "UNKNOWN2"}],
        "trust_scores": {"UNKNOWN1": None, "UNKNOWN2": None},
        "regime_rank": {"UNKNOWN1": None, "UNKNOWN2": None},
        "correlation_breaks": {"UNKNOWN1": None, "UNKNOWN2": None},
        "oi_anomalies": {"UNKNOWN1": None, "UNKNOWN2": None},
    }
    blocked, reason, score = gate_signal(sig)
    assert blocked is False
    assert score == 50  # neutral — no data
```

Run: `python -m pytest pipeline/tests/test_signal_enrichment.py -k gate -v` — expect 3 failures (`gate_signal` not defined).

- [ ] **Step 3.3: Implement `gate_signal`**

Append to `pipeline/signal_enrichment.py`:
```python
# Grade ordering: higher index = stronger trust
_GRADE_ORDER = ["F", "D", "C", "C+", "B", "B+", "A", "A+"]

def _grade_rank(grade: Optional[str]) -> int:
    if not grade:
        return -1
    try:
        return _GRADE_ORDER.index(grade)
    except ValueError:
        return -1


def gate_signal(enriched: Dict[str, Any]) -> tuple[bool, Optional[str], float]:
    """Decide whether to block a signal and compute a conviction score (0-100).

    Returns (blocked, reason, score).
    - blocked: True if any leg violates a hard rule (e.g. shorting A+, longing C/D/F).
    - reason: human-readable explanation when blocked, else None.
    - score: 0-100 conviction. 50 = neutral. >65 = strong. <35 = weak.

    Hard rules (blocking):
      1. Shorting a name with OPUS trust_grade >= A (rank 6)
      2. Longing a name with OPUS trust_grade <= C (rank 2)
    Soft signals (score adjustments, not blocking):
      - Phase C break with trade_rec matching leg direction: +8
      - Phase C break with trade_rec opposite: -8
      - OI anomaly CALL_BUILDUP on long leg: +5 (confirmation)
      - OI anomaly PUT_BUILDUP on long leg: -5 (contradicts)
      - regime_rank.hit_rate > 0.55: +min(10, (hr - 0.5) * 50)
      - regime_rank.hit_rate < 0.45: -min(10, (0.5 - hr) * 50)
    """
    score = 50.0
    reason: Optional[str] = None

    long_legs = [l.get("ticker") for l in enriched.get("long_legs", []) or []]
    short_legs = [l.get("ticker") for l in enriched.get("short_legs", []) or []]
    trust = enriched.get("trust_scores", {}) or {}
    rank = enriched.get("regime_rank", {}) or {}
    breaks = enriched.get("correlation_breaks", {}) or {}
    oi = enriched.get("oi_anomalies", {}) or {}

    # Hard rule checks — first violation wins
    for t in long_legs:
        tr = trust.get(t)
        if tr and _grade_rank(tr.get("trust_grade")) >= 0 and _grade_rank(tr.get("trust_grade")) <= 2:
            return True, f"Long leg {t} has low OPUS trust ({tr.get('trust_grade')}, score {tr.get('trust_score')})", score
    for t in short_legs:
        tr = trust.get(t)
        if tr and _grade_rank(tr.get("trust_grade")) >= 6:  # A or A+
            return True, f"Short leg {t} has high OPUS trust ({tr.get('trust_grade')}, score {tr.get('trust_score')}) — contrarian to OPUS LONG", score

    # Soft adjustments
    for t in long_legs:
        br = breaks.get(t)
        if br and br.get("trade_rec") == "LONG":
            score += 8
        elif br and br.get("trade_rec") == "SHORT":
            score -= 8
        oia = oi.get(t)
        if oia:
            if oia.get("type") == "CALL_BUILDUP":
                score += 5
            elif oia.get("type") == "PUT_BUILDUP":
                score -= 5
        r = rank.get(t)
        if r and r.get("hit_rate") is not None:
            hr = r["hit_rate"]
            if hr > 0.55:
                score += min(10, (hr - 0.5) * 50)
            elif hr < 0.45:
                score -= min(10, (0.5 - hr) * 50)

    for t in short_legs:
        br = breaks.get(t)
        if br and br.get("trade_rec") == "SHORT":
            score += 8
        elif br and br.get("trade_rec") == "LONG":
            score -= 8
        # (OI/rank on short legs: mirror of long-leg logic, inverted)
        oia = oi.get(t)
        if oia:
            if oia.get("type") == "PUT_BUILDUP":
                score += 5
            elif oia.get("type") == "CALL_BUILDUP":
                score -= 5

    score = max(0.0, min(100.0, score))
    return False, reason, score
```

- [ ] **Step 3.4: Re-run gate tests**

```bash
python -m pytest pipeline/tests/test_signal_enrichment.py -k gate -v
```
Expected: 3 PASSED.

- [ ] **Step 3.5: Run full enrichment suite**

```bash
python -m pytest pipeline/tests/test_signal_enrichment.py -v
```
Expected: all tests PASS.

- [ ] **Step 3.6: Commit**

```bash
git add pipeline/signal_enrichment.py pipeline/tests/test_signal_enrichment.py pipeline/config.py
git commit -m "feat(signal): gate_signal hard rules + soft conviction score (Task 3)

Hard rules block: shorting OPUS A/A+ names, longing OPUS C/D/F names.
Soft adjustments on Phase C breaks, OI anomalies, regime hit-rate feed
a 0-100 conviction score. Gate is flagged off (SIGNAL_GATE_ENABLED=False)
until a dry-run day proves no regressions.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Shared `signal_badges.py` — one source for website and Telegram labels

**Files:**
- Create: `pipeline/signal_badges.py`
- Test: `pipeline/tests/test_signal_badges.py`

- [ ] **Step 4.1: Write failing tests**

Create `pipeline/tests/test_signal_badges.py`:
```python
from pipeline.signal_badges import (
    trust_badge, break_badge, rank_badge, conviction_badge,
)


def test_trust_badge_grades():
    assert trust_badge("A+") == {"emoji": "🟢", "label": "A+", "tone": "strong"}
    assert trust_badge("A") == {"emoji": "🟢", "label": "A", "tone": "strong"}
    assert trust_badge("B+") == {"emoji": "🟡", "label": "B+", "tone": "ok"}
    assert trust_badge("B") == {"emoji": "🟡", "label": "B", "tone": "ok"}
    assert trust_badge("C") == {"emoji": "🔴", "label": "C", "tone": "weak"}
    assert trust_badge("F") == {"emoji": "🔴", "label": "F", "tone": "weak"}
    assert trust_badge(None) == {"emoji": "⚪", "label": "—", "tone": "none"}


def test_break_badge():
    assert break_badge("MOMENTUM_CONFIRM")["emoji"] == "🟢"
    assert break_badge("POSSIBLE_OPPORTUNITY")["emoji"] == "🟡"
    assert break_badge("DIVERGENCE_WARNING")["emoji"] == "🔴"
    assert break_badge(None)["emoji"] == "⚪"


def test_rank_badge_from_hit_rate():
    assert rank_badge(0.75)["tone"] == "strong"
    assert rank_badge(0.55)["tone"] == "ok"
    assert rank_badge(0.40)["tone"] == "weak"
    assert rank_badge(None)["tone"] == "none"


def test_conviction_badge_thresholds():
    assert conviction_badge(80)["tone"] == "strong"
    assert conviction_badge(55)["tone"] == "ok"
    assert conviction_badge(30)["tone"] == "weak"
```

Run: `python -m pytest pipeline/tests/test_signal_badges.py -v` — expect FAIL (module missing).

- [ ] **Step 4.2: Create `pipeline/signal_badges.py`**

```python
"""Shared badge renderer — single source of truth for website and Telegram labels.

Keeps the three surfaces (website, Telegram, terminal-in-future) using
identical emoji + label pairs for every enrichment dimension. Change the
mapping here once and all surfaces follow.
"""
from typing import Any, Dict, Optional


_TRUST_STRONG = {"A+", "A"}
_TRUST_OK = {"B+", "B"}
# Any other non-None grade → weak


def trust_badge(grade: Optional[str]) -> Dict[str, str]:
    if grade is None:
        return {"emoji": "⚪", "label": "—", "tone": "none"}
    if grade in _TRUST_STRONG:
        return {"emoji": "🟢", "label": grade, "tone": "strong"}
    if grade in _TRUST_OK:
        return {"emoji": "🟡", "label": grade, "tone": "ok"}
    return {"emoji": "🔴", "label": grade, "tone": "weak"}


def break_badge(classification: Optional[str]) -> Dict[str, str]:
    if classification is None:
        return {"emoji": "⚪", "label": "—", "tone": "none"}
    if classification == "MOMENTUM_CONFIRM":
        return {"emoji": "🟢", "label": "CONFIRM", "tone": "strong"}
    if classification == "POSSIBLE_OPPORTUNITY":
        return {"emoji": "🟡", "label": "OPPO", "tone": "ok"}
    if classification == "DIVERGENCE_WARNING":
        return {"emoji": "🔴", "label": "DIVERGE", "tone": "weak"}
    return {"emoji": "⚪", "label": classification[:7], "tone": "none"}


def rank_badge(hit_rate: Optional[float]) -> Dict[str, str]:
    if hit_rate is None:
        return {"emoji": "⚪", "label": "—", "tone": "none"}
    pct = int(round(hit_rate * 100))
    if hit_rate >= 0.60:
        return {"emoji": "🟢", "label": f"{pct}%", "tone": "strong"}
    if hit_rate >= 0.50:
        return {"emoji": "🟡", "label": f"{pct}%", "tone": "ok"}
    return {"emoji": "🔴", "label": f"{pct}%", "tone": "weak"}


def conviction_badge(score: Optional[float]) -> Dict[str, str]:
    if score is None:
        return {"emoji": "⚪", "label": "—", "tone": "none"}
    s = int(round(score))
    if score >= 65:
        return {"emoji": "🟢", "label": f"{s}", "tone": "strong"}
    if score >= 40:
        return {"emoji": "🟡", "label": f"{s}", "tone": "ok"}
    return {"emoji": "🔴", "label": f"{s}", "tone": "weak"}
```

- [ ] **Step 4.3: Re-run tests**

```bash
python -m pytest pipeline/tests/test_signal_badges.py -v
```
Expected: 4 PASSED.

- [ ] **Step 4.4: Commit**

```bash
git add pipeline/signal_badges.py pipeline/tests/test_signal_badges.py
git commit -m "feat(signal): shared signal_badges module (Task 4)

Single source of truth for trust/break/rank/conviction badge rendering.
Website and Telegram both import from here so any label change stays
reconciled across surfaces.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Integrate enrichment into `signal_tracker.py` at signal open

**Files:**
- Modify: `pipeline/signal_tracker.py`
- Modify: `pipeline/tests/test_signal_tracker.py` (or create if missing)

- [ ] **Step 5.1: Locate the signal creation site**

```bash
grep -n "def.*new_signal\|def.*open_signal\|def.*create_signal\|def.*save_signal\|status.*OPEN" pipeline/signal_tracker.py | head -20
```
Record the function name and line. Expect something like `save_signal` or similar that writes to `open_signals.json`.

- [ ] **Step 5.2: Write failing integration test**

Create/append `pipeline/tests/test_signal_tracker_enrichment.py`:
```python
import json
import pytest
from pathlib import Path
from unittest.mock import patch
from pipeline import signal_tracker
from pipeline.signal_enrichment import (
    TRUST_PATH, BREAKS_PATH, REGIME_PROFILE_PATH, OI_ANOMALIES_PATH,
)


@pytest.fixture
def rigour_fixtures(tmp_path, monkeypatch):
    # Write minimal fixtures to tmp paths and monkeypatch the enrichment paths
    trust = tmp_path / "trust.json"
    trust.write_text(json.dumps({"positions": [{"symbol": "HAL", "side": "LONG", "trust_grade": "A", "trust_score": 80}]}))

    breaks = tmp_path / "breaks.json"
    breaks.write_text(json.dumps({"breaks": []}))

    profile = tmp_path / "profile.json"
    profile.write_text(json.dumps({"stock_profiles": {"HAL": {"summary": {"hit_rate": 0.6, "tradeable_rate": 0.9, "persistence_rate": 0.4, "episode_count": 10, "avg_drift_1d": 0.001}}}}))

    oi = tmp_path / "oi.json"
    oi.write_text(json.dumps({"anomalies": []}))

    monkeypatch.setattr("pipeline.signal_enrichment.TRUST_PATH", trust)
    monkeypatch.setattr("pipeline.signal_enrichment.BREAKS_PATH", breaks)
    monkeypatch.setattr("pipeline.signal_enrichment.REGIME_PROFILE_PATH", profile)
    monkeypatch.setattr("pipeline.signal_enrichment.OI_ANOMALIES_PATH", oi)
    return trust, breaks, profile, oi


def test_new_signal_gets_enrichment_fields(rigour_fixtures, tmp_path, monkeypatch):
    # Redirect signal output to tmp
    signals_dir = tmp_path / "signals"
    signals_dir.mkdir()
    monkeypatch.setattr(signal_tracker, "SIGNALS_DIR", signals_dir)
    monkeypatch.setattr(signal_tracker, "OPEN_FILE", signals_dir / "open_signals.json")

    # Create a minimal signal and persist it via the public save helper
    # (replace `save_signal` with the actual function name discovered in Step 5.1)
    signal = {
        "signal_id": "SIG-TEST-003",
        "spread_name": "Defence vs IT",
        "long_legs": [{"ticker": "HAL", "price": 4284.80}],
        "short_legs": [{"ticker": "TCS", "price": 2572.00}],
        "status": "OPEN",
        "tier": "SIGNAL",
    }
    signal_tracker.save_open_signal(signal)  # assumed public API; adjust per Step 5.1

    loaded = json.loads((signals_dir / "open_signals.json").read_text())
    assert len(loaded) == 1
    assert "trust_scores" in loaded[0]
    assert loaded[0]["trust_scores"]["HAL"]["trust_grade"] == "A"
    assert loaded[0]["regime_rank"]["HAL"]["hit_rate"] == 0.6
    assert "conviction_score" in loaded[0]
    assert "gate_reason" in loaded[0]
```

Run: `python -m pytest pipeline/tests/test_signal_tracker_enrichment.py -v` — expect FAIL (either `save_open_signal` missing or `trust_scores` not attached).

- [ ] **Step 5.3: Wire enrichment into signal_tracker.py**

At the top of `pipeline/signal_tracker.py`, add import:
```python
from config import SIGNAL_ENRICHMENT_ENABLED, SIGNAL_GATE_ENABLED
from signal_enrichment import (
    load_trust_scores, load_correlation_breaks, load_regime_profile,
    load_oi_anomalies, enrich_signal, gate_signal,
)
```

Find (or create, if the save happens inline) a function that writes new signals. Wrap it with:
```python
def _apply_enrichment(signal: dict) -> dict:
    """Attach trust/rank/break/OI + conviction score to a signal. No-op if flag off."""
    if not SIGNAL_ENRICHMENT_ENABLED:
        return signal
    trust = load_trust_scores()
    breaks = load_correlation_breaks()
    profile = load_regime_profile()
    oi = load_oi_anomalies()
    enriched = enrich_signal(signal, trust, breaks, profile, oi)
    blocked, reason, score = gate_signal(enriched)
    enriched["conviction_score"] = score
    enriched["gate_reason"] = reason
    enriched["gate_blocked"] = blocked if SIGNAL_GATE_ENABLED else False
    return enriched


def save_open_signal(signal: dict) -> None:
    """Write a new signal to open_signals.json with enrichment applied."""
    signal = _apply_enrichment(signal)
    if signal.get("gate_blocked"):
        # When gate is enabled, drop the signal and log why.
        import logging
        logging.getLogger(__name__).warning(
            "Signal %s blocked by gate: %s",
            signal.get("signal_id"), signal.get("gate_reason"),
        )
        return
    existing = _load_open_signals()  # existing helper in the module
    existing.append(signal)
    OPEN_FILE.write_text(json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8")
```

(If `_load_open_signals` has a different name, adjust to the module's existing helper discovered in Step 5.1.)

- [ ] **Step 5.4: Re-run test**

```bash
python -m pytest pipeline/tests/test_signal_tracker_enrichment.py -v
```
Expected: PASS.

- [ ] **Step 5.5: Regression check — existing signal tests still green**

```bash
python -m pytest pipeline/tests/test_signal_tracker.py -v  # only if it exists; else skip
python -m pytest pipeline/tests/ -v 2>&1 | tail -30
```
Expected: all green.

- [ ] **Step 5.6: Commit**

```bash
git add pipeline/signal_tracker.py pipeline/tests/test_signal_tracker_enrichment.py
git commit -m "feat(signal): wire enrichment into signal_tracker.save_open_signal (Task 5)

Every new signal now carries trust_scores, regime_rank,
correlation_breaks, oi_anomalies, conviction_score, gate_reason,
gate_blocked. Gate is flagged off so blocked signals are logged but
still persisted.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: `break_signal_generator.py` — Phase C break → standalone signal candidate

**Files:**
- Create: `pipeline/break_signal_generator.py`
- Test: `pipeline/tests/test_break_signal_generator.py`

- [ ] **Step 6.1: Write failing test**

Create `pipeline/tests/test_break_signal_generator.py`:
```python
import json
import pytest
from pathlib import Path
from pipeline.break_signal_generator import generate_break_candidates


@pytest.fixture
def breaks_file(tmp_path):
    p = tmp_path / "correlation_breaks.json"
    p.write_text(json.dumps({
        "date": "2026-04-16",
        "scan_time": "2026-04-16 15:32:15",
        "breaks": [
            # Actionable: trade_rec is set
            {"symbol": "HAL", "regime": "NEUTRAL", "classification": "MOMENTUM_CONFIRM",
             "action": "ENTER", "z_score": 2.3, "trade_rec": "LONG",
             "expected_return": 0.5, "actual_return": 1.8, "oi_anomaly": True},
            # Not actionable: trade_rec is None
            {"symbol": "PIIND", "regime": "NEUTRAL", "classification": "POSSIBLE_OPPORTUNITY",
             "action": "HOLD", "z_score": -2.0, "trade_rec": None,
             "expected_return": 1.52, "actual_return": 0.47, "oi_anomaly": False},
            # Actionable short
            {"symbol": "TCS", "regime": "NEUTRAL", "classification": "DIVERGENCE_WARNING",
             "action": "ENTER", "z_score": -2.5, "trade_rec": "SHORT",
             "expected_return": 1.0, "actual_return": -0.5, "oi_anomaly": False},
        ]
    }))
    return p


def test_generate_break_candidates_only_emits_actionable(breaks_file):
    cands = generate_break_candidates(breaks_file)
    assert len(cands) == 2  # PIIND filtered (trade_rec None)
    symbols = {c["long_legs"][0]["ticker"] if c["long_legs"] else c["short_legs"][0]["ticker"] for c in cands}
    assert symbols == {"HAL", "TCS"}


def test_candidate_has_required_signal_fields(breaks_file):
    cands = generate_break_candidates(breaks_file)
    hal = next(c for c in cands if c["long_legs"] and c["long_legs"][0]["ticker"] == "HAL")
    assert hal["source"] == "CORRELATION_BREAK"
    assert hal["tier"] == "SIGNAL"
    assert hal["status"] == "OPEN"
    assert hal["signal_id"].startswith("BRK-")
    assert hal["spread_name"] == "Phase C: HAL MOMENTUM_CONFIRM"
    assert hal["event_headline"].startswith("Phase C break")
    assert hal["short_legs"] == []
    assert hal["long_legs"][0]["ticker"] == "HAL"


def test_short_candidate_uses_short_legs(breaks_file):
    cands = generate_break_candidates(breaks_file)
    tcs = next(c for c in cands if c["short_legs"] and c["short_legs"][0]["ticker"] == "TCS")
    assert tcs["long_legs"] == []
    assert tcs["short_legs"][0]["ticker"] == "TCS"


def test_empty_file_returns_empty_list(tmp_path):
    p = tmp_path / "empty.json"
    p.write_text(json.dumps({"breaks": []}))
    assert generate_break_candidates(p) == []
```

Run: `python -m pytest pipeline/tests/test_break_signal_generator.py -v` — expect FAIL (module missing).

- [ ] **Step 6.2: Create `pipeline/break_signal_generator.py`**

```python
"""Convert Phase C correlation breaks (with trade_rec set) into signal candidates.

Phase C breaks where trade_rec is None are informational only and are not
promoted to signals. Breaks with a definite LONG/SHORT recommendation become
single-leg signals with source="CORRELATION_BREAK".
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from signal_enrichment import BREAKS_PATH


def generate_break_candidates(breaks_path: Path = BREAKS_PATH) -> List[Dict[str, Any]]:
    """Return a list of signal-shaped dicts for every actionable Phase C break.

    Signal shape matches open_signals.json entries (see signal_tracker) so the
    same enrichment + rendering pipeline applies.
    """
    if not breaks_path.exists():
        return []
    data = json.loads(breaks_path.read_text(encoding="utf-8"))
    scan_date = data.get("date") or datetime.now(timezone.utc).date().isoformat()
    scan_time = data.get("scan_time") or datetime.now(timezone.utc).isoformat()

    candidates: List[Dict[str, Any]] = []
    for br in data.get("breaks", []):
        trade_rec = br.get("trade_rec")
        if trade_rec not in ("LONG", "SHORT"):
            continue  # informational break — skip
        symbol = br.get("symbol")
        if not symbol:
            continue

        leg = {"ticker": symbol, "yf": f"{symbol}.NS", "price": 0.0, "weight": 1.0}
        sig = {
            "signal_id": f"BRK-{scan_date}-{symbol}",
            "source": "CORRELATION_BREAK",
            "open_timestamp": scan_time,
            "status": "OPEN",
            "spread_name": f"Phase C: {symbol} {br.get('classification', 'BREAK')}",
            "category": "phase_c",
            "tier": "SIGNAL",
            "event_headline": (
                f"Phase C break on {symbol}: z={br.get('z_score')}, "
                f"expected={br.get('expected_return')}, actual={br.get('actual_return')}"
            ),
            "hit_rate": None,
            "expected_1d_spread": br.get("expected_return"),
            "long_legs": [leg] if trade_rec == "LONG" else [],
            "short_legs": [leg] if trade_rec == "SHORT" else [],
            "_break_metadata": {
                "classification": br.get("classification"),
                "z_score": br.get("z_score"),
                "regime": br.get("regime"),
                "oi_anomaly": br.get("oi_anomaly"),
            },
        }
        candidates.append(sig)
    return candidates
```

- [ ] **Step 6.3: Re-run tests**

```bash
python -m pytest pipeline/tests/test_break_signal_generator.py -v
```
Expected: 4 PASSED.

- [ ] **Step 6.4: Commit**

```bash
git add pipeline/break_signal_generator.py pipeline/tests/test_break_signal_generator.py
git commit -m "feat(signal): Phase C breaks → signal candidates (Task 6)

Breaks where trade_rec is LONG or SHORT become single-leg signals with
source=CORRELATION_BREAK. trade_rec=None breaks remain informational.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: Wire `break_signal_generator` into `run_signals.py`

**Files:**
- Modify: `pipeline/run_signals.py`
- Modify: `pipeline/tests/` — integration

- [ ] **Step 7.1: Identify signal-emission site in run_signals.py**

```bash
grep -nE "save_open_signal|open_signals|save_signal\b" pipeline/run_signals.py | head -10
```
Record call sites. Expect a main signal-generation loop near the end of `run_intraday()` or similar.

- [ ] **Step 7.2: Add break-candidate emission block**

Near the end of the intraday signal loop (find the function via Step 7.1) add:
```python
# Phase C break candidates — standalone trade ideas from correlation breaks
try:
    from break_signal_generator import generate_break_candidates
    from signal_tracker import save_open_signal
    for cand in generate_break_candidates():
        save_open_signal(cand)
except Exception as e:
    import logging
    logging.getLogger(__name__).warning("break_signal_generator failed: %s", e)
```

(Wrap in try/except so an upstream break-file issue never crashes the main signal loop.)

- [ ] **Step 7.3: Integration test — signals.json gains a BRK- entry after run**

Create `pipeline/tests/test_run_signals_break_integration.py`:
```python
import json
import pytest
from pathlib import Path
from unittest.mock import patch


def test_break_candidates_are_saved_as_signals(tmp_path, monkeypatch):
    from pipeline import signal_tracker, break_signal_generator

    # Fixture: one actionable break + one not
    breaks_file = tmp_path / "correlation_breaks.json"
    breaks_file.write_text(json.dumps({
        "breaks": [
            {"symbol": "HAL", "classification": "MOMENTUM_CONFIRM",
             "trade_rec": "LONG", "z_score": 2.3, "regime": "NEUTRAL",
             "expected_return": 0.5, "actual_return": 1.8, "oi_anomaly": True},
        ]
    }))
    monkeypatch.setattr(break_signal_generator, "BREAKS_PATH", breaks_file)
    monkeypatch.setattr("pipeline.signal_enrichment.BREAKS_PATH", breaks_file)

    signals_dir = tmp_path / "signals"
    signals_dir.mkdir()
    open_file = signals_dir / "open_signals.json"
    monkeypatch.setattr(signal_tracker, "SIGNALS_DIR", signals_dir)
    monkeypatch.setattr(signal_tracker, "OPEN_FILE", open_file)

    # Also patch trust/profile/oi to minimal fixtures so enrichment doesn't fail
    trust = tmp_path / "t.json"; trust.write_text(json.dumps({"positions": []}))
    profile = tmp_path / "p.json"; profile.write_text(json.dumps({"stock_profiles": {}}))
    oi = tmp_path / "o.json"; oi.write_text(json.dumps({"anomalies": []}))
    monkeypatch.setattr("pipeline.signal_enrichment.TRUST_PATH", trust)
    monkeypatch.setattr("pipeline.signal_enrichment.REGIME_PROFILE_PATH", profile)
    monkeypatch.setattr("pipeline.signal_enrichment.OI_ANOMALIES_PATH", oi)

    # Exercise the emission block directly
    for cand in break_signal_generator.generate_break_candidates(breaks_file):
        signal_tracker.save_open_signal(cand)

    loaded = json.loads(open_file.read_text())
    assert len(loaded) == 1
    assert loaded[0]["source"] == "CORRELATION_BREAK"
    assert loaded[0]["signal_id"].startswith("BRK-")
    assert "conviction_score" in loaded[0]
```

Run: `python -m pytest pipeline/tests/test_run_signals_break_integration.py -v` — expect PASS.

- [ ] **Step 7.4: Commit**

```bash
git add pipeline/run_signals.py pipeline/tests/test_run_signals_break_integration.py
git commit -m "feat(signal): emit Phase C break candidates from run_signals (Task 7)

Intraday signal loop now pulls from break_signal_generator alongside
spread signals. Wrapped in try/except so a corrupt breaks file never
crashes the main loop.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: Surface enrichment through `website_exporter.py`

**Files:**
- Modify: `pipeline/website_exporter.py`
- Modify: test file (create if missing)

- [ ] **Step 8.1: Identify signal export function**

```bash
grep -nE "def.*signal|open_sigs|export.*signal" pipeline/website_exporter.py | head -15
```
Record the function name (likely `export_signals` or inside `build_website_payload`).

- [ ] **Step 8.2: Write failing test**

Create/append `pipeline/tests/test_website_exporter_enrichment.py`:
```python
import json
from pipeline.website_exporter import _strip_signal_for_web


def test_web_signal_keeps_enrichment_summary():
    sig = {
        "signal_id": "SIG-X",
        "spread_name": "A vs B",
        "long_legs": [{"ticker": "HAL"}],
        "short_legs": [{"ticker": "TCS"}],
        "trust_scores": {
            "HAL": {"trust_grade": "A", "trust_score": 80},
            "TCS": {"trust_grade": "B+", "trust_score": 70},
        },
        "regime_rank": {"HAL": {"hit_rate": 0.62}, "TCS": {"hit_rate": 0.48}},
        "correlation_breaks": {"HAL": {"classification": "MOMENTUM_CONFIRM"}, "TCS": None},
        "oi_anomalies": {"HAL": None, "TCS": None},
        "conviction_score": 72.5,
        "gate_reason": None,
        "_last_trail_check": "internal",  # must be stripped
    }
    web = _strip_signal_for_web(sig)
    assert web["trust_scores"]["HAL"]["trust_grade"] == "A"
    assert web["conviction_score"] == 72.5
    assert "_last_trail_check" not in web
    assert "_data_levels" not in web
```

Run: `python -m pytest pipeline/tests/test_website_exporter_enrichment.py -v` — expect FAIL.

- [ ] **Step 8.3: Implement `_strip_signal_for_web`**

Append to `pipeline/website_exporter.py`:
```python
_WEB_STRIP_PREFIXES = ("_",)
_WEB_KEEP_ENRICHMENT = (
    "trust_scores", "regime_rank", "correlation_breaks", "oi_anomalies",
    "conviction_score", "gate_reason",
)


def _strip_signal_for_web(signal: dict) -> dict:
    """Return a copy safe for the website JSON: strips internal `_` fields,
    keeps enrichment fields so index.html can render trust/rank/break badges."""
    out = {}
    for k, v in signal.items():
        if any(k.startswith(p) for p in _WEB_STRIP_PREFIXES):
            continue
        out[k] = v
    return out
```

In the existing signal-export function (found in Step 8.1), wrap each signal with `_strip_signal_for_web` before writing. If the function currently does something like `web_sigs = list(open_sigs)`, change to `web_sigs = [_strip_signal_for_web(s) for s in open_sigs]`.

- [ ] **Step 8.4: Re-run test**

```bash
python -m pytest pipeline/tests/test_website_exporter_enrichment.py -v
```
Expected: PASS.

- [ ] **Step 8.5: Run the real exporter once, eyeball output**

```bash
python pipeline/website_exporter.py
python -c "import json; d=json.load(open('data/open_signals.json')); print('count=', len(d) if isinstance(d,list) else '?'); print('first keys:', list(d[0].keys()) if isinstance(d,list) and d else '—')"
```
Expected: `trust_scores`, `regime_rank`, `conviction_score` appear in the first signal's keys.

- [ ] **Step 8.6: Commit**

```bash
git add pipeline/website_exporter.py pipeline/tests/test_website_exporter_enrichment.py
git commit -m "feat(signal): website exporter keeps enrichment fields (Task 8)

_strip_signal_for_web preserves trust/rank/break/OI/conviction while
dropping internal _-prefixed fields. Website JSON now carries the same
enrichment the Telegram card will show.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 9: Render enrichment badges in `index.html`

**Files:**
- Modify: `index.html` (both CSS and the JS that renders signals)

- [ ] **Step 9.1: Locate the signal-row renderer**

```bash
grep -n "result-row\|result-name\|result-meta\|renderSignal\|renderResult" index.html | head -10
```
Record line numbers.

- [ ] **Step 9.2: Add badge styles to :root area**

Inside the existing `<style>` block (near the other `.tier-*` rules, around line 555), add:
```css
.badge-enrich { display: inline-block; font-family: 'JetBrains Mono', monospace;
                font-size: 10px; padding: 2px 6px; border-radius: 4px;
                margin-left: 6px; font-weight: 600; letter-spacing: 0.3px; }
.badge-enrich.strong { background: var(--accent-green-dim); color: var(--accent-green); border: 1px solid rgba(16,185,129,0.3); }
.badge-enrich.ok     { background: rgba(245,158,11,0.12);   color: var(--accent-gold); border: 1px solid rgba(245,158,11,0.3); }
.badge-enrich.weak   { background: var(--accent-red-dim);   color: var(--accent-red); border: 1px solid rgba(239,68,68,0.3); }
.badge-enrich.none   { background: rgba(255,255,255,0.03); color: var(--text-muted); border: 1px solid rgba(255,255,255,0.05); }
.enrich-row { display: flex; gap: 6px; margin-top: 4px; flex-wrap: wrap; }
```

- [ ] **Step 9.3: Add a JS helper that mirrors signal_badges.py**

Inside the existing `<script>` block in index.html (where other JS helpers live — grep for `function ` inside `<script>`), add:
```javascript
// Mirror of pipeline/signal_badges.py — keep in sync when thresholds change.
const TRUST_STRONG = new Set(["A+", "A"]);
const TRUST_OK = new Set(["B+", "B"]);
function trustBadge(grade) {
  if (grade == null) return { emoji: "⚪", label: "—", tone: "none" };
  if (TRUST_STRONG.has(grade)) return { emoji: "🟢", label: grade, tone: "strong" };
  if (TRUST_OK.has(grade))     return { emoji: "🟡", label: grade, tone: "ok" };
  return { emoji: "🔴", label: grade, tone: "weak" };
}
function rankBadge(hr) {
  if (hr == null) return { emoji: "⚪", label: "—", tone: "none" };
  const pct = Math.round(hr * 100);
  if (hr >= 0.60) return { emoji: "🟢", label: pct + "%", tone: "strong" };
  if (hr >= 0.50) return { emoji: "🟡", label: pct + "%", tone: "ok" };
  return { emoji: "🔴", label: pct + "%", tone: "weak" };
}
function convictionBadge(s) {
  if (s == null) return { emoji: "⚪", label: "—", tone: "none" };
  const r = Math.round(s);
  if (s >= 65) return { emoji: "🟢", label: r, tone: "strong" };
  if (s >= 40) return { emoji: "🟡", label: r, tone: "ok" };
  return { emoji: "🔴", label: r, tone: "weak" };
}
function renderBadge(b, prefix) {
  return `<span class="badge-enrich ${b.tone}">${prefix || ""} ${b.label}</span>`;
}
function renderEnrichmentRow(sig) {
  const firstLong = (sig.long_legs || [])[0]?.ticker;
  const firstShort = (sig.short_legs || [])[0]?.ticker;
  const t1 = firstLong ? sig.trust_scores?.[firstLong]?.trust_grade : null;
  const t2 = firstShort ? sig.trust_scores?.[firstShort]?.trust_grade : null;
  const r1 = firstLong ? sig.regime_rank?.[firstLong]?.hit_rate : null;
  const parts = [];
  parts.push(renderBadge(convictionBadge(sig.conviction_score), "CONV"));
  if (t1 != null) parts.push(renderBadge(trustBadge(t1), "L " + firstLong));
  if (t2 != null) parts.push(renderBadge(trustBadge(t2), "S " + firstShort));
  if (r1 != null) parts.push(renderBadge(rankBadge(r1), "RANK"));
  return `<div class="enrich-row">${parts.join("")}</div>`;
}
```

- [ ] **Step 9.4: Insert the badge row into each signal result**

Find the function that builds a result row (grep `.result-row\|result-info` output in Step 9.1). After the `.result-meta` line (typically ends with `</div>` inside the result-info block), insert `${renderEnrichmentRow(sig)}` so the HTML becomes:
```javascript
// inside the signal-card builder
`<div class="result-info">
   <div class="result-name">${name}</div>
   <div class="result-meta">${meta}</div>
   ${renderEnrichmentRow(sig)}
 </div>`
```

(Exact template depends on the existing function — preserve surrounding structure.)

- [ ] **Step 9.5: Smoke test manually**

```bash
cd C:/Users/Claude_Anka/askanka.com
python -m http.server 8000 &
# open http://localhost:8000/index.html in a browser
```
Expected: Each signal row shows a conviction badge (🟢/🟡/🔴 NN), a long-leg trust badge, a short-leg trust badge, and a rank badge. Sample a few signals; trust grades should match the `opus/artifacts/model_portfolio.json` content.

Kill the server after checking:
```bash
jobs -p | xargs -I{} kill {} 2>/dev/null
```

- [ ] **Step 9.6: Commit**

```bash
git add index.html
git commit -m "feat(website): render enrichment badges on signal rows (Task 9)

Each signal card now shows conviction score, long-leg trust grade,
short-leg trust grade, and regime-rank hit rate. JS thresholds mirror
pipeline/signal_badges.py so website and Telegram stay reconciled.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 10: Render the same badges in Telegram

**Files:**
- Modify: `pipeline/telegram_bot.py`
- Modify: `pipeline/tests/test_telegram_bot.py` (or create if missing)

- [ ] **Step 10.1: Write failing test**

Create `pipeline/tests/test_telegram_enrichment_card.py`:
```python
from pipeline.telegram_bot import format_multi_spread_card


def test_spread_card_shows_enrichment_when_present():
    signal = {
        "signal_id": "SIG-TEST-010",
        "event": {"category": "test", "confidence": 0.8, "headline": "Test headline"},
        "spreads": [{
            "spread_name": "X vs Y",
            "tier": "SIGNAL",
            "hit_rate": 0.7,
            "n_precedents": 10,
            "expected_1d_spread": 1.0,
            "long_leg": [{"ticker": "HAL", "price": 100}],
            "short_leg": [{"ticker": "TCS", "price": 200}],
        }],
        # Enrichment fields at signal level (as produced by signal_tracker)
        "trust_scores": {
            "HAL": {"trust_grade": "A", "trust_score": 80},
            "TCS": {"trust_grade": "B+", "trust_score": 70},
        },
        "regime_rank": {"HAL": {"hit_rate": 0.62}, "TCS": {"hit_rate": 0.48}},
        "conviction_score": 72.5,
    }
    card = format_multi_spread_card(signal, regime="NEUTRAL")
    assert "CONV" in card
    assert "73" in card  # conviction rounded
    assert "A" in card   # HAL trust grade
    assert "B+" in card  # TCS trust grade
```

Run: `python -m pytest pipeline/tests/test_telegram_enrichment_card.py -v` — expect FAIL.

- [ ] **Step 10.2: Extend `format_multi_spread_card`**

At the top of `pipeline/telegram_bot.py`, add:
```python
from signal_badges import trust_badge, rank_badge, conviction_badge
```

In `format_multi_spread_card`, after the existing `lines = [...]` block but before the per-spread loop, append an enrichment line when enrichment is present. Find the line `"",` that precedes the spread loop (around line 243) and just before it insert:
```python
trust_scores = signal_card.get("trust_scores") or {}
regime_rank = signal_card.get("regime_rank") or {}
conviction = signal_card.get("conviction_score")
if trust_scores or conviction is not None:
    cb = conviction_badge(conviction)
    enrich_parts = [f"{cb['emoji']} CONV {cb['label']}"]
    for spread in signal_spreads[:1]:  # show for the first (primary) spread
        for lg in spread.get("long_leg", []):
            tg = (trust_scores.get(lg["ticker"]) or {}).get("trust_grade")
            if tg:
                b = trust_badge(tg)
                enrich_parts.append(f"{b['emoji']} L {lg['ticker']} {b['label']}")
        for sg in spread.get("short_leg", []):
            tg = (trust_scores.get(sg["ticker"]) or {}).get("trust_grade")
            if tg:
                b = trust_badge(tg)
                enrich_parts.append(f"{b['emoji']} S {sg['ticker']} {b['label']}")
    lines.append(" | ".join(enrich_parts))
    lines.append("")
```

- [ ] **Step 10.3: Re-run test**

```bash
python -m pytest pipeline/tests/test_telegram_enrichment_card.py -v
```
Expected: PASS.

- [ ] **Step 10.4: Smoke-send a test card**

```bash
python -c "
from pipeline.telegram_bot import format_multi_spread_card, send_message
card = format_multi_spread_card({
    'event': {'category': 'test', 'confidence': 0.8, 'headline': 'Enrichment smoke test'},
    'spreads': [{'spread_name': 'Enrich Test', 'tier': 'SIGNAL', 'hit_rate': 0.7,
                 'n_precedents': 10, 'expected_1d_spread': 1.0,
                 'long_leg': [{'ticker': 'HAL', 'price': 4000}],
                 'short_leg': [{'ticker': 'TCS', 'price': 2500}]}],
    'trust_scores': {'HAL': {'trust_grade': 'A'}, 'TCS': {'trust_grade': 'B+'}},
    'conviction_score': 72.5,
}, regime='NEUTRAL')
print(card)
# Uncomment to actually send:
# send_message(card, parse_mode=None)
"
```
Expected: printed card contains `🟢 CONV 73 | 🟢 L HAL A | 🟡 S TCS B+`.

- [ ] **Step 10.5: Commit**

```bash
git add pipeline/telegram_bot.py pipeline/tests/test_telegram_enrichment_card.py
git commit -m "feat(telegram): render enrichment badges in spread card (Task 10)

format_multi_spread_card now includes a conviction + trust-grade line
when the signal carries enrichment. Uses the shared signal_badges
thresholds so the Telegram card and the website row show identical
labels for the same signal.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 11: Reconciliation test — one fixture, three surfaces, same badges

**Files:**
- Create: `pipeline/tests/test_signal_reconciliation.py`

- [ ] **Step 11.1: Write the reconciliation test**

Create `pipeline/tests/test_signal_reconciliation.py`:
```python
"""Single fixture, three surfaces — assert every surface shows the same
trust/rank/conviction badges for the same signal."""
import re
from pipeline.signal_badges import trust_badge, rank_badge, conviction_badge
from pipeline.telegram_bot import format_multi_spread_card


FIXTURE = {
    "signal_id": "SIG-RECON",
    "event": {"category": "test", "confidence": 0.85, "headline": "Reconciliation"},
    "spreads": [{
        "spread_name": "HAL vs TCS",
        "tier": "SIGNAL",
        "hit_rate": 0.7,
        "n_precedents": 20,
        "expected_1d_spread": 1.2,
        "long_leg": [{"ticker": "HAL", "price": 4000}],
        "short_leg": [{"ticker": "TCS", "price": 2500}],
    }],
    "trust_scores": {
        "HAL": {"trust_grade": "A", "trust_score": 80},
        "TCS": {"trust_grade": "C", "trust_score": 35},
    },
    "regime_rank": {"HAL": {"hit_rate": 0.62}, "TCS": {"hit_rate": 0.48}},
    "conviction_score": 68.0,
}


def test_reconciliation_badges_match_across_surfaces():
    # Python badge helpers
    t_hal = trust_badge("A")
    t_tcs = trust_badge("C")
    r_hal = rank_badge(0.62)
    conv = conviction_badge(68.0)

    # All Python badges agree among themselves
    assert t_hal["tone"] == "strong" and t_hal["label"] == "A"
    assert t_tcs["tone"] == "weak"   and t_tcs["label"] == "C"
    assert r_hal["tone"] == "strong" and r_hal["label"] == "62%"
    assert conv["tone"]  == "strong" and conv["label"]  == "68"

    # Telegram card carries same labels
    card = format_multi_spread_card(FIXTURE, regime="NEUTRAL")
    assert "CONV 68" in card
    assert "L HAL A" in card
    assert "S TCS C" in card

    # index.html JS would produce the same labels. Verify by reading the JS
    # thresholds embedded in the file and asserting they match.
    from pathlib import Path
    html = Path("index.html").read_text(encoding="utf-8")
    # Sanity: the JS thresholds mirror the Python ones
    assert 'TRUST_STRONG = new Set(["A+", "A"])' in html
    assert "hr >= 0.60" in html  # rank strong threshold
    assert "s >= 65" in html     # conviction strong threshold
```

- [ ] **Step 11.2: Run the reconciliation test**

```bash
python -m pytest pipeline/tests/test_signal_reconciliation.py -v
```
Expected: PASS.

- [ ] **Step 11.3: Run the full test suite for regressions**

```bash
python -m pytest pipeline/tests/ -v 2>&1 | tail -40
```
Expected: all tests green. If any pre-existing test breaks, fix it — do not skip.

- [ ] **Step 11.4: Commit**

```bash
git add pipeline/tests/test_signal_reconciliation.py
git commit -m "test(signal): reconciliation across Python, Telegram, index.html (Task 11)

Single fixture asserts trust/rank/conviction labels match across all
three surfaces. Catches drift between signal_badges.py and the
JS-mirror thresholds in index.html.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 12: Dry-run on live data + watchdog clean

**Files:** no code — verification only.

- [ ] **Step 12.1: Regenerate live website payload with enrichment**

```bash
cd C:/Users/Claude_Anka/askanka.com
python pipeline/website_exporter.py
python -c "
import json
d = json.load(open('data/open_signals.json'))
if not isinstance(d, list) or not d:
    print('⚠ no signals in open_signals.json — cannot dry-run')
else:
    sig = d[0]
    print('enrichment keys on first signal:', sorted(k for k in sig if k in ('trust_scores','regime_rank','correlation_breaks','oi_anomalies','conviction_score','gate_reason','gate_blocked')))
    print('conviction_score:', sig.get('conviction_score'))
    print('gate_reason:', sig.get('gate_reason'))
    print('trust_scores:', sig.get('trust_scores'))
"
```
Expected output contains all 7 enrichment keys and populated `trust_scores`.

- [ ] **Step 12.2: Dry-run the break generator against today's data**

```bash
python -c "
from pipeline.break_signal_generator import generate_break_candidates
cands = generate_break_candidates()
print(f'break candidates: {len(cands)}')
for c in cands[:5]:
    print(' ', c['signal_id'], '|', c['spread_name'], '| long' if c['long_legs'] else '| short')
"
```
Expected: 0+ candidates printed (0 is fine — means no actionable breaks today; any breaks with `trade_rec=None` are intentionally filtered out per Task 6).

- [ ] **Step 12.3: Watchdog still clean**

```bash
python -m pipeline.watchdog --all --dry-run 2>&1 | grep -E "issues|CRITICAL|WARN|DRIFT"
```
Expected: `Gate run • 0 issues`, `CRITICAL (0)`, `WARN (0)`, `DRIFT (0)`.

- [ ] **Step 12.4: Manual website check**

```bash
python -m http.server 8000 &
# Browser: http://localhost:8000/index.html — verify badges render on signal rows.
# Kill server:
jobs -p | xargs -I{} kill {} 2>/dev/null
```
Expected: badges visible and legible.

- [ ] **Step 12.5: Commit verification notes**

```bash
git commit --allow-empty -m "verify(signal): dry-run on live data passes (Task 12)

- website_exporter writes enrichment fields to data/open_signals.json
- break_signal_generator emits 0+ candidates from today's breaks
- watchdog still 0 issues
- index.html renders badges manually verified

Gate remains SIGNAL_GATE_ENABLED=False. Revisit tomorrow after a full
trading day of enriched signals to decide whether to flip gating on.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
git push origin feat/data-freshness-watchdog
```

---

## Self-review

**Spec coverage:**
- OPUS Trust → signals: Task 1 (loader), Task 2 (attach), Task 3 (gate), Task 5 (integrate) ✓
- Phase C breaks → signals as candidates: Task 1 (loader), Task 6 (generator), Task 7 (integration) ✓
- Phase A regime rank → signals: Task 1 (loader), Task 2 (attach), Task 3 (gate) ✓
- OI anomalies → signals: Task 1 (loader), Task 2 (attach), Task 3 (gate) ✓
- Website reconciles: Task 8 (exporter), Task 9 (renderer) ✓
- Telegram reconciles: Task 10 (renderer) ✓
- Cross-surface reconciliation test: Task 11 ✓
- Gate is flagged off pending review: Task 3 (flag), Task 12 (dry-run, decide later) ✓
- Rollback safety: all changes additive, flag-gated ✓

**Placeholder scan:** no "TBD" / "implement later" / "similar to Task N" strings detected; every code step has real code.

**Type consistency:** `enrich_signal` accepts `trust_cache, breaks_cache, profile_cache, oi_cache` throughout. `_strip_signal_for_web` accepts `dict` and returns `dict`. `generate_break_candidates` returns `List[Dict[str, Any]]`. `save_open_signal` accepts a signal dict. Consistent.

**Known deferred (out of scope — not silent gaps):**
- `morning_brief.py` still only reads correlation_report. Enriching the 07:30 Telegram brief is a separate follow-up plan.
- Article pipeline still uses only 4 inputs. Separate plan.
- Conviction score thresholds (40/65) and hard-rule grades are first-pass values — will need backtest validation after a few days of real data.

---

Plan complete and saved to `docs/superpowers/plans/2026-04-16-wire-rigour-into-signals.md`.

**Two execution options:**

1. **Subagent-Driven (recommended)** — I dispatch a fresh subagent per task with two-stage review (spec compliance → code quality) between each task. Faster iteration, higher quality.

2. **Inline Execution** — I execute tasks directly in this session with checkpoints for review.

Which approach?
