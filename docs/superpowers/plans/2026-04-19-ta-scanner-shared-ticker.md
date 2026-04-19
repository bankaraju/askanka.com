# TA Scanner + Shared Ticker State Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a filterable TA pattern scanner as the first sub-tab in Trading, with shared ticker state that persists across Charts/TA/Scanner sub-tabs.

**Architecture:** New `/api/scanner` endpoint reads existing TA fingerprint files, filters/groups/sorts server-side. Frontend adds a Scanner sub-tab with card grid, and a shared `_activeTicker` state that all sub-tabs read/write. Card click sets ticker + navigates to Charts.

**Tech Stack:** FastAPI (Python), vanilla JS, Lightweight Charts, existing CSS variables.

**Spec:** `docs/superpowers/specs/2026-04-19-ta-scanner-shared-ticker-design.md`

---

## File Structure

| Action | File | Responsibility |
|--------|------|---------------|
| Create | `pipeline/terminal/api/scanner.py` | `/api/scanner` endpoint — read fingerprints, filter, group, sort |
| Create | `pipeline/terminal/tests/test_scanner_api.py` | Tests for scanner endpoint |
| Modify | `pipeline/terminal/app.py:8-34` | Register scanner router |
| Modify | `pipeline/terminal/static/js/pages/trading.js:1-111` | Shared ticker state + Scanner sub-tab + sub-tab wiring |
| Modify | `pipeline/terminal/static/css/terminal.css` | Scanner card grid + filter bar + ticker badge CSS |

---

### Task 1: Scanner API Endpoint

**Files:**
- Create: `pipeline/terminal/api/scanner.py`
- Create: `pipeline/terminal/tests/test_scanner_api.py`
- Modify: `pipeline/terminal/app.py`

- [ ] **Step 1: Write the failing tests**

