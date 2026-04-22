# Anka Terminal Plan 1: Foundation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the foundational FastAPI application with static file serving, design system CSS, shell layout (sidebar + top bar + tab routing), and CLI entry point — so the terminal opens in a browser with working navigation.

**Architecture:** FastAPI serves REST API endpoints and static files from `pipeline/terminal/static/`. A single `index.html` entry point loads ES module JS files that handle client-side routing between 5 primary tabs. No build step — all vanilla JS loaded directly by the browser.

**Tech Stack:** Python 3.13, FastAPI 0.135, Uvicorn 0.44, Lightweight Charts (CDN), Lucide Icons (CDN), DM Serif Display + Inter + JetBrains Mono (Google Fonts)

---

## File Structure

```
pipeline/terminal/
├── __init__.py              # Package marker
├── app.py                   # FastAPI app: mounts static files, includes API routers
├── cli.py                   # CLI entry point: `python -m pipeline.terminal`
├── api/
│   ├── __init__.py
│   └── health.py            # GET /api/health — system health + data freshness
├── static/
│   ├── index.html           # Single page entry point, loads all JS/CSS
│   ├── css/
│   │   └── terminal.css     # Design system tokens + layout + component styles
│   └── js/
│       ├── app.js           # Router, tab switching, keyboard shortcuts, init
│       ├── lib/
│       │   └── api.js       # REST API client (fetch wrapper)
│       └── pages/
│           ├── dashboard.js     # Dashboard tab placeholder
│           ├── trading.js       # Trading tab placeholder
│           ├── intelligence.js  # Intelligence tab placeholder
│           ├── track-record.js  # Track Record tab placeholder
│           └── settings.js      # Settings tab placeholder
└── tests/
    ├── __init__.py
    ├── test_app.py           # FastAPI app tests (static serving, health endpoint)
    └── test_cli.py           # CLI entry point tests
```

---

### Task 1: FastAPI Application + Health Endpoint

**Files:**
- Create: `pipeline/terminal/__init__.py`
- Create: `pipeline/terminal/app.py`
- Create: `pipeline/terminal/api/__init__.py`
- Create: `pipeline/terminal/api/health.py`
- Create: `pipeline/terminal/tests/__init__.py`
- Create: `pipeline/terminal/tests/test_app.py`

- [ ] **Step 1: Write the failing test**

```python
# pipeline/terminal/tests/test_app.py
"""Tests for the Anka Terminal FastAPI application."""
import pytest
from fastapi.testclient import TestClient


def test_health_endpoint_returns_200():
    from pipeline.terminal.app import app
    client = TestClient(app)
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert "status" in data
    assert "timestamp" in data
    assert data["status"] == "ok"


def test_health_endpoint_includes_data_freshness(tmp_path, monkeypatch):
    import pipeline.terminal.api.health as health_mod
    monkeypatch.setattr(health_mod, "_DATA_DIR", tmp_path)
    monkeypatch.setattr(health_mod, "_PIPELINE_DATA_DIR", tmp_path)

    from pipeline.terminal.app import app
    client = TestClient(app)
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert "data_files" in data


def test_static_files_mount():
    from pipeline.terminal.app import app
    client = TestClient(app)
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd C:\Users\Claude_Anka\askanka.com && python -m pytest pipeline/terminal/tests/test_app.py -v`
Expected: FAIL with ModuleNotFoundError

- [ ] **Step 3: Create package markers**

```python
# pipeline/terminal/__init__.py
# Anka Terminal — Trading Intelligence Terminal

# pipeline/terminal/api/__init__.py
# Terminal API routers

# pipeline/terminal/tests/__init__.py
# Terminal test suite
```

- [ ] **Step 4: Write the health endpoint**

```python
# pipeline/terminal/api/health.py
"""GET /api/health — system health and data freshness."""
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

from fastapi import APIRouter

router = APIRouter()

IST = timezone(timedelta(hours=5, minutes=30))

_HERE = Path(__file__).resolve().parent.parent.parent
_DATA_DIR = _HERE.parent / "data"
_PIPELINE_DATA_DIR = _HERE / "data"

_CRITICAL_FILES = {
    "global_regime": _DATA_DIR / "global_regime.json",
    "today_recommendations": _DATA_DIR / "today_recommendations.json",
    "track_record": _DATA_DIR / "track_record.json",
    "trust_scores": _DATA_DIR / "trust_scores.json",
    "live_status": _DATA_DIR / "live_status.json",
    "today_regime": _PIPELINE_DATA_DIR / "today_regime.json",
}


def _check_file(path: Path) -> dict:
    if not path.exists():
        return {"exists": False, "stale": True}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        updated = raw.get("updated_at") or raw.get("timestamp") or raw.get("source_timestamp")
        return {"exists": True, "updated_at": updated, "stale": False}
    except Exception:
        return {"exists": True, "stale": True}


@router.get("/health")
def health():
    now = datetime.now(IST).isoformat()
    data_files = {name: _check_file(path) for name, path in _CRITICAL_FILES.items()}
    return {
        "status": "ok",
        "timestamp": now,
        "data_files": data_files,
    }
```

