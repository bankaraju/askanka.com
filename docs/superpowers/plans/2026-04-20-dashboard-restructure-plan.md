# Dashboard Restructure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restructure the Anka Terminal so Dashboard shows only live positions, Trading consumes a generic `tradeable_candidates[]` schema, Scanner consumes a separate `signals[]` schema, and the four sub-tabs currently nested inside Intelligence (Trust, News, Research, Options) plus new Regime + Risk tabs are promoted to top-level navigation.

**Architecture:** UI-only restructure. One new API endpoint (`/api/candidates`) composes the dual-array schema (`tradeable_candidates[]` + `signals[]`) from existing data files — no new pipeline writers, no scheduled tasks. Each top-level tab becomes a focused page with one feed and one question to answer. Existing API endpoints (`/api/regime`, `/api/risk-gates`, `/api/trust-scores`, `/api/news`, `/api/research/digest`, `/api/scanner`, `/api/oi`) are reused as-is.

**Tech Stack:** FastAPI (Python 3.11), vanilla JS modules (no framework), Lightweight Charts, pytest + FastAPI TestClient.

**Spec:** `docs/superpowers/specs/2026-04-20-dashboard-restructure-design.md`

---

## File Structure

### New files
- `pipeline/terminal/api/candidates.py` — composes `tradeable_candidates[]` + `signals[]` from existing files
- `pipeline/terminal/static/js/components/positions-table.js` — Open Positions table with stop/target/P&L columns (extracted from `signals-table.js`, positions-only)
- `pipeline/terminal/static/js/components/scenario-strip.js` — Portfolio P&L scenario strip for Dashboard
- `pipeline/terminal/static/js/components/filter-chips.js` — Reusable URL-encoded filter chips
- `pipeline/terminal/static/js/components/candidates-table.js` — Sortable candidate table with expandable drawer rows
- `pipeline/terminal/static/js/components/candidate-drawer.js` — Inline narration drawer (5-layer spread reasoning, scorecard delta, backtest stats)
- `pipeline/terminal/static/js/pages/regime.js` — Regime detail page (ETF, MSI, Phase A/B/C narration)
- `pipeline/terminal/static/js/pages/scanner.js` — Top-level Scanner page consuming `signals[]`
- `pipeline/terminal/static/js/pages/trust.js` — Promoted from Intelligence sub-tab
- `pipeline/terminal/static/js/pages/news.js` — Promoted from Intelligence sub-tab
- `pipeline/terminal/static/js/pages/research.js` — Promoted from Intelligence sub-tab
- `pipeline/terminal/static/js/pages/options.js` — Promoted from Intelligence sub-tab
- `pipeline/terminal/static/js/pages/risk.js` — New page consuming `/api/risk-gates`
- `pipeline/terminal/tests/test_candidates_api.py` — endpoint tests with frozen fixtures

### Modified files
- `pipeline/terminal/app.py` — register `candidates_router`
- `pipeline/terminal/static/index.html` — sidebar nav buttons (10 visible tabs + settings)
- `pipeline/terminal/static/js/app.js` — PAGES registry, keyboard shortcuts (1–9 + 0 for settings)
- `pipeline/terminal/static/js/pages/dashboard.js` — strip everything except Open Positions + scenarios
- `pipeline/terminal/static/js/pages/trading.js` — rewrite as candidates browser; Charts + TA sub-tabs move into the candidate drawer / Research tab
- `pipeline/terminal/tests/test_trading_apis.py` — update for new `/api/candidates` shape

### Deleted files
- `pipeline/terminal/static/js/pages/intelligence.js` — its four sub-tabs are promoted to top-level pages

---

## Sidebar tab order (final)

```
1. Dashboard      (positions only)
2. Trading        (tradeable_candidates[] browser)
3. Regime         (ETF + MSI + Phase A/B/C)
4. Scanner        (signals[] events)
5. Trust          (OPUS ANKA scorecards)
6. News           (news intelligence)
7. Options        (synthetic options)
8. Risk           (gates, sizing, drawdown)
9. Research       (digest)
0. Track Record   (existing)
   Settings      (existing)
```

Keyboard shortcuts: digit keys map to position above (`1`=Dashboard … `9`=Research, `0`=Track Record). Settings reachable via sidebar click only.

---

### Task 1: Create `/api/candidates` endpoint with dual-array schema

**Files:**
- Create: `pipeline/terminal/api/candidates.py`
- Create: `pipeline/terminal/tests/test_candidates_api.py`
- Modify: `pipeline/terminal/app.py:1-49`

- [ ] **Step 1: Write the failing test for tradeable_candidates from static_config**

```python
# pipeline/terminal/tests/test_candidates_api.py
"""Tests for /api/candidates endpoint."""
import json
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def mock_candidates(tmp_path, monkeypatch):
    import pipeline.terminal.api.candidates as cand_mod

    today_regime = {
        "regime": "NEUTRAL",
        "eligible_spreads": {
            "Pharma vs Banks": {
                "best_win": 70, "best_period": 5,
                "1d_win": 60, "3d_win": 65, "5d_win": 70,
                "long_legs": ["SUNPHARMA", "DRREDDY"],
                "short_legs": ["HDFCBANK", "ICICIBANK"],
                "conviction": "HIGH",
                "score": 87,
            },
        },
    }
    today_recs = {
        "regime_zone": "NEUTRAL",
        "stocks": [
            {"ticker": "KAYNES", "direction": "LONG", "conviction": "HIGH",
             "hit_rate": 1.0, "episodes": 12, "reason": "regime fit"},
        ],
        "spreads": [],
    }
    correlation_breaks = [
        {"ticker": "TATAMOTORS", "z_score": -2.3,
         "classification": "CONFIRMED_WARNING", "oi_confirmation": "yes"},
    ]
    fingerprints_dir = tmp_path / "ta_fingerprints"
    fingerprints_dir.mkdir()
    (fingerprints_dir / "APLAPOLLO.json").write_text(json.dumps({
        "symbol": "APLAPOLLO",
        "patterns": [{
            "pattern": "DMA200_CROSS_UP", "direction": "LONG",
            "significance": "STRONG", "win_rate_5d": 0.72,
            "occurrences": 18, "last_occurrence": "2026-04-20",
        }],
    }))

    rfile = tmp_path / "today_regime.json"
    rfile.write_text(json.dumps(today_regime))
    recfile = tmp_path / "today_recommendations.json"
    recfile.write_text(json.dumps(today_recs))
    breaksfile = tmp_path / "correlation_breaks.json"
    breaksfile.write_text(json.dumps(correlation_breaks))

    monkeypatch.setattr(cand_mod, "_TODAY_REGIME_FILE", rfile)
    monkeypatch.setattr(cand_mod, "_RECOMMENDATIONS_FILE", recfile)
    monkeypatch.setattr(cand_mod, "_BREAKS_FILE", breaksfile)
    monkeypatch.setattr(cand_mod, "_FINGERPRINTS_DIR", fingerprints_dir)


def test_candidates_returns_dual_arrays(mock_candidates):
    from pipeline.terminal.app import app
    data = TestClient(app).get("/api/candidates").json()
    assert "tradeable_candidates" in data
    assert "signals" in data


def test_candidates_includes_static_spread(mock_candidates):
    from pipeline.terminal.app import app
    data = TestClient(app).get("/api/candidates").json()
    static = [c for c in data["tradeable_candidates"] if c["source"] == "static_config"]
    assert len(static) == 1
    c = static[0]
    assert c["name"] == "Pharma vs Banks"
    assert c["long_legs"] == ["SUNPHARMA", "DRREDDY"]
    assert c["short_legs"] == ["HDFCBANK", "ICICIBANK"]
    assert c["conviction"] == "HIGH"
    assert c["score"] == 87
    assert c["horizon_basis"] == "mean_reversion"
    assert c["sizing_basis"] is None


def test_candidates_includes_regime_engine_pick(mock_candidates):
    from pipeline.terminal.app import app
    data = TestClient(app).get("/api/candidates").json()
    regime = [c for c in data["tradeable_candidates"] if c["source"] == "regime_engine"]
    assert len(regime) == 1
    c = regime[0]
    assert c["name"] == "Phase B: KAYNES"
    assert c["long_legs"] == ["KAYNES"]
    assert c["short_legs"] == []
    assert c["horizon_basis"] == "event_decay"


def test_candidates_signals_includes_ta_event(mock_candidates):
    from pipeline.terminal.app import app
    data = TestClient(app).get("/api/candidates").json()
    ta = [s for s in data["signals"] if s["source"] == "ta_scanner"]
    assert any(s["ticker"] == "APLAPOLLO" and s["event_type"] == "DMA200_CROSS_UP" for s in ta)


def test_candidates_signals_includes_correlation_break(mock_candidates):
    from pipeline.terminal.app import app
    data = TestClient(app).get("/api/candidates").json()
    breaks = [s for s in data["signals"] if s["source"] == "correlation_break"]
    assert len(breaks) == 1
    assert breaks[0]["ticker"] == "TATAMOTORS"


def test_candidates_missing_files_returns_empty_arrays(tmp_path, monkeypatch):
    import pipeline.terminal.api.candidates as cand_mod
    monkeypatch.setattr(cand_mod, "_TODAY_REGIME_FILE", tmp_path / "nope1.json")
    monkeypatch.setattr(cand_mod, "_RECOMMENDATIONS_FILE", tmp_path / "nope2.json")
    monkeypatch.setattr(cand_mod, "_BREAKS_FILE", tmp_path / "nope3.json")
    monkeypatch.setattr(cand_mod, "_FINGERPRINTS_DIR", tmp_path / "nope_dir")
    from pipeline.terminal.app import app
    data = TestClient(app).get("/api/candidates").json()
    assert data["tradeable_candidates"] == []
    assert data["signals"] == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest pipeline/terminal/tests/test_candidates_api.py -v`
Expected: FAIL — module `pipeline.terminal.api.candidates` not found.

- [ ] **Step 3: Create the endpoint module**