```python
# pipeline/terminal/tests/test_scanner_api.py
"""Tests for GET /api/scanner — TA pattern scanner."""
import json
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def fingerprint_dir(tmp_path, monkeypatch):
    import pipeline.terminal.api.scanner as scanner_mod

    fp_dir = tmp_path / "ta_fingerprints"
    fp_dir.mkdir()

    # Stock 1: RELIANCE — 2 strong patterns, 1 weak
    (fp_dir / "RELIANCE.json").write_text(json.dumps({
        "symbol": "RELIANCE", "generated": "2026-04-17",
        "personality": "mixed", "best_pattern": "ATR_COMPRESSION",
        "best_win_rate": 0.72, "significant_patterns": 2,
        "fingerprint": [
            {"pattern": "ATR_COMPRESSION", "direction": "LONG", "significance": "STRONG",
             "win_rate_5d": 0.72, "avg_return_5d": 2.1, "avg_return_10d": 3.4,
             "avg_drawdown": -1.8, "occurrences": 45, "last_occurrence": "2026-04-14"},
            {"pattern": "MACD_CROSS_UP", "direction": "LONG", "significance": "MODERATE",
             "win_rate_5d": 0.65, "avg_return_5d": 1.5, "avg_return_10d": 2.2,
             "avg_drawdown": -1.2, "occurrences": 31, "last_occurrence": "2026-04-10"},
            {"pattern": "CANDLE_DOJI", "direction": "NEUTRAL", "significance": "WEAK",
             "win_rate_5d": 0.48, "avg_return_5d": 0.3, "avg_return_10d": 0.5,
             "avg_drawdown": -2.0, "occurrences": 80, "last_occurrence": "2026-04-16"},
        ],
    }))

    # Stock 2: TCS — 1 short pattern
    (fp_dir / "TCS.json").write_text(json.dumps({
        "symbol": "TCS", "generated": "2026-04-17",
        "personality": "bearish_reversal", "best_pattern": "BB_SQUEEZE",
        "best_win_rate": 0.75, "significant_patterns": 1,
        "fingerprint": [
            {"pattern": "BB_SQUEEZE", "direction": "SHORT", "significance": "STRONG",
             "win_rate_5d": 0.75, "avg_return_5d": -1.9, "avg_return_10d": -2.8,
             "avg_drawdown": -0.9, "occurrences": 22, "last_occurrence": "2026-04-12"},
        ],
    }))

    # Stock 3: INFY — patterns below default thresholds
    (fp_dir / "INFY.json").write_text(json.dumps({
        "symbol": "INFY", "generated": "2026-04-17",
        "personality": "neutral", "best_pattern": "RSI_OVERSOLD",
        "best_win_rate": 0.55, "significant_patterns": 1,
        "fingerprint": [
            {"pattern": "RSI_OVERSOLD", "direction": "LONG", "significance": "MODERATE",
             "win_rate_5d": 0.55, "avg_return_5d": 0.8, "avg_return_10d": 1.1,
             "avg_drawdown": -1.5, "occurrences": 5, "last_occurrence": "2026-04-08"},
        ],
    }))

    monkeypatch.setattr(scanner_mod, "_FINGERPRINTS_DIR", fp_dir)
    scanner_mod._cache.clear()
    return fp_dir


def test_scanner_default_filters(fingerprint_dir):
    from pipeline.terminal.app import app
    data = TestClient(app).get("/api/scanner").json()
    assert data["total_stocks"] >= 1
    assert data["total_patterns"] >= 1
    assert "stocks" in data
    assert "filters" in data
    for stock in data["stocks"]:
        assert "symbol" in stock
        assert "patterns" in stock
        assert len(stock["patterns"]) >= 1


def test_scanner_min_win_filter(fingerprint_dir):
    from pipeline.terminal.app import app
    data = TestClient(app).get("/api/scanner?min_win=70").json()
    symbols = [s["symbol"] for s in data["stocks"]]
    assert "RELIANCE" in symbols
    assert "TCS" in symbols
    assert "INFY" not in symbols
    for stock in data["stocks"]:
        for p in stock["patterns"]:
            assert p["win_rate_5d"] >= 0.70


def test_scanner_direction_filter(fingerprint_dir):
    from pipeline.terminal.app import app
    data = TestClient(app).get("/api/scanner?min_win=60&direction=SHORT").json()
    for stock in data["stocks"]:
        for p in stock["patterns"]:
            assert p["direction"] == "SHORT"


def test_scanner_min_occurrences_filter(fingerprint_dir):
    from pipeline.terminal.app import app
    data = TestClient(app).get("/api/scanner?min_win=50&min_occ=25").json()
    for stock in data["stocks"]:
        for p in stock["patterns"]:
            assert p["occurrences"] >= 25


def test_scanner_sort_by_avg_return(fingerprint_dir):
    from pipeline.terminal.app import app
    data = TestClient(app).get("/api/scanner?min_win=60&sort=avg_return").json()
    if len(data["stocks"]) >= 2:
        wins = [s["best_avg"] for s in data["stocks"]]
        assert wins == sorted(wins, reverse=True)


def test_scanner_empty_result(fingerprint_dir):
    from pipeline.terminal.app import app
    data = TestClient(app).get("/api/scanner?min_win=100").json()
    assert data["total_stocks"] == 0
    assert data["stocks"] == []


def test_scanner_filters_echoed(fingerprint_dir):
    from pipeline.terminal.app import app
    data = TestClient(app).get("/api/scanner?min_win=75&direction=LONG&min_occ=20&sort=occurrences").json()
    assert data["filters"]["min_win"] == 75
    assert data["filters"]["direction"] == "LONG"
    assert data["filters"]["min_occ"] == 20
    assert data["filters"]["sort"] == "occurrences"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd C:/Users/Claude_Anka/askanka.com && python -m pytest pipeline/terminal/tests/test_scanner_api.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pipeline.terminal.api.scanner'`

- [ ] **Step 3: Implement scanner.py**