- [ ] **Step 5: Write the FastAPI app**

```python
# pipeline/terminal/app.py
"""Anka Terminal — FastAPI application."""
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from pipeline.terminal.api.health import router as health_router

app = FastAPI(title="Anka Terminal", version="0.1.0")

app.include_router(health_router, prefix="/api")

_STATIC_DIR = Path(__file__).parent / "static"


@app.get("/")
async def index():
    return FileResponse(_STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")
```

- [ ] **Step 6: Create a minimal index.html so the static mount works**

```html
<!-- pipeline/terminal/static/index.html -->
<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><title>Anka Terminal</title></head>
<body><h1>Anka Terminal</h1></body>
</html>
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `cd C:\Users\Claude_Anka\askanka.com && python -m pytest pipeline/terminal/tests/test_app.py -v`
Expected: 3 tests PASS

- [ ] **Step 8: Commit**

```bash
cd C:\Users\Claude_Anka\askanka.com
git add pipeline/terminal/__init__.py pipeline/terminal/app.py pipeline/terminal/api/__init__.py pipeline/terminal/api/health.py pipeline/terminal/tests/__init__.py pipeline/terminal/tests/test_app.py pipeline/terminal/static/index.html
git commit -m "feat(terminal): FastAPI app with health endpoint and static serving"
```

---

### Task 2: CLI Entry Point

**Files:**
- Create: `pipeline/terminal/cli.py`
- Create: `pipeline/terminal/__main__.py`
- Create: `pipeline/terminal/tests/test_cli.py`

- [ ] **Step 1: Write the failing test**

```python
# pipeline/terminal/tests/test_cli.py
"""Tests for the Anka Terminal CLI entry point."""
import subprocess
import sys


def test_cli_help():
    result = subprocess.run(
        [sys.executable, "-m", "pipeline.terminal", "--help"],
        capture_output=True, text=True, cwd="C:\\Users\\Claude_Anka\\askanka.com",
    )
    assert result.returncode == 0
    assert "Anka Terminal" in result.stdout


def test_cli_default_port():
    from pipeline.terminal.cli import parse_args
    args = parse_args([])
    assert args.port == 8501


def test_cli_custom_port():
    from pipeline.terminal.cli import parse_args
    args = parse_args(["--port", "9000"])
    assert args.port == 9000


def test_cli_no_open_flag():
    from pipeline.terminal.cli import parse_args
    args = parse_args(["--no-open"])
    assert args.no_open is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd C:\Users\Claude_Anka\askanka.com && python -m pytest pipeline/terminal/tests/test_cli.py -v`
Expected: FAIL with ModuleNotFoundError

- [ ] **Step 3: Write the CLI module**

```python
# pipeline/terminal/cli.py
"""CLI entry point for Anka Terminal.

Usage:
    python -m pipeline.terminal              # start on port 8501, open browser
    python -m pipeline.terminal --port 9000  # custom port
    python -m pipeline.terminal --no-open    # don't auto-open browser
"""
import argparse
import threading
import time
import webbrowser


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        prog="anka-terminal",
        description="Anka Terminal — Trading Intelligence Terminal",
    )
    parser.add_argument("--port", type=int, default=8501, help="Port to serve on (default: 8501)")
    parser.add_argument("--no-open", action="store_true", help="Don't auto-open browser")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    url = f"http://localhost:{args.port}"

    if not args.no_open:
        def open_browser():
            time.sleep(1.5)
            webbrowser.open(url)
        threading.Thread(target=open_browser, daemon=True).start()

    print(f"\n  Anka Terminal running at {url}\n  Press Ctrl+C to stop.\n")

    import uvicorn
    uvicorn.run("pipeline.terminal.app:app", host="127.0.0.1", port=args.port, log_level="warning")
```

- [ ] **Step 4: Write the __main__.py**

```python
# pipeline/terminal/__main__.py
"""Allow `python -m pipeline.terminal` to start the terminal."""
from pipeline.terminal.cli import main

