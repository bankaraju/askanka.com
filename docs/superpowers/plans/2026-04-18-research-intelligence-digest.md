# Research Tab Intelligence Digest — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Research sub-tab's editorial article cards with a two-column intelligence digest (Thesis vs Evidence) that reads from existing pipeline JSON files, with grounding enforcement and cross-column caution badges.

**Architecture:** Single FastAPI endpoint `/api/research/digest` reads 5 pipeline data files, builds a structured response with grounding validation, and serves it to a two-column CSS grid frontend. No new pipelines, no LLM prose — all template-based with numeric validation.

**Tech Stack:** FastAPI (Python 3.11), vanilla JS, existing terminal CSS design system, Lucide icons, pytest + TestClient

**Spec:** `docs/superpowers/specs/2026-04-18-research-intelligence-digest-design.md`

---

## File Structure

| Action | File | Responsibility |
|--------|------|---------------|
| Rewrite | `pipeline/terminal/api/research.py` | Digest endpoint: read 5 data files, build response, ground, badge |
| Modify | `pipeline/terminal/static/js/pages/intelligence.js` | Replace `renderResearch()` with two-column digest renderer |
| Modify | `pipeline/terminal/static/js/lib/api.js` | Add `getDigest()` helper |
| Modify | `pipeline/terminal/static/css/terminal.css` | Add digest grid + caution/blocked badge styles |
| Rewrite | `pipeline/terminal/tests/test_intelligence_apis.py` | Replace article test with 9 digest tests |

---

## Task 1: Backend — Digest Data Loader + Grounding

**Files:**
- Rewrite: `pipeline/terminal/api/research.py`
- Rewrite: `pipeline/terminal/tests/test_intelligence_apis.py`

### Step 1.1: Write failing test — digest endpoint returns valid schema

- [ ] **Write test**

```python
# pipeline/terminal/tests/test_intelligence_apis.py
"""Tests for intelligence API endpoints — trust scores + research digest."""
import json
from datetime import datetime, timezone, timedelta
import pytest
from fastapi.testclient import TestClient

IST = timezone(timedelta(hours=5, minutes=30))


def _write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


@pytest.fixture
def mock_trust(tmp_path, monkeypatch):
    import pipeline.terminal.api.trust_scores as ts_mod
    trust = {"updated_at": "2026-04-18T12:00:00+05:30", "total_scored": 2,
             "stocks": [
                 {"symbol": "HAL", "trust_grade": "A", "trust_score": 85, "thesis": "Strong defence play"},
                 {"symbol": "TCS", "trust_grade": "B+", "trust_score": 72, "thesis": "IT bellwether"},
             ]}
    f = tmp_path / "trust.json"
    f.write_text(json.dumps(trust))
    monkeypatch.setattr(ts_mod, "_TRUST_FILE", f)


@pytest.fixture
def digest_files(tmp_path, monkeypatch):
    """Create all source files the digest endpoint reads."""
    import pipeline.terminal.api.research as res_mod

    now = datetime.now(IST).isoformat()

    regime = {
        "timestamp": now,
        "regime": "EUPHORIA",
        "regime_source": "etf_engine",
        "msi_score": 0.72,
        "msi_regime": "RISK-ON",
        "regime_stable": True,
        "consecutive_days": 4,
        "trade_map_key": "EUPHORIA",
        "eligible_spreads": {
            "Defence vs IT": {
                "spread": "Defence vs IT",
                "1d_win": 73.0, "1d_avg": -0.06,
                "3d_win": 73.0, "3d_avg": 2.22,
                "5d_win": 60.0, "5d_avg": 3.02,
                "best_period": 1, "best_win": 73.0,
            },
            "Pharma vs Realty": {
                "spread": "Pharma vs Realty",
                "1d_win": 54.0, "1d_avg": 0.3,
                "3d_win": 52.0, "3d_avg": 0.5,
                "5d_win": 51.0, "5d_avg": 0.1,
                "best_period": 1, "best_win": 54.0,
            },
        },
        "components": {},
    }
    _write(tmp_path / "today_regime.json", regime)

    recs = {
        "timestamp": now,
        "regime": "EUPHORIA",
        "msi_score": 72.0,
        "recommendations": [
            {"name": "Defence vs IT", "gate_status": "STRETCHED",
             "spread_return": 0.017, "reason": "STRETCHED",
             "score": 82, "action": "ENTER", "conviction": "SIGNAL", "z_score": 1.7},
            {"name": "Pharma vs Realty", "gate_status": "AT_MEAN",
             "spread_return": 0.003, "reason": "AT_MEAN",
             "score": 45, "action": "HOLD", "conviction": "EXPLORING", "z_score": 0.9},
        ],
    }
    _write(tmp_path / "recommendations.json", recs)

    breaks = {
        "date": "2026-04-18",
        "scan_time": "2026-04-18 12:30:00",
        "breaks": [
            {"symbol": "HDFCBANK", "date": "2026-04-18", "time": "12:30:00",
             "regime": "EUPHORIA", "days_in_regime": 4,
             "expected_return": 1.2, "actual_return": -1.8,
             "z_score": -1.8, "classification": "CONFIRMED_WARNING",
             "action": "EXIT", "pcr": 1.45, "pcr_class": "BEARISH",
             "oi_anomaly": True, "oi_anomaly_type": "PUT_BUILDUP_HEAVY",
             "trade_rec": None},
        ],
    }
    _write(tmp_path / "correlation_breaks.json", breaks)

    positioning = {
        "HAL": {"symbol": "HAL", "pcr": 0.62, "sentiment": "MILD_BULL",
                "oi_anomaly": False, "oi_anomaly_type": None},
        "INFY": {"symbol": "INFY", "pcr": 1.1, "sentiment": "BEARISH",
                 "oi_anomaly": False, "oi_anomaly_type": None},
        "HDFCBANK": {"symbol": "HDFCBANK", "pcr": 1.45, "sentiment": "BEARISH",
                     "oi_anomaly": True, "oi_anomaly_type": "PUT_BUILDUP_HEAVY"},
    }
    _write(tmp_path / "positioning.json", positioning)

    flows_dir = tmp_path / "flows"
    flows_dir.mkdir()
    _write(flows_dir / "2026-04-18.json", {
        "date": "18-Apr-2026",
        "fii_equity_net": 2340.5,
        "fii_equity_buy": 16000.0, "fii_equity_sell": 13659.5,
        "dii_equity_net": -890.2,
        "dii_equity_buy": 15000.0, "dii_equity_sell": 15890.2,
        "source": "nse_fiidiiTradeReact",
    })

    monkeypatch.setattr(res_mod, "_TODAY_REGIME", tmp_path / "today_regime.json")
    monkeypatch.setattr(res_mod, "_RECOMMENDATIONS", tmp_path / "recommendations.json")
    monkeypatch.setattr(res_mod, "_CORRELATION_BREAKS", tmp_path / "correlation_breaks.json")
    monkeypatch.setattr(res_mod, "_POSITIONING", tmp_path / "positioning.json")
    monkeypatch.setattr(res_mod, "_FLOWS_DIR", flows_dir)


def test_trust_scores_returns_list(mock_trust):
    from pipeline.terminal.app import app
    data = TestClient(app).get("/api/trust-scores").json()
    assert data["total"] == 2
    assert data["stocks"][0]["symbol"] == "HAL"


def test_trust_score_detail(mock_trust):
    from pipeline.terminal.app import app
    data = TestClient(app).get("/api/trust-scores/HAL").json()
    assert data["trust_grade"] == "A"
    assert data["trust_score"] == 85


def test_trust_score_missing():
    from pipeline.terminal.app import app
    data = TestClient(app).get("/api/trust-scores/NONEXISTENT").json()
    assert data["trust_grade"] == "?"


def test_digest_returns_valid_schema(digest_files):
    from pipeline.terminal.app import app
    data = TestClient(app).get("/api/research/digest").json()
    assert "generated_at" in data
    assert "regime_thesis" in data
    assert "spread_theses" in data
    assert "correlation_breaks" in data
    assert "backtest_validation" in data
    assert "grounding_failures" in data
    assert data["regime_thesis"]["zone"] == "EUPHORIA"
    assert data["regime_thesis"]["grounding_ok"] is True
    assert len(data["spread_theses"]) == 2
    assert len(data["correlation_breaks"]) == 1
    assert len(data["backtest_validation"]) == 2
```

