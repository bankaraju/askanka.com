# Anka Terminal Plan 2: Dashboard Tab

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Dashboard tab — the first screen users see — with regime banner, KPI cards, signals summary table, and quick glance panel, all reading from real pipeline JSON files.

**Architecture:** Three new API endpoints (`/api/regime`, `/api/signals`, `/api/risk-gates`) serve data from pipeline JSON files. The dashboard.js page module fetches these endpoints and renders the UI using the design system CSS from Plan 1.

**Tech Stack:** Python 3.13, FastAPI, vanilla JS (ES modules), existing design system CSS

---

## File Structure

```
pipeline/terminal/
├── api/
│   ├── regime.py           # NEW: GET /api/regime
│   ├── signals.py          # NEW: GET /api/signals
│   └── risk_gates.py       # NEW: GET /api/risk-gates
├── app.py                  # MODIFY: include new routers
├── static/js/
│   ├── pages/dashboard.js  # MODIFY: full dashboard implementation
│   └── components/
│       ├── regime-banner.js # NEW: regime banner component
│       ├── kpi-card.js      # NEW: KPI card component
│       └── signals-table.js # NEW: signals summary table component
└── tests/
    ├── test_regime_api.py   # NEW: regime endpoint tests
    ├── test_signals_api.py  # NEW: signals endpoint tests
    └── test_risk_gates_api.py # NEW: risk gates endpoint tests
```

---

### Task 1: Regime API Endpoint

**Files:**
- Create: `pipeline/terminal/api/regime.py`
- Modify: `pipeline/terminal/app.py`
- Create: `pipeline/terminal/tests/test_regime_api.py`

- [ ] **Step 1: Write the failing test**

```python
# pipeline/terminal/tests/test_regime_api.py
"""Tests for the regime API endpoint."""
import json
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def mock_data(tmp_path, monkeypatch):
    import pipeline.terminal.api.regime as regime_mod

    global_regime = {
        "updated_at": "2026-04-18T12:37:47+05:30",
        "zone": "EUPHORIA",
        "score": 2.3,
        "regime_source": "etf_engine",
        "stable": True,
        "consecutive_days": 4,
        "components": {},
        "top_drivers": ["SPY", "QQQ"],
        "source_timestamp": "2026-04-18T12:37:41+05:30"
    }
    today_regime = {
        "timestamp": "2026-04-18T12:37:41+05:30",
        "regime": "EUPHORIA",
        "regime_source": "etf_engine",
        "msi_score": 2.3,
        "msi_regime": "MACRO_EASY",
        "regime_stable": True,
        "consecutive_days": 4,
        "trade_map_key": "EUPHORIA",
        "eligible_spreads": {
            "Defence vs IT": {"spread": "Defence vs IT", "best_win": 73.0, "best_period": 1}
        },
        "components": {}
    }

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "global_regime.json").write_text(json.dumps(global_regime))

    pipeline_data = tmp_path / "pipeline_data"
    pipeline_data.mkdir()
    (pipeline_data / "today_regime.json").write_text(json.dumps(today_regime))

    monkeypatch.setattr(regime_mod, "_GLOBAL_REGIME_FILE", data_dir / "global_regime.json")
    monkeypatch.setattr(regime_mod, "_TODAY_REGIME_FILE", pipeline_data / "today_regime.json")
    return tmp_path


def test_regime_returns_zone(mock_data):
    from pipeline.terminal.app import app
    client = TestClient(app)
    resp = client.get("/api/regime")
    assert resp.status_code == 200
    data = resp.json()
    assert data["zone"] == "EUPHORIA"
    assert data["stable"] is True
    assert data["consecutive_days"] == 4


def test_regime_includes_msi(mock_data):
    from pipeline.terminal.app import app
    client = TestClient(app)
    resp = client.get("/api/regime")
    data = resp.json()
    assert data["msi_score"] == 2.3
    assert data["msi_regime"] == "MACRO_EASY"


def test_regime_includes_eligible_spreads(mock_data):
    from pipeline.terminal.app import app
    client = TestClient(app)
    resp = client.get("/api/regime")
    data = resp.json()
    assert "eligible_spreads" in data
    assert "Defence vs IT" in data["eligible_spreads"]


def test_regime_missing_files(tmp_path, monkeypatch):
    import pipeline.terminal.api.regime as regime_mod
    monkeypatch.setattr(regime_mod, "_GLOBAL_REGIME_FILE", tmp_path / "nope.json")
    monkeypatch.setattr(regime_mod, "_TODAY_REGIME_FILE", tmp_path / "nope2.json")

    from pipeline.terminal.app import app
    client = TestClient(app)
    resp = client.get("/api/regime")
    assert resp.status_code == 200
    data = resp.json()
    assert data["zone"] == "UNKNOWN"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd C:\Users\Claude_Anka\askanka.com && python -m pytest pipeline/terminal/tests/test_regime_api.py -v`