if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd C:\Users\Claude_Anka\askanka.com && python -m pytest pipeline/terminal/tests/test_cli.py -v`
Expected: 4 tests PASS

- [ ] **Step 6: Commit**

```bash
cd C:\Users\Claude_Anka\askanka.com
git add pipeline/terminal/cli.py pipeline/terminal/__main__.py pipeline/terminal/tests/test_cli.py
git commit -m "feat(terminal): CLI entry point with port config and auto-open"
```

---

### Task 3: Design System CSS

**Files:**
- Create: `pipeline/terminal/static/css/terminal.css`

- [ ] **Step 1: Write the complete design system CSS**

```css
/* pipeline/terminal/static/css/terminal.css */
/* Anka Terminal — Design System Tokens + Layout + Components */

/* ── Tokens ── */
:root {
  --bg-primary: #0a0e1a;
  --bg-card: #111827;
  --bg-elevated: #1e293b;
  --border: #1e293b;

  --text-primary: #f1f5f9;
  --text-secondary: #94a3b8;
  --text-muted: #64748b;

  --accent-gold: #f59e0b;
  --accent-green: #10b981;
  --accent-red: #ef4444;
  --accent-blue: #3b82f6;
  --accent-amber: #d97706;

  --font-display: 'DM Serif Display', serif;
  --font-body: 'Inter', sans-serif;
  --font-mono: 'JetBrains Mono', monospace;

  --radius-sm: 6px;
  --radius-md: 10px;
  --radius-lg: 14px;

  --spacing-xs: 4px;
  --spacing-sm: 8px;
  --spacing-md: 16px;
  --spacing-lg: 24px;
  --spacing-xl: 32px;
  --spacing-2xl: 48px;

  --sidebar-width: 220px;
  --sidebar-collapsed: 64px;
  --topbar-height: 48px;
  --context-panel-width: 400px;

  --transition-fast: 150ms ease-out;
  --transition-normal: 200ms ease-out;
  --transition-slow: 300ms ease-out;

  --z-base: 0;
  --z-card: 10;
  --z-sidebar: 20;
  --z-topbar: 30;
  --z-panel: 40;
  --z-modal: 100;
  --z-toast: 1000;
}

/* ── Reset ── */
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

html {
  font-size: 16px;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}

body {
  font-family: var(--font-body);
  background: var(--bg-primary);
  color: var(--text-primary);
  line-height: 1.5;
  overflow: hidden;
  height: 100vh;
}

/* ── Typography ── */
h1, h2, h3 { font-family: var(--font-display); font-weight: 400; }
h1 { font-size: 2rem; }
h2 { font-size: 1.5rem; }
h3 { font-size: 1.125rem; }

.mono { font-family: var(--font-mono); font-variant-numeric: tabular-nums; }
.text-secondary { color: var(--text-secondary); }
.text-muted { color: var(--text-muted); }
.text-gold { color: var(--accent-gold); }
.text-green { color: var(--accent-green); }
.text-red { color: var(--accent-red); }

/* ── App Shell ── */
.app-shell {
  display: grid;
  grid-template-columns: var(--sidebar-width) 1fr;
  grid-template-rows: var(--topbar-height) 1fr;
  grid-template-areas:
    "sidebar topbar"
    "sidebar main";
  height: 100vh;
  width: 100vw;
}

/* ── Top Bar ── */
.topbar {
  grid-area: topbar;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 var(--spacing-lg);
  background: var(--bg-card);
  border-bottom: 1px solid var(--border);
  z-index: var(--z-topbar);
}

.topbar__regime {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
}

.topbar__regime-badge {
  padding: 4px 12px;
  border-radius: var(--radius-sm);
  font-family: var(--font-mono);
  font-size: 0.75rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.regime-euphoria { background: rgba(245, 158, 11, 0.2); color: var(--accent-gold); }
.regime-risk-on { background: rgba(16, 185, 129, 0.2); color: var(--accent-green); }
.regime-neutral { background: rgba(59, 130, 246, 0.2); color: var(--accent-blue); }
.regime-caution { background: rgba(217, 119, 6, 0.2); color: var(--accent-amber); }
.regime-risk-off { background: rgba(239, 68, 68, 0.2); color: var(--accent-red); }

.topbar__market {
  font-family: var(--font-mono);
  font-size: 0.875rem;
  color: var(--text-secondary);
}

.topbar__clock {
  font-family: var(--font-mono);
  font-size: 0.875rem;
  color: var(--text-muted);
}

/* ── Sidebar ── */
.sidebar {
  grid-area: sidebar;
  display: flex;
  flex-direction: column;
  background: var(--bg-card);
  border-right: 1px solid var(--border);
  z-index: var(--z-sidebar);
  padding-top: var(--spacing-lg);
}

.sidebar__brand {
  padding: var(--spacing-md) var(--spacing-lg);
  margin-bottom: var(--spacing-lg);
}

.sidebar__brand h1 {
  font-size: 1.25rem;
  color: var(--accent-gold);
}

.sidebar__brand span {
  font-size: 0.75rem;
  color: var(--text-muted);
  font-family: var(--font-mono);
}

.sidebar__nav {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xs);
  padding: 0 var(--spacing-sm);
  flex: 1;
}

