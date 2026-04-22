# Slippage Stress Grid Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a slippage stress-testing layer into the weekly Sunday Unified Backtest so every strategy and every Phase C label is evaluated at 4 execution-cost regimes (S0/S1/S2/S3) and gets a durable classification (Robust / Execution-Sensitive / Fragile / Not Deployable) surfaced on the Track Record tab.

**Architecture:**
- **Data layer**: parametrize slippage in the existing unified backtester (`pipeline/unified_backtest.py`), persist per-(strategy, label, slippage) metrics
- **Classification layer**: deterministic rules map metric triplet → one of 4 classifications, stored in `data/slippage_resilience.json`
- **UI layer**: Track Record tab gets a "Slippage Resilience" section with per-strategy table + per-label heatmap
- **Risk tie-in**: the item-12 regime-flip scenario (in `2026-04-22-trading-day-cleanup.md`) is revised in Phase D.4 to use S1 metrics (realistic execution), not raw backtest pnls
- **Scheduling**: weekly `AnkaUnifiedBacktest` (Sunday 00:00) runs the grid — ~4× current runtime

**Tech Stack:** Python 3.13, pandas/numpy, pytest, FastAPI, vanilla JS, Windows Task Scheduler

**Prerequisites:**
- Complete `2026-04-22-trading-day-cleanup.md` Phase A + B first (clean test suite, clean terminal data)
- Item 11 (v52–v55 empty ledgers) should be resolved before Phase D.0 — Phase C labels need populated ledgers

---

## Background from backtesting-specs.txt

Four slippage levels, applied as per-side bps haircut/markup on every fill:

| Level | bps/side | Round-trip (incl base) | Label on fail |
|-------|---------:|-----------------------:|---------------|
| S0    | 5        | 10 bps                 | Not Deployable |
| S1    | 15       | 30 bps                 | Fragile |
| S2    | 25       | 50 bps                 | Execution-Sensitive |
| S3    | 35       | 70 bps                 | (informational, no hard bar) |

Pass criteria per level:
- **S0**: Sharpe ≥ 1.0, Hit ≥ 55%, MaxDD ≤ 20%, edge present (Sharpe ≥ 0.5) in ≥3/4 regimes, p ≤ 0.05 Bonferroni
- **S1**: Sharpe ≥ 0.8, MaxDD ≤ 25%, edge in ≥2/4 regimes, positive cumulative P&L
- **S2**: Sharpe > 0.5, MaxDD ≤ 30%, positive cumulative P&L

Classification:
- Fails S0 → **Not Deployable** (strategy dead)
- Passes S0, fails S1 → **Fragile** (research only, low cap)
- Passes S1, fails S2 → **Execution-Sensitive** (liquid contexts only, conservative size)
- Passes S2 → **Robust** (standard sizing)

---

## File Map

**Modified:**
- `pipeline/unified_backtest.py` — add `--slippage-bps` CLI arg, grid driver
- `pipeline/scripts/unified_backtest.bat` — run 4 times instead of once
- `pipeline/config/anka_inventory.json` — update AnkaUnifiedBacktest outputs + grace_multiplier
- `pipeline/terminal/static/js/pages/track-record.js` — new "Slippage Resilience" section
- `pipeline/terminal/app.py` — mount resilience router
- `pipeline/risk_guardrails.py` — add classification-based sizing caps (optional Phase D.5)
- `docs/SYSTEM_OPERATIONS_MANUAL.md` — new Sunday batch behavior + UI section

**Created:**
- `pipeline/slippage_grid.py` — orchestrates the 4-level run
- `pipeline/backtest_classifier.py` — pass/fail rules + classification
- `pipeline/terminal/api/resilience.py` — serves `/api/resilience/strategies`, `/api/resilience/labels`
- `pipeline/terminal/static/css/resilience.css` — heatmap styling
- `data/slippage_resilience.json` — output file (gitignored if large)
- `pipeline/tests/test_slippage_grid.py`
- `pipeline/tests/test_backtest_classifier.py`
- `pipeline/tests/test_resilience_api.py`

---

## Phase D.0 — Parametrize Slippage in Fill Simulator

### Task D0.1: Add slippage parameter to fill simulator

