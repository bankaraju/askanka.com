# Website Cleanup + Global Regime Score Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the stale, mis-labelled MSI on askanka.com with the live 31-ETF Global Regime Score, strip non-production sections, and wire the export job into the daily clockwork so the site stays fresh forever.

**Architecture:** `unified_regime_engine.py` writes `pipeline/data/today_regime.json` (already happening). A refactored `pipeline/website_exporter.py` reads it, derives top drivers, and writes `data/global_regime.json` + a slimmed `data/live_status.json`. Bat files in `pipeline/scripts/` invoke the exporter at end of every intraday scan and EOD. `index.html` is surgically cleaned to read only the new files, with the Global Regime Score as the new hero.

**Tech Stack:** Python 3.13, pytest, vanilla HTML/JS, Windows Task Scheduler via .bat files.

**Spec:** `docs/superpowers/specs/2026-04-15-website-cleanup-regime-score-design.md`

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `pipeline/website_exporter.py` | Modify | Read `today_regime.json`, write `global_regime.json` + slimmed `live_status.json` |
| `pipeline/tests/test_website_exporter.py` | Create | Unit tests for `export_global_regime()` and slimmed `export_live_status()` |
| `pipeline/tests/fixtures/today_regime_fixture.json` | Create | Sample input for tests |
| `pipeline/scripts/intraday_scan.bat` | Modify | Append exporter call at end |
| `pipeline/scripts/eod_track_record.bat` | Modify | Append exporter call at end |
| `index.html` | Modify | Remove deprecated sections, add Global Regime Score hero, simplify positions table |
| `data/global_regime.json` | Created at runtime | New canonical regime file the website reads |
| `data/track_record.json` | Delete | Section removed from site |
| `data/spread_universe.json` | Delete | Section removed from site |
| `data/weekly_index.json` | Delete | Section removed from site |
| `data/msi_history.json` | Delete | Replaced by `global_regime.json` |

---

## Task 1: Create test fixture for `today_regime.json`

**Files:**
- Create: `pipeline/tests/fixtures/today_regime_fixture.json`

- [ ] **Step 1: Create the fixture file**

```json
{
  "timestamp": "2026-04-15T09:25:08.354943+05:30",
  "regime": "NEUTRAL",
  "regime_source": "etf_engine",
  "msi_score": 43.7,
  "msi_regime": "MACRO_NEUTRAL",
  "regime_stable": true,
  "consecutive_days": 2,
  "trade_map_key": "NEUTRAL",
  "eligible_spreads": {
    "Defence vs IT": {"spread": "Defence vs IT", "1d_win": 57.0, "best_period": 5, "best_win": 59.0}
  },
  "components": {
    "inst_flow": {"raw": null, "norm": 0.5, "weight": 0.3, "contribution": 15.0},
    "india_vix": {"raw": 19.93, "norm": 0.49, "weight": 0.25, "contribution": 12.3},
    "usd_inr": {"raw": 0.002, "norm": 0.4, "weight": 0.2, "contribution": 8.0},
    "nifty_30d": {"raw": 0.015, "norm": 0.55, "weight": 0.15, "contribution": 8.25},
    "crude_5d": {"raw": -0.01, "norm": 0.015, "weight": 0.1, "contribution": 0.15}
  }
}
```

- [ ] **Step 2: Commit fixture**

```bash
git add pipeline/tests/fixtures/today_regime_fixture.json
git commit -m "test: fixture for today_regime.json (website exporter tests)"
```

---

## Task 2: Write failing test for `export_global_regime()`

**Files:**
- Create: `pipeline/tests/test_website_exporter.py`

- [ ] **Step 1: Write the failing test**