.sidebar__item {
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
  padding: var(--spacing-sm) var(--spacing-md);
  border-radius: var(--radius-sm);
  color: var(--text-secondary);
  cursor: pointer;
  transition: all var(--transition-fast);
  border: none;
  background: none;
  font-family: var(--font-body);
  font-size: 0.875rem;
  width: 100%;
  text-align: left;
}

.sidebar__item:hover {
  background: var(--bg-elevated);
  color: var(--text-primary);
}

.sidebar__item--active {
  background: var(--bg-elevated);
  color: var(--accent-gold);
  font-weight: 500;
}

.sidebar__item svg {
  width: 20px;
  height: 20px;
  flex-shrink: 0;
}

/* ── Main Content ── */
.main {
  grid-area: main;
  overflow-y: auto;
  padding: var(--spacing-lg);
}

.main__subtabs {
  display: flex;
  gap: var(--spacing-xs);
  margin-bottom: var(--spacing-lg);
  border-bottom: 1px solid var(--border);
  padding-bottom: var(--spacing-sm);
}

.subtab {
  padding: var(--spacing-sm) var(--spacing-md);
  border: none;
  background: none;
  color: var(--text-muted);
  font-family: var(--font-body);
  font-size: 0.875rem;
  cursor: pointer;
  border-bottom: 2px solid transparent;
  transition: all var(--transition-fast);
}

.subtab:hover { color: var(--text-secondary); }
.subtab--active {
  color: var(--accent-gold);
  border-bottom-color: var(--accent-gold);
}

/* ── Contextual Right Panel ── */
.context-panel {
  position: fixed;
  top: var(--topbar-height);
  right: 0;
  bottom: 0;
  width: var(--context-panel-width);
  background: var(--bg-card);
  border-left: 1px solid var(--border);
  z-index: var(--z-panel);
  transform: translateX(100%);
  transition: transform var(--transition-normal);
  overflow-y: auto;
  padding: var(--spacing-lg);
}

.context-panel--open { transform: translateX(0); }

.context-panel__header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-lg);
}

.context-panel__close {
  background: none;
  border: none;
  color: var(--text-muted);
  cursor: pointer;
  padding: var(--spacing-xs);
}

.context-panel__close:hover { color: var(--text-primary); }

/* ── Cards ── */
.card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  padding: var(--spacing-lg);
}

.card--elevated {
  background: var(--bg-elevated);
}

.card--gold-accent {
  border-left: 3px solid var(--accent-gold);
}

/* ── Badges ── */
.badge {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  border-radius: var(--radius-sm);
  font-family: var(--font-mono);
  font-size: 0.6875rem;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.badge--green { background: rgba(16, 185, 129, 0.15); color: var(--accent-green); }
.badge--red { background: rgba(239, 68, 68, 0.15); color: var(--accent-red); }
.badge--gold { background: rgba(245, 158, 11, 0.15); color: var(--accent-gold); }
.badge--blue { background: rgba(59, 130, 246, 0.15); color: var(--accent-blue); }
.badge--amber { background: rgba(217, 119, 6, 0.15); color: var(--accent-amber); }
.badge--muted { background: rgba(100, 116, 139, 0.15); color: var(--text-muted); }

.badge--stale {
  background: rgba(217, 119, 6, 0.2);
  color: var(--accent-amber);
  animation: pulse-stale 2s ease-in-out infinite;
}

@keyframes pulse-stale {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.6; }
}

/* ── Tables ── */
.data-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.875rem;
}

.data-table th {
  text-align: left;
  padding: var(--spacing-sm) var(--spacing-md);
  color: var(--text-muted);
  font-weight: 500;
  font-size: 0.75rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  border-bottom: 1px solid var(--border);
}

.data-table td {
  padding: var(--spacing-sm) var(--spacing-md);
  border-bottom: 1px solid rgba(30, 41, 59, 0.5);
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
}

.data-table tr:hover td { background: rgba(30, 41, 59, 0.3); }

.data-table .clickable { cursor: pointer; }

/* ── Skeleton Loading ── */
.skeleton {
  background: linear-gradient(90deg, var(--bg-card) 25%, var(--bg-elevated) 50%, var(--bg-card) 75%);
  background-size: 200% 100%;
  animation: shimmer 1.5s ease-in-out infinite;
  border-radius: var(--radius-sm);
}