**Files:**
- Read: `pipeline/unified_backtest.py` — find the fill simulator (likely `_simulate_trade` or similar)
- Modify: add `slippage_bps` kwarg, default 0.0005 (5 bps = S0)

- [ ] **Step 1: Locate the fill function**

```bash
grep -n "def.*simulate\|def.*fill\|fill_price\|def backtest" pipeline/unified_backtest.py | head -10
```

- [ ] **Step 2: Write the failing test**

```python
# pipeline/tests/test_slippage_grid.py
from pipeline.unified_backtest import simulate_fill

def test_buy_fill_applies_positive_slippage():
    # Mid price 100, slippage 10 bps (0.001) → fill at 100.10
    result = simulate_fill(mid_price=100.0, side="buy", slippage_bps=0.0010)
    assert result == 100.10

def test_sell_fill_applies_negative_slippage():
    result = simulate_fill(mid_price=100.0, side="sell", slippage_bps=0.0010)
    assert result == 99.90

def test_zero_slippage_returns_mid():
    assert simulate_fill(mid_price=50.0, side="buy", slippage_bps=0.0) == 50.0

def test_default_slippage_is_s0_5bps():
    # Default should be S0 level: 5 bps
    assert simulate_fill(mid_price=100.0, side="buy") == 100.05
```

- [ ] **Step 3: Expect fail (function may not exist or lacks parameter)**

- [ ] **Step 4: Implement**

```python
# pipeline/unified_backtest.py — extract or refactor the fill logic
def simulate_fill(mid_price: float, side: str, slippage_bps: float = 0.0005) -> float:
    """Apply per-side slippage to a fill price.

    slippage_bps is a decimal fraction (0.0005 = 5 bps per side).
    Buys haircut up, sells haircut down.
    """
    if side == "buy":
        return round(mid_price * (1 + slippage_bps), 2)
    elif side == "sell":
        return round(mid_price * (1 - slippage_bps), 2)
    raise ValueError(f"side must be 'buy' or 'sell', got {side}")
```

Wire it into existing fill code path so the rest of the backtest uses it.

- [ ] **Step 5: Tests pass**

- [ ] **Step 6: Commit**

```bash
git add pipeline/unified_backtest.py pipeline/tests/test_slippage_grid.py
git commit -m "feat(backtest): parametrize slippage in fill simulator

simulate_fill(mid, side, slippage_bps) — per-side bps haircut/markup
Default 0.0005 (S0 level). Downstream grid driver varies this 4 levels."
```

ETA: 30 min.

---

## Phase D.1 — Grid Driver + Metrics Persistence

### Task D1.1: Run backtest at 4 slippage levels and persist metrics

**Files:**
- Create: `pipeline/slippage_grid.py`
- Modify: `pipeline/unified_backtest.py` — expose `run_backtest(slippage_bps=...)` programmatic entry

- [ ] **Step 1: Write the failing test**

```python
# pipeline/tests/test_slippage_grid.py — extend
from pipeline.slippage_grid import run_grid, SLIPPAGE_LEVELS

def test_levels_are_s0_s1_s2_s3():
    assert SLIPPAGE_LEVELS == {"S0": 0.0005, "S1": 0.0015, "S2": 0.0025, "S3": 0.0035}

def test_grid_runs_all_four_levels(monkeypatch, tmp_path):
    out = tmp_path / "resilience.json"
    # Stub run_backtest to return a synthetic result
    called = []
    def fake_run(slippage_bps):
        called.append(slippage_bps)
        return {"strategies": {"OPPORTUNITY": {"sharpe": 2.0 - slippage_bps*1000,
                                                "max_dd_pct": 5 + slippage_bps*1000,
                                                "hit_rate": 0.6, "net_pnl_pct": 10.0,
                                                "trade_count": 500}}}
    monkeypatch.setattr("pipeline.slippage_grid.run_backtest", fake_run)
    run_grid(output_path=out)
    import json
    d = json.loads(out.read_text())
    assert set(d["levels"].keys()) == {"S0", "S1", "S2", "S3"}
    assert called == [0.0005, 0.0015, 0.0025, 0.0035]
```

- [ ] **Step 2: Expect fail — module doesn't exist**

- [ ] **Step 3: Implement**