```python
# pipeline/terminal/api/scanner.py
"""GET /api/scanner — filterable TA pattern scanner across all stocks."""
import json
import time
from pathlib import Path
from fastapi import APIRouter, Query

router = APIRouter()

_HERE = Path(__file__).resolve().parent.parent
_FINGERPRINTS_DIR = _HERE.parent / "data" / "ta_fingerprints"

_CACHE_TTL = 300
_cache: dict = {}


def _load_fingerprints() -> list[dict]:
    now = time.time()
    if _cache.get("data") and now - _cache.get("ts", 0) < _CACHE_TTL:
        return _cache["data"]

    stocks = []
    if not _FINGERPRINTS_DIR.exists():
        return stocks
    for f in _FINGERPRINTS_DIR.glob("*.json"):
        try:
            raw = json.loads(f.read_text(encoding="utf-8"))
            stocks.append(raw)
        except Exception:
            continue
    _cache["data"] = stocks
    _cache["ts"] = now
    return stocks


@router.get("/scanner")
def scanner(
    min_win: int = Query(60, ge=0, le=100),
    direction: str = Query("ALL"),
    min_occ: int = Query(10, ge=0),
    sort: str = Query("win_rate"),
    significance: str = Query("STRONG,MODERATE"),
):
    sig_set = {s.strip().upper() for s in significance.split(",")}
    direction_upper = direction.upper()
    threshold = min_win / 100.0

    all_stocks = _load_fingerprints()
    results = []

    for stock in all_stocks:
        symbol = stock.get("symbol", "")
        patterns = stock.get("fingerprint", stock.get("patterns", []))
        matched = []
        for p in patterns:
            if p.get("significance", "").upper() not in sig_set:
                continue
            if (p.get("win_rate_5d") or 0) < threshold:
                continue
            if direction_upper != "ALL" and p.get("direction", "").upper() != direction_upper:
                continue
            if (p.get("occurrences") or 0) < min_occ:
                continue
            matched.append(p)

        if not matched:
            continue

        best_win = max(p.get("win_rate_5d", 0) for p in matched)
        best_avg = max(abs(p.get("avg_return_5d", 0)) for p in matched)
        best_occ = max(p.get("occurrences", 0) for p in matched)

        matched.sort(key=lambda p: p.get("win_rate_5d", 0), reverse=True)

        results.append({
            "symbol": symbol,
            "personality": stock.get("personality"),
            "best_win": best_win,
            "best_avg": best_avg,
            "pattern_count": len(matched),
            "patterns": matched,
        })

    sort_keys = {
        "win_rate": lambda s: s["best_win"],
        "avg_return": lambda s: s["best_avg"],
        "occurrences": lambda s: max((p.get("occurrences", 0) for p in s["patterns"]), default=0),
    }
    results.sort(key=sort_keys.get(sort, sort_keys["win_rate"]), reverse=True)

    total_patterns = sum(s["pattern_count"] for s in results)

    return {
        "stocks": results,
        "total_stocks": len(results),
        "total_patterns": total_patterns,
        "filters": {
            "min_win": min_win,
            "direction": direction_upper,
            "min_occ": min_occ,
            "sort": sort,
        },
    }
```

- [ ] **Step 4: Register the router in app.py**

Add to `pipeline/terminal/app.py` at line 8 (with the other imports):
```python
from pipeline.terminal.api.scanner import router as scanner_router
```

Add at line 34 (after the last `include_router`):
```python
app.include_router(scanner_router, prefix="/api")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd C:/Users/Claude_Anka/askanka.com && python -m pytest pipeline/terminal/tests/test_scanner_api.py -v`
Expected: 7 passed

- [ ] **Step 6: Commit**

```bash
git add pipeline/terminal/api/scanner.py pipeline/terminal/tests/test_scanner_api.py pipeline/terminal/app.py
git commit -m "feat(terminal): /api/scanner endpoint with filter/group/sort"
```

---

### Task 2: Shared Ticker State + Sub-Tab Wiring

**Files:**
- Modify: `pipeline/terminal/static/js/pages/trading.js:1-111`

- [ ] **Step 1: Add shared ticker state variables and functions**

Add after line 6 (`let _tickerCache = null;`) in `trading.js`:

```javascript
let _activeTicker = null;
let _activeContainer = null;

function setActiveTicker(symbol) {
  _activeTicker = symbol ? symbol.toUpperCase() : null;
  _renderTickerBadge();
}

function getActiveTicker() {
  return _activeTicker;
}

function clearActiveTicker() {
  _activeTicker = null;
  _renderTickerBadge();
}

function _renderTickerBadge() {
  const badge = document.getElementById('active-ticker-badge');
  if (!badge) return;
  if (!_activeTicker) {
    badge.style.display = 'none';
    badge.innerHTML = '';
    return;
  }
  const name = _tickerCache
    ? (_tickerCache.find(t => t.symbol === _activeTicker) || {}).name || ''
    : '';
  badge.style.display = 'flex';
  badge.innerHTML = `
    <span class="ticker-badge__label">Viewing</span>
    <span class="ticker-badge__symbol">${_activeTicker}</span>
    ${name ? `<span class="ticker-badge__name">${name}</span>` : ''}
    <span class="ticker-badge__clear" onclick="document.dispatchEvent(new CustomEvent('clear-ticker'))">&times;</span>`;
}
```

- [ ] **Step 2: Update render() — add Scanner sub-tab + ticker badge + clear listener**

Replace the `render()` function (lines 71-90) with:

```javascript
export async function render(container) {
  _activeContainer = container;
  container.innerHTML = `
    <div class="main__subtabs">
      <button class="subtab subtab--active" data-subtab="scanner">Scanner</button>
      <button class="subtab" data-subtab="signals">Signals</button>
      <button class="subtab" data-subtab="spreads">Spreads</button>
      <button class="subtab" data-subtab="charts">Charts</button>
      <button class="subtab" data-subtab="ta">TA</button>
    </div>
    <div id="active-ticker-badge" class="ticker-badge" style="display:none;"></div>
    <div id="trading-content"></div>`;

  container.querySelectorAll('.subtab').forEach(btn => {
    btn.addEventListener('click', () => {
      container.querySelectorAll('.subtab').forEach(b => b.classList.remove('subtab--active'));
      btn.classList.add('subtab--active');
      switchSubTab(btn.dataset.subtab);
    });
  });

  document.addEventListener('clear-ticker', () => {
    clearActiveTicker();
    switchSubTab(currentSubTab);
  });

  await _loadTickers();
  await switchSubTab('scanner');
}
```

- [ ] **Step 3: Update switchSubTab() — add scanner case + auto-load active ticker**

Replace `switchSubTab()` (lines 97-111) with:

```javascript
async function switchSubTab(tab) {
  currentSubTab = tab;
  if (refreshTimer) { clearInterval(refreshTimer); refreshTimer = null; }
  if (chartInstance) { chartInstance.remove(); chartInstance = null; }

  const content = document.getElementById('trading-content');
  if (!content) return;

  switch (tab) {
    case 'scanner': await renderScanner(content); break;
    case 'signals': await renderSignals(content); break;
    case 'spreads': await renderSpreads(content); break;
    case 'charts':
      await renderCharts(content);
      if (_activeTicker) createChart(_activeTicker);
      break;
    case 'ta':
      await renderTA(content);
      if (_activeTicker) renderTAData(_activeTicker);
      break;
  }
}
```

- [ ] **Step 4: Wire setActiveTicker into existing Charts and TA search handlers**

In `renderCharts()` — find where `_setupTickerSearch` is called (around line 302). Change the `onSelect` callback to also call `setActiveTicker`:

Replace the `_setupTickerSearch` call in renderCharts with:
```javascript
_setupTickerSearch('chart-ticker-input', (sym) => { setActiveTicker(sym); createChart(sym); });
```

And the button click handler:
```javascript
btn.onclick = () => { const t = inp.value.trim().toUpperCase(); if (t) { setActiveTicker(t); createChart(t); } };
```

In `renderTA()` — same pattern (around line 443):
```javascript
_setupTickerSearch('ta-ticker-input', (sym) => { setActiveTicker(sym); renderTAData(sym); });
```

And the button click handler:
```javascript
btn.onclick = () => { const t = inp.value.trim().toUpperCase(); if (t) { setActiveTicker(t); renderTAData(t); } };
```

- [ ] **Step 5: Test manually in browser**