```python
"""Tests for pipeline/website_exporter.py — Global Regime Score export."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from website_exporter import export_global_regime

FIXTURE = Path(__file__).parent / "fixtures" / "today_regime_fixture.json"


def test_global_regime_basic_fields(tmp_path, monkeypatch):
    """Reads today_regime.json fixture and emits zone, score, source, stability."""
    # Point exporter at fixture
    monkeypatch.setattr("website_exporter.TODAY_REGIME_FILE", FIXTURE)
    out = export_global_regime()
    assert out["zone"] == "NEUTRAL"
    assert out["score"] == 43.7
    assert out["regime_source"] == "etf_engine"
    assert out["stable"] is True
    assert out["consecutive_days"] == 2


def test_global_regime_top_drivers(monkeypatch):
    """Top 3 drivers ordered by absolute contribution descending."""
    monkeypatch.setattr("website_exporter.TODAY_REGIME_FILE", FIXTURE)
    out = export_global_regime()
    # Fixture contributions: inst_flow=15.0, india_vix=12.3, nifty_30d=8.25, usd_inr=8.0, crude_5d=0.15
    assert out["top_drivers"] == ["inst_flow", "india_vix", "nifty_30d"]


def test_global_regime_components_passthrough(monkeypatch):
    """Full components dict is preserved for the website to render."""
    monkeypatch.setattr("website_exporter.TODAY_REGIME_FILE", FIXTURE)
    out = export_global_regime()
    assert "components" in out
    assert out["components"]["india_vix"]["raw"] == 19.93


def test_global_regime_missing_file(tmp_path, monkeypatch):
    """If today_regime.json is missing, return a sentinel record (not crash)."""
    monkeypatch.setattr("website_exporter.TODAY_REGIME_FILE", tmp_path / "nope.json")
    out = export_global_regime()
    assert out["zone"] == "UNKNOWN"
    assert out["score"] is None
    assert out["top_drivers"] == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd C:/Users/Claude_Anka/askanka.com && python -m pytest pipeline/tests/test_website_exporter.py -v`
Expected: ImportError or AttributeError — `export_global_regime` does not exist yet, `TODAY_REGIME_FILE` does not exist yet.

---

## Task 3: Implement `export_global_regime()` and `TODAY_REGIME_FILE`

**Files:**
- Modify: `pipeline/website_exporter.py`

- [ ] **Step 1: Add the constant near the existing path constants (top of file)**

After the line `SPREAD_STATS = DATA_DIR / "spread_stats.json"`, add:

```python
TODAY_REGIME_FILE = DATA_DIR / "today_regime.json"
```

- [ ] **Step 2: Add the new function before `def export_live_status()`**

```python
def export_global_regime() -> dict:
    """Export 31-ETF regime engine output for the website hero block."""
    raw = _load_json(TODAY_REGIME_FILE)
    if not raw:
        return {
            "updated_at": datetime.now(IST).isoformat(),
            "zone": "UNKNOWN",
            "score": None,
            "regime_source": "unavailable",
            "stable": False,
            "consecutive_days": 0,
            "components": {},
            "top_drivers": [],
            "source_timestamp": None,
        }

    components = raw.get("components", {}) or {}
    # Rank by absolute contribution; take top 3 names
    ranked = sorted(
        components.items(),
        key=lambda kv: abs((kv[1] or {}).get("contribution", 0) or 0),
        reverse=True,
    )
    top_drivers = [name for name, _ in ranked[:3]]

    return {
        "updated_at": datetime.now(IST).isoformat(),
        "zone": raw.get("regime", "UNKNOWN"),
        "score": raw.get("msi_score"),
        "regime_source": raw.get("regime_source", "unknown"),
        "stable": raw.get("regime_stable", False),
        "consecutive_days": raw.get("consecutive_days", 0),
        "components": components,
        "top_drivers": top_drivers,
        "source_timestamp": raw.get("timestamp"),
    }
```

- [ ] **Step 3: Run tests to verify they pass**

Run: `python -m pytest pipeline/tests/test_website_exporter.py -v`
Expected: All 4 tests PASS.

- [ ] **Step 4: Commit**

```bash
git add pipeline/website_exporter.py pipeline/tests/test_website_exporter.py
git commit -m "feat(exporter): add export_global_regime() reading 31-ETF today_regime.json"
```

---

## Task 4: Slim down `export_live_status()` and add test