```python
# pipeline/terminal/api/candidates.py
"""GET /api/candidates — composed tradeable_candidates[] + signals[]."""
import json
from pathlib import Path
from fastapi import APIRouter

router = APIRouter()

_HERE = Path(__file__).resolve().parent.parent
_TODAY_REGIME_FILE = _HERE.parent / "data" / "today_regime.json"
_RECOMMENDATIONS_FILE = _HERE.parent.parent / "data" / "today_recommendations.json"
_BREAKS_FILE = _HERE.parent / "data" / "correlation_breaks.json"
_FINGERPRINTS_DIR = _HERE.parent / "data" / "ta_fingerprints"
_DYNAMIC_PAIRS_FILE = _HERE.parent / "data" / "dynamic_pairs.json"  # forward-compat: Project B


def _read_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _build_static_spreads(today_regime: dict) -> list:
    out = []
    for name, stats in (today_regime.get("eligible_spreads") or {}).items():
        if not isinstance(stats, dict):
            continue
        out.append({
            "source": "static_config",
            "name": name,
            "long_legs": list(stats.get("long_legs") or []),
            "short_legs": list(stats.get("short_legs") or []),
            "conviction": stats.get("conviction", "NONE"),
            "score": stats.get("score", 0),
            "horizon_days": stats.get("best_period", 5),
            "horizon_basis": "mean_reversion",
            "sizing_basis": None,
            "reason": stats.get("reason") or f"win_rate={stats.get('best_win', 0)}%",
        })
    return out


def _build_dynamic_pairs() -> list:
    """Forward-compat loader for Project B output. Returns [] until B lands."""
    raw = _read_json(_DYNAMIC_PAIRS_FILE, default={})
    pairs = raw.get("tradeable_candidates") if isinstance(raw, dict) else raw
    if not isinstance(pairs, list):
        return []
    out = []
    for p in pairs:
        if not isinstance(p, dict) or not p.get("name"):
            continue
        # Trust the engine's schema; tag the source if missing.
        p.setdefault("source", "dynamic_pair_engine")
        out.append(p)
    return out


def _build_regime_picks(today_recs: dict) -> list:
    out = []
    for s in today_recs.get("stocks") or []:
        ticker = s.get("ticker")
        if not ticker:
            continue
        direction = (s.get("direction") or "").upper()
        long_legs = [ticker] if direction == "LONG" else []
        short_legs = [ticker] if direction == "SHORT" else []
        out.append({
            "source": "regime_engine",
            "name": f"Phase B: {ticker}",
            "long_legs": long_legs,
            "short_legs": short_legs,
            "conviction": s.get("conviction", "NONE"),
            "score": s.get("score") or 0,
            "horizon_days": s.get("horizon_days", 3),
            "horizon_basis": "event_decay",
            "sizing_basis": None,
            "reason": s.get("reason") or f"hit_rate={s.get('hit_rate', 0)}",
        })
    return out


def _build_ta_signals() -> list:
    out = []
    if not _FINGERPRINTS_DIR.exists():
        return out
    for f in _FINGERPRINTS_DIR.glob("*.json"):
        try:
            raw = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        ticker = raw.get("symbol")
        if not ticker:
            continue
        for p in raw.get("patterns") or raw.get("fingerprint") or []:
            if (p.get("significance") or "").upper() != "STRONG":
                continue
            out.append({
                "source": "ta_scanner",
                "name": f"{ticker} {p.get('pattern')}",
                "ticker": ticker,
                "event_type": p.get("pattern"),
                "fired_at": p.get("last_occurrence"),
                "context": {
                    "win_rate_5d": p.get("win_rate_5d"),
                    "occurrences": p.get("occurrences"),
                    "direction": p.get("direction"),
                },
                "suggests_pair_with": None,
            })
    return out


def _build_correlation_break_signals() -> list:
    raw = _read_json(_BREAKS_FILE, default=[])
    if isinstance(raw, dict):
        raw = raw.get("breaks", [])
    out = []
    for b in raw:
        ticker = b.get("ticker")
        if not ticker:
            continue
        out.append({
            "source": "correlation_break",
            "name": f"{ticker} divergence",
            "ticker": ticker,
            "event_type": b.get("classification"),
            "fired_at": b.get("timestamp"),
            "context": {
                "z_score": b.get("z_score"),
                "oi_confirmation": b.get("oi_confirmation"),
            },
            "suggests_pair_with": None,
        })
    return out


@router.get("/candidates")
def candidates():
    today_regime = _read_json(_TODAY_REGIME_FILE, default={})
    today_recs = _read_json(_RECOMMENDATIONS_FILE, default={})
    return {
        "tradeable_candidates": (
            _build_static_spreads(today_regime)
            + _build_regime_picks(today_recs)
            + _build_dynamic_pairs()
        ),
        "signals": (
            _build_ta_signals()
            + _build_correlation_break_signals()
        ),
        "regime_zone": today_regime.get("regime"),
    }
```

- [ ] **Step 4: Register the router in app.py**

Modify `pipeline/terminal/app.py` — add import and include_router lines:

```python
from pipeline.terminal.api.candidates import router as candidates_router
# ... existing imports ...

app.include_router(candidates_router, prefix="/api")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest pipeline/terminal/tests/test_candidates_api.py -v`
Expected: 6 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add pipeline/terminal/api/candidates.py pipeline/terminal/tests/test_candidates_api.py pipeline/terminal/app.py
git commit -m "feat(terminal): add /api/candidates with tradeable_candidates + signals dual-array schema"
```

---

### Task 2: Build positions-table component for Dashboard

**Files:**
- Create: `pipeline/terminal/static/js/components/positions-table.js`

- [ ] **Step 1: Create the component**

```javascript
// pipeline/terminal/static/js/components/positions-table.js
// Renders the Open Positions table for Dashboard.
// Shows entry, current, P&L, stop, target, exit triggers, days held, source signal.

export function render(container, positions) {
  if (!positions || positions.length === 0) {
    container.innerHTML = `
      <div class="empty-state"><p>No open positions</p>
      <p class="text-muted">When a signal fires and executes, it will appear here.</p></div>`;
    return;
  }

  function legsHtml(item) {
    const longs = (item.long_legs || []).map(l => l.ticker || l).join(', ');
    const shorts = (item.short_legs || []).map(l => l.ticker || l).join(', ');
    if (longs && !shorts) return `<span class="text-green"><b>LONG</b> ${longs}</span>`;
    if (shorts && !longs) return `<span class="text-red"><b>SHORT</b> ${shorts}</span>`;
    return `<span class="text-green">L: ${longs}</span><br><span class="text-red">S: ${shorts}</span>`;
  }

  function fmtPct(v) {
    if (v == null) return '--';
    return `${v >= 0 ? '+' : ''}${Number(v).toFixed(2)}%`;
  }

  function pnlClass(v) {
    if (v == null) return '';
    return v >= 0 ? 'text-green' : 'text-red';
  }

  const rows = positions.map(p => {
    const pnl = p.spread_pnl_pct ?? p.pnl_pct ?? 0;
    const stop = p.stop_pct != null ? fmtPct(p.stop_pct) : '--';
    const target = p.target_pct != null ? fmtPct(p.target_pct) : '--';
    const opened = p.open_date || (p.open_timestamp ? p.open_timestamp.split('T')[0] : '--');
    const days = p.days_held != null ? `${p.days_held}d` : '--';
    const source = p.source_signal || p.tier || '--';
    const exitTrigger = p.exit_trigger || (p.is_stale ? 'STALE' : '');

    return `<tr>
      <td>${p.spread_name || p.signal_id || '--'}</td>
      <td>${legsHtml(p)}</td>
      <td class="mono">${opened}</td>
      <td class="mono ${pnlClass(pnl)}">${fmtPct(pnl)}</td>
      <td class="mono text-red">${stop}</td>
      <td class="mono text-green">${target}</td>
      <td class="mono">${days}</td>
      <td><span class="badge badge--gold">${source}</span>${exitTrigger ? ` <span class="badge badge--amber">${exitTrigger}</span>` : ''}</td>
    </tr>`;
  }).join('');

  const totalPnl = positions.reduce((sum, p) => sum + (p.spread_pnl_pct || p.pnl_pct || 0), 0);
  const headerCls = totalPnl >= 0 ? 'text-green' : 'text-red';

  container.innerHTML = `
    <div style="display: flex; justify-content: space-between; align-items: baseline; margin-bottom: var(--spacing-md);">
      <h3 style="margin: 0;">Open Positions <span class="text-muted" style="font-size: 0.875rem;">(${positions.length})</span></h3>
      <div class="mono ${headerCls}" style="font-size: 1rem;">Total P&L: ${fmtPct(totalPnl)}</div>
    </div>
    <table class="data-table">
      <thead><tr>
        <th>Name</th><th>Legs</th><th>Opened</th><th>P&L</th>
        <th>Stop</th><th>Target</th><th>Held</th><th>Source / Exit</th>
      </tr></thead>
      <tbody>${rows}</tbody>
    </table>`;
}
```

- [ ] **Step 2: Smoke-test that the component imports cleanly**

Run: `node --input-type=module -e "import('./pipeline/terminal/static/js/components/positions-table.js').then(m => console.log(typeof m.render))"`
Expected: prints `function`.

- [ ] **Step 3: Commit**

```bash
git add pipeline/terminal/static/js/components/positions-table.js
git commit -m "feat(terminal): add positions-table component (stops, targets, exit triggers)"
```

---

### Task 3: Build scenario-strip component for Dashboard

**Files:**
- Create: `pipeline/terminal/static/js/components/scenario-strip.js`

- [ ] **Step 1: Create the component**

```javascript
// pipeline/terminal/static/js/components/scenario-strip.js
// Portfolio aggregates + simple P&L scenarios for the Dashboard footer.
// Inputs: positions array (each with spread_pnl_pct, long_legs, short_legs).

export function render(container, positions, regimeData) {
  if (!positions || positions.length === 0) {
    container.innerHTML = '';
    return;
  }

  const totalPnl = positions.reduce((s, p) => s + (p.spread_pnl_pct || p.pnl_pct || 0), 0);
  const winners = positions.filter(p => (p.spread_pnl_pct || p.pnl_pct || 0) > 0).length;
  const losers = positions.filter(p => (p.spread_pnl_pct || p.pnl_pct || 0) < 0).length;
  const avgPnl = totalPnl / positions.length;

  const regimeFlipPct = -2.0;
  const allTargetsPct = positions.reduce((s, p) => s + (p.target_pct || 0), 0);
  const allStopsPct = positions.reduce((s, p) => s + (p.stop_pct || 0), 0);

  const cls = (v) => v >= 0 ? 'text-green' : 'text-red';
  const fmt = (v) => `${v >= 0 ? '+' : ''}${v.toFixed(2)}%`;

  container.innerHTML = `
    <div class="card" style="margin-top: var(--spacing-md);">
      <h3 style="margin-bottom: var(--spacing-sm); font-size: 0.875rem;">Portfolio Aggregates</h3>
      <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: var(--spacing-md);">
        <div><div class="text-muted" style="font-size: 0.6875rem;">POSITIONS</div>
          <div class="mono" style="font-size: 1.25rem;">${positions.length}</div></div>
        <div><div class="text-muted" style="font-size: 0.6875rem;">TOTAL P&L</div>
          <div class="mono ${cls(totalPnl)}" style="font-size: 1.25rem;">${fmt(totalPnl)}</div></div>
        <div><div class="text-muted" style="font-size: 0.6875rem;">AVG P&L</div>
          <div class="mono ${cls(avgPnl)}" style="font-size: 1.25rem;">${fmt(avgPnl)}</div></div>
        <div><div class="text-muted" style="font-size: 0.6875rem;">WIN / LOSS</div>
          <div class="mono" style="font-size: 1.25rem;">${winners} / ${losers}</div></div>
      </div>
    </div>
    <div class="card" style="margin-top: var(--spacing-sm);">
      <h3 style="margin-bottom: var(--spacing-sm); font-size: 0.875rem;">P&L Scenarios</h3>
      <table class="data-table">
        <thead><tr><th>Scenario</th><th>Aggregate P&L</th></tr></thead>
        <tbody>
          <tr><td>All targets hit</td>
            <td class="mono text-green">${allTargetsPct ? fmt(allTargetsPct) : '--'}</td></tr>
          <tr><td>All stops hit</td>
            <td class="mono text-red">${allStopsPct ? fmt(allStopsPct) : '--'}</td></tr>
          <tr><td>Regime flip from ${regimeData?.zone || '--'} (assume ${regimeFlipPct}% per position)</td>
            <td class="mono text-red">${fmt(positions.length * regimeFlipPct)}</td></tr>
        </tbody>
      </table>
    </div>`;
}
```

- [ ] **Step 2: Commit**

```bash
git add pipeline/terminal/static/js/components/scenario-strip.js
git commit -m "feat(terminal): add scenario-strip component for Dashboard portfolio view"
```

---

### Task 4: Rewrite Dashboard page — Open Positions only + scenarios

**Files:**
- Modify: `pipeline/terminal/static/js/pages/dashboard.js` (full rewrite)

- [ ] **Step 1: Replace dashboard.js with the trimmed version**

```javascript
// pipeline/terminal/static/js/pages/dashboard.js
import { get } from '../lib/api.js';
import * as regimeBanner from '../components/regime-banner.js';
import * as positionsTable from '../components/positions-table.js';
import * as scenarioStrip from '../components/scenario-strip.js';