Run: `cd C:/Users/Claude_Anka/askanka.com/pipeline/terminal && python -m uvicorn app:app --reload --port 8501`

1. Open http://localhost:8501 → Trading tab
2. Scanner should be the first active sub-tab (empty for now — renderScanner not yet implemented)
3. Switch to Charts → type RELIANCE → badge appears "Viewing: RELIANCE"
4. Switch to TA → RELIANCE should auto-load
5. Click ✕ on badge → clears, TA shows empty state
6. Type TCS in TA → badge updates to TCS, switch to Charts → TCS chart loads

- [ ] **Step 6: Commit**

```bash
git add pipeline/terminal/static/js/pages/trading.js
git commit -m "feat(terminal): shared ticker state across Charts/TA/Scanner"
```

---

### Task 3: Scanner Sub-Tab UI

**Files:**
- Modify: `pipeline/terminal/static/js/pages/trading.js` (add `renderScanner` function)
- Modify: `pipeline/terminal/static/css/terminal.css` (add scanner styles)

- [ ] **Step 1: Add CSS for scanner components**

Append to `pipeline/terminal/static/css/terminal.css`:

```css
/* ── Scanner ─────────────────────────────────────── */
.scanner-filters {
  display: flex; flex-wrap: wrap; gap: 16px; align-items: flex-end;
  padding-bottom: 12px; margin-bottom: 16px; border-bottom: 1px solid var(--border);
}
.scanner-filter-group { display: flex; flex-direction: column; gap: 4px; }
.scanner-filter-label {
  font-size: 0.625rem; text-transform: uppercase; letter-spacing: 0.08em;
  color: var(--text-muted);
}
.scanner-filter-btns { display: flex; gap: 4px; }
.scanner-filter-btn {
  background: var(--bg-elevated); border: 1px solid var(--border); border-radius: var(--radius-sm);
  padding: 4px 10px; font-size: 0.75rem; color: var(--text-muted); cursor: pointer;
  transition: border-color 0.15s, color 0.15s;
}
.scanner-filter-btn:hover { border-color: var(--accent-gold); color: var(--text-primary); }
.scanner-filter-btn--active {
  border-color: var(--accent-gold); color: var(--accent-gold);
  background: rgba(212, 168, 85, 0.1); font-weight: 600;
}
.scanner-count {
  margin-left: auto; font-size: 0.8125rem; color: var(--text-secondary); font-weight: 600;
}
.scanner-grid {
  display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px;
}
@media (max-width: 768px) { .scanner-grid { grid-template-columns: repeat(2, 1fr); } }
@media (max-width: 480px) { .scanner-grid { grid-template-columns: 1fr; } }
.scanner-card {
  background: var(--bg-card); border: 1px solid var(--border); border-radius: var(--radius);
  padding: 12px; cursor: pointer; transition: border-color 0.2s;
}
.scanner-card:hover { border-color: var(--accent-gold); }
.scanner-card__header {
  display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;
}
.scanner-card__symbol { color: var(--accent-gold); font-weight: 700; font-size: 0.9375rem; }
.scanner-card__badge {
  font-size: 0.625rem; padding: 2px 8px; border-radius: 3px; font-weight: 600;
}
.scanner-card__badge--long { background: rgba(34, 197, 94, 0.12); color: var(--green); }
.scanner-card__badge--short { background: rgba(239, 68, 68, 0.12); color: var(--red); }
.scanner-card__badge--mixed { background: rgba(212, 168, 85, 0.12); color: var(--accent-gold); }
.scanner-card__patterns {
  font-family: var(--font-mono); font-size: 0.6875rem; color: var(--text-secondary);
  line-height: 1.8;
}
.scanner-card__pattern-row { display: flex; justify-content: space-between; }
.scanner-card__footer {
  color: var(--text-muted); font-size: 0.625rem; margin-top: 6px;
}

/* ── Ticker Badge ────────────────────────────────── */
.ticker-badge {
  display: flex; align-items: center; gap: 8px;
  padding: 8px 12px; margin: 8px 0;
  background: var(--bg-card); border: 1px solid var(--accent-gold);
  border-radius: var(--radius); width: fit-content;
}
.ticker-badge__label {
  font-size: 0.625rem; text-transform: uppercase; letter-spacing: 0.08em;
  color: var(--text-muted);
}
.ticker-badge__symbol { color: var(--accent-gold); font-weight: 700; font-size: 0.9375rem; }
.ticker-badge__name { color: var(--text-muted); font-size: 0.6875rem; }
.ticker-badge__clear {
  color: var(--text-muted); font-size: 0.875rem; cursor: pointer; margin-left: 4px;
  padding: 0 4px; line-height: 1;
}
.ticker-badge__clear:hover { color: var(--text-primary); }
```