**Files:**
- Modify: `pipeline/website_exporter.py`
- Modify: `pipeline/tests/test_website_exporter.py`

- [ ] **Step 1: Add a fixture for open signals**

Append to `pipeline/tests/fixtures/`:

Create `pipeline/tests/fixtures/open_signals_fixture.json`:

```json
[
  {
    "signal_id": "DEF_IT_2026-04-12",
    "spread_name": "Defence vs IT",
    "category": "REGIME_NEUTRAL",
    "tier": "SIGNAL",
    "open_timestamp": "2026-04-12T09:30:00+05:30",
    "long_legs": [{"ticker": "HAL", "price": 4500.0}],
    "short_legs": [{"ticker": "INFY", "price": 1800.0}],
    "_data_levels": {"cumulative": 11.14, "todays_move": 0.4, "daily_stop": -2.0, "two_day_stop": -3.5},
    "peak_spread_pnl_pct": 12.0
  }
]
```

- [ ] **Step 2: Add failing test**

Append to `pipeline/tests/test_website_exporter.py`:

```python
OPEN_SIG_FIXTURE = Path(__file__).parent / "fixtures" / "open_signals_fixture.json"


def test_live_status_only_positions_and_fragility(tmp_path, monkeypatch):
    """Slimmed live_status emits updated_at, positions, fragility — no win/loss/track stats."""
    monkeypatch.setattr("website_exporter.OPEN_FILE", OPEN_SIG_FIXTURE)
    monkeypatch.setattr("website_exporter.CLOSED_FILE", tmp_path / "missing.json")
    monkeypatch.setattr("website_exporter.DATA_DIR", tmp_path)  # disables fragility load
    from website_exporter import export_live_status
    out = export_live_status()
    assert set(out.keys()) == {"updated_at", "positions", "fragility"}
    assert len(out["positions"]) == 1
    pos = out["positions"][0]
    assert pos["spread_name"] == "Defence vs IT"
    assert pos["spread_pnl_pct"] == 11.14
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python -m pytest pipeline/tests/test_website_exporter.py::test_live_status_only_positions_and_fragility -v`
Expected: FAIL — `out` still contains `msi`, `stats` keys.

- [ ] **Step 4: Replace `export_live_status()` body**

In `pipeline/website_exporter.py`, replace the entire `export_live_status()` function with:

```python
def export_live_status() -> dict:
    """Export current open positions for the live dashboard."""
    open_sigs = _load_json(OPEN_FILE)

    positions = []
    for sig in open_sigs:
        dl = sig.get("_data_levels", {})
        positions.append({
            "signal_id": sig.get("signal_id", ""),
            "spread_name": sig.get("spread_name", ""),
            "category": sig.get("category", ""),
            "tier": sig.get("tier", "SIGNAL"),
            "open_date": sig.get("open_timestamp", "")[:10],
            "long_legs": [
                {"ticker": l["ticker"], "entry": l["price"], "current": l.get("price", 0)}
                for l in sig.get("long_legs", [])
            ],
            "short_legs": [
                {"ticker": s["ticker"], "entry": s["price"], "current": s.get("price", 0)}
                for s in sig.get("short_legs", [])
            ],
            "spread_pnl_pct": dl.get("cumulative", 0),
            "todays_move": dl.get("todays_move", 0),
            "daily_stop": dl.get("daily_stop", 0),
            "two_day_stop": dl.get("two_day_stop", 0),
            "peak_pnl": sig.get("peak_spread_pnl_pct", 0),
        })

    # Fragility scores (optional)
    fragility = {}
    frag_file = DATA_DIR / "fragility_scores.json"
    if frag_file.exists():
        try:
            frag_data = json.loads(frag_file.read_text(encoding="utf-8"))
            fragility = frag_data.get("scores", {})
        except Exception:
            pass

    return {
        "updated_at": datetime.now(IST).isoformat(),
        "positions": positions,
        "fragility": fragility,
    }
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest pipeline/tests/test_website_exporter.py -v`
Expected: All 5 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add pipeline/website_exporter.py pipeline/tests/test_website_exporter.py pipeline/tests/fixtures/open_signals_fixture.json
git commit -m "refactor(exporter): slim live_status to positions+fragility only"
```

---

## Task 5: Remove deprecated exports and rewrite `run_export()`

**Files:**
- Modify: `pipeline/website_exporter.py`

- [ ] **Step 1: Delete `export_track_record()`**

Remove the entire function `def export_track_record() -> dict:` and its body (the function that builds the closed trades summary).

- [ ] **Step 2: Delete `export_spread_universe()`**

Remove the entire function `def export_spread_universe() -> dict:` and its body.

- [ ] **Step 3: Delete `export_msi_history()`**

Remove the entire function `def export_msi_history() -> list:` and its body.

- [ ] **Step 4: Delete the now-unused `from config import` line if INDIA_SPREAD_PAIRS / INDIA_SIGNAL_STOCKS aren't referenced anywhere else in the file**

If after deletions the file no longer references `INDIA_SPREAD_PAIRS` or `INDIA_SIGNAL_STOCKS`, remove the import line:

```python
from config import INDIA_SPREAD_PAIRS, INDIA_SIGNAL_STOCKS
```

- [ ] **Step 5: Replace `run_export()` with the new minimal version**

```python
def run_export():
    """Run full export to website JSON files."""
    WEBSITE_DIR.mkdir(parents=True, exist_ok=True)

    regime = export_global_regime()
    live = export_live_status()

    for name, data in [
        ("global_regime.json", regime),
        ("live_status.json", live),
    ]:
        path = WEBSITE_DIR / name
        path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        print(f"  Exported {name} ({path})")

    print(f"\nWebsite data exported to {WEBSITE_DIR}")
    print(f"  Regime zone:    {regime['zone']} (score {regime['score']})")
    print(f"  Open positions: {len(live['positions'])}")
```

- [ ] **Step 6: Run all exporter tests**

Run: `python -m pytest pipeline/tests/test_website_exporter.py -v`
Expected: All 5 tests still PASS (deletions did not affect them).

- [ ] **Step 7: Commit**

```bash
git add pipeline/website_exporter.py
git commit -m "refactor(exporter): remove track_record, spread_universe, msi_history exports"
```

---

## Task 6: End-to-end smoke test of the exporter

**Files:**
- (none — runtime check)

- [ ] **Step 1: Run the exporter against live pipeline data**

Run: `cd C:/Users/Claude_Anka/askanka.com && python -X utf8 pipeline/website_exporter.py`
Expected output:
```
  Exported global_regime.json (...\data\global_regime.json)
  Exported live_status.json (...\data\live_status.json)

Website data exported to ...\data
  Regime zone:    NEUTRAL (score 43.7)
  Open positions: <n>
```

- [ ] **Step 2: Verify the produced JSON**

Run: `python -c "import json; d=json.load(open('data/global_regime.json')); print('zone:', d['zone'], 'score:', d['score'], 'top:', d['top_drivers'])"`
Expected: zone=NEUTRAL, score=43.7, top_drivers list with 3 names.

Run: `python -c "import json; d=json.load(open('data/live_status.json')); print('keys:', sorted(d.keys()), 'positions:', len(d['positions']))"`
Expected: keys=['fragility', 'positions', 'updated_at'], positions=count of open spreads.

- [ ] **Step 3: Confirm fresh mtimes**

Run: `ls -la data/global_regime.json data/live_status.json`
Expected: both files dated today.

---

## Task 7: Wire the exporter into scheduled bat files

**Files:**
- Modify: `pipeline/scripts/intraday_scan.bat`
- Modify: `pipeline/scripts/eod_track_record.bat`

- [ ] **Step 1: Read current `intraday_scan.bat`**

Run: `cat pipeline/scripts/intraday_scan.bat`

- [ ] **Step 2: Append exporter line to `intraday_scan.bat`**

Add this line at the very end of `pipeline/scripts/intraday_scan.bat` (after the `if not "%_TRANS%"==""` block):

```batch
python -X utf8 website_exporter.py >> logs\intraday_scan.log 2>&1
```

- [ ] **Step 3: Read current `eod_track_record.bat`**

Run: `cat pipeline/scripts/eod_track_record.bat`

- [ ] **Step 4: Append exporter line to `eod_track_record.bat`**

Add this line at the very end of `pipeline/scripts/eod_track_record.bat`:

```batch
cd /d "C:\Users\Claude_Anka\askanka.com\pipeline"
python -X utf8 website_exporter.py >> logs\website_exporter.log 2>&1
```

(If the file already starts with a `cd` command, only add the python line. If not, both lines are needed for safety.)

- [ ] **Step 5: Test by running intraday_scan.bat manually**

Run: `cmd //c pipeline/scripts/intraday_scan.bat`
Expected: completes without errors. `tail logs/intraday_scan.log` shows the exporter ran (no PermissionError, no traceback).