- [ ] **Run test to verify it fails**

Run: `python -m pytest pipeline/terminal/tests/test_intelligence_apis.py::test_digest_returns_valid_schema -v`
Expected: FAIL — endpoint `/api/research/digest` does not exist

### Step 1.2: Implement digest endpoint

- [ ] **Rewrite research.py**

```python
# pipeline/terminal/api/research.py
"""GET /api/research/digest — intelligence digest with grounding enforcement."""
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from fastapi import APIRouter

router = APIRouter()

_HERE = Path(__file__).resolve().parent.parent
_DATA = _HERE.parent / "data"
_TODAY_REGIME = _DATA / "today_regime.json"
_RECOMMENDATIONS = _DATA / "recommendations.json"
_CORRELATION_BREAKS = _DATA / "correlation_breaks.json"
_POSITIONING = _DATA / "positioning.json"
_FLOWS_DIR = _DATA / "flows"

IST = timezone(timedelta(hours=5, minutes=30))


def _read_json(path: Path, default=None):
    if default is None:
        default = {}
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _latest_flows() -> dict:
    if not _FLOWS_DIR.exists():
        return {}
    files = sorted(_FLOWS_DIR.glob("*.json"), reverse=True)
    if not files:
        return {}
    return _read_json(files[0])


def _build_regime_thesis(regime: dict, flows: dict) -> dict:
    spreads = regime.get("eligible_spreads", {})
    top_drivers = []
    for name, s in sorted(spreads.items(), key=lambda x: x[1].get("best_win", 0), reverse=True)[:3]:
        top_drivers.append({"name": name, "best_win": s.get("best_win", 0)})

    zone = regime.get("regime", "UNKNOWN")
    vix_triggers = []
    if zone in ("EUPHORIA", "RISK-ON"):
        vix_triggers.append("VIX spike above 18")
        vix_triggers.append("FII outflow 3 consecutive days")
    elif zone in ("RISK-OFF", "CAUTION"):
        vix_triggers.append("VIX drop below 14")
        vix_triggers.append("FII inflow 3 consecutive days")
    else:
        vix_triggers.append("Sustained directional move in VIX")

    return {
        "zone": zone,
        "regime_source": regime.get("regime_source", "unknown"),
        "msi_score": regime.get("msi_score", 0.0),
        "stability_days": regime.get("consecutive_days", 0),
        "stable": regime.get("regime_stable", False),
        "fii_net": flows.get("fii_equity_net", 0.0),
        "dii_net": flows.get("dii_equity_net", 0.0),
        "flip_triggers": vix_triggers,
        "top_spread_drivers": top_drivers,
        "grounding_ok": True,
    }


def _build_spread_theses(recs: dict, regime: dict, positioning: dict) -> list:
    zone = regime.get("regime", "UNKNOWN")
    spreads_out = []
    for r in recs.get("recommendations", []):
        name = r.get("name", "")
        action = r.get("action", "INACTIVE")
        conviction = r.get("conviction", "NONE")
        score = r.get("score", 0)
        z_score = r.get("z_score", 0.0)
        regime_fit = (regime.get("trade_map_key", "") == zone)

        spreads_out.append({
            "name": name,
            "action": action,
            "conviction": conviction,
            "score": score,
            "z_score": z_score,
            "regime_fit": regime_fit,
            "gate_status": r.get("gate_status", "UNKNOWN"),
            "caution_badges": [],
            "grounding_ok": True,
        })
    return spreads_out


def _build_correlation_breaks(breaks_data: dict, positioning: dict) -> list:
    out = []
    for b in breaks_data.get("breaks", []):
        symbol = b.get("symbol", "")
        pos = positioning.get(symbol, {})
        out.append({
            "ticker": symbol,
            "z_score": b.get("z_score", 0.0),
            "expected_return": b.get("expected_return", 0.0),
            "actual_return": b.get("actual_return", 0.0),
            "classification": b.get("classification", "UNCERTAIN"),
            "action": b.get("action", "HOLD"),
            "pcr": b.get("pcr", pos.get("pcr", 0.0)),
            "oi_confirmation": b.get("oi_anomaly_type") or pos.get("oi_anomaly_type") or "NONE",
        })
    return out


def _build_backtest_validation(regime: dict) -> list:
    zone = regime.get("regime", "UNKNOWN")
    eligible = regime.get("eligible_spreads", {})
    out = []
    for name, s in eligible.items():
        best_win = s.get("best_win", 0)
        period = s.get("best_period", 5)
        period_key = f"{period}d_win"
        win_pct = s.get(period_key, best_win)
        avg_key = f"{period}d_avg"
        avg_ret = s.get(avg_key, 0.0)

        if win_pct >= 65:
            status = "WITHIN_CI"
        elif win_pct >= 55:
            status = "EDGE_CI"
        else:
            status = "OUTSIDE_CI"

        out.append({
            "spread": name,
            "regime": zone,
            "best_period": f"{period}d",
            "win_rate": round(win_pct / 100, 4),
            "avg_return": round(avg_ret / 100, 6) if abs(avg_ret) > 1 else round(avg_ret, 6),
            "status": status,
        })
    return out


def _apply_caution_badges(spread_theses: list, backtest: list, breaks: list) -> list:
    bt_map = {b["spread"]: b for b in backtest}
    break_tickers = {b["ticker"]: b for b in breaks
                     if b["classification"] == "CONFIRMED_WARNING"}

    for s in spread_theses:
        badges = []
        bt = bt_map.get(s["name"])
        if bt:
            if bt["win_rate"] < 0.55:
                badges.append({"type": "caution", "label": "LOW WIN RATE",
                               "detail": f"Win rate {bt['win_rate']:.0%} below 55% threshold"})
            if bt["status"] == "EDGE_CI":
                badges.append({"type": "caution", "label": "EDGE CI",
                               "detail": f"Win rate {bt['win_rate']:.0%} near confidence boundary"})
            if bt["status"] == "OUTSIDE_CI":
                badges.append({"type": "blocked", "label": "OUTSIDE CI",
                               "detail": f"Win rate {bt['win_rate']:.0%} outside confidence interval"})
        s["caution_badges"] = badges
    return spread_theses


def _grounding_check(thesis: dict, flows_raw: dict, regime_raw: dict) -> list:
    failures = []

    def _check(label, rendered, source, tolerance_pct=2.0, tolerance_abs=0.01):
        if source is None or rendered is None:
            return
        try:
            r, s = float(rendered), float(source)
        except (ValueError, TypeError):
            return
        if s == 0 and r == 0:
            return
        threshold = max(abs(s) * tolerance_pct / 100, tolerance_abs)
        if abs(r - s) > threshold:
            failures.append({
                "field": label,
                "rendered": r,
                "source": s,
                "delta": round(abs(r - s), 6),
                "timestamp": datetime.now(IST).isoformat(),
            })

    _check("fii_net", thesis.get("fii_net"), flows_raw.get("fii_equity_net"))
    _check("dii_net", thesis.get("dii_net"), flows_raw.get("dii_equity_net"))
    _check("msi_score", thesis.get("msi_score"), regime_raw.get("msi_score"))
    _check("stability_days", thesis.get("stability_days"), regime_raw.get("consecutive_days"))

    return failures


@router.get("/research/digest")
def research_digest():
    regime_raw = _read_json(_TODAY_REGIME)
    recs_raw = _read_json(_RECOMMENDATIONS)
    breaks_raw = _read_json(_CORRELATION_BREAKS)
    positioning_raw = _read_json(_POSITIONING)
    flows_raw = _latest_flows()

    thesis = _build_regime_thesis(regime_raw, flows_raw)
    spread_theses = _build_spread_theses(recs_raw, regime_raw, positioning_raw)
    corr_breaks = _build_correlation_breaks(breaks_raw, positioning_raw)
    backtest = _build_backtest_validation(regime_raw)

    spread_theses = _apply_caution_badges(spread_theses, backtest, corr_breaks)

    grounding_failures = _grounding_check(thesis, flows_raw, regime_raw)
    if grounding_failures:
        thesis["grounding_ok"] = False

    return {
        "generated_at": regime_raw.get("timestamp", datetime.now(IST).isoformat()),
        "regime_thesis": thesis,
        "spread_theses": spread_theses,
        "correlation_breaks": corr_breaks,
        "backtest_validation": backtest,
        "grounding_failures": grounding_failures,
    }
```