- [ ] **Step 2: Implement renderScanner() in trading.js**

Add this function in `trading.js` (before the `renderSignals` function):

```javascript
// ── Scanner Sub-Tab ──
let _scannerFilters = { min_win: 60, direction: 'ALL', min_occ: 10, sort: 'win_rate' };

async function renderScanner(el) {
  el.innerHTML = `
    <div class="scanner-filters">
      <div class="scanner-filter-group">
        <div class="scanner-filter-label">Min Win Rate</div>
        <div class="scanner-filter-btns" data-filter="min_win">
          <button class="scanner-filter-btn" data-val="50">≥50%</button>
          <button class="scanner-filter-btn scanner-filter-btn--active" data-val="60">≥60%</button>
          <button class="scanner-filter-btn" data-val="70">≥70%</button>
          <button class="scanner-filter-btn" data-val="80">≥80%</button>
        </div>
      </div>
      <div class="scanner-filter-group">
        <div class="scanner-filter-label">Direction</div>
        <div class="scanner-filter-btns" data-filter="direction">
          <button class="scanner-filter-btn scanner-filter-btn--active" data-val="ALL">ALL</button>
          <button class="scanner-filter-btn" data-val="LONG">LONG</button>
          <button class="scanner-filter-btn" data-val="SHORT">SHORT</button>
        </div>
      </div>
      <div class="scanner-filter-group">
        <div class="scanner-filter-label">Min Occurrences</div>
        <div class="scanner-filter-btns" data-filter="min_occ">
          <button class="scanner-filter-btn scanner-filter-btn--active" data-val="10">≥10</button>
          <button class="scanner-filter-btn" data-val="25">≥25</button>
          <button class="scanner-filter-btn" data-val="50">≥50</button>
        </div>
      </div>
      <div class="scanner-filter-group">
        <div class="scanner-filter-label">Sort By</div>
        <div class="scanner-filter-btns" data-filter="sort">
          <button class="scanner-filter-btn scanner-filter-btn--active" data-val="win_rate">Win Rate</button>
          <button class="scanner-filter-btn" data-val="avg_return">Avg Return</button>
          <button class="scanner-filter-btn" data-val="occurrences">Occurrences</button>
        </div>
      </div>
      <div class="scanner-count" id="scanner-count"></div>
    </div>
    <div id="scanner-grid" class="scanner-grid"></div>`;

  el.querySelectorAll('.scanner-filter-btns').forEach(group => {
    const filterKey = group.dataset.filter;
    group.querySelectorAll('.scanner-filter-btn').forEach(btn => {
      if (String(_scannerFilters[filterKey]) === btn.dataset.val) {
        group.querySelectorAll('.scanner-filter-btn').forEach(b => b.classList.remove('scanner-filter-btn--active'));
        btn.classList.add('scanner-filter-btn--active');
      }
      btn.addEventListener('click', () => {
        group.querySelectorAll('.scanner-filter-btn').forEach(b => b.classList.remove('scanner-filter-btn--active'));
        btn.classList.add('scanner-filter-btn--active');
        _scannerFilters[filterKey] = isNaN(btn.dataset.val) ? btn.dataset.val : Number(btn.dataset.val);
        _fetchAndRenderScanner();
      });
    });
  });

  await _fetchAndRenderScanner();
}

async function _fetchAndRenderScanner() {
  const grid = document.getElementById('scanner-grid');
  const countEl = document.getElementById('scanner-count');
  if (!grid) return;

  grid.innerHTML = '<div class="skeleton skeleton--card"></div>';
  const params = new URLSearchParams({
    min_win: _scannerFilters.min_win,
    direction: _scannerFilters.direction,
    min_occ: _scannerFilters.min_occ,
    sort: _scannerFilters.sort,
  });

  try {
    const data = await get(`/scanner?${params}`);
    if (countEl) countEl.textContent = `${data.total_stocks} stocks · ${data.total_patterns} patterns`;

    if (data.stocks.length === 0) {
      grid.innerHTML = '<div class="empty-state"><p>No patterns match these filters.</p><p class="text-muted">Try lowering the win rate threshold.</p></div>';
      return;
    }

    grid.innerHTML = data.stocks.map(stock => {
      const dirs = new Set(stock.patterns.map(p => p.direction));
      const badgeClass = dirs.size > 1 ? 'mixed' : dirs.has('SHORT') ? 'short' : 'long';
      const badgeLabel = dirs.size > 1 ? `${stock.pattern_count} patterns` : `${stock.pattern_count} ${[...dirs][0].toLowerCase()}`;

      const patternRows = stock.patterns.map(p => {
        const winCls = p.win_rate_5d >= 0.65 ? 'color:var(--green)' : p.win_rate_5d >= 0.55 ? 'color:var(--accent-gold)' : 'color:var(--red)';
        const sign = p.avg_return_5d >= 0 ? '+' : '';
        const dir = p.direction === 'SHORT' ? ' <span style="color:var(--red)">▼</span>' : '';
        return `<div class="scanner-card__pattern-row">
          <span>${p.pattern.replace(/_/g, '_')}${dir}</span>
          <span><span style="${winCls};font-weight:600">${Math.round(p.win_rate_5d * 100)}%</span> · ${sign}${p.avg_return_5d.toFixed(1)}% · ${p.occurrences}×</span>
        </div>`;
      }).join('');

      const bestP = stock.patterns[0];
      const lastDate = bestP.last_occurrence ? new Date(bestP.last_occurrence).toLocaleDateString('en-IN', { month: 'short', day: 'numeric' }) : '—';

      return `<div class="scanner-card" data-symbol="${stock.symbol}">
        <div class="scanner-card__header">
          <span class="scanner-card__symbol">${stock.symbol}</span>
          <span class="scanner-card__badge scanner-card__badge--${badgeClass}">${badgeLabel}</span>
        </div>
        <div class="scanner-card__patterns">${patternRows}</div>
        <div class="scanner-card__footer">Best: ${bestP.pattern} · Last fired ${lastDate}</div>
      </div>`;
    }).join('');

    grid.querySelectorAll('.scanner-card').forEach(card => {
      card.addEventListener('click', () => {
        const sym = card.dataset.symbol;
        setActiveTicker(sym);
        const chartsBtn = _activeContainer?.querySelector('[data-subtab="charts"]');
        if (chartsBtn) {
          _activeContainer.querySelectorAll('.subtab').forEach(b => b.classList.remove('subtab--active'));
          chartsBtn.classList.add('subtab--active');
        }
        switchSubTab('charts');
      });
    });

  } catch (err) {
    grid.innerHTML = `<div class="empty-state"><p>Error loading scanner data.</p><p class="text-muted">${err.message}</p></div>`;
  }
}
```