```python
# pipeline/slippage_grid.py
import json
from pathlib import Path
from datetime import datetime, timezone, timedelta
from pipeline.unified_backtest import run_backtest

IST = timezone(timedelta(hours=5, minutes=30))
SLIPPAGE_LEVELS = {"S0": 0.0005, "S1": 0.0015, "S2": 0.0025, "S3": 0.0035}
OUTPUT_PATH = Path(__file__).parent.parent / "data" / "slippage_resilience.json"

def run_grid(output_path: Path = OUTPUT_PATH) -> dict:
    """Run backtest at all 4 slippage levels and persist metrics."""
    result = {"run_at": datetime.now(IST).isoformat(), "levels": {}}
    for name, bps in SLIPPAGE_LEVELS.items():
        metrics = run_backtest(slippage_bps=bps)
        result["levels"][name] = metrics
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2, ensure_ascii=False),
                            encoding="utf-8")
    return result

if __name__ == "__main__":
    run_grid()
```

- [ ] **Step 4: Tests pass**

- [ ] **Step 5: Add metrics per Phase C label to run_backtest output**

Extend `run_backtest` (or its result assembler) to also compute per-label blocks:

```python
{
  "strategies": {"OPPORTUNITY": {...}, "POSSIBLE_OPPORTUNITY": {...}},
  "labels": {
    "OPPORTUNITY": {"mean_next_bar_return": 0.12, "hit_rate": 0.61, "sharpe": 1.8, "pnl_contribution_pct": 45.0},
    "POSSIBLE_OPPORTUNITY": {...},
    "WARNING": {...}, "CONFIRMED_WARNING": {...}, "UNCERTAIN": {...}
  },
  "portfolio": {"sharpe": ..., "max_dd_pct": ..., "cagr_pct": ...}
}
```

- [ ] **Step 6: Test the metric assembler with fixture**

```python
def test_per_label_metrics_included(fake_trades):
    result = run_backtest(slippage_bps=0.0005, trades=fake_trades)
    assert "labels" in result
    assert "OPPORTUNITY" in result["labels"]
    assert result["labels"]["OPPORTUNITY"]["hit_rate"] >= 0
```

- [ ] **Step 7: Commit**

```bash
git add pipeline/slippage_grid.py pipeline/unified_backtest.py pipeline/tests/test_slippage_grid.py
git commit -m "feat(backtest): slippage stress grid runs S0-S3 and persists per-label metrics

Sunday batch now produces slippage_resilience.json with per-strategy,
per-Phase-C-label Sharpe/MaxDD/Hit/PnL at each of 4 cost regimes."
```

ETA: 90 min.

---

## Phase D.2 — Pass/Fail Classification

### Task D2.1: Deterministic classification from metric triplet

**Files:**
- Create: `pipeline/backtest_classifier.py`
- Create: `pipeline/tests/test_backtest_classifier.py`

- [ ] **Step 1: Write the failing tests (all 4 classifications)**

```python
# pipeline/tests/test_backtest_classifier.py
from pipeline.backtest_classifier import classify

def _levels(s0, s1, s2):
    """Build a levels dict from triplet of (sharpe, max_dd_pct, hit_rate, net_pnl_pct)."""
    def block(s, d, h, p):
        return {"sharpe": s, "max_dd_pct": d, "hit_rate": h, "net_pnl_pct": p}
    return {"S0": block(*s0), "S1": block(*s1), "S2": block(*s2)}

def test_robust_passes_all_bars():
    levels = _levels((1.5, 15, 0.60, 30),  # S0: pass
                     (1.0, 20, 0.58, 22),   # S1: pass
                     (0.7, 25, 0.55, 15))   # S2: pass
    assert classify(levels) == "Robust"

def test_execution_sensitive_passes_s1_fails_s2():
    levels = _levels((1.5, 15, 0.60, 30),
                     (1.0, 20, 0.58, 22),
                     (0.3, 35, 0.50, 2))    # S2: sharpe fails
    assert classify(levels) == "Execution-Sensitive"

def test_fragile_passes_s0_fails_s1():
    levels = _levels((1.5, 15, 0.60, 30),
                     (0.6, 20, 0.55, 5),    # S1: sharpe < 0.8 fails
                     (0.3, 35, 0.50, -5))
    assert classify(levels) == "Fragile"

def test_not_deployable_fails_s0():
    levels = _levels((0.5, 25, 0.50, -5),   # S0: sharpe < 1.0 fails
                     (0.3, 30, 0.45, -10),
                     (0.1, 35, 0.40, -15))
    assert classify(levels) == "Not Deployable"
```

