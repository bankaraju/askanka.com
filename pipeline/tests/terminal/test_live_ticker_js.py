"""Node-driven behavioral tests for live-ticker.js (Task FE-2).

The poller scans the DOM every 5s for [data-live-ltp-ticker] cells, fetches
/api/live_ltp?tickers=..., and patches cell textContent + recomputes the
paired P&L cell. Tests cover:

- tick collects unique tickers from [data-live-ltp-ticker] cells
- dedupes tickers (two cells with the same ticker -> one in the request)
- updates cell textContent to Rs N,NNN.NN on successful fetch
- null response for a ticker -> cell unchanged (fallback to snapshot)
- recomputes P&L cell for long side: entry=100, ltp=105 -> +5.00% green
- recomputes P&L cell for short side: entry=100, ltp=95 -> +5.00% green
- fetch error swallowed, console.warn called, no DOM mutation, no throw
- stop() clears interval -> no further ticks fire
- no cells -> no fetch
- entry=0 guard skips P&L recompute
- syntax smoke: node --check live-ticker.js

Runs a Node harness via subprocess because the component is pure ES-module
DOM code and the repo has no JS test framework. The poller's cell lookup
uses only querySelectorAll + dataset + textContent + classList/className,
so the shim is small: a document with an array of cell objects.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
COMPONENT = REPO_ROOT / "pipeline/terminal/static/js/components/live-ticker.js"


def _node() -> str:
    node = shutil.which("node")
    if not node:
        pytest.skip("node not on PATH")
    return node


def _run_harness(body: str) -> dict:
    """Run a Node ESM harness; expects the script to print one JSON line."""
    script = _PRELUDE + "\n" + body
    with tempfile.NamedTemporaryFile(mode="w", suffix=".mjs", delete=False, dir=str(REPO_ROOT)) as f:
        f.write(script)
        temp_path = f.name
    try:
        proc = subprocess.run(
            [_node(), temp_path],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=30,
        )
    finally:
        Path(temp_path).unlink(missing_ok=True)
    if proc.returncode != 0:
        raise AssertionError(
            f"Node harness failed (rc={proc.returncode})\n"
            f"STDOUT:\n{proc.stdout}\n"
            f"STDERR:\n{proc.stderr}"
        )
    for line in reversed(proc.stdout.splitlines()):
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            return json.loads(line)
    raise AssertionError(f"no JSON in harness stdout:\n{proc.stdout}\nSTDERR:\n{proc.stderr}")


# ---------------------------------------------------------------------------
# Prelude: tiny DOM shim + mockable fetch.
#
# We build cells as plain objects with dataset + textContent + className.
# document.querySelectorAll('[data-live-ltp-ticker]') returns all LTP cells.
# document.querySelectorAll('[data-live-pnl-ticker="TICKER"]') returns the
# paired P&L cells. The component only needs these selectors.
#
# fetch is stubbed so we can control the response and count calls.
# console.warn is captured.
# ---------------------------------------------------------------------------
_PRELUDE = r"""
import { pathToFileURL } from 'node:url';

globalThis.__fetchCalls = [];
globalThis.__fetchImpl = async (url) => {
  globalThis.__fetchCalls.push(url);
  return { ok: true, json: async () => ({}) };
};
globalThis.fetch = (url) => globalThis.__fetchImpl(url);

globalThis.__warnCalls = [];
const _origWarn = console.warn;
console.warn = (...args) => { globalThis.__warnCalls.push(args.map(String).join(' ')); };