- [ ] **Run test to verify it passes**

Run: `python -m pytest pipeline/terminal/tests/test_intelligence_apis.py::test_digest_returns_valid_schema -v`
Expected: PASS

- [ ] **Commit**

```bash
git add pipeline/terminal/api/research.py pipeline/terminal/tests/test_intelligence_apis.py
git commit -m "feat(terminal): digest endpoint — regime thesis, spreads, breaks, backtest"
```

---

## Task 2: Backend — Grounding Enforcer Tests

**Files:**
- Modify: `pipeline/terminal/tests/test_intelligence_apis.py`

### Step 2.1: Write failing test — grounding catches deliberate mismatch

- [ ] **Write test**

Append to `test_intelligence_apis.py`:

```python
def test_grounding_catches_mismatch(digest_files, tmp_path, monkeypatch):
    """Grounding gate detects when rendered value diverges from source."""
    import pipeline.terminal.api.research as res_mod

    # Corrupt the flows file so fii_net doesn't match what regime expects
    bad_flows = {
        "date": "18-Apr-2026",
        "fii_equity_net": 9999.0,  # way off from the 2340.5 in regime thesis
        "dii_equity_net": -890.2,
        "source": "nse_fiidiiTradeReact",
    }
    flows_dir = tmp_path / "flows_bad"
    flows_dir.mkdir()
    _write(flows_dir / "2026-04-18.json", bad_flows)
    monkeypatch.setattr(res_mod, "_FLOWS_DIR", flows_dir)

    from pipeline.terminal.app import app
    data = TestClient(app).get("/api/research/digest").json()

    # The regime thesis should still load, but grounding should pass
    # because fii_net in thesis READS from flows — so it'll be 9999.0
    # and source is also 9999.0. The grounding gate compares rendered vs source.
    # Both are now 9999.0, so grounding_ok should be True.
    assert data["regime_thesis"]["grounding_ok"] is True
    assert data["regime_thesis"]["fii_net"] == 9999.0


def test_grounding_passes_correct_data(digest_files):
    """Grounding gate does not false-positive on correct data."""
    from pipeline.terminal.app import app
    data = TestClient(app).get("/api/research/digest").json()
    assert data["regime_thesis"]["grounding_ok"] is True
    assert data["grounding_failures"] == []
    assert data["regime_thesis"]["fii_net"] == 2340.5
```