- [ ] **Step 6: Re-verify data file mtimes**

Run: `ls -la data/global_regime.json data/live_status.json`
Expected: timestamps from this minute (proves bat invocation worked).

- [ ] **Step 7: Commit**

```bash
git add pipeline/scripts/intraday_scan.bat pipeline/scripts/eod_track_record.bat
git commit -m "feat(scheduling): wire website_exporter into intraday + eod bat files"
```

---

## Task 8: Inventory `index.html` sections to remove

**Files:**
- Read: `index.html`

- [ ] **Step 1: Identify line ranges of each section to remove**

Open `index.html` and locate (record line numbers in a scratch note for use in next steps):

1. Methodology section/nav link
2. Telegram link/footer reference
3. Heatmap / Spread Universe Explorer block
4. Track Record table + closed-trades section
5. Weekly Reports archive + the JS that fetches `weekly_index.json`
6. MSI gauge component (the `<svg>` or `<div id="msi-gauge">` and its JS handler)
7. Signal ticker scroll bar (depends on track stats)
8. Any JS code that fetches: `track_record.json`, `spread_universe.json`, `weekly_index.json`, `msi_history.json`

Use grep to be precise:

```bash
grep -n "methodology\|telegram\|heatmap\|spread.universe\|track.record\|weekly.index\|msi.gauge\|msi.history\|signal.ticker" index.html
```

Record the section start/end line numbers in a scratch note.

---

## Task 9: Surgically remove deprecated sections from `index.html`

**Files:**
- Modify: `index.html`

- [ ] **Step 1: Make a backup before HTML surgery**

Run: `cp index.html index.html.bak-2026-04-15`

- [ ] **Step 2: Remove sections one by one using Edit tool**

For each section identified in Task 8, use the Edit tool to remove the HTML block, the matching JS handler, and any nav link / button that points to it. Do them one at a time and re-open the file in the browser between cuts to confirm nothing else breaks visually.

Specific items:
- `<a href="#methodology">` and `<section id="methodology">`
- `<a href="https://t.me/...">` (telegram)
- `<section id="spread-universe">` / `<div class="heatmap">`
- `<section id="track-record">` / `<table id="closed-trades">`
- `<section id="weekly-reports">` and the corresponding `fetch('data/weekly_index.json')` JS
- `<div id="msi-gauge">` and the `fetch('data/msi_history.json')` JS
- `<div class="signal-ticker">` and any associated JS

- [ ] **Step 3: Verify page loads with no console errors**

Open `index.html` in a browser (right-click → Open in browser, or use a local server). Open DevTools Console.
Expected: no 404s for the deleted JSON files, no JS reference errors, page renders cleanly with remaining sections (articles + F&O news for now — hero is added in Task 10).

- [ ] **Step 4: Commit**

```bash
git add index.html
git commit -m "chore(site): remove methodology, telegram, heatmap, track record, MSI gauge"
```

---

## Task 10: Add Global Regime Score hero block to `index.html`

**Files:**
- Modify: `index.html`

- [ ] **Step 1: Locate insertion point**