let refreshTimer = null;

export async function render(container) {
  container.innerHTML = `
    <div id="dash-regime"></div>
    <div id="dash-mode-badge" style="margin: var(--spacing-sm) 0;"></div>
    <div id="dash-positions"></div>
    <div id="dash-scenarios"></div>`;

  await loadData();
  refreshTimer = setInterval(loadData, 30000);
}

export function destroy() {
  if (refreshTimer) { clearInterval(refreshTimer); refreshTimer = null; }
}

async function loadData() {
  const [regime, signals] = await Promise.allSettled([
    get('/regime'), get('/signals'),
  ]);

  const regimeData = regime.status === 'fulfilled'
    ? regime.value
    : { zone: 'UNKNOWN', stable: false, consecutive_days: 0 };

  // Single snapshot for both header and table — fixes the 5-vs-6 race.
  const positions = signals.status === 'fulfilled'
    ? (signals.value.positions || [])
    : [];

  const regimeEl = document.getElementById('dash-regime');
  if (regimeEl) regimeBanner.render(regimeEl, regimeData);

  const modeEl = document.getElementById('dash-mode-badge');
  if (modeEl) {
    modeEl.innerHTML = `<span class="badge badge--muted" style="font-size: 0.6875rem;">MODE: SHADOW</span>`;
  }

  const posEl = document.getElementById('dash-positions');
  if (posEl) positionsTable.render(posEl, positions);

  const scenEl = document.getElementById('dash-scenarios');
  if (scenEl) scenarioStrip.render(scenEl, positions, regimeData);
}
```

- [ ] **Step 2: Manual smoke-test in browser**

From `C:\Users\Claude_Anka\askanka.com`, restart the terminal:

```bash
python -m pipeline.terminal
```

Open `http://localhost:5050` (or the configured port). Click Dashboard. Expect:
- Regime banner at top
- `MODE: SHADOW` badge below banner
- Open Positions table with columns: Name, Legs, Opened, P&L, Stop, Target, Held, Source / Exit
- Portfolio Aggregates + P&L Scenarios at bottom
- No "Active Signals", "Top Eligible Spreads", "Stock Recommendations" sections

- [ ] **Step 3: Commit**

```bash
git add pipeline/terminal/static/js/pages/dashboard.js
git commit -m "refactor(terminal): trim Dashboard to Open Positions + scenarios only"
```

---

### Task 5: Build filter-chips component

**Files:**
- Create: `pipeline/terminal/static/js/components/filter-chips.js`

- [ ] **Step 1: Create the component**

```javascript
// pipeline/terminal/static/js/components/filter-chips.js
// URL-encoded filter chips. State is read from window.location.hash query string
// (after #) so filtered views are deep-linkable. onChange fires after each toggle.
//
// Usage:
//   render(container, {
//     groups: [
//       { key: 'source', label: 'Source', options: ['static_config', 'regime_engine'] },
//       { key: 'conviction', label: 'Conviction', options: ['HIGH', 'MEDIUM', 'LOW'] },
//     ],
//   }, onChange);
//
// State helper:
//   getState() → { source: ['static_config'], conviction: ['HIGH'] }

export function getState() {
  const hash = window.location.hash.slice(1);
  if (!hash) return {};
  const params = new URLSearchParams(hash);
  const out = {};
  for (const [k, v] of params.entries()) {
    out[k] = v ? v.split(',').filter(Boolean) : [];
  }
  return out;
}

function setState(state) {
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(state)) {
    if (v && v.length > 0) params.set(k, v.join(','));
  }
  const next = params.toString();
  const newHash = next ? `#${next}` : '';
  if (window.location.hash !== newHash) {
    history.replaceState(null, '', `${window.location.pathname}${window.location.search}${newHash}`);
  }
}

export function render(container, config, onChange) {
  const state = getState();
  for (const g of config.groups) {
    if (!state[g.key]) state[g.key] = [];
  }

  function chipHtml(groupKey, opt) {
    const selected = state[groupKey].includes(opt);
    return `<button class="filter-chip ${selected ? 'filter-chip--active' : ''}"
      data-group="${groupKey}" data-val="${opt}">${opt}</button>`;
  }

  container.innerHTML = config.groups.map(g => `
    <div class="filter-chip-group">
      <span class="filter-chip-label">${g.label}</span>
      ${g.options.map(o => chipHtml(g.key, o)).join('')}
    </div>`).join('');

  container.querySelectorAll('.filter-chip').forEach(btn => {
    btn.addEventListener('click', () => {
      const group = btn.dataset.group;
      const val = btn.dataset.val;
      const current = state[group] || [];
      if (current.includes(val)) {
        state[group] = current.filter(v => v !== val);
      } else {
        state[group] = [...current, val];
      }
      setState(state);
      btn.classList.toggle('filter-chip--active');
      onChange(state);
    });
  });
}
```

- [ ] **Step 2: Add minimal CSS**

Append to `pipeline/terminal/static/css/terminal.css`:

```css
.filter-chip-group {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-xs);
  margin-right: var(--spacing-md);
}
.filter-chip-label {
  font-size: 0.6875rem;
  text-transform: uppercase;
  color: var(--text-muted);
  margin-right: var(--spacing-xs);
}
.filter-chip {
  font-size: 0.75rem;
  padding: 4px 10px;
  border-radius: var(--radius-sm);
  background: var(--bg-card);
  border: 1px solid var(--border);
  color: var(--text-secondary);
  cursor: pointer;
}
.filter-chip:hover { background: var(--bg-elevated); }
.filter-chip--active {
  background: var(--accent-gold);
  color: var(--bg-base);
  border-color: var(--accent-gold);
}
```

- [ ] **Step 3: Commit**

```bash
git add pipeline/terminal/static/js/components/filter-chips.js pipeline/terminal/static/css/terminal.css
git commit -m "feat(terminal): add filter-chips component with URL-encoded state"
```

---

### Task 6: Build candidate-drawer component (expandable narration)

**Files:**
- Create: `pipeline/terminal/static/js/components/candidate-drawer.js`

- [ ] **Step 1: Create the component**

```javascript
// pipeline/terminal/static/js/components/candidate-drawer.js
// Renders the expandable inline drawer beneath a candidate row.
// For static_config + dynamic_pair_engine spreads, fetches the 5-layer narration
// (regime gate → scorecard delta → technicals → news → composer) from
// /api/research/digest spread_theses where available; falls back to the basic
// reason field for other sources.
import { get } from '../lib/api.js';

export async function render(container, candidate) {
  container.innerHTML = '<div class="skeleton skeleton--card"></div>';
  let narration = candidate.reason || '';
  let layers = null;

  if (candidate.source === 'static_config' || candidate.source === 'dynamic_pair_engine') {
    try {
      const digest = await get('/research/digest');
      const match = (digest.spread_theses || []).find(s => s.name === candidate.name);
      if (match) layers = match;
    } catch { /* fall through */ }
  }

  const sizingLine = candidate.sizing_basis
    ? `<div><span class="text-muted">Sizing basis:</span> <span class="mono">${candidate.sizing_basis}</span></div>`
    : '';

  const horizonLine = `<div><span class="text-muted">Horizon:</span> <span class="mono">${candidate.horizon_days}d (${candidate.horizon_basis})</span></div>`;

  let layersHtml = '';
  if (layers) {
    layersHtml = `
      <div style="margin-top: var(--spacing-md);">
        <div class="text-muted" style="font-size: 0.6875rem; margin-bottom: 4px;">5-LAYER NARRATION</div>
        <div class="mono" style="font-size: 0.75rem; line-height: 1.6;">
          <div>1. Regime gate: <strong>${layers.regime_fit ? 'PASS' : 'FAIL'}</strong></div>
          <div>2. Scorecard / Conviction: <strong>${layers.conviction} (${layers.score})</strong></div>
          <div>3. Z-score: <strong>${layers.z_score != null ? layers.z_score.toFixed(2) + 'σ' : '--'}</strong></div>
          <div>4. Action: <strong>${layers.action}</strong></div>
          <div>5. Gate status: <strong>${layers.gate_status}</strong></div>
        </div>
      </div>`;
  }

  container.innerHTML = `
    <div style="padding: var(--spacing-md); background: var(--bg-elevated); border-left: 3px solid var(--accent-gold);">
      <div style="font-size: 0.875rem; line-height: 1.6;">${narration}</div>
      <div style="margin-top: var(--spacing-sm); display: grid; grid-template-columns: repeat(2, 1fr); gap: var(--spacing-xs); font-size: 0.75rem;">
        ${horizonLine}
        ${sizingLine}
        <div><span class="text-muted">Source:</span> <span class="mono">${candidate.source}</span></div>
        <div><span class="text-muted">Conviction:</span> <span class="mono">${candidate.conviction}</span></div>
      </div>
      ${layersHtml}
    </div>`;
}
```

- [ ] **Step 2: Commit**

```bash
git add pipeline/terminal/static/js/components/candidate-drawer.js
git commit -m "feat(terminal): add candidate-drawer with 5-layer narration fallback"
```

---

### Task 7: Build candidates-table component

**Files:**
- Create: `pipeline/terminal/static/js/components/candidates-table.js`

- [ ] **Step 1: Create the component**

```javascript
// pipeline/terminal/static/js/components/candidates-table.js
// Sortable table of tradeable_candidates with click-to-expand row drawer.
import * as drawer from './candidate-drawer.js';