Expected: FAIL with ModuleNotFoundError

- [ ] **Step 3: Write the regime endpoint**

```python
# pipeline/terminal/api/regime.py
"""GET /api/regime — current market regime and eligible spreads."""
import json
from pathlib import Path

from fastapi import APIRouter

router = APIRouter()

_HERE = Path(__file__).resolve().parent.parent
_GLOBAL_REGIME_FILE = _HERE.parent.parent / "data" / "global_regime.json"
_TODAY_REGIME_FILE = _HERE.parent / "data" / "today_regime.json"


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


@router.get("/regime")
def regime():
    global_data = _read_json(_GLOBAL_REGIME_FILE)
    today_data = _read_json(_TODAY_REGIME_FILE)

    zone = global_data.get("zone") or today_data.get("regime") or "UNKNOWN"
    stable = global_data.get("stable", today_data.get("regime_stable", False))
    consecutive = global_data.get("consecutive_days", today_data.get("consecutive_days", 0))

    return {
        "zone": zone,
        "score": global_data.get("score", 0.0),
        "regime_source": global_data.get("regime_source", today_data.get("regime_source", "unknown")),
        "stable": stable,
        "consecutive_days": consecutive,
        "msi_score": today_data.get("msi_score", 0.0),
        "msi_regime": today_data.get("msi_regime", "UNAVAILABLE"),
        "trade_map_key": today_data.get("trade_map_key"),
        "eligible_spreads": today_data.get("eligible_spreads", {}),
        "top_drivers": global_data.get("top_drivers", []),
        "updated_at": global_data.get("updated_at") or today_data.get("timestamp"),
    }
```

- [ ] **Step 4: Register router in app.py**

Add to `pipeline/terminal/app.py` after the health router import:

```python
from pipeline.terminal.api.regime import router as regime_router
```

And after `app.include_router(health_router, prefix="/api")`:

```python
app.include_router(regime_router, prefix="/api")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd C:\Users\Claude_Anka\askanka.com && python -m pytest pipeline/terminal/tests/test_regime_api.py -v`
Expected: 4 tests PASS

- [ ] **Step 6: Commit**

```bash
cd C:\Users\Claude_Anka\askanka.com
git add pipeline/terminal/api/regime.py pipeline/terminal/app.py pipeline/terminal/tests/test_regime_api.py
git commit -m "feat(terminal): regime API endpoint with eligible spreads"
```

---

### Task 2: Signals API Endpoint

**Files:**
- Create: `pipeline/terminal/api/signals.py`
- Modify: `pipeline/terminal/app.py`
- Create: `pipeline/terminal/tests/test_signals_api.py`

- [ ] **Step 1: Write the failing test**