- [ ] **Step 2: Tests fail (module missing)**

- [ ] **Step 3: Implement**

```python
# pipeline/backtest_classifier.py

def _pass_s0(block: dict) -> bool:
    return (block["sharpe"] >= 1.0
            and block["max_dd_pct"] <= 20
            and block["hit_rate"] >= 0.55)

def _pass_s1(block: dict) -> bool:
    return (block["sharpe"] >= 0.8
            and block["max_dd_pct"] <= 25
            and block["net_pnl_pct"] > 0)

def _pass_s2(block: dict) -> bool:
    return (block["sharpe"] > 0.5
            and block["max_dd_pct"] <= 30
            and block["net_pnl_pct"] > 0)

def classify(levels: dict) -> str:
    """Map per-level metrics to a single classification.

    levels["S0"|"S1"|"S2"] each have keys: sharpe, max_dd_pct, hit_rate, net_pnl_pct.
    """
    s0, s1, s2 = levels["S0"], levels["S1"], levels["S2"]
    if not _pass_s0(s0):
        return "Not Deployable"
    if not _pass_s1(s1):
        return "Fragile"
    if not _pass_s2(s2):
        return "Execution-Sensitive"
    return "Robust"
```

- [ ] **Step 4: All tests pass**

- [ ] **Step 5: Wire into `run_grid` so output carries classifications**

```python
# pipeline/slippage_grid.py — add after level loop
from pipeline.backtest_classifier import classify
for strat_name in result["levels"]["S0"]["strategies"]:
    strat_levels = {lvl: result["levels"][lvl]["strategies"][strat_name]
                    for lvl in ("S0","S1","S2")}
    result.setdefault("classifications", {})[strat_name] = classify(strat_levels)
```

- [ ] **Step 6: Commit**

```bash
git add pipeline/backtest_classifier.py pipeline/slippage_grid.py pipeline/tests/test_backtest_classifier.py
git commit -m "feat(backtest): classify strategies Robust/Fragile/ExecSensitive/NotDeployable

Rules per backtesting-specs.txt §3 — S0 (base) is the hard bar, S1/S2
are degradation thresholds. Classification persists to slippage_resilience.json."
```

ETA: 45 min.

---

## Phase D.3 — UI: Slippage Resilience Section

### Task D3.1: Backend endpoint

**Files:**
- Create: `pipeline/terminal/api/resilience.py`
- Modify: `pipeline/terminal/app.py`
- Create: `pipeline/tests/test_resilience_api.py`

- [ ] **Step 1: Write endpoint test**

```python
# pipeline/tests/test_resilience_api.py
from fastapi.testclient import TestClient
from pipeline.terminal.app import app

def test_strategies_endpoint_returns_classification(monkeypatch, tmp_path):
    fake = tmp_path / "resilience.json"
    fake.write_text('''{"levels":{"S0":{"strategies":{"OPPORTUNITY":{"sharpe":1.5,"max_dd_pct":15,"hit_rate":0.6,"net_pnl_pct":30}}}},
                        "classifications":{"OPPORTUNITY":"Robust"}}''')
    monkeypatch.setattr("pipeline.terminal.api.resilience.RESILIENCE_FILE", fake)
    client = TestClient(app)
    r = client.get("/api/resilience/strategies")
    assert r.status_code == 200
    data = r.json()
    assert data["OPPORTUNITY"]["classification"] == "Robust"
```

- [ ] **Step 2: Implement**