The hero goes immediately after the site header / nav, above all other content blocks. Identify the line where the existing "above the fold" section starts.

- [ ] **Step 2: Insert the hero HTML**

Insert this block at the chosen location:

```html
<!-- Global Regime Score Hero -->
<section id="regime-hero" class="hero-block">
  <div class="hero-grid">
    <div class="zone-badge" id="regime-zone">—</div>
    <div class="zone-detail">
      <div class="score-line">Score: <span id="regime-score">—</span></div>
      <div class="stability-line" id="regime-stability">—</div>
      <div class="updated-line">Updated: <span id="regime-updated">—</span></div>
    </div>
    <div class="drivers-list">
      <div class="drivers-title">Top drivers</div>
      <ol id="regime-drivers"><li>loading…</li></ol>
    </div>
  </div>
</section>
```

- [ ] **Step 3: Add the matching CSS** (inside the existing `<style>` block; follow gold theme)

```css
.hero-block { padding: 32px 24px; border-bottom: 1px solid #2a2a2a; }
.hero-grid { display: grid; grid-template-columns: auto 1fr 1fr; gap: 32px; align-items: center; max-width: 1200px; margin: 0 auto; }
.zone-badge { font-family: 'DM Serif Display', serif; font-size: 48px; padding: 16px 28px; border-radius: 8px; text-align: center; }
.zone-badge.RISK-OFF   { background: #3a1818; color: #ff6b6b; }
.zone-badge.CAUTION    { background: #3a2a18; color: #ffa94d; }
.zone-badge.NEUTRAL    { background: #2a2418; color: #f59e0b; }
.zone-badge.RISK-ON    { background: #18331f; color: #69db7c; }
.zone-badge.EUPHORIA   { background: #18402b; color: #2fb344; }
.zone-badge.UNKNOWN    { background: #222; color: #888; }
.zone-detail { font-family: 'JetBrains Mono', monospace; font-size: 14px; line-height: 1.7; color: #cfcfcf; }
.score-line { font-size: 18px; color: #f3f3f3; }
.stability-line { color: #9c9c9c; }
.updated-line { color: #6e6e6e; font-size: 12px; }
.drivers-title { font-family: 'Inter', sans-serif; font-size: 12px; text-transform: uppercase; letter-spacing: 0.08em; color: #9c9c9c; margin-bottom: 6px; }
#regime-drivers { font-family: 'JetBrains Mono', monospace; font-size: 14px; color: #f3f3f3; padding-left: 20px; }
```

- [ ] **Step 4: Add the JS that fetches and renders `data/global_regime.json`**

Inside the existing `<script>` block (or in the location where other fetch handlers live), add:

```javascript
async function loadGlobalRegime() {
  try {
    const res = await fetch('data/global_regime.json?t=' + Date.now());
    if (!res.ok) throw new Error('fetch failed');
    const d = await res.json();
    const zone = d.zone || 'UNKNOWN';
    document.getElementById('regime-zone').textContent = zone;
    document.getElementById('regime-zone').className = 'zone-badge ' + zone;
    document.getElementById('regime-score').textContent = d.score == null ? '—' : Number(d.score).toFixed(1);
    document.getElementById('regime-stability').textContent =
      (d.stable ? 'Stable' : 'Shifting') + ' · Day ' + (d.consecutive_days || 0) + ' of ' + zone;
    document.getElementById('regime-updated').textContent =
      d.updated_at ? new Date(d.updated_at).toLocaleString('en-IN', { hour12: false }) : '—';
    const ol = document.getElementById('regime-drivers');
    ol.innerHTML = '';
    (d.top_drivers || []).forEach(name => {
      const li = document.createElement('li');
      const c = (d.components || {})[name] || {};
      const contrib = c.contribution != null ? ' (' + Number(c.contribution).toFixed(1) + ')' : '';
      li.textContent = name + contrib;
      ol.appendChild(li);
    });
  } catch (e) {
    document.getElementById('regime-zone').textContent = 'OFFLINE';
  }
}
loadGlobalRegime();
setInterval(loadGlobalRegime, 60_000);  // refresh every minute
```