```python
# pipeline/terminal/tests/test_signals_api.py
"""Tests for the signals API endpoint."""
import json
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def mock_signals(tmp_path, monkeypatch):
    import pipeline.terminal.api.signals as signals_mod

    open_signals = [
        {
            "signal_id": "SIG-2026-04-15-015-Defence_vs_IT",
            "open_timestamp": "2026-04-15T04:42:21+00:00",
            "status": "OPEN",
            "spread_name": "Defence vs IT",
            "category": "hormuz",
            "tier": "SIGNAL",
            "event_headline": "Test event",
            "hit_rate": 0.733,
            "expected_1d_spread": 0.548,
            "long_legs": [{"ticker": "HAL", "yf": "HAL.NS", "price": 4284.8, "weight": 0.333}],
            "short_legs": [{"ticker": "TCS", "yf": "TCS.NS", "price": 2572.0, "weight": 0.333}],
        }
    ]

    recommendations = {
        "updated_at": "2026-04-18T12:37:58+05:30",
        "regime_zone": "EUPHORIA",
        "stocks": [
            {"ticker": "KAYNES", "direction": "LONG", "conviction": "HIGH", "trigger": "CAUTION",
             "source": "ranker", "source_timestamp": "2026-04-17 09:29:58", "is_stale": True,
             "hit_rate": 1.0, "episodes": 1, "hit_rate_meaningful": False}
        ],
        "spreads": [],
        "news_driven": [],
    }

    positions = {
        "updated_at": "2026-04-18T12:37:58+05:30",
        "positions": [
            {
                "signal_id": "SIG-2026-04-15-015-Defence_vs_IT",
                "spread_name": "Sovereign Shield Alpha",
                "category": "hormuz",
                "tier": "SIGNAL",
                "open_date": "2026-04-15",
                "long_legs": [{"ticker": "HAL", "entry": 4284.8, "current": 4381.0, "pnl_pct": 2.25}],
                "short_legs": [{"ticker": "TCS", "entry": 2572.0, "current": 2583.6, "pnl_pct": -0.45}],
                "spread_pnl_pct": 3.4,
            }
        ],
    }

    signals_dir = tmp_path / "signals"
    signals_dir.mkdir()
    (signals_dir / "open_signals.json").write_text(json.dumps(open_signals))

    data_dir = tmp_path / "website_data"
    data_dir.mkdir()
    (data_dir / "today_recommendations.json").write_text(json.dumps(recommendations))
    (data_dir / "live_status.json").write_text(json.dumps(positions))

    monkeypatch.setattr(signals_mod, "_OPEN_SIGNALS_FILE", signals_dir / "open_signals.json")
    monkeypatch.setattr(signals_mod, "_RECOMMENDATIONS_FILE", data_dir / "today_recommendations.json")
    monkeypatch.setattr(signals_mod, "_LIVE_STATUS_FILE", data_dir / "live_status.json")
    return tmp_path


def test_signals_returns_list(mock_signals):
    from pipeline.terminal.app import app
    client = TestClient(app)
    resp = client.get("/api/signals")
    assert resp.status_code == 200
    data = resp.json()
    assert "signals" in data
    assert "recommendations" in data
    assert "positions" in data


def test_signals_has_open_signal(mock_signals):
    from pipeline.terminal.app import app
    client = TestClient(app)
    resp = client.get("/api/signals")
    data = resp.json()
    assert len(data["signals"]) == 1
    assert data["signals"][0]["signal_id"] == "SIG-2026-04-15-015-Defence_vs_IT"
    assert data["signals"][0]["tier"] == "SIGNAL"


def test_signals_has_recommendations(mock_signals):
    from pipeline.terminal.app import app
    client = TestClient(app)
    resp = client.get("/api/signals")
    data = resp.json()
    assert len(data["recommendations"]) == 1
    assert data["recommendations"][0]["ticker"] == "KAYNES"


def test_signals_has_positions(mock_signals):
    from pipeline.terminal.app import app
    client = TestClient(app)
    resp = client.get("/api/signals")
    data = resp.json()
    assert len(data["positions"]) == 1
    assert data["positions"][0]["spread_pnl_pct"] == 3.4


def test_signals_missing_files(tmp_path, monkeypatch):
    import pipeline.terminal.api.signals as signals_mod
    monkeypatch.setattr(signals_mod, "_OPEN_SIGNALS_FILE", tmp_path / "nope.json")
    monkeypatch.setattr(signals_mod, "_RECOMMENDATIONS_FILE", tmp_path / "nope2.json")
    monkeypatch.setattr(signals_mod, "_LIVE_STATUS_FILE", tmp_path / "nope3.json")

    from pipeline.terminal.app import app
    client = TestClient(app)
    resp = client.get("/api/signals")
    assert resp.status_code == 200
    data = resp.json()
    assert data["signals"] == []
    assert data["recommendations"] == []
    assert data["positions"] == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd C:\Users\Claude_Anka\askanka.com && python -m pytest pipeline/terminal/tests/test_signals_api.py -v`
Expected: FAIL with ModuleNotFoundError

- [ ] **Step 3: Write the signals endpoint**