```python
# pipeline/terminal/api/resilience.py
import json
from pathlib import Path
from fastapi import APIRouter, HTTPException

router = APIRouter()
RESILIENCE_FILE = Path(__file__).parent.parent.parent.parent / "data" / "slippage_resilience.json"

@router.get("/api/resilience/strategies")
def strategies():
    if not RESILIENCE_FILE.exists():
        raise HTTPException(503, "resilience report not generated yet")
    data = json.loads(RESILIENCE_FILE.read_text(encoding="utf-8"))
    out = {}
    classifications = data.get("classifications", {})
    for strat in data["levels"]["S0"]["strategies"]:
        out[strat] = {
            "classification": classifications.get(strat, "Unknown"),
            "S0": data["levels"]["S0"]["strategies"][strat],
            "S1": data["levels"]["S1"]["strategies"][strat],
            "S2": data["levels"]["S2"]["strategies"][strat],
            "S3": data["levels"].get("S3", {}).get("strategies", {}).get(strat),
        }
    return out

@router.get("/api/resilience/labels")
def labels():
    if not RESILIENCE_FILE.exists():
        raise HTTPException(503, "resilience report not generated yet")
    data = json.loads(RESILIENCE_FILE.read_text(encoding="utf-8"))
    out = {}
    for label in data["levels"]["S0"].get("labels", {}):
        out[label] = {
            "S0": data["levels"]["S0"]["labels"][label],
            "S2": data["levels"]["S2"]["labels"][label],
        }
    return out
```

- [ ] **Step 3: Mount + test**

```python
# pipeline/terminal/app.py
from pipeline.terminal.api import resilience as resilience_api
app.include_router(resilience_api.router)
```

- [ ] **Step 4: Tests pass**

- [ ] **Step 5: Commit**

```bash
git add pipeline/terminal/api/resilience.py pipeline/terminal/app.py pipeline/tests/test_resilience_api.py
git commit -m "feat(terminal): /api/resilience endpoints serve classification + per-level metrics"
```

ETA: 30 min.

---

### Task D3.2: Frontend "Slippage Resilience" section on Track Record tab

**Files:**
- Modify: `pipeline/terminal/static/js/pages/track-record.js`
- Create: `pipeline/terminal/static/css/resilience.css`
- Modify: `pipeline/terminal/static/index.html` — inject new CSS

- [ ] **Step 1: Add section to track-record.js**

```javascript
// pipeline/terminal/static/js/pages/track-record.js — append to renderTrackRecord
async function renderResilience() {
  const container = document.querySelector('.resilience-section');
  try {
    const data = await fetch('/api/resilience/strategies').then(r => {
      if (!r.ok) throw new Error('not ready');
      return r.json();
    });
    let html = '<h3>Slippage Resilience</h3><table class="resilience-table">';
    html += '<thead><tr><th>Strategy</th><th>Class</th><th>S0 Sharpe</th><th>S0 DD</th><th>S1 Sharpe</th><th>S1 DD</th><th>S2 Sharpe</th><th>S2 DD</th></tr></thead><tbody>';
    for (const [strat, d] of Object.entries(data)) {
      const klass = d.classification.toLowerCase().replace(/\s/g, '-');
      html += `<tr class="class-${klass}"><td>${strat}</td><td class="badge">${d.classification}</td>
        <td>${d.S0.sharpe.toFixed(2)}</td><td>${d.S0.max_dd_pct.toFixed(1)}%</td>
        <td>${d.S1.sharpe.toFixed(2)}</td><td>${d.S1.max_dd_pct.toFixed(1)}%</td>
        <td>${d.S2.sharpe.toFixed(2)}</td><td>${d.S2.max_dd_pct.toFixed(1)}%</td></tr>`;
    }
    html += '</tbody></table>';
    container.innerHTML = html;
  } catch (e) {
    container.innerHTML = '<p class="text-muted">Slippage resilience report not yet generated. Next Sunday 00:00 IST.</p>';
  }
}
```

- [ ] **Step 2: Add CSS**

```css
/* pipeline/terminal/static/css/resilience.css */
.resilience-table { width: 100%; border-collapse: collapse; margin-top: 12px; }
.resilience-table th, .resilience-table td { padding: 8px 12px; text-align: left; border-bottom: 1px solid #333; }
.resilience-table .badge { padding: 2px 8px; border-radius: 4px; font-size: 12px; }
.class-robust .badge             { background: #18331f; color: #69db7c; }
.class-execution-sensitive .badge{ background: #3a2a18; color: #ffa94d; }
.class-fragile .badge            { background: #3a1818; color: #ff6b6b; }
.class-not-deployable .badge     { background: #222; color: #888; }
```