function makeCell(attrs = {}) {
  const cell = {
    _textContent: attrs.textContent || '',
    _className: attrs.className || '',
    dataset: {},
    _attrs: { ...attrs },
    get textContent() { return this._textContent; },
    set textContent(v) { this._textContent = String(v); },
    get className() { return this._className; },
    set className(v) { this._className = String(v); },
    classList: {
      _cell: null,
      add(...cls) {
        const cur = new Set(this._cell._className.split(/\s+/).filter(Boolean));
        cls.forEach(c => cur.add(c));
        this._cell._className = [...cur].join(' ');
      },
      remove(...cls) {
        const cur = new Set(this._cell._className.split(/\s+/).filter(Boolean));
        cls.forEach(c => cur.delete(c));
        this._cell._className = [...cur].join(' ');
      },
      contains(c) {
        return new Set(this._cell._className.split(/\s+/).filter(Boolean)).has(c);
      },
    },
    getAttribute(name) {
      if (name.startsWith('data-')) {
        const key = name.slice(5).replace(/-([a-z])/g, (_, c) => c.toUpperCase());
        return this.dataset[key] ?? null;
      }
      return this._attrs[name] ?? null;
    },
  };
  cell.classList._cell = cell;
  // Populate dataset from data-* attributes.
  for (const [k, v] of Object.entries(attrs)) {
    if (k.startsWith('data-')) {
      const key = k.slice(5).replace(/-([a-z])/g, (_, c) => c.toUpperCase());
      cell.dataset[key] = v;
    }
  }
  return cell;
}
globalThis.makeCell = makeCell;

globalThis.__cells = [];
globalThis.document = {
  querySelectorAll(sel) {
    // Two selectors we support:
    //   '[data-live-ltp-ticker]'           -> all LTP cells
    //   '[data-live-pnl-ticker="T"]'       -> paired P&L cells for ticker T
    const ltpAll = /^\[data-live-ltp-ticker\]$/;
    const pnlFor = /^\[data-live-pnl-ticker=["']([^"']+)["']\]$/;
    let m;
    if (ltpAll.test(sel)) {
      return globalThis.__cells.filter(c => c.dataset.liveLtpTicker);
    }
    if ((m = pnlFor.exec(sel))) {
      const t = m[1];
      return globalThis.__cells.filter(c => c.dataset.livePnlTicker === t);
    }
    return [];
  },
};

// Fake timer: run the interval body N times synchronously.
globalThis.__timers = [];
globalThis.setInterval = (fn, ms) => {
  const id = globalThis.__timers.length + 1;
  globalThis.__timers.push({ id, fn, ms, active: true });
  return id;
};
globalThis.clearInterval = (id) => {
  const t = globalThis.__timers.find(x => x.id === id);
  if (t) t.active = false;
};
globalThis.__fireAllTimers = async () => {
  for (const t of globalThis.__timers) {
    if (t.active) await t.fn();
  }
};

const modUrl = pathToFileURL(process.cwd() + '/pipeline/terminal/static/js/components/live-ticker.js').href;
globalThis.live = await import(modUrl);
"""


def test_tick_collects_unique_tickers_and_issues_single_request():
    result = _run_harness(r"""
globalThis.__cells = [
  makeCell({'data-live-ltp-ticker': 'HAL', 'data-live-ltp-entry': '100', 'data-live-ltp-side': 'long'}),
  makeCell({'data-live-ltp-ticker': 'BEL', 'data-live-ltp-entry': '100', 'data-live-ltp-side': 'long'}),
];
globalThis.__fetchImpl = async (url) => {
  globalThis.__fetchCalls.push(url);
  return { ok: true, json: async () => ({ HAL: 110.0, BEL: 95.0 }) };
};
const stop = live.startLivePolling(5000);
await new Promise(r => setTimeout(r, 30));
console.log(JSON.stringify({
  calls: globalThis.__fetchCalls.length,
  url: globalThis.__fetchCalls[0] || '',
}));
if (typeof stop === 'function') stop(); else stop.stop();
""")
    assert result["calls"] == 1
    assert "/api/live_ltp?tickers=" in result["url"]
    assert "HAL" in result["url"] and "BEL" in result["url"]


def test_dedupes_tickers_in_request():
    result = _run_harness(r"""
globalThis.__cells = [
  makeCell({'data-live-ltp-ticker': 'HAL', 'data-live-ltp-entry': '100', 'data-live-ltp-side': 'long'}),
  makeCell({'data-live-ltp-ticker': 'HAL', 'data-live-ltp-entry': '100', 'data-live-ltp-side': 'long'}),
  makeCell({'data-live-ltp-ticker': 'BEL', 'data-live-ltp-entry': '100', 'data-live-ltp-side': 'long'}),
];
globalThis.__fetchImpl = async (url) => {
  globalThis.__fetchCalls.push(url);
  return { ok: true, json: async () => ({ HAL: 110.0, BEL: 95.0 }) };
};
const stop = live.startLivePolling(5000);
await new Promise(r => setTimeout(r, 30));
const url = globalThis.__fetchCalls[0] || '';
const tickersQs = url.split('tickers=')[1] || '';
const tickers = decodeURIComponent(tickersQs).split(',');
console.log(JSON.stringify({ tickers }));
if (typeof stop === 'function') stop(); else stop.stop();
""")
    assert sorted(result["tickers"]) == ["BEL", "HAL"]


def test_updates_cell_textcontent_on_success():
    result = _run_harness(r"""