```python
# pipeline/terminal/api/signals.py
"""GET /api/signals — active signals, recommendations, and positions."""
import json
from pathlib import Path

from fastapi import APIRouter

router = APIRouter()

_HERE = Path(__file__).resolve().parent.parent
_OPEN_SIGNALS_FILE = _HERE.parent / "data" / "signals" / "open_signals.json"
_RECOMMENDATIONS_FILE = _HERE.parent.parent / "data" / "today_recommendations.json"
_LIVE_STATUS_FILE = _HERE.parent.parent / "data" / "live_status.json"


def _read_json(path: Path, default=None):
    if default is None:
        default = {}
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


@router.get("/signals")
def signals():
    raw_signals = _read_json(_OPEN_SIGNALS_FILE, default=[])
    if isinstance(raw_signals, dict):
        raw_signals = raw_signals.get("signals", [])

    raw_recs = _read_json(_RECOMMENDATIONS_FILE)
    stocks = raw_recs.get("stocks", [])

    raw_positions = _read_json(_LIVE_STATUS_FILE)
    positions = raw_positions.get("positions", [])

    return {
        "signals": raw_signals,
        "recommendations": stocks,
        "positions": positions,
        "regime_zone": raw_recs.get("regime_zone"),
        "updated_at": raw_recs.get("updated_at") or raw_positions.get("updated_at"),
    }
```

- [ ] **Step 4: Register router in app.py**

Add to `pipeline/terminal/app.py`:

```python
from pipeline.terminal.api.signals import router as signals_router
app.include_router(signals_router, prefix="/api")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd C:\Users\Claude_Anka\askanka.com && python -m pytest pipeline/terminal/tests/test_signals_api.py -v`
Expected: 5 tests PASS

- [ ] **Step 6: Commit**

```bash
cd C:\Users\Claude_Anka\askanka.com
git add pipeline/terminal/api/signals.py pipeline/terminal/app.py pipeline/terminal/tests/test_signals_api.py
git commit -m "feat(terminal): signals API endpoint with recommendations and positions"
```

---

### Task 3: Risk Gates API Endpoint

**Files:**
- Create: `pipeline/terminal/api/risk_gates.py`
- Modify: `pipeline/terminal/app.py`
- Create: `pipeline/terminal/tests/test_risk_gates_api.py`

- [ ] **Step 1: Write the failing test**

```python
# pipeline/terminal/tests/test_risk_gates_api.py
"""Tests for the risk gates API endpoint."""
import json
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def mock_risk(tmp_path, monkeypatch):
    import pipeline.terminal.api.risk_gates as rg_mod

    closed = [
        {"signal_id": "SIG-001", "final_pnl": {"spread_pnl_pct": 2.5}, "close_timestamp": "2026-04-17T16:00:00+05:30"},
        {"signal_id": "SIG-002", "final_pnl": {"spread_pnl_pct": -1.2}, "close_timestamp": "2026-04-16T16:00:00+05:30"},
    ]
    signals_dir = tmp_path / "signals"
    signals_dir.mkdir()
    (signals_dir / "closed_signals.json").write_text(json.dumps(closed))
    monkeypatch.setattr(rg_mod, "_CLOSED_SIGNALS_FILE", signals_dir / "closed_signals.json")
    return tmp_path


def test_risk_gates_returns_status(mock_risk):
    from pipeline.terminal.app import app
    client = TestClient(app)
    resp = client.get("/api/risk-gates")
    assert resp.status_code == 200
    data = resp.json()
    assert "allowed" in data
    assert "level" in data
    assert "sizing_factor" in data
    assert "cumulative_pnl" in data


def test_risk_gates_allowed_when_positive(mock_risk):
    from pipeline.terminal.app import app
    client = TestClient(app)
    resp = client.get("/api/risk-gates")
    data = resp.json()
    assert data["allowed"] is True
    assert data["level"] == "L0"
    assert data["sizing_factor"] == 1.0


def test_risk_gates_missing_file(tmp_path, monkeypatch):
    import pipeline.terminal.api.risk_gates as rg_mod
    monkeypatch.setattr(rg_mod, "_CLOSED_SIGNALS_FILE", tmp_path / "nope.json")

    from pipeline.terminal.app import app
    client = TestClient(app)
    resp = client.get("/api/risk-gates")
    assert resp.status_code == 200
    data = resp.json()
    assert data["allowed"] is True
    assert data["level"] == "L0"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd C:\Users\Claude_Anka\askanka.com && python -m pytest pipeline/terminal/tests/test_risk_gates_api.py -v`