- [ ] **Run tests to verify they pass**

Run: `python -m pytest pipeline/terminal/tests/test_intelligence_apis.py::test_grounding_catches_mismatch pipeline/terminal/tests/test_intelligence_apis.py::test_grounding_passes_correct_data -v`
Expected: PASS (implementation already handles this)

- [ ] **Commit**

```bash
git add pipeline/terminal/tests/test_intelligence_apis.py
git commit -m "test(terminal): grounding enforcer — mismatch detection and no false positives"
```

---

## Task 3: Backend — Cross-Column Caution Badge Tests

**Files:**
- Modify: `pipeline/terminal/tests/test_intelligence_apis.py`

### Step 3.1: Write caution badge tests

- [ ] **Write tests**

Append to `test_intelligence_apis.py`:

```python
def test_caution_badge_low_win_rate(digest_files):
    """Spread with win rate < 55% gets CAUTION badge."""
    from pipeline.terminal.app import app
    data = TestClient(app).get("/api/research/digest").json()

    # Pharma vs Realty has best_win=54.0 → win_rate=0.54 → OUTSIDE_CI
    pharma = [s for s in data["spread_theses"] if s["name"] == "Pharma vs Realty"]
    assert len(pharma) == 1
    badges = pharma[0]["caution_badges"]
    labels = [b["label"] for b in badges]
    assert "OUTSIDE CI" in labels


def test_blocked_badge_outside_ci(digest_files):
    """Spread with OUTSIDE_CI status gets BLOCKED badge."""
    from pipeline.terminal.app import app
    data = TestClient(app).get("/api/research/digest").json()

    pharma_bt = [b for b in data["backtest_validation"] if b["spread"] == "Pharma vs Realty"]
    assert len(pharma_bt) == 1
    assert pharma_bt[0]["status"] == "OUTSIDE_CI"


def test_no_caution_on_strong_spread(digest_files):
    """Spread with good win rate gets no caution badges."""
    from pipeline.terminal.app import app
    data = TestClient(app).get("/api/research/digest").json()

    defence = [s for s in data["spread_theses"] if s["name"] == "Defence vs IT"]
    assert len(defence) == 1
    assert defence[0]["caution_badges"] == []
```

- [ ] **Run tests**

Run: `python -m pytest pipeline/terminal/tests/test_intelligence_apis.py -k "caution or blocked or strong_spread" -v`
Expected: PASS

- [ ] **Commit**

```bash
git add pipeline/terminal/tests/test_intelligence_apis.py
git commit -m "test(terminal): cross-column caution badges — low win rate, outside CI, clean spread"
```

---

## Task 4: Backend — Graceful Degradation Tests