- [ ] **Step 5: Smoke-test in browser**

Open `index.html` in a browser. Confirm: zone badge shows NEUTRAL in gold, score shows 43.7, stability says "Stable · Day 2 of NEUTRAL", drivers list shows 3 entries.

- [ ] **Step 6: Commit**

```bash
git add index.html
git commit -m "feat(site): add Global Regime Score hero block reading data/global_regime.json"
```

---

## Task 11: Slim down Live Positions table on `index.html`

**Files:**
- Modify: `index.html`

- [ ] **Step 1: Locate the existing positions table**

Grep for the existing positions block:

```bash
grep -n "positions\|active.position\|open.position" index.html
```

- [ ] **Step 2: Replace the existing positions HTML with a clean table**

Find the existing positions section and replace with:

```html
<section id="live-positions" class="positions-block">
  <h2 class="block-title">Live Positions</h2>
  <table class="positions-table">
    <thead>
      <tr>
        <th>Spread</th><th>Open</th><th>Today's move</th><th>Cumulative</th><th>Peak</th>
      </tr>
    </thead>
    <tbody id="positions-body">
      <tr><td colspan="5">Loading…</td></tr>
    </tbody>
  </table>
</section>
```

- [ ] **Step 3: Update the JS that renders positions to read from the slimmed `live_status.json`**

Replace any existing `loadLiveStatus()` JS with:

```javascript
async function loadLivePositions() {
  try {
    const res = await fetch('data/live_status.json?t=' + Date.now());
    if (!res.ok) throw new Error('fetch failed');
    const d = await res.json();
    const tbody = document.getElementById('positions-body');
    tbody.innerHTML = '';
    if (!d.positions || d.positions.length === 0) {
      tbody.innerHTML = '<tr><td colspan="5">No open positions</td></tr>';
      return;
    }
    d.positions.forEach(p => {
      const tr = document.createElement('tr');
      const todayCls = p.todays_move >= 0 ? 'pos' : 'neg';
      const cumCls = p.spread_pnl_pct >= 0 ? 'pos' : 'neg';
      tr.innerHTML =
        '<td>' + p.spread_name + '</td>' +
        '<td>' + p.open_date + '</td>' +
        '<td class="' + todayCls + '">' + Number(p.todays_move).toFixed(2) + '%</td>' +
        '<td class="' + cumCls + '">' + Number(p.spread_pnl_pct).toFixed(2) + '%</td>' +
        '<td>' + Number(p.peak_pnl).toFixed(2) + '%</td>';
      tbody.appendChild(tr);
    });
  } catch (e) {
    document.getElementById('positions-body').innerHTML = '<tr><td colspan="5">Offline</td></tr>';
  }
}
loadLivePositions();
setInterval(loadLivePositions, 60_000);
```

- [ ] **Step 4: Add minimal table CSS if not already present**

```css
.positions-block { padding: 24px; max-width: 1200px; margin: 0 auto; }
.block-title { font-family: 'DM Serif Display', serif; font-size: 28px; color: #f3f3f3; }
.positions-table { width: 100%; border-collapse: collapse; font-family: 'JetBrains Mono', monospace; font-size: 14px; }
.positions-table th, .positions-table td { padding: 10px 12px; text-align: left; border-bottom: 1px solid #2a2a2a; }
.positions-table th { color: #9c9c9c; text-transform: uppercase; font-size: 11px; letter-spacing: 0.08em; }
.positions-table td.pos { color: #69db7c; }
.positions-table td.neg { color: #ff6b6b; }
```

- [ ] **Step 5: Smoke-test in browser**

Open `index.html`. Confirm the positions table renders with the open Defence vs IT spread (entry/today/cumulative/peak columns).

- [ ] **Step 6: Commit**

```bash
git add index.html
git commit -m "feat(site): slim live positions table to read new live_status.json"
```

---

## Task 12: Final smoke test on the whole page

**Files:**
- (none — visual verification)