let _sortCol = 'score';
let _sortDir = -1;

export function render(container, candidates) {
  if (!candidates || candidates.length === 0) {
    container.innerHTML = '<div class="empty-state"><p>No candidates match these filters</p></div>';
    return;
  }

  const sorted = [...candidates].sort((a, b) => {
    let av = a[_sortCol], bv = b[_sortCol];
    if (av == null) av = _sortDir === -1 ? -Infinity : Infinity;
    if (bv == null) bv = _sortDir === -1 ? -Infinity : Infinity;
    if (typeof av === 'string') return _sortDir * av.localeCompare(bv);
    return _sortDir * (av - bv);
  });

  function legsCell(c) {
    const longs = (c.long_legs || []).join(', ');
    const shorts = (c.short_legs || []).join(', ');
    if (longs && !shorts) return `<span class="text-green">LONG ${longs}</span>`;
    if (shorts && !longs) return `<span class="text-red">SHORT ${shorts}</span>`;
    return `<span class="text-green">L: ${longs}</span><br><span class="text-red">S: ${shorts}</span>`;
  }

  function convClass(c) {
    if (c === 'HIGH') return 'badge--gold';
    if (c === 'MEDIUM') return 'badge--amber';
    return 'badge--muted';
  }

  const cols = [
    { key: 'name', label: 'Name' },
    { key: 'source', label: 'Source' },
    { key: 'long_legs', label: 'Legs' },
    { key: 'conviction', label: 'Conviction' },
    { key: 'score', label: 'Score' },
    { key: 'horizon_days', label: 'Horizon' },
  ];

  const thHtml = cols.map(col => {
    const arrow = col.key === _sortCol ? (_sortDir === -1 ? ' ▼' : ' ▲') : '';
    return `<th class="sortable" data-col="${col.key}" style="cursor: pointer;">${col.label}${arrow}</th>`;
  }).join('');

  const rows = sorted.map((c, i) => `
    <tr class="clickable" data-idx="${i}">
      <td>${c.name}</td>
      <td><span class="badge badge--muted">${c.source}</span></td>
      <td>${legsCell(c)}</td>
      <td><span class="badge ${convClass(c.conviction)}">${c.conviction}</span></td>
      <td class="mono">${c.score}</td>
      <td class="mono">${c.horizon_days}d</td>
    </tr>
    <tr class="drawer-row" data-drawer-for="${i}" style="display: none;">
      <td colspan="6"><div id="drawer-content-${i}"></div></td>
    </tr>`).join('');

  container.innerHTML = `
    <table class="data-table">
      <thead><tr>${thHtml}</tr></thead>
      <tbody>${rows}</tbody>
    </table>`;

  container.querySelectorAll('th.sortable').forEach(th => {
    th.addEventListener('click', () => {
      const col = th.dataset.col;
      if (_sortCol === col) { _sortDir *= -1; }
      else { _sortCol = col; _sortDir = -1; }
      render(container, candidates);
    });
  });

  container.querySelectorAll('tr.clickable').forEach(row => {
    row.addEventListener('click', () => {
      const idx = row.dataset.idx;
      const drawerRow = container.querySelector(`tr[data-drawer-for="${idx}"]`);
      if (!drawerRow) return;
      const isOpen = drawerRow.style.display === 'table-row';
      container.querySelectorAll('tr.drawer-row').forEach(d => { d.style.display = 'none'; });
      if (!isOpen) {
        drawerRow.style.display = 'table-row';
        const mount = document.getElementById(`drawer-content-${idx}`);
        if (mount) drawer.render(mount, sorted[idx]);
      }
    });
  });
}
```

- [ ] **Step 2: Commit**

```bash
git add pipeline/terminal/static/js/components/candidates-table.js
git commit -m "feat(terminal): add candidates-table with sortable cols + click-to-expand drawer"
```

---

### Task 8: Rewrite Trading page as candidates browser

**Files:**
- Modify: `pipeline/terminal/static/js/pages/trading.js` (full rewrite)

- [ ] **Step 1: Replace trading.js**

```javascript
// pipeline/terminal/static/js/pages/trading.js
// Read-only browser of all tradeable_candidates from /api/candidates.
// Filter by source / conviction / horizon_basis (URL-encoded).
import { get } from '../lib/api.js';
import * as filterChips from '../components/filter-chips.js';
import * as candidatesTable from '../components/candidates-table.js';

let _allCandidates = [];

export async function render(container) {
  container.innerHTML = `
    <div style="margin-bottom: var(--spacing-md);">
      <h2 style="margin-bottom: var(--spacing-xs); font-size: 1.125rem;">Trading — All Tradeable Candidates</h2>
      <div class="text-muted" style="font-size: 0.75rem;">Read-only. Filter and study; no actions taken from this surface.</div>
    </div>
    <div id="trading-filters" style="margin-bottom: var(--spacing-md); display: flex; flex-wrap: wrap; gap: var(--spacing-sm);"></div>
    <div id="trading-count" class="text-muted" style="font-size: 0.75rem; margin-bottom: var(--spacing-sm);"></div>
    <div id="trading-table"></div>`;

  await loadData();
}

export function destroy() {}

async function loadData() {
  try {
    const data = await get('/candidates');
    _allCandidates = data.tradeable_candidates || [];

    const sources = [...new Set(_allCandidates.map(c => c.source).filter(Boolean))];
    const convictions = [...new Set(_allCandidates.map(c => c.conviction).filter(Boolean))];
    const horizons = [...new Set(_allCandidates.map(c => c.horizon_basis).filter(Boolean))];

    const filterEl = document.getElementById('trading-filters');
    filterChips.render(filterEl, {
      groups: [
        { key: 'source', label: 'Source', options: sources },
        { key: 'conviction', label: 'Conviction', options: convictions },
        { key: 'horizon_basis', label: 'Horizon', options: horizons },
      ],
    }, applyFilters);

    applyFilters(filterChips.getState());
  } catch (err) {
    document.getElementById('trading-table').innerHTML =
      `<div class="empty-state"><p>Failed to load candidates: ${err.message}</p></div>`;
  }
}

function applyFilters(state) {
  const filtered = _allCandidates.filter(c => {
    if (state.source?.length && !state.source.includes(c.source)) return false;
    if (state.conviction?.length && !state.conviction.includes(c.conviction)) return false;
    if (state.horizon_basis?.length && !state.horizon_basis.includes(c.horizon_basis)) return false;
    return true;
  });

  const countEl = document.getElementById('trading-count');
  if (countEl) countEl.textContent = `${filtered.length} of ${_allCandidates.length} candidates`;

  const tableEl = document.getElementById('trading-table');
  if (tableEl) candidatesTable.render(tableEl, filtered);
}
```

- [ ] **Step 2: Manual smoke-test**

Restart terminal, click Trading. Expect:
- Filter chips for Source / Conviction / Horizon at top
- Table with columns: Name, Source, Legs, Conviction, Score, Horizon
- Row click expands a drawer with narration
- Filter clicks update URL hash (`#source=static_config,regime_engine`)
- Reload preserves filter state from URL hash

- [ ] **Step 3: Commit**

```bash
git add pipeline/terminal/static/js/pages/trading.js
git commit -m "refactor(terminal): rewrite Trading as candidates browser with filter chips + drawer"
```

---

### Task 9: Promote Trust, News, Research, Options to top-level pages

**Files:**
- Create: `pipeline/terminal/static/js/pages/trust.js`
- Create: `pipeline/terminal/static/js/pages/news.js`
- Create: `pipeline/terminal/static/js/pages/research.js`
- Create: `pipeline/terminal/static/js/pages/options.js`

- [ ] **Step 1: Create `pages/trust.js` from intelligence.js renderTrustScores**