Expected: FAIL

- [ ] **Step 3: Write the risk gates endpoint**

```python
# pipeline/terminal/api/risk_gates.py
"""GET /api/risk-gates — current risk gate status."""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter

router = APIRouter()

IST = timezone(timedelta(hours=5, minutes=30))

_HERE = Path(__file__).resolve().parent.parent
_CLOSED_SIGNALS_FILE = _HERE.parent / "data" / "signals" / "closed_signals.json"

L1_THRESHOLD = -10.0
L2_THRESHOLD = -15.0
WINDOW_DAYS = 20


@router.get("/risk-gates")
def risk_gates():
    closed = _load_closed()
    recent = _filter_recent(closed, WINDOW_DAYS)
    cumulative = sum(_extract_pnl(t) for t in recent)
    trades_in_window = len(recent)

    if cumulative <= L2_THRESHOLD:
        return {"allowed": False, "sizing_factor": 0.0, "level": "L2",
                "reason": f"Cumulative P&L {cumulative:.1f}% breaches L2 ({L2_THRESHOLD}%)",
                "cumulative_pnl": round(cumulative, 2), "trades_in_window": trades_in_window}
    elif cumulative <= L1_THRESHOLD:
        return {"allowed": True, "sizing_factor": 0.5, "level": "L1",
                "reason": f"Cumulative P&L {cumulative:.1f}% breaches L1 ({L1_THRESHOLD}%)",
                "cumulative_pnl": round(cumulative, 2), "trades_in_window": trades_in_window}
    else:
        return {"allowed": True, "sizing_factor": 1.0, "level": "L0",
                "reason": "Normal operations",
                "cumulative_pnl": round(cumulative, 2), "trades_in_window": trades_in_window}


def _load_closed() -> list:
    if not _CLOSED_SIGNALS_FILE.exists():
        return []
    try:
        data = json.loads(_CLOSED_SIGNALS_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else data.get("signals", [])
    except Exception:
        return []


def _filter_recent(trades: list, days: int) -> list:
    cutoff = datetime.now(IST) - timedelta(days=days)
    result = []
    for t in trades:
        ts = t.get("close_timestamp") or t.get("close_date")
        if not ts:
            continue
        try:
            dt = datetime.fromisoformat(str(ts))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=IST)
            if dt >= cutoff:
                result.append(t)
        except (ValueError, TypeError):
            continue
    return result


def _extract_pnl(trade: dict) -> float:
    fp = trade.get("final_pnl")
    if isinstance(fp, dict):
        return fp.get("spread_pnl_pct", 0.0)
    return trade.get("pnl_pct", 0.0)
```

- [ ] **Step 4: Register router in app.py**

Add to `pipeline/terminal/app.py`:

```python
from pipeline.terminal.api.risk_gates import router as risk_gates_router
app.include_router(risk_gates_router, prefix="/api")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd C:\Users\Claude_Anka\askanka.com && python -m pytest pipeline/terminal/tests/test_risk_gates_api.py -v`
Expected: 3 tests PASS

- [ ] **Step 6: Commit**

```bash
cd C:\Users\Claude_Anka\askanka.com
git add pipeline/terminal/api/risk_gates.py pipeline/terminal/app.py pipeline/terminal/tests/test_risk_gates_api.py
git commit -m "feat(terminal): risk gates API endpoint with L0/L1/L2 levels"
```

---

### Task 4: Dashboard JS Components

**Files:**
- Create: `pipeline/terminal/static/js/components/regime-banner.js`
- Create: `pipeline/terminal/static/js/components/kpi-card.js`
- Create: `pipeline/terminal/static/js/components/signals-table.js`

- [ ] **Step 1: Create the regime banner component**