const cell = makeCell({'data-live-ltp-ticker': 'HAL', 'data-live-ltp-entry': '4000', 'data-live-ltp-side': 'long', textContent: 'Rs 4,000.00'});
globalThis.__cells = [cell];
globalThis.__fetchImpl = async () => ({ ok: true, json: async () => ({ HAL: 4284.80 }) });
const stop = live.startLivePolling(5000);
await new Promise(r => setTimeout(r, 30));
console.log(JSON.stringify({ text: cell.textContent }));
if (typeof stop === 'function') stop(); else stop.stop();
""")
    # Rupee symbol or plain "Rs" prefix, then 4,284.80 formatted Indian-style.
    assert "4,284.80" in result["text"], f"expected 4,284.80 in updated cell, got {result['text']!r}"


def test_null_response_leaves_cell_untouched():
    result = _run_harness(r"""
const cell = makeCell({'data-live-ltp-ticker': 'TCS', 'data-live-ltp-entry': '3000', 'data-live-ltp-side': 'long', textContent: 'ORIGINAL'});
globalThis.__cells = [cell];
globalThis.__fetchImpl = async () => ({ ok: true, json: async () => ({ TCS: null }) });
const stop = live.startLivePolling(5000);
await new Promise(r => setTimeout(r, 30));
console.log(JSON.stringify({ text: cell.textContent }));
if (typeof stop === 'function') stop(); else stop.stop();
""")
    assert result["text"] == "ORIGINAL"


def test_recomputes_pnl_long_side_gain():
    result = _run_harness(r"""
const ltp = makeCell({'data-live-ltp-ticker': 'HAL', 'data-live-ltp-entry': '100', 'data-live-ltp-side': 'long', textContent: 'Rs 100.00'});
const pnl = makeCell({'data-live-pnl-ticker': 'HAL', textContent: '+0.00%', className: 'mono text-green'});
globalThis.__cells = [ltp, pnl];
globalThis.__fetchImpl = async () => ({ ok: true, json: async () => ({ HAL: 105.0 }) });
const stop = live.startLivePolling(5000);
await new Promise(r => setTimeout(r, 30));
console.log(JSON.stringify({ text: pnl.textContent, cls: pnl.className }));
if (typeof stop === 'function') stop(); else stop.stop();
""")
    assert result["text"] == "+5.00%"
    assert "text-green" in result["cls"]
    assert "mono" in result["cls"]


def test_recomputes_pnl_short_side_gain():
    result = _run_harness(r"""
const ltp = makeCell({'data-live-ltp-ticker': 'INFY', 'data-live-ltp-entry': '100', 'data-live-ltp-side': 'short', textContent: 'Rs 100.00'});
const pnl = makeCell({'data-live-pnl-ticker': 'INFY', textContent: '+0.00%', className: 'mono text-red'});
globalThis.__cells = [ltp, pnl];
globalThis.__fetchImpl = async () => ({ ok: true, json: async () => ({ INFY: 95.0 }) });
const stop = live.startLivePolling(5000);
await new Promise(r => setTimeout(r, 30));
console.log(JSON.stringify({ text: pnl.textContent, cls: pnl.className }));
if (typeof stop === 'function') stop(); else stop.stop();
""")
    assert result["text"] == "+5.00%"
    assert "text-green" in result["cls"]


def test_recomputes_pnl_long_side_loss():
    result = _run_harness(r"""