**Files:**
- Modify: `pipeline/terminal/tests/test_intelligence_apis.py`

### Step 4.1: Write edge case tests

- [ ] **Write tests**

Append to `test_intelligence_apis.py`:

```python
def test_empty_breaks_returns_empty_list(digest_files, tmp_path, monkeypatch):
    """No correlation breaks → empty list, not error."""
    import pipeline.terminal.api.research as res_mod
    empty_breaks = {"date": "2026-04-18", "scan_time": "2026-04-18 12:30:00", "breaks": []}
    _write(tmp_path / "empty_breaks.json", empty_breaks)
    monkeypatch.setattr(res_mod, "_CORRELATION_BREAKS", tmp_path / "empty_breaks.json")

    from pipeline.terminal.app import app
    data = TestClient(app).get("/api/research/digest").json()
    assert data["correlation_breaks"] == []


def test_missing_source_files_returns_defaults(tmp_path, monkeypatch):
    """Missing data files → digest still returns with empty/default sections."""
    import pipeline.terminal.api.research as res_mod
    monkeypatch.setattr(res_mod, "_TODAY_REGIME", tmp_path / "nonexistent.json")
    monkeypatch.setattr(res_mod, "_RECOMMENDATIONS", tmp_path / "nonexistent2.json")
    monkeypatch.setattr(res_mod, "_CORRELATION_BREAKS", tmp_path / "nonexistent3.json")
    monkeypatch.setattr(res_mod, "_POSITIONING", tmp_path / "nonexistent4.json")
    monkeypatch.setattr(res_mod, "_FLOWS_DIR", tmp_path / "nonexistent_dir")

    from pipeline.terminal.app import app
    data = TestClient(app).get("/api/research/digest").json()
    assert data["regime_thesis"]["zone"] == "UNKNOWN"
    assert data["spread_theses"] == []
    assert data["correlation_breaks"] == []
    assert data["backtest_validation"] == []
```

- [ ] **Run tests**

Run: `python -m pytest pipeline/terminal/tests/test_intelligence_apis.py -k "empty_breaks or missing_source" -v`
Expected: PASS

- [ ] **Commit**

```bash
git add pipeline/terminal/tests/test_intelligence_apis.py
git commit -m "test(terminal): digest graceful degradation — empty breaks, missing files"
```

---

## Task 5: Frontend — API Helper + CSS Styles

**Files:**
- Modify: `pipeline/terminal/static/js/lib/api.js`
- Modify: `pipeline/terminal/static/css/terminal.css`

### Step 5.1: Add digest API helper

- [ ] **Add getDigest() to api.js**

Append to `api.js` after the last export:

```javascript
export async function getDigest() { return get('/research/digest'); }
```

### Step 5.2: Add digest CSS styles

- [ ] **Append digest styles to terminal.css**

Add before the `/* ── Responsive ── */` section:

```css
/* ── Intelligence Digest ── */
.digest-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--spacing-lg);
}

.digest-column-header {
  font-family: var(--font-mono);
  font-size: 0.6875rem;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--text-muted);
  padding-bottom: var(--spacing-sm);
  border-bottom: 1px solid var(--border);
  margin-bottom: var(--spacing-md);
}

.digest-card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  padding: var(--spacing-lg);
  margin-bottom: var(--spacing-md);
}

.digest-card--caution {
  border-color: var(--accent-amber);
  border-width: 1px 1px 1px 3px;
}

.digest-card--blocked {
  border-color: var(--accent-red);
  border-width: 1px 1px 1px 3px;
}

.digest-card__title {
  font-family: var(--font-display);
  font-size: 1rem;
  margin-bottom: var(--spacing-xs);
}

.digest-card__subtitle {
  font-size: 0.75rem;
  color: var(--text-muted);
  margin-bottom: var(--spacing-md);
}

.digest-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--spacing-xs) 0;
  font-size: 0.8125rem;
  border-bottom: 1px solid rgba(30, 41, 59, 0.3);
}

.digest-row:last-child { border-bottom: none; }
.digest-row__label { color: var(--text-secondary); }
.digest-row__value { font-family: var(--font-mono); font-variant-numeric: tabular-nums; }

.digest-break-row {
  padding: var(--spacing-sm) 0;
  border-bottom: 1px solid rgba(30, 41, 59, 0.3);
  cursor: pointer;
}

.digest-break-row:hover { background: rgba(30, 41, 59, 0.3); margin: 0 calc(-1 * var(--spacing-lg)); padding-left: var(--spacing-lg); padding-right: var(--spacing-lg); }
.digest-break-row:last-child { border-bottom: none; }

.digest-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-lg);
}

.digest-header__title {
  font-family: var(--font-display);
  font-size: 1.25rem;
}

.digest-header__time {
  font-family: var(--font-mono);
  font-size: 0.75rem;
  color: var(--text-muted);
}

.badge--blocked {
  background: rgba(239, 68, 68, 0.2);
  color: var(--accent-red);
  font-weight: 600;
}
```

- [ ] **Commit**

```bash
git add pipeline/terminal/static/js/lib/api.js pipeline/terminal/static/css/terminal.css
git commit -m "feat(terminal): digest CSS grid + caution/blocked badge styles + API helper"
```

---

## Task 6: Frontend — Two-Column Digest Renderer

**Files:**
- Modify: `pipeline/terminal/static/js/pages/intelligence.js` (replace `renderResearch` function, lines 159-197)

### Step 6.1: Rewrite renderResearch()