```javascript
// pipeline/terminal/static/js/pages/trust.js
// Promoted from Intelligence sub-tab. Same logic, top-level page.
import { get } from '../lib/api.js';

const GRADE_COLORS = {
  'A+': 'badge--green', 'A': 'badge--green',
  'B+': 'badge--blue', 'B': 'badge--blue',
  'C': 'badge--amber',
  'D': 'badge--red', 'F': 'badge--red',
  '?': 'badge--muted',
};

function _esc(s) {
  if (s == null) return '';
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

function _heatmapBg(score) {
  if (score == null) return '';
  if (score >= 80) return 'background: rgba(34,197,94,0.25)';
  if (score >= 60) return 'background: rgba(34,197,94,0.12)';
  if (score >= 40) return 'background: rgba(245,158,11,0.15)';
  if (score >= 20) return 'background: rgba(249,115,22,0.15)';
  return 'background: rgba(239,68,68,0.15)';
}

export async function render(container) {
  container.innerHTML = '<div class="skeleton skeleton--card"></div>';

  try {
    const [data, sectorsData] = await Promise.all([
      get('/trust-scores'),
      get('/trust-scores/sectors').catch(() => ({ sectors: {} })),
    ]);
    const stocks = data.stocks || [];
    const sectorsRaw = sectorsData.sectors || {};
    const sectors = Array.isArray(sectorsRaw)
      ? sectorsRaw
      : Object.entries(sectorsRaw).map(([id, v]) => ({
          id, display_name: v.name || id, count: v.count || 0,
        }));

    if (stocks.length === 0) {
      container.innerHTML = '<div class="empty-state"><p>No trust scores available</p></div>';
      return;
    }

    sectors.sort((a, b) => (b.count || 0) - (a.count || 0));
    const sectorOptions = sectors.map(sec =>
      `<option value="${_esc(sec.id)}">${_esc(sec.display_name)} (${sec.count})</option>`
    ).join('');

    container.innerHTML = `
      <div class="filter-bar" style="display:flex; align-items:center; gap: var(--spacing-sm); flex-wrap:wrap; margin-bottom: var(--spacing-sm);">
        <input type="text" id="trust-search" class="filter-search" placeholder="Search ticker..." style="min-width:140px;">
        <select id="trust-sector" class="filter-search" style="min-width:160px;">
          <option value="">All Sectors</option>
          ${sectorOptions}
        </select>
        <span id="trust-count" class="text-muted" style="font-size: 0.75rem;">${stocks.length} stocks scored</span>
      </div>
      <div id="trust-table-wrap"></div>`;

    let sortCol = 'composite_score';
    let sortDir = -1;

    const renderTable = () => {
      const tickerFilter = (document.getElementById('trust-search')?.value || '').toUpperCase();
      const sectorFilter = document.getElementById('trust-sector')?.value || '';
      let filtered = stocks.filter(s => {
        const matchTicker = !tickerFilter || (s.symbol || '').toUpperCase().includes(tickerFilter);
        const matchSector = !sectorFilter || (s.sector || '') === sectorFilter;
        return matchTicker && matchSector;
      });
      filtered = [...filtered].sort((a, b) => {
        let av = a[sortCol], bv = b[sortCol];
        if (av == null) av = sortDir === -1 ? -Infinity : Infinity;
        if (bv == null) bv = sortDir === -1 ? -Infinity : Infinity;
        if (typeof av === 'string') return sortDir * av.localeCompare(bv);
        return sortDir * (av - bv);
      });
      document.getElementById('trust-count').textContent = `${filtered.length} / ${stocks.length} stocks`;

      const colDefs = [
        { key: 'symbol', label: 'Ticker' },
        { key: 'display_name', label: 'Sector' },
        { key: 'sector_grade', label: 'Grade' },
        { key: 'composite_score', label: 'Composite' },
        { key: 'financial_score', label: 'Fin' },
        { key: 'management_score', label: 'Mgmt' },
        { key: 'sector_rank', label: 'Rank' },
        { key: 'grade_reason', label: 'Remark' },
      ];
      const thHtml = colDefs.map(col => {
        const active = col.key === sortCol ? 'style="color:var(--accent-gold);"' : '';
        return `<th class="sortable" data-col="${col.key}" ${active}>${col.label}</th>`;
      }).join('');

      const rows = filtered.map(s => {
        const grade = s.sector_grade || s.trust_grade || '?';
        const badgeCls = GRADE_COLORS[grade] || 'badge--muted';
        const composite = s.composite_score ?? s.trust_score;
        const fin = s.financial_score;
        const mgmt = s.management_score;
        const rank = (s.sector_rank != null && s.sector_total != null)
          ? `${s.sector_rank}/${s.sector_total}` : '--';
        const remarkFull = s.grade_reason || s.thesis || '';
        const remarkShort = remarkFull.length > 80 ? remarkFull.slice(0, 80) + '…' : remarkFull;
        const sectorDisplay = (s.display_name || s.sector || '').slice(0, 20);
        return `<tr><td style="font-family: var(--font-mono); font-weight:600;">${_esc(s.symbol)}</td>
          <td class="text-muted" style="font-size:0.75rem;" title="${_esc(s.display_name || s.sector || '')}">${_esc(sectorDisplay)}</td>
          <td><span class="badge ${badgeCls}">${_esc(grade)}</span></td>
          <td class="mono" style="${_heatmapBg(composite)}">${composite != null ? composite : '--'}</td>
          <td class="mono" style="${_heatmapBg(fin)}">${fin != null ? fin : '--'}</td>
          <td class="mono" style="${_heatmapBg(mgmt)}">${mgmt != null ? mgmt : '--'}</td>
          <td class="mono" style="font-size:0.75rem;">${_esc(rank)}</td>
          <td class="text-muted" style="font-size:0.75rem; max-width:260px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;" title="${_esc(remarkFull)}">${_esc(remarkShort)}</td>
        </tr>`;
      }).join('');

      document.getElementById('trust-table-wrap').innerHTML = `
        <table class="data-table">
          <thead><tr>${thHtml}</tr></thead>
          <tbody>${rows}</tbody>
        </table>`;

      document.querySelectorAll('#trust-table-wrap th.sortable').forEach(th => {
        th.style.cursor = 'pointer';
        th.addEventListener('click', () => {
          const col = th.dataset.col;
          if (sortCol === col) { sortDir *= -1; } else { sortCol = col; sortDir = -1; }
          renderTable();
        });
      });
    };

    renderTable();
    document.getElementById('trust-search').addEventListener('input', renderTable);
    document.getElementById('trust-sector').addEventListener('change', renderTable);
  } catch {
    container.innerHTML = '<div class="empty-state"><p>Failed to load trust scores</p></div>';
  }
}

export function destroy() {}
```

- [ ] **Step 2: Create `pages/news.js`**

```javascript
// pipeline/terminal/static/js/pages/news.js
import { get } from '../lib/api.js';

export async function render(container) {
  container.innerHTML = '<div class="skeleton skeleton--card"></div>';
  try {
    const data = await get('/news/macro');
    const items = data.items || [];
    if (items.length === 0) {
      container.innerHTML = '<div class="empty-state"><p>No news available</p></div>';
      return;
    }
    const newsHtml = items.slice(0, 50).map(item => {
      const headline = item.headline || item.title || JSON.stringify(item).slice(0, 100);
      const time = item.timestamp || item.date || '';
      const sentiment = item.sentiment || item.impact || '';
      const sentBadge = sentiment
        ? `<span class="badge badge--${sentiment === 'HIGH' || sentiment === 'negative' ? 'red' : sentiment === 'MEDIUM' ? 'amber' : 'blue'}">${sentiment}</span>`
        : '';
      return `<div style="padding: var(--spacing-sm) 0; border-bottom: 1px solid var(--border);">
        <div style="display: flex; justify-content: space-between; align-items: flex-start; gap: 8px;">
          <div style="font-size: 0.875rem;">${headline}</div>
          ${sentBadge}
        </div>
        <div class="text-muted" style="font-size: 0.6875rem; margin-top: 2px;">${time}</div>
      </div>`;
    }).join('');
    container.innerHTML = `<div class="card">${newsHtml}</div>`;
  } catch {
    container.innerHTML = '<div class="empty-state"><p>Failed to load news</p></div>';
  }
}

export function destroy() {}
```

- [ ] **Step 3: Create `pages/research.js`**

```javascript
// pipeline/terminal/static/js/pages/research.js
// Promoted from Intelligence "Research" sub-tab. Renders the full digest:
// regime thesis, spread theses, correlation breaks, backtest validation.
import { get } from '../lib/api.js';

let _refreshTimer = null;

function _esc(s) {
  if (s == null) return '';
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

function _istHour() {
  const h = new Date().toLocaleString('en-US', { timeZone: 'Asia/Kolkata', hour: 'numeric', hour12: false });
  return parseInt(h, 10);
}

function _isStale(isoTimestamp) {
  if (!isoTimestamp) return false;
  const hours = _istHour();
  const inMarket = hours >= 9 && hours < 16;
  if (!inMarket) return false;
  const ageMinutes = (Date.now() - new Date(isoTimestamp)) / 60000;
  return ageMinutes > 30;
}

function _fmt(n) {
  if (n == null) return '--';
  return n.toLocaleString('en-IN', { maximumFractionDigits: 1 });
}

function _digestHeader(genTime, isStale) {
  const timeStr = genTime ? new Date(genTime).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata' }) : '--';
  const staleBadge = isStale ? ' <span class="badge badge--stale">STALE</span>' : '';
  return `<div class="digest-header">
    <h2 class="digest-header__title">Intelligence Digest</h2>
    <span class="digest-header__time">Last computed: ${timeStr}${staleBadge}</span>
  </div>`;
}

function _regimeCard(r) {
  if (!r) return '<div class="digest-card"><p class="text-muted">No regime data</p></div>';
  const groundBadge = r.grounding_ok === false ? '<span class="badge badge--red">GROUNDING FAILURE</span>' : '';
  return `<div class="digest-card">
    <div style="display: flex; justify-content: space-between; align-items: center;">
      <div class="digest-card__title">Regime Thesis</div>${groundBadge}
    </div>
    <div class="digest-card__subtitle">Why are we in ${r.zone}?</div>
    <div class="digest-row"><span class="digest-row__label">Zone</span>
      <span class="digest-row__value"><span class="badge badge--gold">${r.zone}</span></span></div>
    <div class="digest-row"><span class="digest-row__label">Source</span>
      <span class="digest-row__value">${r.regime_source || '--'}</span></div>
    <div class="digest-row"><span class="digest-row__label">FII Net</span>
      <span class="digest-row__value ${r.fii_net >= 0 ? 'text-green' : 'text-red'}">₹${_fmt(r.fii_net)}cr</span></div>
    <div class="digest-row"><span class="digest-row__label">DII Net</span>
      <span class="digest-row__value ${r.dii_net >= 0 ? 'text-green' : 'text-red'}">₹${_fmt(r.dii_net)}cr</span></div>
    <div class="digest-row"><span class="digest-row__label">MSI Score</span>
      <span class="digest-row__value">${r.msi_score != null ? r.msi_score.toFixed(2) : '--'}</span></div>
    <div class="digest-row"><span class="digest-row__label">Stability</span>
      <span class="digest-row__value">${r.stability_days}d ${r.stable ? '(locked)' : '(unstable)'}</span></div>
    ${r.flip_triggers && r.flip_triggers.length > 0 ? `
      <div style="margin-top: var(--spacing-sm); font-size: 0.75rem; color: var(--text-muted);">
        <strong>Flip triggers:</strong> ${r.flip_triggers.join(' · ')}
      </div>` : ''}
  </div>`;
}

function _spreadCards(spreads) {
  if (!spreads || spreads.length === 0) return '<div class="digest-card"><p class="text-muted">No active spreads</p></div>';
  return spreads.map(s => {
    const badges = (s.caution_badges || []).map(b => {
      const cls = b.type === 'blocked' ? 'badge--blocked' : b.type === 'caution' ? 'badge--amber' : 'badge--muted';
      return `<span class="badge ${cls}" title="${b.detail || ''}">${b.label}</span>`;
    }).join(' ');
    const cardCls = s.caution_badges?.some(b => b.type === 'blocked') ? 'digest-card--blocked'
      : s.caution_badges?.length > 0 ? 'digest-card--caution' : '';
    const actionCls = s.action === 'ENTER' ? 'text-green' : s.action === 'EXIT' ? 'text-red' : 'text-secondary';
    return `<div class="digest-card ${cardCls}">
      <div style="display: flex; justify-content: space-between; align-items: center;">
        <div class="digest-card__title">${s.name}</div><div>${badges}</div>
      </div>
      <div class="digest-card__subtitle">Spread thesis</div>
      <div class="digest-row"><span class="digest-row__label">Action</span>
        <span class="digest-row__value ${actionCls}">${s.action}</span></div>
      <div class="digest-row"><span class="digest-row__label">Conviction</span>
        <span class="digest-row__value">${s.conviction} (${s.score})</span></div>
      <div class="digest-row"><span class="digest-row__label">Z-Score</span>
        <span class="digest-row__value">${s.z_score != null ? s.z_score.toFixed(2) + 'σ' : '--'}</span></div>
      <div class="digest-row"><span class="digest-row__label">Regime Fit</span>
        <span class="digest-row__value">${s.regime_fit ? '✓' : '✗'}</span></div>
      <div class="digest-row"><span class="digest-row__label">Gate</span>
        <span class="digest-row__value">${s.gate_status}</span></div>
    </div>`;
  }).join('');
}

function _breaksCard(breaks) {
  if (!breaks || breaks.length === 0) {
    return `<div class="digest-card">
      <div class="digest-card__title">Correlation Breaks</div>
      <div class="digest-card__subtitle">What is behaving wrong?</div>
      <p class="text-muted" style="font-size: 0.8125rem;">No breaks detected</p>
    </div>`;
  }
  const rows = breaks.map(b => {
    const dir = b.z_score < 0 ? '▼' : '▲';
    const cls = b.classification === 'CONFIRMED_WARNING' ? 'text-red'
      : b.classification === 'CONFIRMED_OPPORTUNITY' ? 'text-green' : 'text-secondary';
    return `<div class="digest-break-row">
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
  return `<div class="digest-card">
    <div class="digest-card__title">Correlation Breaks</div>
    <div class="digest-card__subtitle">What is behaving wrong?</div>
    ${rows}
  </div>`;
}