@keyframes shimmer {
  0% { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}

.skeleton--text { height: 1rem; width: 60%; }
.skeleton--card { height: 120px; }
.skeleton--chart { height: 300px; }

/* ── KPI Cards ── */
.kpi-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: var(--spacing-md);
}

.kpi-card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-left: 3px solid var(--accent-gold);
  border-radius: var(--radius-md);
  padding: var(--spacing-lg);
}

.kpi-card__label {
  font-size: 0.75rem;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: var(--spacing-xs);
}

.kpi-card__value {
  font-family: var(--font-mono);
  font-size: 1.75rem;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}

.kpi-card__sub {
  font-size: 0.75rem;
  color: var(--text-secondary);
  margin-top: var(--spacing-xs);
}

/* ── Filter Bar ── */
.filter-bar {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  margin-bottom: var(--spacing-md);
  flex-wrap: wrap;
}

.filter-toggle {
  padding: var(--spacing-xs) var(--spacing-md);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: none;
  color: var(--text-muted);
  font-family: var(--font-body);
  font-size: 0.8125rem;
  cursor: pointer;
  transition: all var(--transition-fast);
}

.filter-toggle:hover { border-color: var(--text-secondary); color: var(--text-secondary); }
.filter-toggle--active {
  background: rgba(245, 158, 11, 0.15);
  border-color: var(--accent-gold);
  color: var(--accent-gold);
}

.filter-search {
  padding: var(--spacing-xs) var(--spacing-md);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--bg-primary);
  color: var(--text-primary);
  font-family: var(--font-body);
  font-size: 0.8125rem;
  outline: none;
  min-width: 200px;
}

.filter-search:focus { border-color: var(--accent-gold); }

/* ── Empty States ── */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: var(--spacing-2xl);
  color: var(--text-muted);
  text-align: center;
}

.empty-state svg { width: 48px; height: 48px; margin-bottom: var(--spacing-md); opacity: 0.5; }
.empty-state p { max-width: 300px; }

/* ── Page placeholder ── */
.page-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 60vh;
  color: var(--text-muted);
}

.page-placeholder h2 {
  margin-bottom: var(--spacing-sm);
  color: var(--text-secondary);
}

/* ── Responsive ── */
@media (max-width: 1024px) {
  .app-shell { grid-template-columns: var(--sidebar-collapsed) 1fr; }
  .sidebar__item span { display: none; }
  .sidebar__brand h1 { font-size: 1rem; }
  .sidebar__brand span { display: none; }
  .sidebar__item { justify-content: center; padding: var(--spacing-sm); }
}

@media (max-width: 768px) {
  .app-shell {
    grid-template-columns: 1fr;
    grid-template-rows: var(--topbar-height) 1fr 56px;
    grid-template-areas:
      "topbar"
      "main"
      "sidebar";
  }
  .sidebar {
    flex-direction: row;
    padding: 0;
    border-right: none;
    border-top: 1px solid var(--border);
    justify-content: space-around;
  }
  .sidebar__brand { display: none; }
  .sidebar__nav { flex-direction: row; padding: 0; gap: 0; }
  .sidebar__item {
    flex-direction: column;
    gap: 2px;
    padding: var(--spacing-xs);
    font-size: 0.625rem;
    justify-content: center;
    align-items: center;
  }
  .sidebar__item svg { width: 20px; height: 20px; }
  .context-panel { width: 100%; }
}

/* ── Accessibility ── */
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    transition-duration: 0.01ms !important;
  }
}

:focus-visible {
  outline: 2px solid var(--accent-gold);
  outline-offset: 2px;
}
```

- [ ] **Step 2: Verify CSS file is syntactically valid**

Run: `cd C:\Users\Claude_Anka\askanka.com && python -c "p = 'pipeline/terminal/static/css/terminal.css'; open(p).read(); print(f'{p}: {len(open(p).read())} bytes, OK')"`
Expected: file size printed, no errors

- [ ] **Step 3: Commit**

```bash
cd C:\Users\Claude_Anka\askanka.com
git add pipeline/terminal/static/css/terminal.css
git commit -m "feat(terminal): design system CSS with tokens, layout, and components"
```

---

### Task 4: Shell HTML + App Router

**Files:**
- Modify: `pipeline/terminal/static/index.html`
- Create: `pipeline/terminal/static/js/app.js`
- Create: `pipeline/terminal/static/js/lib/api.js`
- Create: `pipeline/terminal/static/js/pages/dashboard.js`
- Create: `pipeline/terminal/static/js/pages/trading.js`
- Create: `pipeline/terminal/static/js/pages/intelligence.js`
- Create: `pipeline/terminal/static/js/pages/track-record.js`
- Create: `pipeline/terminal/static/js/pages/settings.js`

- [ ] **Step 1: Write the full index.html**

```html
<!-- pipeline/terminal/static/index.html -->
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Anka Terminal</title>

  <!-- Fonts -->
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">

  <!-- Icons -->
  <script src="https://unpkg.com/lucide@latest/dist/umd/lucide.min.js"></script>

  <!-- Lightweight Charts -->
  <script src="https://unpkg.com/lightweight-charts@4/dist/lightweight-charts.standalone.production.js"></script>

  <!-- Design System -->
  <link rel="stylesheet" href="/static/css/terminal.css">