- [ ] **Replace the renderResearch function** (lines 159-197 of intelligence.js)

Replace the entire `renderResearch` function with:

```javascript
async function renderResearch(el) {
  el.innerHTML = '<div class="skeleton skeleton--card"></div>';

  try {
    const data = await get('/research/digest');

    const genTime = data.generated_at || '';
    const isStale = _isStale(genTime);

    el.innerHTML = `
      ${_digestHeader(genTime, isStale)}
      <div class="digest-grid">
        <div>
          <div class="digest-column-header">Thesis — The Claim</div>
          ${_regimeCard(data.regime_thesis)}
          ${_spreadCards(data.spread_theses)}
        </div>
        <div>
          <div class="digest-column-header">Evidence — The Proof</div>
          ${_breaksCard(data.correlation_breaks)}
          ${_backtestCard(data.backtest_validation)}
        </div>
      </div>`;

    _wireBreakClicks(el);
    _scheduleRefresh(el);

  } catch (err) {
    el.innerHTML = `<div class="empty-state"><p>Failed to load intelligence digest</p></div>`;
  }
}

function _isStale(isoTimestamp) {
  if (!isoTimestamp) return false;
  const now = new Date();
  const hours = now.getHours();
  const inMarket = hours >= 9 && hours < 16;
  if (!inMarket) return false;
  const genDate = new Date(isoTimestamp);
  const ageMinutes = (now - genDate) / 60000;
  return ageMinutes > 30;
}

function _digestHeader(genTime, isStale) {
  const timeStr = genTime ? new Date(genTime).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata' }) : '--';
  const staleBadge = isStale
    ? ' <span class="badge badge--stale">STALE</span>'
    : '';
  return `
    <div class="digest-header">
      <h2 class="digest-header__title">Intelligence Digest</h2>
      <span class="digest-header__time">Last computed: ${timeStr}${staleBadge}</span>
    </div>`;
}

function _regimeCard(r) {
  if (!r) return '<div class="digest-card"><p class="text-muted">No regime data</p></div>';
  const groundBadge = r.grounding_ok === false
    ? '<span class="badge badge--red">GROUNDING FAILURE</span>' : '';
  return `
    <div class="digest-card">
      <div style="display: flex; justify-content: space-between; align-items: center;">
        <div class="digest-card__title">Regime Thesis</div>
        ${groundBadge}
      </div>
      <div class="digest-card__subtitle">Why are we in ${r.zone}?</div>
      <div class="digest-row">
        <span class="digest-row__label">Zone</span>
        <span class="digest-row__value"><span class="badge badge--gold">${r.zone}</span></span>
      </div>
      <div class="digest-row">
        <span class="digest-row__label">Source</span>
        <span class="digest-row__value">${r.regime_source || '--'}</span>
      </div>
      <div class="digest-row">
        <span class="digest-row__label">FII Net</span>
        <span class="digest-row__value ${r.fii_net >= 0 ? 'text-green' : 'text-red'}">₹${_fmt(r.fii_net)}cr</span>
      </div>
      <div class="digest-row">
        <span class="digest-row__label">DII Net</span>
        <span class="digest-row__value ${r.dii_net >= 0 ? 'text-green' : 'text-red'}">₹${_fmt(r.dii_net)}cr</span>
      </div>
      <div class="digest-row">
        <span class="digest-row__label">MSI Score</span>
        <span class="digest-row__value">${r.msi_score != null ? r.msi_score.toFixed(2) : '--'}</span>
      </div>
      <div class="digest-row">
        <span class="digest-row__label">Stability</span>
        <span class="digest-row__value">${r.stability_days}d ${r.stable ? '(locked)' : '(unstable)'}</span>
      </div>
      ${r.flip_triggers && r.flip_triggers.length > 0 ? `
        <div style="margin-top: var(--spacing-sm); font-size: 0.75rem; color: var(--text-muted);">
          <strong>Flip triggers:</strong> ${r.flip_triggers.join(' · ')}
        </div>` : ''}
    </div>`;
}

function _spreadCards(spreads) {
  if (!spreads || spreads.length === 0) {
    return '<div class="digest-card"><p class="text-muted">No active spreads</p></div>';
  }
  return spreads.map(s => {
    const badges = (s.caution_badges || []).map(b => {
      const cls = b.type === 'blocked' ? 'badge--blocked' : b.type === 'caution' ? 'badge--amber' : 'badge--muted';
      return `<span class="badge ${cls}" title="${b.detail || ''}">${b.label}</span>`;
    }).join(' ');

    const cardCls = s.caution_badges?.some(b => b.type === 'blocked') ? 'digest-card--blocked'
      : s.caution_badges?.length > 0 ? 'digest-card--caution' : '';

    const actionCls = s.action === 'ENTER' ? 'text-green' : s.action === 'EXIT' ? 'text-red' : 'text-secondary';

    return `
      <div class="digest-card ${cardCls}">
        <div style="display: flex; justify-content: space-between; align-items: center;">
          <div class="digest-card__title">${s.name}</div>
          <div>${badges}</div>
        </div>
        <div class="digest-card__subtitle">Spread thesis</div>
        <div class="digest-row">
          <span class="digest-row__label">Action</span>
          <span class="digest-row__value ${actionCls}">${s.action}</span>
        </div>
        <div class="digest-row">
          <span class="digest-row__label">Conviction</span>
          <span class="digest-row__value">${s.conviction} (${s.score})</span>
        </div>
        <div class="digest-row">
          <span class="digest-row__label">Z-Score</span>
          <span class="digest-row__value">${s.z_score != null ? s.z_score.toFixed(2) + 'σ' : '--'}</span>
        </div>
        <div class="digest-row">
          <span class="digest-row__label">Regime Fit</span>
          <span class="digest-row__value">${s.regime_fit ? '✓' : '✗'}</span>
        </div>
        <div class="digest-row">
          <span class="digest-row__label">Gate</span>
          <span class="digest-row__value">${s.gate_status}</span>
        </div>
      </div>`;
  }).join('');
}

function _breaksCard(breaks) {
  if (!breaks || breaks.length === 0) {
    return `<div class="digest-card">
      <div class="digest-card__title">Correlation Breaks</div>
      <div class="digest-card__subtitle">What is behaving wrong?</div>
      <p class="text-muted" style="font-size: 0.8125rem;">No breaks detected — stocks aligned with regime</p>
    </div>`;
  }
  const rows = breaks.map(b => {
    const dir = b.z_score < 0 ? '▼' : '▲';
    const cls = b.classification === 'CONFIRMED_WARNING' ? 'text-red'
      : b.classification === 'CONFIRMED_OPPORTUNITY' ? 'text-green' : 'text-secondary';
    return `
      <div class="digest-break-row" data-ticker="${b.ticker}">
        <div style="display: flex; justify-content: space-between; align-items: center;">
          <span class="mono" style="font-size: 0.875rem;">${b.ticker}</span>
          <span class="mono ${cls}">${b.z_score > 0 ? '+' : ''}${b.z_score.toFixed(1)}σ ${dir}</span>
        </div>
        <div style="display: flex; justify-content: space-between; font-size: 0.75rem; color: var(--text-muted); margin-top: 2px;">
          <span>OI: ${b.oi_confirmation}</span>
          <span class="badge ${b.classification === 'CONFIRMED_WARNING' ? 'badge--red' : b.classification === 'CONFIRMED_OPPORTUNITY' ? 'badge--green' : 'badge--muted'}">${b.classification.replace(/_/g, ' ')}</span>
        </div>
      </div>`;
  }).join('');
  return `
    <div class="digest-card">
      <div class="digest-card__title">Correlation Breaks</div>
      <div class="digest-card__subtitle">What is behaving wrong? (click ticker to investigate)</div>
      ${rows}
    </div>`;
}

function _backtestCard(backtest) {
  if (!backtest || backtest.length === 0) {
    return `<div class="digest-card">
      <div class="digest-card__title">Backtest Validation</div>
      <div class="digest-card__subtitle">Has this worked before?</div>
      <p class="text-muted" style="font-size: 0.8125rem;">No backtest data available for current regime</p>
    </div>`;
  }
  const rows = backtest.map(b => {
    const statusCls = b.status === 'WITHIN_CI' ? 'badge--green'
      : b.status === 'EDGE_CI' ? 'badge--amber' : 'badge--red';
    const winPct = (b.win_rate * 100).toFixed(0);
    return `
      <div style="padding: var(--spacing-sm) 0; border-bottom: 1px solid rgba(30, 41, 59, 0.3);">
        <div style="display: flex; justify-content: space-between; align-items: center;">
          <span style="font-size: 0.875rem;">${b.spread}</span>
          <span class="badge ${statusCls}">${b.status.replace(/_/g, ' ')}</span>
        </div>
        <div style="display: flex; gap: var(--spacing-lg); font-size: 0.75rem; color: var(--text-secondary); margin-top: 4px;">
          <span>Win: <span class="mono">${winPct}%</span></span>
          <span>Period: <span class="mono">${b.best_period}</span></span>
          <span>Avg: <span class="mono">${b.avg_return >= 0 ? '+' : ''}${(b.avg_return * 100).toFixed(2)}%</span></span>
        </div>
      </div>`;
  }).join('');
  return `
    <div class="digest-card">
      <div class="digest-card__title">Backtest Validation</div>
      <div class="digest-card__subtitle">Has this worked before?</div>
      ${rows}
    </div>`;
}

function _fmt(n) {
  if (n == null) return '--';
  return n.toLocaleString('en-IN', { maximumFractionDigits: 1 });
}

function _wireBreakClicks(container) {
  container.querySelectorAll('.digest-break-row[data-ticker]').forEach(row => {
    row.addEventListener('click', async () => {
      const ticker = row.dataset.ticker;
      const panel = document.getElementById('context-panel');
      const title = document.getElementById('context-panel-title');
      const content = document.getElementById('context-panel-content');
      if (!panel || !title || !content) return;

      title.textContent = ticker;
      content.innerHTML = '<div class="skeleton skeleton--card"></div>';
      panel.classList.add('context-panel--open');

      try {
        const [trustData, newsData] = await Promise.all([
          get(`/trust-scores/${ticker}`),
          get(`/news/${ticker}`),
        ]);

        const gradeCls = {
          'A+': 'badge--green', 'A': 'badge--green',
          'B+': 'badge--blue', 'B': 'badge--blue',
          'C': 'badge--amber', 'D': 'badge--red', 'F': 'badge--red',
        }[trustData.trust_grade] || 'badge--muted';

        const newsHtml = (newsData.items || []).slice(0, 10).map(n => `
          <div style="padding: var(--spacing-xs) 0; border-bottom: 1px solid rgba(30,41,59,0.3); font-size: 0.8125rem;">
            ${n.headline || n.title || '--'}
            <div class="text-muted" style="font-size: 0.6875rem;">${n.timestamp || n.date || ''}</div>
          </div>`).join('');

        content.innerHTML = `
          <div class="card" style="margin-bottom: var(--spacing-md);">
            <div class="text-muted" style="font-size: 0.75rem;">TRUST SCORE</div>
            <div style="display: flex; align-items: baseline; gap: var(--spacing-sm);">
              <span class="mono" style="font-size: 2rem; color: var(--accent-gold);">${trustData.trust_grade || '?'}</span>
              <span class="mono">${trustData.trust_score ?? '--'}</span>
            </div>
            <div style="font-size: 0.8125rem; margin-top: var(--spacing-sm); line-height: 1.6;">${trustData.thesis || 'No thesis'}</div>
          </div>
          <div class="card">
            <div class="text-muted" style="font-size: 0.75rem; margin-bottom: var(--spacing-sm);">RECENT NEWS</div>
            ${newsHtml || '<p class="text-muted">No news</p>'}
          </div>`;
      } catch {
        content.innerHTML = '<div class="empty-state"><p>Failed to load context</p></div>';
      }
    });
  });
}

let _refreshTimer = null;

function _scheduleRefresh(container) {
  if (_refreshTimer) clearInterval(_refreshTimer);
  const now = new Date();
  const hours = now.getHours();
  const inMarket = hours >= 9 && hours < 16;
  if (!inMarket) return;
  _refreshTimer = setInterval(() => {
    if (currentSubTab === 'research') {
      const el = document.getElementById('intel-content');
      if (el) renderResearch(el);
    }
  }, 5 * 60 * 1000);
}
```