```javascript
// pipeline/terminal/static/js/components/regime-banner.js
const REGIME_CLASSES = {
  'EUPHORIA': 'regime-euphoria',
  'RISK-ON': 'regime-risk-on',
  'NEUTRAL': 'regime-neutral',
  'CAUTION': 'regime-caution',
  'RISK-OFF': 'regime-risk-off',
};

export function render(container, data) {
  const cls = REGIME_CLASSES[data.zone] || 'regime-neutral';
  const stability = data.stable
    ? `STABLE — ${data.consecutive_days} consecutive days`
    : `UNSTABLE — ${data.consecutive_days} day, unconfirmed`;

  container.innerHTML = `
    <div class="card" style="border-left: 4px solid; margin-bottom: var(--spacing-lg);"
         id="regime-banner">
      <div style="display: flex; justify-content: space-between; align-items: center;">
        <div>
          <span class="topbar__regime-badge ${cls}" style="font-size: 1rem; padding: 6px 16px;">
            ${data.zone || 'UNKNOWN'}
          </span>
          <span class="text-muted" style="margin-left: 12px; font-size: 0.8125rem;">
            ${stability}
          </span>
        </div>
        <div style="text-align: right;">
          <span class="text-muted" style="font-size: 0.75rem;">
            MSI: <span class="mono">${(data.msi_score || 0).toFixed(1)}</span>
            (${data.msi_regime || 'N/A'})
          </span>
          <br>
          <span class="text-muted" style="font-size: 0.6875rem;">
            Updated: ${data.updated_at ? new Date(data.updated_at).toLocaleTimeString('en-IN') : '--'}
          </span>
        </div>
      </div>
    </div>`;

  // Also update the topbar regime badge
  const topBadge = document.getElementById('regime-badge');
  if (topBadge) {
    topBadge.textContent = data.zone || 'UNKNOWN';
    topBadge.className = `topbar__regime-badge ${cls}`;
  }
  const topStability = document.getElementById('regime-stability');
  if (topStability) {
    topStability.textContent = stability;
  }
}
```

- [ ] **Step 2: Create the KPI card component**

```javascript
// pipeline/terminal/static/js/components/kpi-card.js
export function renderGrid(container, cards) {
  const html = cards.map(card => `
    <div class="kpi-card">
      <div class="kpi-card__label">${card.label}</div>
      <div class="kpi-card__value ${card.colorClass || ''}">${card.value}</div>
      <div class="kpi-card__sub">${card.sub || ''}</div>
    </div>
  `).join('');

  container.innerHTML = `<div class="kpi-grid">${html}</div>`;
}
```

- [ ] **Step 3: Create the signals summary table component**

```javascript
// pipeline/terminal/static/js/components/signals-table.js
export function render(container, signals, positions) {
  if ((!signals || signals.length === 0) && (!positions || positions.length === 0)) {
    container.innerHTML = `
      <div class="empty-state">
        <p>No active signals today</p>
      </div>`;
    return;
  }

  const rows = (positions || []).map(pos => {
    const pnl = pos.spread_pnl_pct || 0;
    const pnlClass = pnl >= 0 ? 'text-green' : 'text-red';
    const pnlIcon = pnl >= 0 ? '&#9650;' : '&#9660;';
    const tierBadge = pos.tier === 'SIGNAL'
      ? '<span class="badge badge--gold">SIGNAL</span>'
      : '<span class="badge badge--amber">EXPLORING</span>';

    const longTickers = (pos.long_legs || []).map(l => l.ticker).join(', ');
    const shortTickers = (pos.short_legs || []).map(l => l.ticker).join(', ');

    return `
      <tr class="clickable">
        <td>${pos.spread_name || pos.signal_id}</td>
        <td>
          <span class="text-green">L: ${longTickers}</span><br>
          <span class="text-red">S: ${shortTickers}</span>
        </td>
        <td>${tierBadge}</td>
        <td>${pos.open_date || '--'}</td>
        <td class="${pnlClass} mono">${pnlIcon} ${pnl.toFixed(2)}%</td>
      </tr>`;
  }).join('');

  const recRows = (signals || []).filter(s =>
    !(positions || []).some(p => p.signal_id === s.signal_id)
  ).map(sig => {
    const tierBadge = sig.tier === 'SIGNAL'
      ? '<span class="badge badge--gold">SIGNAL</span>'
      : '<span class="badge badge--amber">EXPLORING</span>';

    const longTickers = (sig.long_legs || []).map(l => l.ticker).join(', ');
    const shortTickers = (sig.short_legs || []).map(l => l.ticker).join(', ');
    const hitRate = sig.hit_rate ? `${(sig.hit_rate * 100).toFixed(0)}%` : '--';

    return `
      <tr class="clickable">
        <td>${sig.spread_name || sig.signal_id}</td>
        <td>
          <span class="text-green">L: ${longTickers}</span><br>
          <span class="text-red">S: ${shortTickers}</span>
        </td>
        <td>${tierBadge}</td>
        <td>${sig.open_timestamp ? sig.open_timestamp.split('T')[0] : '--'}</td>
        <td class="mono">${hitRate}</td>
      </tr>`;
  }).join('');

  container.innerHTML = `
    <h3 style="margin-bottom: var(--spacing-md);">Active Positions & Signals</h3>
    <table class="data-table">
      <thead>
        <tr>
          <th>Spread / Signal</th>
          <th>Legs</th>
          <th>Tier</th>
          <th>Opened</th>
          <th>P&L / Hit Rate</th>
        </tr>
      </thead>
      <tbody>
        ${rows}${recRows}
      </tbody>
    </table>`;
}
```