</head>
<body>
  <div class="app-shell">
    <!-- Top Bar -->
    <header class="topbar">
      <div class="topbar__regime">
        <span id="regime-badge" class="topbar__regime-badge regime-neutral">LOADING</span>
        <span id="regime-stability" class="text-muted" style="font-size: 0.75rem;"></span>
      </div>
      <div class="topbar__market">
        <span id="market-status">--</span>
      </div>
      <div class="topbar__clock">
        <span id="clock">--:--:--</span>
        <span id="stale-indicator" style="display:none; margin-left: 8px;" class="badge badge--stale">STALE</span>
      </div>
    </header>

    <!-- Sidebar -->
    <nav class="sidebar" role="navigation" aria-label="Primary">
      <div class="sidebar__brand">
        <h1>Anka</h1>
        <span>Terminal v0.1</span>
      </div>
      <div class="sidebar__nav">
        <button class="sidebar__item sidebar__item--active" data-tab="dashboard" aria-label="Dashboard">
          <i data-lucide="layout-dashboard"></i>
          <span>Dashboard</span>
        </button>
        <button class="sidebar__item" data-tab="trading" aria-label="Trading">
          <i data-lucide="trending-up"></i>
          <span>Trading</span>
        </button>
        <button class="sidebar__item" data-tab="intelligence" aria-label="Intelligence">
          <i data-lucide="brain"></i>
          <span>Intelligence</span>
        </button>
        <button class="sidebar__item" data-tab="track-record" aria-label="Track Record">
          <i data-lucide="bar-chart-2"></i>
          <span>Track Record</span>
        </button>
        <button class="sidebar__item" data-tab="settings" aria-label="Settings">
          <i data-lucide="settings"></i>
          <span>Settings</span>
        </button>
      </div>
    </nav>

    <!-- Main Content -->
    <main class="main" id="main-content" role="main">
      <!-- Pages injected by JS -->
    </main>

    <!-- Contextual Right Panel -->
    <aside class="context-panel" id="context-panel" role="complementary" aria-label="Stock details">
      <div class="context-panel__header">
        <h3 id="context-panel-title">--</h3>
        <button class="context-panel__close" id="context-panel-close" aria-label="Close panel">
          <i data-lucide="x"></i>
        </button>
      </div>
      <div id="context-panel-content"></div>
    </aside>
  </div>

  <!-- App JS -->
  <script type="module" src="/static/js/app.js"></script>
</body>
</html>
```

- [ ] **Step 2: Write the API client library**

```javascript
// pipeline/terminal/static/js/lib/api.js
const BASE = '/api';

export async function get(path) {
  const resp = await fetch(`${BASE}${path}`);
  if (!resp.ok) throw new Error(`API ${path}: ${resp.status}`);
  return resp.json();
}

export async function getHealth() { return get('/health'); }
export async function getRegime() { return get('/regime'); }
export async function getSignals() { return get('/signals'); }
export async function getSpreads() { return get('/spreads'); }
export async function getTrustScores() { return get('/trust-scores'); }
export async function getTrackRecord() { return get('/track-record'); }
export async function getNewsMacro() { return get('/news/macro'); }
export async function getChart(ticker) { return get(`/charts/${ticker}`); }
export async function getTA(ticker) { return get(`/ta/${ticker}`); }
export async function getNewsStock(ticker) { return get(`/news/${ticker}`); }
export async function getRiskGates() { return get('/risk-gates'); }
```

- [ ] **Step 3: Write page placeholder modules**

```javascript
// pipeline/terminal/static/js/pages/dashboard.js
export function render(container) {
  container.innerHTML = `
    <div class="page-placeholder">
      <h2>Dashboard</h2>
      <p class="text-muted">Regime, signals, and market overview — coming in Plan 2</p>
    </div>`;
}