const ltp = makeCell({'data-live-ltp-ticker': 'WIPRO', 'data-live-ltp-entry': '200', 'data-live-ltp-side': 'long', textContent: 'Rs 200.00'});
const pnl = makeCell({'data-live-pnl-ticker': 'WIPRO', textContent: '+0.00%', className: 'mono text-green'});
globalThis.__cells = [ltp, pnl];
globalThis.__fetchImpl = async () => ({ ok: true, json: async () => ({ WIPRO: 190.0 }) });
const stop = live.startLivePolling(5000);
await new Promise(r => setTimeout(r, 30));
console.log(JSON.stringify({ text: pnl.textContent, cls: pnl.className }));
if (typeof stop === 'function') stop(); else stop.stop();
""")
    assert result["text"] == "-5.00%"
    assert "text-red" in result["cls"]


def test_fetch_error_swallowed_with_warn_and_no_mutation():
    result = _run_harness(r"""
const cell = makeCell({'data-live-ltp-ticker': 'HAL', 'data-live-ltp-entry': '100', 'data-live-ltp-side': 'long', textContent: 'ORIGINAL'});
globalThis.__cells = [cell];
globalThis.__fetchImpl = async () => { throw new Error('network fail'); };
let threw = false;
try {
  const stop = live.startLivePolling(5000);
  await new Promise(r => setTimeout(r, 30));
  if (typeof stop === 'function') stop(); else stop.stop();
} catch (e) { threw = true; }
console.log(JSON.stringify({
  threw,
  text: cell.textContent,
  warnCount: globalThis.__warnCalls.length,
  warnFirst: globalThis.__warnCalls[0] || '',
}));
""")
    assert not result["threw"]
    assert result["text"] == "ORIGINAL"
    assert result["warnCount"] >= 1
    assert "live-ticker" in result["warnFirst"]


def test_stop_clears_interval_no_further_ticks():
    result = _run_harness(r"""
globalThis.__cells = [
  makeCell({'data-live-ltp-ticker': 'HAL', 'data-live-ltp-entry': '100', 'data-live-ltp-side': 'long'}),
];
globalThis.__fetchImpl = async (url) => {
  globalThis.__fetchCalls.push(url);
  return { ok: true, json: async () => ({ HAL: 110.0 }) };
};
const handle = live.startLivePolling(5000);
await new Promise(r => setTimeout(r, 30));
const afterFirst = globalThis.__fetchCalls.length;
if (typeof handle === 'function') handle(); else handle.stop();
// Force the fake interval body to run; stop() should have marked it inactive.
await globalThis.__fireAllTimers();
const afterStop = globalThis.__fetchCalls.length;
console.log(JSON.stringify({ afterFirst, afterStop }));
""")
    assert result["afterFirst"] == 1
    # After stop(), no further ticks should fire even if we attempt to fire the interval.
    assert result["afterStop"] == 1


def test_no_cells_no_fetch():
    result = _run_harness(r"""
globalThis.__cells = [];
globalThis.__fetchImpl = async () => ({ ok: true, json: async () => ({}) });
const stop = live.startLivePolling(5000);
await new Promise(r => setTimeout(r, 30));
console.log(JSON.stringify({ calls: globalThis.__fetchCalls.length }));
if (typeof stop === 'function') stop(); else stop.stop();
""")
    assert result["calls"] == 0


def test_zero_entry_skips_pnl_recompute():
    result = _run_harness(r"""
const ltp = makeCell({'data-live-ltp-ticker': 'ZERO', 'data-live-ltp-entry': '0', 'data-live-ltp-side': 'long', textContent: 'Rs 0.00'});
const pnl = makeCell({'data-live-pnl-ticker': 'ZERO', textContent: '+1.23%', className: 'mono text-green'});
globalThis.__cells = [ltp, pnl];
globalThis.__fetchImpl = async () => ({ ok: true, json: async () => ({ ZERO: 5.0 }) });
const stop = live.startLivePolling(5000);
await new Promise(r => setTimeout(r, 30));
console.log(JSON.stringify({ text: pnl.textContent, cls: pnl.className }));
if (typeof stop === 'function') stop(); else stop.stop();
""")
    # Entry=0 -> no recompute; P&L cell left as-is.
    assert result["text"] == "+1.23%"


def test_syntax_smoke():
    """Minimum guard: node --check must succeed on the component file."""
    proc = subprocess.run(
        [_node(), "--check", str(COMPONENT)],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert proc.returncode == 0, f"syntax error: {proc.stderr}"