- [ ] **Step 3: Test in browser**

Run: `cd C:/Users/Claude_Anka/askanka.com/pipeline/terminal && python -m uvicorn app:app --reload --port 8501`

1. Open http://localhost:8501 → Trading tab → Scanner is first and active
2. Card grid shows stocks grouped with pattern stat lines
3. Click ≥70% filter → grid updates with fewer stocks
4. Click LONG → only long patterns shown
5. Click a stock card → badge shows "Viewing: RELIANCE", auto-switches to Charts, chart loads
6. Switch to TA → RELIANCE TA auto-loads
7. Switch back to Scanner → filter state preserved
8. Click ✕ on badge → clears, Charts/TA show empty search state

- [ ] **Step 4: Commit**

```bash
git add pipeline/terminal/static/js/pages/trading.js pipeline/terminal/static/css/terminal.css
git commit -m "feat(terminal): Scanner sub-tab with filter bar + card grid"
```

---

### Task 4: Enhanced TA Narration

**Files:**
- Modify: `pipeline/terminal/static/js/pages/trading.js` (update `renderTAData` function)

- [ ] **Step 1: Update renderTAData to show compact stat narration**

Find the `renderTAData` function (around line 451). Update the pattern card rendering to include the one-liner stat narration. Replace the card body inside the `.forEach` loop that builds pattern cards:

In each pattern card, after the existing badges (direction, significance, win_rate), add:

```javascript
const narration = `Fired ${p.occurrences}× in 5 years. Won ${Math.round((p.win_rate_5d || 0) * 100)}% over 5 days. Avg ${p.avg_return_5d >= 0 ? '+' : ''}${(p.avg_return_5d || 0).toFixed(1)}%, worst ${(p.avg_drawdown || 0).toFixed(1)}%.`;
```

And include it in the card HTML as:
```html
<div style="font-size:0.6875rem;color:var(--text-muted);margin-top:6px;line-height:1.5;">
  ${narration}
  ${p.avg_return_10d ? `<br>10-day avg: ${p.avg_return_10d >= 0 ? '+' : ''}${p.avg_return_10d.toFixed(1)}%` : ''}
</div>
```

- [ ] **Step 2: Test in browser**

1. Open Trading → select a stock → switch to TA
2. Each pattern card shows: "Fired 45× in 5 years. Won 72% over 5 days. Avg +2.1%, worst -1.8%."
3. 10-day return shown as secondary line where available

- [ ] **Step 3: Commit**

```bash
git add pipeline/terminal/static/js/pages/trading.js
git commit -m "feat(terminal): compact stat narration on TA pattern cards"
```

---

### Task 5: Run All Tests + Final Verification

**Files:** None (verification only)

- [ ] **Step 1: Run the full test suite**

Run: `cd C:/Users/Claude_Anka/askanka.com && python -m pytest pipeline/terminal/tests/ -v`
Expected: All tests pass (existing + 7 new scanner tests)

- [ ] **Step 2: Manual end-to-end test**

Run terminal, open browser, test full flow:
1. Scanner loads as first tab with stock cards
2. Filter buttons work (win rate, direction, occurrences, sort)
3. Click stock card → sets shared ticker → navigates to Charts → chart loads
4. Switch to TA → same stock auto-loaded with stat narration
5. Switch back to Scanner → filter state preserved, clicked card's stock highlighted in badge
6. Type different ticker in Charts search → badge updates → switch to TA → new stock loaded
7. Click ✕ → clears everything
8. Responsive: resize to 768px → 2 columns, 480px → 1 column

- [ ] **Step 3: Commit and push**

```bash
git push
```

---

## Self-Review Checklist

**Spec coverage:**
- ✅ `/api/scanner` endpoint with all 5 query params → Task 1
- ✅ Scanner sub-tab as first position → Task 2 (render) + Task 3 (UI)
- ✅ Filter bar with button groups → Task 3
- ✅ Card grid grouped by stock → Task 3
- ✅ Compact stat narration → Task 3 (scanner cards) + Task 4 (TA detail)
- ✅ Shared ticker state → Task 2
- ✅ Ticker badge UI → Task 2 (JS) + Task 3 (CSS)
- ✅ Click flow: Scanner → Charts → TA with persistence → Task 2 + Task 3
- ✅ Responsive breakpoints (768px, 480px) → Task 3 (CSS)
- ✅ Cache with 5-min TTL → Task 1
- ✅ Tests → Task 1 (API) + Task 5 (full suite)

**Placeholder scan:** No TBD/TODO found. All code blocks complete.

**Type consistency:** `_activeTicker`, `setActiveTicker`, `clearActiveTicker`, `getActiveTicker` used consistently. `_scannerFilters` object keys match API query params. Response field `best_avg` used in both API and sort test.