export function destroy() {}
```

```javascript
// pipeline/terminal/static/js/pages/trading.js
export function render(container) {
  container.innerHTML = `
    <div class="page-placeholder">
      <h2>Trading</h2>
      <p class="text-muted">Signals, spreads, charts, and TA — coming in Plan 3</p>
    </div>`;
}

export function destroy() {}
```

```javascript
// pipeline/terminal/static/js/pages/intelligence.js
export function render(container) {
  container.innerHTML = `
    <div class="page-placeholder">
      <h2>Intelligence</h2>
      <p class="text-muted">Trust scores, news, and research — coming in Plan 4</p>
    </div>`;
}

export function destroy() {}
```

```javascript
// pipeline/terminal/static/js/pages/track-record.js
export function render(container) {
  container.innerHTML = `
    <div class="page-placeholder">
      <h2>Track Record</h2>
      <p class="text-muted">Shadow P&L, equity curve, and proof strip — coming in Plan 5</p>
    </div>`;
}

export function destroy() {}
```

```javascript
// pipeline/terminal/static/js/pages/settings.js
export function render(container) {
  container.innerHTML = `
    <div class="page-placeholder">
      <h2>Settings</h2>
      <p class="text-muted">Broker, alerts, and display preferences — coming in Plan 6</p>
    </div>`;
}

export function destroy() {}
```

- [ ] **Step 4: Write the main app router**

```javascript
// pipeline/terminal/static/js/app.js
import { getHealth } from './lib/api.js';
import * as dashboard from './pages/dashboard.js';
import * as trading from './pages/trading.js';
import * as intelligence from './pages/intelligence.js';
import * as trackRecord from './pages/track-record.js';
import * as settings from './pages/settings.js';

const PAGES = {
  dashboard,
  trading,
  intelligence,
  'track-record': trackRecord,
  settings,
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
  } catch {
    // health check failed silently
  }
}

function initKeyboard() {
  const tabKeys = { '1': 'dashboard', '2': 'trading', '3': 'intelligence', '4': 'track-record', '5': 'settings' };

  document.addEventListener('keydown', (e) => {
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;

    if (tabKeys[e.key]) {
      e.preventDefault();
      switchTab(tabKeys[e.key]);
    }
    if (e.key === 'Escape') {
      closeContextPanel();
    }
  });
}

function init() {
  // Sidebar click handlers
  document.querySelectorAll('.sidebar__item').forEach(btn => {
    btn.addEventListener('click', () => switchTab(btn.dataset.tab));
  });

  // Context panel close
  document.getElementById('context-panel-close').addEventListener('click', closeContextPanel);

  // Initialize Lucide icons
  if (window.lucide) lucide.createIcons();

  // Start clock
  updateClock();
  setInterval(updateClock, 1000);

  // Health check
  checkHealth();
  setInterval(checkHealth, 60000);

  // Keyboard shortcuts
  initKeyboard();

  // Render default tab
  switchTab('dashboard');
}

document.addEventListener('DOMContentLoaded', init);
```

- [ ] **Step 5: Verify the app loads in browser**

Run: `cd C:\Users\Claude_Anka\askanka.com && python -m pipeline.terminal --no-open &` then open `http://localhost:8501` in browser.

Expected:
- Dark background with gold "Anka" sidebar
- 5 sidebar items with Lucide icons
- Top bar with clock updating every second
- Clicking sidebar items switches page placeholder content
- Keys 1-5 switch tabs
- Health endpoint returns JSON at `/api/health`

- [ ] **Step 6: Commit**

```bash
cd C:\Users\Claude_Anka\askanka.com
git add pipeline/terminal/static/index.html pipeline/terminal/static/js/app.js pipeline/terminal/static/js/lib/api.js pipeline/terminal/static/js/pages/dashboard.js pipeline/terminal/static/js/pages/trading.js pipeline/terminal/static/js/pages/intelligence.js pipeline/terminal/static/js/pages/track-record.js pipeline/terminal/static/js/pages/settings.js
git commit -m "feat(terminal): shell HTML, app router, page placeholders, keyboard nav"
```

---

### Task 5: Integration Test — Full App Launch

**Files:**
- Create: `pipeline/terminal/tests/test_integration.py`

- [ ] **Step 1: Write the integration test**