function _backtestCard(backtest) {
  if (!backtest || backtest.length === 0) {
    return `<div class="digest-card">
      <div class="digest-card__title">Backtest Validation</div>
      <p class="text-muted" style="font-size: 0.8125rem;">No backtest data</p>
    </div>`;
  }
  const rows = backtest.map(b => {
    const statusCls = b.status === 'WITHIN_CI' ? 'badge--green'
      : b.status === 'EDGE_CI' ? 'badge--amber' : 'badge--red';
    const winPct = (b.win_rate * 100).toFixed(0);
    return `<div style="padding: var(--spacing-sm) 0; border-bottom: 1px solid rgba(30, 41, 59, 0.3);">
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
  return `<div class="digest-card">
    <div class="digest-card__title">Backtest Validation</div>
    <div class="digest-card__subtitle">Has this worked before?</div>
    ${rows}
  </div>`;
}

export async function render(container) {
  container.innerHTML = '<div class="skeleton skeleton--card"></div>';
  try {
    const data = await get('/research/digest');
    const genTime = data.generated_at || '';
    const isStale = _isStale(genTime);
    container.innerHTML = `
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

    if (_refreshTimer) clearInterval(_refreshTimer);
    const inMarket = _istHour() >= 9 && _istHour() < 16;
    if (inMarket) {
      _refreshTimer = setInterval(() => render(container), 5 * 60 * 1000);
    }
  } catch {
    container.innerHTML = '<div class="empty-state"><p>Failed to load research digest</p></div>';
  }
}

export function destroy() {
  if (_refreshTimer) { clearInterval(_refreshTimer); _refreshTimer = null; }
}
```

- [ ] **Step 4: Create `pages/options.js`**

```javascript
// pipeline/terminal/static/js/pages/options.js
import { get } from '../lib/api.js';
import { renderLeverageCard, renderShadowStrip } from '../components/leverage-matrix.js';

function _isStale(isoTimestamp) {
  if (!isoTimestamp) return false;
  const h = new Date().toLocaleString('en-US', { timeZone: 'Asia/Kolkata', hour: 'numeric', hour12: false });
  const hours = parseInt(h, 10);
  const inMarket = hours >= 9 && hours < 16;
  if (!inMarket) return false;
  return (Date.now() - new Date(isoTimestamp)) / 60000 > 30;
}

export async function render(container) {
  container.innerHTML = '<div class="skeleton skeleton--card"></div>';
  try {
    const [digestData, shadows] = await Promise.all([
      get('/research/digest'),
      get('/research/options-shadow').catch(() => []),
    ]);
    const genTime = digestData.generated_at || '';
    const isStale = _isStale(genTime);
    const timeStr = genTime ? new Date(genTime).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata' }) : '--';
    const staleBadge = isStale ? ' <span class="badge badge--stale">STALE</span>' : '';
    const matrices = digestData.leverage_matrices || [];
    const matrixCards = matrices.length > 0
      ? matrices.map(m => renderLeverageCard(m)).join('')
      : '<div class="digest-card"><p class="text-muted">No spreads with 65+ conviction — leverage matrix requires qualifying signals</p></div>';
    container.innerHTML = `
      <div class="digest-header">
        <h2 class="digest-header__title">Synthetic Options — Drift vs Rent</h2>
        <span class="digest-header__time">Vol data: ${timeStr}${staleBadge}</span>
      </div>
      <div style="display: flex; flex-direction: column; gap: var(--spacing-md);">
        ${matrixCards}
        ${renderShadowStrip(shadows)}
      </div>`;
  } catch {
    container.innerHTML = '<div class="empty-state"><p>Failed to load options intelligence</p></div>';
  }
}

export function destroy() {}
```

- [ ] **Step 5: Smoke-test all four pages import cleanly**

Run: `node --input-type=module -e "Promise.all(['trust','news','research','options'].map(p => import('./pipeline/terminal/static/js/pages/' + p + '.js'))).then(ms => console.log(ms.map(m => typeof m.render).join(',')))"`
Expected: `function,function,function,function`

- [ ] **Step 6: Commit**

```bash
git add pipeline/terminal/static/js/pages/trust.js pipeline/terminal/static/js/pages/news.js pipeline/terminal/static/js/pages/research.js pipeline/terminal/static/js/pages/options.js
git commit -m "feat(terminal): promote Trust/News/Research/Options to top-level pages"
```

---

### Task 10: Build Regime page

**Files:**
- Create: `pipeline/terminal/static/js/pages/regime.js`

- [ ] **Step 1: Create the page**

```javascript
// pipeline/terminal/static/js/pages/regime.js
// "Where is the market?" surface. Composes from /api/regime + /api/research/digest.
// Sections: ETF zone + score, MSI secondary context, hysteresis state, top drivers,
// eligible spreads (snapshot, full detail lives in Trading), Phase B picks (snapshot).
import { get } from '../lib/api.js';

let _refreshTimer = null;

function _esc(s) {
  if (s == null) return '';
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

export async function render(container) {
  container.innerHTML = '<div class="skeleton skeleton--card"></div>';
  try {
    const [regime, digest, candidates] = await Promise.allSettled([
      get('/regime'), get('/research/digest'), get('/candidates'),
    ]);
    const r = regime.status === 'fulfilled' ? regime.value : {};
    const d = digest.status === 'fulfilled' ? digest.value : {};
    const c = candidates.status === 'fulfilled' ? candidates.value : { tradeable_candidates: [] };

    const driversHtml = (r.top_drivers || []).slice(0, 8).map(drv => `
      <div class="digest-row">
        <span class="digest-row__label">${_esc(drv.symbol || drv.name || '--')}</span>
        <span class="digest-row__value mono ${drv.contribution >= 0 ? 'text-green' : 'text-red'}">${drv.contribution >= 0 ? '+' : ''}${(drv.contribution || 0).toFixed(3)}</span>
      </div>`).join('');

    const phaseBHtml = c.tradeable_candidates
      .filter(x => x.source === 'regime_engine')
      .slice(0, 8)
      .map(p => `<div class="digest-row">
        <span class="digest-row__label">${_esc(p.name)}</span>
        <span class="digest-row__value">${p.conviction} (${p.score})</span>
      </div>`).join('') || '<p class="text-muted" style="font-size: 0.8125rem;">No Phase B picks today</p>';

    const eligibleHtml = c.tradeable_candidates
      .filter(x => x.source === 'static_config')
      .slice(0, 8)
      .map(s => `<div class="digest-row">
        <span class="digest-row__label">${_esc(s.name)}</span>
        <span class="digest-row__value">${s.conviction} (${s.score})</span>
      </div>`).join('') || '<p class="text-muted" style="font-size: 0.8125rem;">No eligible spreads</p>';

    const stableLabel = r.stable ? 'LOCKED' : 'UNSTABLE';
    const stableCls = r.stable ? 'text-green' : 'text-amber';

    container.innerHTML = `
      <h2 style="margin-bottom: var(--spacing-md);">Regime — Where is the market?</h2>
      <div class="digest-grid">
        <div>
          <div class="digest-column-header">ETF Engine (Primary)</div>
          <div class="digest-card">
            <div class="digest-card__title">Zone: <span class="badge badge--gold">${_esc(r.zone || 'UNKNOWN')}</span></div>
            <div class="digest-row"><span class="digest-row__label">Score</span>
              <span class="digest-row__value mono">${r.score != null ? r.score.toFixed(3) : '--'}</span></div>
            <div class="digest-row"><span class="digest-row__label">Source</span>
              <span class="digest-row__value">${_esc(r.regime_source || '--')}</span></div>
            <div class="digest-row"><span class="digest-row__label">Stability</span>
              <span class="digest-row__value ${stableCls}">${stableLabel} (${r.consecutive_days || 0}d)</span></div>
            <div class="digest-row"><span class="digest-row__label">Updated</span>
              <span class="digest-row__value mono">${_esc(r.updated_at || '--')}</span></div>
          </div>
          <div class="digest-card">
            <div class="digest-card__title">Top Drivers</div>
            ${driversHtml || '<p class="text-muted" style="font-size: 0.8125rem;">No driver data</p>'}
          </div>
          <div class="digest-card">
            <div class="digest-card__title">MSI (Secondary Context)</div>
            <div class="digest-row"><span class="digest-row__label">Score</span>
              <span class="digest-row__value mono">${r.msi_score != null ? r.msi_score.toFixed(2) : '--'}</span></div>
            <div class="digest-row"><span class="digest-row__label">Regime</span>
              <span class="digest-row__value">${_esc(r.msi_regime || '--')}</span></div>
          </div>
        </div>
        <div>
          <div class="digest-column-header">Phase A/B/C (Reverse Regime)</div>
          <div class="digest-card">
            <div class="digest-card__title">Phase B: Stock Picks</div>
            <div class="digest-card__subtitle">Today's regime-derived stock recommendations</div>
            ${phaseBHtml}
          </div>
          <div class="digest-card">
            <div class="digest-card__title">Phase C: Correlation Breaks</div>
            <div class="digest-card__subtitle">See Scanner tab for full event feed</div>
            <p class="text-muted" style="font-size: 0.8125rem;">${(d.correlation_breaks || []).length} breaks detected</p>
          </div>
          <div class="digest-card">
            <div class="digest-card__title">Eligible Spreads (snapshot)</div>
            <div class="digest-card__subtitle">Full detail + filters in Trading tab</div>
            ${eligibleHtml}
          </div>
        </div>
      </div>`;

    if (_refreshTimer) clearInterval(_refreshTimer);
    _refreshTimer = setInterval(() => render(container), 60000);
  } catch {
    container.innerHTML = '<div class="empty-state"><p>Failed to load regime data</p></div>';
  }
}

export function destroy() {
  if (_refreshTimer) { clearInterval(_refreshTimer); _refreshTimer = null; }
}
```

- [ ] **Step 2: Commit**

```bash
git add pipeline/terminal/static/js/pages/regime.js
git commit -m "feat(terminal): add Regime page (ETF + MSI + Phase A/B/C)"
```

---

### Task 11: Build Scanner page (signals[] events)

**Files:**
- Create: `pipeline/terminal/static/js/pages/scanner.js`

- [ ] **Step 1: Create the page**

```javascript
// pipeline/terminal/static/js/pages/scanner.js
// Top-level page consuming signals[] from /api/candidates.
// Read-only event feed: TA fingerprint hits, OI anomalies, correlation breaks.
import { get } from '../lib/api.js';
import * as filterChips from '../components/filter-chips.js';

let _allSignals = [];
let _refreshTimer = null;

function _esc(s) {
  if (s == null) return '';
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

export async function render(container) {
  container.innerHTML = `
    <div style="margin-bottom: var(--spacing-md);">
      <h2 style="margin-bottom: var(--spacing-xs); font-size: 1.125rem;">Scanner — Events &amp; Anomalies</h2>
      <div class="text-muted" style="font-size: 0.75rem;">Read-only event feed. Look-at-this items, not trades.</div>
    </div>
    <div id="scanner-filters" style="margin-bottom: var(--spacing-md);"></div>
    <div id="scanner-count" class="text-muted" style="font-size: 0.75rem; margin-bottom: var(--spacing-sm);"></div>
    <div id="scanner-feed"></div>`;

  await loadData();
  if (_refreshTimer) clearInterval(_refreshTimer);
  _refreshTimer = setInterval(loadData, 60000);
}

export function destroy() {
  if (_refreshTimer) { clearInterval(_refreshTimer); _refreshTimer = null; }
}

async function loadData() {
  try {
    const data = await get('/candidates');
    _allSignals = data.signals || [];
    const sources = [...new Set(_allSignals.map(s => s.source))];
    const filterEl = document.getElementById('scanner-filters');
    if (filterEl) {
      filterChips.render(filterEl, {
        groups: [{ key: 'source', label: 'Source', options: sources }],
      }, applyFilters);
    }
    applyFilters(filterChips.getState());
  } catch (err) {
    document.getElementById('scanner-feed').innerHTML =
      `<div class="empty-state"><p>Failed to load signals: ${err.message}</p></div>`;
  }
}

function applyFilters(state) {
  const filtered = _allSignals.filter(s => {
    if (state.source?.length && !state.source.includes(s.source)) return false;
    return true;
  });
  const countEl = document.getElementById('scanner-count');
  if (countEl) countEl.textContent = `${filtered.length} of ${_allSignals.length} signals`;
  const feedEl = document.getElementById('scanner-feed');
  if (!feedEl) return;
  if (filtered.length === 0) {
    feedEl.innerHTML = '<div class="empty-state"><p>No events match these filters</p></div>';
    return;
  }
  const sourceColors = {
    ta_scanner: 'badge--blue',
    correlation_break: 'badge--amber',
    oi_anomaly: 'badge--gold',
  };
  const rows = filtered.map(s => {
    const ctxParts = Object.entries(s.context || {})
      .filter(([, v]) => v != null)
      .map(([k, v]) => `<span class="text-muted">${k}:</span> <span class="mono">${typeof v === 'number' ? v.toFixed(2) : _esc(String(v))}</span>`)
      .join(' &nbsp; ');
    return `<div style="padding: var(--spacing-sm) 0; border-bottom: 1px solid var(--border);">
      <div style="display: flex; justify-content: space-between; align-items: baseline; gap: var(--spacing-sm);">
        <div>
          <span class="mono" style="font-size: 0.875rem; font-weight: 600;">${_esc(s.ticker || '--')}</span>
          <span class="text-muted" style="font-size: 0.75rem;"> · ${_esc(s.event_type || '--')}</span>
        </div>
        <span class="badge ${sourceColors[s.source] || 'badge--muted'}">${_esc(s.source)}</span>
      </div>
      <div style="font-size: 0.75rem; margin-top: 4px;">${ctxParts}</div>
      <div class="text-muted" style="font-size: 0.6875rem; margin-top: 2px;">Fired: ${_esc(s.fired_at || '--')}</div>
    </div>`;
  }).join('');
  feedEl.innerHTML = `<div class="card">${rows}</div>`;
}
```

- [ ] **Step 2: Commit**

```bash
git add pipeline/terminal/static/js/pages/scanner.js
git commit -m "feat(terminal): add Scanner page consuming signals[] events"
```

---

### Task 12: Build Risk page

**Files:**
- Create: `pipeline/terminal/static/js/pages/risk.js`

- [ ] **Step 1: Create the page**

```javascript
// pipeline/terminal/static/js/pages/risk.js
// Risk gates dashboard: current level (L0/L1/L2), sizing factor, cumulative P&L,
// trades in window, breach thresholds. Read-only.
import { get } from '../lib/api.js';

let _refreshTimer = null;

export async function render(container) {
  container.innerHTML = '<div class="skeleton skeleton--card"></div>';
  try {
    const data = await get('/risk-gates');
    const levelColors = { L0: 'text-green', L1: 'text-amber', L2: 'text-red' };
    const levelCls = levelColors[data.level] || 'text-muted';
    const allowedBadge = data.allowed
      ? '<span class="badge badge--green">TRADING ALLOWED</span>'
      : '<span class="badge badge--red">TRADING HALTED</span>';

    container.innerHTML = `
      <h2 style="margin-bottom: var(--spacing-md);">Risk — Am I within bounds?</h2>
      <div class="digest-grid">
        <div>
          <div class="digest-card">
            <div class="digest-card__title">Current Gate</div>
            <div style="display: flex; align-items: baseline; gap: var(--spacing-md); margin-top: var(--spacing-sm);">
              <span class="${levelCls} mono" style="font-size: 2.5rem; font-weight: 700;">${data.level}</span>
              ${allowedBadge}
            </div>
            <div class="text-muted" style="font-size: 0.8125rem; margin-top: var(--spacing-sm);">${data.reason || ''}</div>
          </div>
          <div class="digest-card">
            <div class="digest-card__title">Sizing Factor</div>
            <div class="mono" style="font-size: 1.5rem; margin-top: var(--spacing-xs);">${(data.sizing_factor * 100).toFixed(0)}%</div>
            <div class="text-muted" style="font-size: 0.75rem;">Multiplier applied to all new positions</div>
          </div>
        </div>
        <div>
          <div class="digest-card">
            <div class="digest-card__title">Recent Performance</div>
            <div class="digest-row">
              <span class="digest-row__label">Cumulative P&amp;L (20d)</span>
              <span class="digest-row__value mono ${data.cumulative_pnl >= 0 ? 'text-green' : 'text-red'}">${data.cumulative_pnl >= 0 ? '+' : ''}${data.cumulative_pnl}%</span>
            </div>
            <div class="digest-row">
              <span class="digest-row__label">Trades in window</span>
              <span class="digest-row__value mono">${data.trades_in_window || 0}</span>
            </div>
          </div>
          <div class="digest-card">
            <div class="digest-card__title">Breach Thresholds</div>
            <div class="digest-row">
              <span class="digest-row__label">L1 (50% sizing)</span>
              <span class="digest-row__value mono text-amber">-10.0%</span>
            </div>
            <div class="digest-row">
              <span class="digest-row__label">L2 (halt trading)</span>
              <span class="digest-row__value mono text-red">-15.0%</span>
            </div>
          </div>
        </div>
      </div>`;

    if (_refreshTimer) clearInterval(_refreshTimer);
    _refreshTimer = setInterval(() => render(container), 60000);
  } catch {
    container.innerHTML = '<div class="empty-state"><p>Failed to load risk gates</p></div>';
  }
}

export function destroy() {
  if (_refreshTimer) { clearInterval(_refreshTimer); _refreshTimer = null; }
}
```

- [ ] **Step 2: Commit**

```bash
git add pipeline/terminal/static/js/pages/risk.js
git commit -m "feat(terminal): add Risk page with gate status, sizing, breach thresholds"
```

---

### Task 13: Wire new sidebar (10 visible tabs + settings) and update app.js

**Files:**
- Modify: `pipeline/terminal/static/index.html:34-55`
- Modify: `pipeline/terminal/static/js/app.js:1-105`

- [ ] **Step 1: Update the sidebar nav buttons in index.html**

Replace the `<div class="sidebar__nav">…</div>` block (lines 34-55) with:

```html
      <div class="sidebar__nav">
        <button class="sidebar__item sidebar__item--active" data-tab="dashboard" aria-label="Dashboard">
          <i data-lucide="layout-dashboard"></i><span>Dashboard</span>
        </button>
        <button class="sidebar__item" data-tab="trading" aria-label="Trading">
          <i data-lucide="trending-up"></i><span>Trading</span>
        </button>
        <button class="sidebar__item" data-tab="regime" aria-label="Regime">
          <i data-lucide="activity"></i><span>Regime</span>
        </button>
        <button class="sidebar__item" data-tab="scanner" aria-label="Scanner">
          <i data-lucide="radar"></i><span>Scanner</span>
        </button>
        <button class="sidebar__item" data-tab="trust" aria-label="Trust Scores">
          <i data-lucide="shield-check"></i><span>Trust</span>
        </button>
        <button class="sidebar__item" data-tab="news" aria-label="News">
          <i data-lucide="newspaper"></i><span>News</span>
        </button>
        <button class="sidebar__item" data-tab="options" aria-label="Options">
          <i data-lucide="layers"></i><span>Options</span>
        </button>
        <button class="sidebar__item" data-tab="risk" aria-label="Risk">
          <i data-lucide="shield-alert"></i><span>Risk</span>
        </button>
        <button class="sidebar__item" data-tab="research" aria-label="Research">
          <i data-lucide="brain"></i><span>Research</span>
        </button>
        <button class="sidebar__item" data-tab="track-record" aria-label="Track Record">
          <i data-lucide="bar-chart-2"></i><span>Track Record</span>
        </button>
        <button class="sidebar__item" data-tab="settings" aria-label="Settings">
          <i data-lucide="settings"></i><span>Settings</span>
        </button>
      </div>
```

- [ ] **Step 2: Replace app.js with the updated PAGES registry and keyboard map**

```javascript
// pipeline/terminal/static/js/app.js
import { getHealth } from './lib/api.js';
import * as dashboard from './pages/dashboard.js';
import * as trading from './pages/trading.js';
import * as regime from './pages/regime.js';
import * as scanner from './pages/scanner.js';
import * as trust from './pages/trust.js';
import * as news from './pages/news.js';
import * as options from './pages/options.js';
import * as risk from './pages/risk.js';
import * as research from './pages/research.js';
import * as trackRecord from './pages/track-record.js';
import * as settings from './pages/settings.js';

const PAGES = {
  dashboard, trading, regime, scanner, trust, news, options, risk, research,
  'track-record': trackRecord, settings,
};

let currentPage = null;
let currentTab = 'dashboard';

function switchTab(tab) {
  if (tab === currentTab && currentPage) return;
  const main = document.getElementById('main-content');
  if (currentPage && currentPage.destroy) currentPage.destroy();
  document.querySelectorAll('.sidebar__item').forEach(el => {
    el.classList.toggle('sidebar__item--active', el.dataset.tab === tab);
  });
  const page = PAGES[tab];
  if (page) {
    page.render(main);
    currentPage = page;
    currentTab = tab;
  }
}

function closeContextPanel() {
  document.getElementById('context-panel').classList.remove('context-panel--open');
}

function updateClock() {
  const now = new Date();
  const ist = new Date(now.getTime() + (5.5 * 60 * 60 * 1000 - now.getTimezoneOffset() * 60 * 1000));
  const hh = String(ist.getUTCHours()).padStart(2, '0');
  const mm = String(ist.getUTCMinutes()).padStart(2, '0');
  const ss = String(ist.getUTCSeconds()).padStart(2, '0');
  document.getElementById('clock').textContent = `${hh}:${mm}:${ss} IST`;
  const hour = ist.getUTCHours();
  const min = ist.getUTCMinutes();
  const totalMin = hour * 60 + min;
  let status = 'CLOSED';
  if (totalMin >= 555 && totalMin < 570) status = 'PRE-OPEN';
  else if (totalMin >= 570 && totalMin < 930) status = 'OPEN';
  document.getElementById('market-status').textContent = `Market: ${status}`;
}

async function checkHealth() {
  try {
    const data = await getHealth();
    const staleFiles = Object.values(data.data_files || {}).filter(f => f.stale);
    const indicator = document.getElementById('stale-indicator');
    indicator.style.display = staleFiles.length > 0 ? 'inline-flex' : 'none';
  } catch { /* silent */ }
}

function initKeyboard() {
  const tabKeys = {
    '1': 'dashboard', '2': 'trading', '3': 'regime', '4': 'scanner',
    '5': 'trust', '6': 'news', '7': 'options', '8': 'risk',
    '9': 'research', '0': 'track-record',
  };
  document.addEventListener('keydown', (e) => {
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
    if (tabKeys[e.key]) { e.preventDefault(); switchTab(tabKeys[e.key]); }
    if (e.key === 'Escape') closeContextPanel();
  });
}

function init() {
  document.querySelectorAll('.sidebar__item').forEach(btn => {
    btn.addEventListener('click', () => switchTab(btn.dataset.tab));
  });
  document.getElementById('context-panel-close').addEventListener('click', closeContextPanel);
  if (window.lucide) lucide.createIcons();
  updateClock();
  setInterval(updateClock, 1000);
  checkHealth();
  setInterval(checkHealth, 60000);
  initKeyboard();
  switchTab('dashboard');
}

document.addEventListener('DOMContentLoaded', init);
```

- [ ] **Step 3: Manual smoke-test of every tab**

Restart terminal:

```bash
python -m pipeline.terminal
```

Open `http://localhost:5050`. Verify in this order:
- Sidebar shows 11 items: Dashboard, Trading, Regime, Scanner, Trust, News, Options, Risk, Research, Track Record, Settings.
- Click each tab in sequence (1–9, 0). Each renders without console errors.
- Keyboard shortcuts 1–9 + 0 navigate to the correct tab.
- Context panel close (Escape) still works on Trust tab row clicks.

- [ ] **Step 4: Commit**

```bash
git add pipeline/terminal/static/index.html pipeline/terminal/static/js/app.js
git commit -m "feat(terminal): wire 10-tab sidebar + keyboard shortcuts for restructure"
```

---

### Task 14: Delete intelligence.js and prune Trading sub-tabs

**Files:**
- Delete: `pipeline/terminal/static/js/pages/intelligence.js`

- [ ] **Step 1: Confirm no remaining imports of intelligence.js**

Run: `grep -r "pages/intelligence" pipeline/terminal/static/js/ pipeline/terminal/static/index.html`
Expected: no matches (Task 13 removed the import in app.js).

- [ ] **Step 2: Delete the file and verify the site still loads**

```bash
git rm pipeline/terminal/static/js/pages/intelligence.js
```

Restart terminal, click through all tabs again. Expect no broken imports.

- [ ] **Step 3: Commit**

```bash
git commit -m "chore(terminal): remove intelligence.js (sub-tabs promoted to top-level)"
```

---

### Task 15: Update existing tests + final test run

**Files:**
- Modify: `pipeline/terminal/tests/test_trading_apis.py` — no schema changes needed for `/api/spreads`, `/api/news`, `/api/charts`, `/api/ta` (still in use). Add a single test that `/api/candidates` is registered.

- [ ] **Step 1: Add registration test**

Append to `pipeline/terminal/tests/test_candidates_api.py`:

```python
def test_candidates_endpoint_registered():
    from pipeline.terminal.app import app
    routes = [r.path for r in app.routes]
    assert "/api/candidates" in routes
```

- [ ] **Step 2: Run the full terminal test suite**

Run: `pytest pipeline/terminal/tests/ -v`
Expected: all tests pass. If any test failure references `intelligence.js` or removed signals-table behavior, update or remove the assertion.

- [ ] **Step 3: Commit**

```bash
git add pipeline/terminal/tests/test_candidates_api.py
git commit -m "test(terminal): assert /api/candidates is registered"
```

---

### Task 16: Final manual verification + close-out

- [ ] **Step 1: Run end-to-end manual checklist**

Restart terminal: `python -m pipeline.terminal` (from `C:\Users\Claude_Anka\askanka.com`). Open in browser.

Checklist (tick each):
- [ ] Dashboard: shows Open Positions table with Stop, Target, Held, Source/Exit columns. Header position count matches table row count (no 5-vs-6 race).
- [ ] Dashboard: `MODE: SHADOW` badge visible.
- [ ] Dashboard: Portfolio Aggregates + P&L Scenarios render at bottom.
- [ ] Trading: filter chips for Source / Conviction / Horizon. Selecting `static_config` updates URL hash and table.
- [ ] Trading: clicking a row opens the inline narration drawer; clicking again (or another row) closes it.
- [ ] Trading: reload preserves filter state from the URL hash.
- [ ] Regime: ETF zone, score, MSI, top drivers, Phase B picks, eligible spreads snapshot all render.
- [ ] Scanner: signals[] feed renders. Filter by source works.
- [ ] Trust: trust score table renders, search + sector filter work, sortable headers work.
- [ ] News: news items render.
- [ ] Options: leverage matrix + shadow strip render.
- [ ] Risk: gate level (L0/L1/L2), sizing factor %, cumulative P&L, breach thresholds render.
- [ ] Research: full digest (regime card + spread cards + breaks + backtest) renders.
- [ ] Track Record: still works (untouched).
- [ ] Settings: still works (untouched).
- [ ] Keyboard shortcuts 1–9 + 0 navigate correctly.

- [ ] **Step 2: Update SYSTEM_OPERATIONS_MANUAL.md and CLAUDE.md per project doc-sync rule**

Per `feedback_doc_sync_mandate.md`: any structural change to the system requires updating docs in the same commit set. Add a brief note to `docs/SYSTEM_OPERATIONS_MANUAL.md` under the Terminal section describing the new tab map and the `/api/candidates` endpoint.

```bash
# After updating the doc:
git add docs/SYSTEM_OPERATIONS_MANUAL.md
git commit -m "docs: update terminal section with restructured tab map + /api/candidates"
```

- [ ] **Step 3: Save a memory pointer to the new tab map**

Create `C:/Users/Claude_Anka/.claude/projects/C--Users-Claude-Anka-askanka-com/memory/project_terminal_tab_map.md`:

```markdown
---
name: Terminal Tab Map (post-restructure)
description: Anka Terminal's 10-tab structure after the 2026-04-20 restructure — what each tab answers and what feed it consumes.
type: project
---
**Layout (left sidebar, top to bottom):**
1. Dashboard — Open Positions only (live P&L, stops, targets). Feed: `/api/signals` positions array.
2. Trading — `tradeable_candidates[]` browser, filter chips, expandable drawer. Feed: `/api/candidates`.
3. Regime — ETF + MSI + Phase A/B/C. Feed: `/api/regime` + `/api/research/digest` + `/api/candidates`.
4. Scanner — `signals[]` events (TA, OI, correlation breaks). Feed: `/api/candidates` signals array.
5. Trust — OPUS ANKA scorecards. Feed: `/api/trust-scores`.
6. News — News intelligence. Feed: `/api/news/macro`.
7. Options — Synthetic options leverage. Feed: `/api/research/digest` leverage_matrices.
8. Risk — Gates, sizing, cumulative P&L. Feed: `/api/risk-gates`.
9. Research — Full intelligence digest. Feed: `/api/research/digest`.
0. Track Record — unchanged.
   Settings — unchanged.

**Why:** Spec at `docs/superpowers/specs/2026-04-20-dashboard-restructure-design.md`. Schema split (tradeable_candidates vs signals) drives the Trading vs Scanner separation. Discovery-phase compatibility: threshold or basket changes require zero UI work.

**How to apply:** When asked about the terminal layout or where a feature lives, refer to this map. Sub-tabs no longer exist on Intelligence (deleted) or Trading (rewrote). Charts + TA are reachable via the candidate drawer or future Research tab additions, not as standalone sub-tabs.
```

Then add a one-line entry to `MEMORY.md`:

```
- [Terminal Tab Map (v2)](project_terminal_tab_map.md) — 10-tab structure post-2026-04-20 restructure
```

- [ ] **Step 4: Commit**

```bash
git add C:/Users/Claude_Anka/.claude/projects/C--Users-Claude-Anka-askanka-com/memory/project_terminal_tab_map.md
git add C:/Users/Claude_Anka/.claude/projects/C--Users-Claude-Anka-askanka-com/memory/MEMORY.md
git commit -m "docs: memory pointer for new terminal tab map"
```

---

## Out-of-scope reminders (do not implement in this plan)

- Project B (Dynamic Pair Engine) — separate spec/plan once Project C is run.
- Project C (Trust-as-beta backtest) — 1-2 hour validation script. Run before Project B brainstorm.
- Layer 8 (Kite live execution) — schema accommodates via `sizing_basis`; wiring is later.
- KAYNES Phase B vs Phase C contradiction — engine-side fix (apply MIN_PRECEDENTS=5 to the stock ranker), not UI.
- Charts and TA sub-tabs (formerly inside Trading) — leave the components in place for now (`createChart`, `renderTAData` in old trading.js); a follow-up task can either fold them into the candidate drawer or add a small Charts tab. **Do not** delete those code paths yet.

If the implementer notices that any code path from the old trading.js (charts, TA, ticker search) is now orphaned and needs to be re-homed before delete, surface it during Task 14 and create a follow-up task instead of removing functionality.