- [ ] **Step 1: Open `index.html` in browser, hard-refresh (Ctrl+Shift+R)**

- [ ] **Step 2: Visual checklist**

- [ ] Hero block visible above fold with NEUTRAL badge, score 43.7, drivers list
- [ ] Live Positions table renders with ≥1 row
- [ ] Articles section renders (reads `articles_index.json`)
- [ ] F&O News scroll renders (reads `fno_news.json`)
- [ ] No methodology link in nav
- [ ] No telegram link
- [ ] No heatmap / spread universe section
- [ ] No track record table
- [ ] No weekly reports section
- [ ] No old MSI gauge

- [ ] **Step 3: DevTools Console check**

Open DevTools (F12) → Console. Expected: zero errors, zero 404s.

- [ ] **Step 4: Network tab check**

DevTools → Network → reload. Expected JSON requests: `global_regime.json`, `live_status.json`, `articles_index.json`, `fno_news.json`. No requests for: `track_record.json`, `spread_universe.json`, `weekly_index.json`, `msi_history.json`.

---

## Task 13: Delete deprecated JSON files and remove backup

**Files:**
- Delete: `data/track_record.json`, `data/spread_universe.json`, `data/weekly_index.json`, `data/msi_history.json`, `index.html.bak-2026-04-15`

- [ ] **Step 1: Delete deprecated data files**

Run:
```bash
rm data/track_record.json data/spread_universe.json data/weekly_index.json data/msi_history.json index.html.bak-2026-04-15
```

- [ ] **Step 2: Confirm git sees the deletions**

Run: `git status`
Expected: 4 deleted files in `data/`.

- [ ] **Step 3: Commit deletions**

```bash
git add -u data/
git commit -m "chore(site): remove deprecated JSON files (track_record, spread_universe, weekly_index, msi_history)"
```

---

## Task 14: Push and verify on live askanka.com

**Files:**
- (none — deployment)

- [ ] **Step 1: Push to remote**

Confirm with user before pushing — askanka.com is the live public site.

If approved by user, run:
```bash
git push origin master
```

- [ ] **Step 2: Wait for GitHub Pages to deploy (~1-2 minutes)**

- [ ] **Step 3: Open https://askanka.com in browser, hard-refresh**

Confirm the same visual checklist from Task 12 passes on the live URL.

---

## Self-Review Notes

**Spec coverage (all sections from `2026-04-15-website-cleanup-regime-score-design.md`):**
- ✅ Pipeline `export_global_regime()` → Task 3
- ✅ Slimmed `export_live_status()` → Task 4
- ✅ Removed `export_track_record` / `export_spread_universe` → Task 5
- ✅ Updated `run_export()` writes only the two new files → Task 5
- ✅ Schedule into `intraday_scan.bat` + `eod_track_record.bat` → Task 7
- ✅ Remove methodology, telegram, heatmap, track record, weekly, MSI gauge from index.html → Tasks 8-9
- ✅ Add Global Regime Score hero → Task 10
- ✅ Live positions tracker reads new `live_status.json` → Task 11
- ✅ Verification plan from spec → Tasks 6, 12, 14
- ✅ Explicitly deferred items (backfill, eod_report fix, Kite, article workflow) — not in plan, correctly out of scope

**Type consistency check:**
- `TODAY_REGIME_FILE` defined in Task 3, monkeypatched in Tasks 2, 4 — consistent name
- `export_global_regime` returns dict with keys `zone`, `score`, `top_drivers`, `components`, `consecutive_days`, `stable`, `updated_at`, `regime_source`, `source_timestamp`. The HTML JS in Task 10 reads exactly these keys — consistent.
- `export_live_status` returns `{updated_at, positions, fragility}`. The HTML JS in Task 11 reads `d.positions[*].{spread_name, open_date, todays_move, spread_pnl_pct, peak_pnl}` — consistent with the dict built in Task 4.

**Placeholder scan:** No TBDs, no "implement later", no "similar to Task N", no "add appropriate error handling" without showing what to add. Clean.