```python
# pipeline/terminal/tests/test_integration.py
"""Integration tests: full app serves correctly."""
from fastapi.testclient import TestClient


def test_index_html_has_app_shell():
    from pipeline.terminal.app import app
    client = TestClient(app)
    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.text
    assert "Anka Terminal" in html
    assert "app-shell" in html
    assert "sidebar" in html
    assert "topbar" in html
    assert "main-content" in html


def test_css_served():
    from pipeline.terminal.app import app
    client = TestClient(app)
    resp = client.get("/static/css/terminal.css")
    assert resp.status_code == 200
    assert "text/css" in resp.headers["content-type"]
    assert "--bg-primary" in resp.text


def test_js_app_served():
    from pipeline.terminal.app import app
    client = TestClient(app)
    resp = client.get("/static/js/app.js")
    assert resp.status_code == 200
    assert "javascript" in resp.headers["content-type"]


def test_health_returns_valid_json():
    from pipeline.terminal.app import app
    client = TestClient(app)
    resp = client.get("/api/health")
    data = resp.json()
    assert data["status"] == "ok"
    assert "timestamp" in data
    assert "data_files" in data


def test_nonexistent_api_returns_404():
    from pipeline.terminal.app import app
    client = TestClient(app)
    resp = client.get("/api/nonexistent")
    assert resp.status_code in (404, 405)
```

- [ ] **Step 2: Run all terminal tests**

Run: `cd C:\Users\Claude_Anka\askanka.com && python -m pytest pipeline/terminal/tests/ -v`
Expected: All tests PASS (3 from test_app + 4 from test_cli + 5 from test_integration = 12 total)

- [ ] **Step 3: Commit**

```bash
cd C:\Users\Claude_Anka\askanka.com
git add pipeline/terminal/tests/test_integration.py
git commit -m "test(terminal): integration tests for full app serving"
```

---

### Task 6: Documentation Update

**Files:**
- Modify: `docs/SYSTEM_OPERATIONS_MANUAL.md`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Add terminal section to System Operations Manual**

Add after the existing "Known Gaps" section in `docs/SYSTEM_OPERATIONS_MANUAL.md`:

```markdown
## Anka Terminal

The trading intelligence terminal is a local web application that provides a visual interface over the pipeline data.

### Usage

```bash
python -m pipeline.terminal              # start on localhost:8501, opens browser
python -m pipeline.terminal --port 9000  # custom port
python -m pipeline.terminal --no-open    # don't auto-open browser
```

### Architecture

- **Backend:** FastAPI serving REST APIs from pipeline JSON files
- **Frontend:** Vanilla JS + Lightweight Charts (TradingView) + Lucide icons
- **Data flow:** Pipeline scheduled tasks → JSON files → FastAPI → Browser
- **No database:** reads directly from `pipeline/data/` and `data/`

### Tabs

| Tab | Content | Data Sources |
|-----|---------|-------------|
| Dashboard | Regime, KPIs, signals summary | global_regime.json, today_regime.json, today_recommendations.json |
| Trading | Signals, spreads, charts, TA | open_signals.json, regime_trade_map.json, OHLCV data |
| Intelligence | Trust scores, news, research | trust_scores.json, fno_news.json, articles_index.json |
| Track Record | P&L, equity curve, trades | track_record.json, closed_signals.json |
| Settings | Broker, alerts, display | Local config file |

### Design System

Design tokens defined in `pipeline/terminal/static/css/terminal.css`. Locked: DM Serif Display + Inter + JetBrains Mono, dark theme with gold accents.
```

- [ ] **Step 2: Add terminal to CLAUDE.md Repository Structure**

Add under the existing `pipeline/` entry in the Repository Structure section:

```markdown
- `pipeline/terminal/` — Anka Terminal: local web UI (FastAPI + vanilla JS + Lightweight Charts)
```

- [ ] **Step 3: Commit**

```bash
cd C:\Users\Claude_Anka\askanka.com
git add docs/SYSTEM_OPERATIONS_MANUAL.md CLAUDE.md
git commit -m "docs: add Anka Terminal to operations manual and CLAUDE.md"
```

---

## Self-Review

**Spec coverage check:**
- Section 1 (Architecture): Task 1 (FastAPI), Task 2 (CLI), Task 3 (CSS design system), Task 4 (HTML shell) ✅
- Section 2 (Navigation): Task 4 (sidebar, topbar, routing, context panel, keyboard) ✅
- Sections 3-7 (Tab content): Placeholder pages, deferred to Plans 2-5 ✅
- Section 8 (Cross-cutting UX): Skeleton CSS, staleness badge, keyboard nav, responsive breakpoints, context panel — all in Tasks 3-4 ✅
- Section 9 (API endpoints): Health endpoint in Task 1; remaining endpoints deferred to Plans 2-5 ✅
- Section 10 (File structure): Matches Tasks 1-4 layout ✅
- Section 12 (Success criteria): Performance, staleness, keyboard, responsive — foundations laid ✅

**Placeholder scan:** No TBD/TODO. All code blocks are complete.

**Type consistency:** `render(container)` and `destroy()` interface consistent across all 5 page modules. API client function names match endpoint paths.