- [ ] **Step 3: Verify in browser**

- [ ] **Step 4: Commit**

```bash
git add pipeline/terminal/static/js/pages/track-record.js pipeline/terminal/static/css/resilience.css pipeline/terminal/static/index.html
git commit -m "feat(terminal): Track Record tab surfaces Slippage Resilience classification"
```

ETA: 45 min.

---

## Phase D.4 — Revise Risk Page to Use S1 Metrics

Previously in `2026-04-22-trading-day-cleanup.md` Phase B.5, the regime-flip scenario used raw backtest pnls. Now that we have S1 metrics (realistic execution), the Risk page should reference them instead.

- [ ] **Step 1: Update `compute_flip_drawdown_ci` to accept slippage_bps param**

```python
# pipeline/autoresearch/regime_flip_analyzer.py
def compute_flip_drawdown_ci(backtest_path, from_zone, to_zone, percentile=95,
                              slippage_bps: float = 0.0015):
    # Apply S1 haircut to flip-day pnls before computing percentile
    ...
```

- [ ] **Step 2: Update API to default to S1**

- [ ] **Step 3: Frontend tooltip reads "p95 of N=k flips at S1 slippage (+15 bps/side)"**

- [ ] **Step 4: Commit**

ETA: 30 min.

---

## Phase D.5 — Wire into Sunday Cron

### Task D5.1: Update scheduled task + inventory

- [ ] **Step 1: Modify `pipeline/scripts/unified_backtest.bat`**

Change from single run to grid driver:
```batch
@echo off
cd /d C:\Users\Claude_Anka\askanka.com
python -m pipeline.slippage_grid >> pipeline\logs\unified_backtest.log 2>&1
```

- [ ] **Step 2: Update `pipeline/config/anka_inventory.json`**

```json
{
  "task_name": "AnkaUnifiedBacktest",
  "tier": "critical",
  "cadence_class": "weekly",
  "outputs": ["data/slippage_resilience.json"],
  "grace_multiplier": 1.5,
  "notes": "Sunday 00:00 IST. Runs 4-level slippage grid (S0-S3) and classifies all strategies."
}
```

- [ ] **Step 3: Verify watchdog recognizes new output path**

```bash
python -m pipeline.watchdog
```

- [ ] **Step 4: Commit**

```bash
git add pipeline/scripts/unified_backtest.bat pipeline/config/anka_inventory.json
git commit -m "ops: Sunday AnkaUnifiedBacktest now runs slippage grid + persists resilience.json"
```

ETA: 20 min.

---

## Phase D.6 — Optional: Classification-Based Sizing Caps

The spec hints at this but doesn't mandate it. If time permits:

- Not Deployable → 0% capital (hard stop)
- Fragile → 25% of standard cap
- Execution-Sensitive → 50% of standard cap
- Robust → 100%

- [ ] Wire into `pipeline/risk_guardrails.py` check path
- [ ] Add test
- [ ] Commit

ETA: 45 min (deferrable).

---

## Total ETA

- D.0 (parametrize): 30min
- D.1 (grid + metrics): 90min
- D.2 (classifier): 45min
- D.3 (UI endpoints + section): 75min
- D.4 (risk page revise): 30min
- D.5 (cron wire-up): 20min
- D.6 (sizing caps, optional): 45min

**~5 hours end-to-end**, spread across 2 work sessions. Safe to execute mid-week; no market-hours urgency. First real output lands at next Sunday's `AnkaUnifiedBacktest` run.

---

## Validation Checklist

Before declaring done:

- [ ] `python -m pytest pipeline/tests/test_slippage_grid.py pipeline/tests/test_backtest_classifier.py pipeline/tests/test_resilience_api.py -v` → all green
- [ ] Run `python -m pipeline.slippage_grid` once manually → `data/slippage_resilience.json` exists and has all 4 levels + classifications
- [ ] Open terminal Track Record tab → Slippage Resilience section renders
- [ ] `python -m pipeline.watchdog` → no ORPHAN_TASK or missing-output alerts for AnkaUnifiedBacktest
- [ ] `docs/SYSTEM_OPERATIONS_MANUAL.md` has the new Sunday batch section
- [ ] `memory/project_slippage_stress_grid.md` created