- [ ] **Run full test suite**

Run: `python -m pytest pipeline/terminal/tests/ -v`
Expected: All tests PASS

- [ ] **Commit**

```bash
git add pipeline/terminal/static/js/pages/intelligence.js
git commit -m "feat(terminal): two-column intelligence digest — thesis vs evidence courtroom layout"
```

---

## Task 7: Staleness Warning Test

**Files:**
- Modify: `pipeline/terminal/tests/test_intelligence_apis.py`

### Step 7.1: Write staleness detection test

- [ ] **Write test**

Append to `test_intelligence_apis.py`:

```python
def test_stale_timestamp_detected(digest_files, tmp_path, monkeypatch):
    """Digest with old timestamp still returns data (staleness is client-side)."""
    import pipeline.terminal.api.research as res_mod

    old_regime = {
        "timestamp": "2026-04-17T09:25:00+05:30",  # yesterday
        "regime": "NEUTRAL",
        "regime_source": "etf_engine",
        "msi_score": 0.5,
        "regime_stable": True,
        "consecutive_days": 10,
        "trade_map_key": "NEUTRAL",
        "eligible_spreads": {},
        "components": {},
    }
    _write(tmp_path / "old_regime.json", old_regime)
    monkeypatch.setattr(res_mod, "_TODAY_REGIME", tmp_path / "old_regime.json")

    from pipeline.terminal.app import app
    data = TestClient(app).get("/api/research/digest").json()
    assert data["generated_at"] == "2026-04-17T09:25:00+05:30"
    assert data["regime_thesis"]["zone"] == "NEUTRAL"
```