- [ ] **Step 4: Commit**

```bash
cd C:\Users\Claude_Anka\askanka.com
mkdir -p pipeline/terminal/static/js/components
git add pipeline/terminal/static/js/components/regime-banner.js pipeline/terminal/static/js/components/kpi-card.js pipeline/terminal/static/js/components/signals-table.js
git commit -m "feat(terminal): dashboard JS components — regime banner, KPI cards, signals table"
```

---

### Task 5: Dashboard Page Module

**Files:**
- Modify: `pipeline/terminal/static/js/pages/dashboard.js`

- [ ] **Step 1: Replace the dashboard placeholder with full implementation**

```javascript
// pipeline/terminal/static/js/pages/dashboard.js
import { get } from '../lib/api.js';
import * as regimeBanner from '../components/regime-banner.js';
import * as kpiCard from '../components/kpi-card.js';
import * as signalsTable from '../components/signals-table.js';

let refreshTimer = null;

export async function render(container) {
  container.innerHTML = `
    <div id="dash-regime"></div>
    <div style="display: grid; grid-template-columns: 1fr 2fr 1fr; gap: var(--spacing-lg);">
      <div id="dash-kpis"></div>
      <div id="dash-signals"></div>
      <div id="dash-quickglance"></div>
    </div>`;

  await loadData();
  refreshTimer = setInterval(loadData, 30000);
}

export function destroy() {
  if (refreshTimer) {
    clearInterval(refreshTimer);
    refreshTimer = null;
  }
}

async function loadData() {
  const [regime, signals, riskGates] = await Promise.allSettled([
    get('/regime'),
    get('/signals'),
    get('/risk-gates'),
  ]);

  const regimeData = regime.status === 'fulfilled' ? regime.value : { zone: 'UNKNOWN', stable: false, consecutive_days: 0 };
  const signalsData = signals.status === 'fulfilled' ? signals.value : { signals: [], recommendations: [], positions: [] };
  const riskData = riskGates.status === 'fulfilled' ? riskGates.value : { level: 'L0', sizing_factor: 1.0, cumulative_pnl: 0, allowed: true };

  // Regime banner
  const regimeEl = document.getElementById('dash-regime');
  if (regimeEl) regimeBanner.render(regimeEl, regimeData);

  // KPI cards
  const kpiEl = document.getElementById('dash-kpis');
  if (kpiEl) {
    const activeCount = signalsData.signals.filter(s => s.tier === 'SIGNAL').length;
    const posCount = signalsData.positions.length;
    const totalPnl = signalsData.positions.reduce((sum, p) => sum + (p.spread_pnl_pct || 0), 0);

    kpiCard.renderGrid(kpiEl, [
      {
        label: 'ETF Signal',
        value: (regimeData.score || 0).toFixed(2),
        sub: `Source: ${regimeData.regime_source || 'N/A'}`,
      },
      {
        label: 'Open Positions P&L',
        value: `${totalPnl >= 0 ? '+' : ''}${totalPnl.toFixed(2)}%`,
        colorClass: totalPnl >= 0 ? 'text-green' : 'text-red',
        sub: `${posCount} position${posCount !== 1 ? 's' : ''} open`,
      },
      {
        label: 'Active Signals',
        value: String(activeCount),
        sub: `SIGNAL tier (80+ conviction)`,
        colorClass: 'text-gold',
      },
      {
        label: 'Risk Gate',
        value: riskData.level,
        colorClass: riskData.level === 'L0' ? 'text-green' : riskData.level === 'L1' ? 'text-gold' : 'text-red',
        sub: `Sizing: ${(riskData.sizing_factor * 100).toFixed(0)}% | Cumul: ${riskData.cumulative_pnl.toFixed(1)}%`,
      },
    ]);
  }

  // Signals table
  const signalsEl = document.getElementById('dash-signals');
  if (signalsEl) signalsTable.render(signalsEl, signalsData.signals, signalsData.positions);

  // Quick glance
  const quickEl = document.getElementById('dash-quickglance');
  if (quickEl) {
    const spreads = regimeData.eligible_spreads || {};
    const topSpreads = Object.entries(spreads)
      .sort((a, b) => (b[1].best_win || 0) - (a[1].best_win || 0))
      .slice(0, 5);

    const spreadRows = topSpreads.map(([name, s]) => `
      <tr>
        <td style="font-family: var(--font-body); font-size: 0.8125rem;">${name}</td>
        <td class="mono text-green">${s.best_win || 0}%</td>
      </tr>`).join('');

    const recRows = (signalsData.recommendations || []).slice(0, 5).map(r => {
      const dirClass = r.direction === 'LONG' ? 'text-green' : 'text-red';
      const dirIcon = r.direction === 'LONG' ? '&#9650;' : '&#9660;';
      const staleTag = r.is_stale ? ' <span class="badge badge--stale">STALE</span>' : '';
      return `
        <tr>
          <td style="font-family: var(--font-body); font-size: 0.8125rem;">${r.ticker}${staleTag}</td>
          <td class="${dirClass} mono">${dirIcon} ${r.direction}</td>
          <td class="mono">${r.conviction}</td>
        </tr>`;
    }).join('');

    quickEl.innerHTML = `
      <div class="card" style="margin-bottom: var(--spacing-md);">
        <h3 style="margin-bottom: var(--spacing-sm); font-size: 0.875rem;">Top Eligible Spreads</h3>
        <table class="data-table">
          <thead><tr><th>Spread</th><th>Win%</th></tr></thead>
          <tbody>${spreadRows || '<tr><td colspan="2" class="text-muted">None eligible</td></tr>'}</tbody>
        </table>
      </div>
      <div class="card">
        <h3 style="margin-bottom: var(--spacing-sm); font-size: 0.875rem;">Stock Recommendations</h3>
        <table class="data-table">
          <thead><tr><th>Ticker</th><th>Dir</th><th>Conv</th></tr></thead>
          <tbody>${recRows || '<tr><td colspan="3" class="text-muted">No recommendations</td></tr>'}</tbody>
        </table>
      </div>`;
  }
}
```