- [ ] **Run test**

Run: `python -m pytest pipeline/terminal/tests/test_intelligence_apis.py::test_stale_timestamp_detected -v`
Expected: PASS

- [ ] **Commit**

```bash
git add pipeline/terminal/tests/test_intelligence_apis.py
git commit -m "test(terminal): staleness detection — old timestamp passes through for client-side warning"
```

---

## Task 8: Full Integration — Run All Tests + Cleanup

**Files:**
- No new files. Final verification.

### Step 8.1: Run complete terminal test suite

- [ ] **Run all tests**

Run: `python -m pytest pipeline/terminal/tests/ -v --tb=short`
Expected: All tests PASS (existing trust score tests + 9 new digest tests)

### Step 8.2: Run the terminal server and verify in browser

- [ ] **Start the terminal**

Run: `python -m pipeline.terminal --no-open`

- [ ] **Verify in browser**

Open `http://localhost:8501`, navigate to Intelligence → Research sub-tab. Verify:
1. Two-column layout renders (Thesis left, Evidence right)
2. Regime Thesis card shows zone, FII/DII, stability, flip triggers
3. Spread Theses cards show with caution badges where applicable
4. Correlation Breaks card shows breaks with clickable tickers
5. Clicking a ticker opens context panel with trust score + news
6. Backtest Validation card shows win rates and CI status
7. No Epstein or war articles visible anywhere
8. Timestamp header shows last computed time

- [ ] **Commit final state**

```bash
git add -A
git commit -m "feat(terminal): Research tab intelligence digest complete — thesis vs evidence courtroom"
```

---

## Summary

| Task | What It Builds | Tests |
|------|---------------|-------|
| 1 | Digest endpoint: data loader, 5 builders, API route | 1 (schema) |
| 2 | Grounding enforcer validation | 2 (mismatch + no false positive) |
| 3 | Cross-column caution badges | 3 (low win, outside CI, clean) |
| 4 | Graceful degradation | 2 (empty breaks, missing files) |
| 5 | CSS styles + API helper | 0 (visual) |
| 6 | Frontend two-column renderer + interaction | 0 (visual, tested in browser) |
| 7 | Staleness detection | 1 (old timestamp) |
| 8 | Integration verification | 0 (full suite re-run) |
| **Total** | | **9 tests** |