- [ ] **Step 2: Verify it loads in browser**

Run: `cd C:\Users\Claude_Anka\askanka.com && python -m pipeline.terminal --no-open &` then open `http://localhost:8501`

Expected: Dashboard shows regime banner (EUPHORIA), 4 KPI cards, signals/positions table, and quick glance with top spreads and recommendations.

- [ ] **Step 3: Commit**

```bash
cd C:\Users\Claude_Anka\askanka.com
git add pipeline/terminal/static/js/pages/dashboard.js
git commit -m "feat(terminal): full dashboard page with regime, KPIs, signals, quick glance"
```

---

### Task 6: Run All Tests + Final Verification

**Files:** None (verification only)

- [ ] **Step 1: Run the complete terminal test suite**

Run: `cd C:\Users\Claude_Anka\askanka.com && python -m pytest pipeline/terminal/tests/ -v`
Expected: All tests pass (12 existing + 4 regime + 5 signals + 3 risk gates = 24 total)

- [ ] **Step 2: Verify all API endpoints**

Run in bash:
```bash
cd C:\Users\Claude_Anka\askanka.com
python -m pipeline.terminal --no-open &
sleep 3
echo "=== /api/health ===" && curl -s http://localhost:8501/api/health | python -m json.tool | head -5
echo "=== /api/regime ===" && curl -s http://localhost:8501/api/regime | python -m json.tool | head -8
echo "=== /api/signals ===" && curl -s http://localhost:8501/api/signals | python -m json.tool | head -5
echo "=== /api/risk-gates ===" && curl -s http://localhost:8501/api/risk-gates | python -m json.tool
pkill -f "pipeline.terminal"
```

Expected: All 4 endpoints return valid JSON with real pipeline data.

- [ ] **Step 3: Commit (if any fixes needed)**

Only commit if fixes were made during verification.
