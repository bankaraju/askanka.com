"""Node-driven behavioral tests for scenario-strip.js.

Covers the regime-flip row replacement (Task FE-1):
- on fetch success: patches the row with worst_drawdown_pct aggregate
- on n_flips==0: shows "n/a" with "(no historical flips)" label
- on fetch error: same "n/a" fallback
- on empty positions: no fetch fires
- zone defaulting: UNKNOWN/missing defaults the query to RISK-OFF
- caches by zone across re-renders so we don't re-spam the endpoint

Runs a Node harness via subprocess because the component is pure ES-module
DOM code and the repo has no JS test framework. Node 22's builtin fetch is
monkey-patched per case.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
COMPONENT = REPO_ROOT / "pipeline/terminal/static/js/components/scenario-strip.js"


def _node() -> str:
    node = shutil.which("node")
    if not node:
        pytest.skip("node not on PATH")
    return node


def _run_harness(body: str) -> dict:
    """Run a Node ESM harness; expects the script to print one JSON line."""
    script = _PRELUDE + "\n" + body
    # Write to a temp .mjs file so node treats it as a module.
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


# Shared harness prelude. Uses a tiny DOM shim + configurable fetch stub.
# The shim uses regex LITERALS (not RegExp constructor) so backslash
# escaping from Python->file->node stays predictable.
_PRELUDE = r"""
import { pathToFileURL } from 'node:url';

globalThis.__fetchCalls = [];
globalThis.__fetchImpl = async (url) => {
  globalThis.__fetchCalls.push(url);
  return { ok: true, json: async () => ({ n_flips: 0, worst_drawdown_pct: null, percentile: 95 }) };
};
globalThis.fetch = (url) => globalThis.__fetchImpl(url);

function extractRow(html, id) {
  // Find the <tr ... id="ID"...> through </tr>.
  const startRe = new RegExp('<tr[^>]*id=["\']' + id + '["\']');
  const m = startRe.exec(html);
  if (!m) return null;
  const start = m.index;
  const endIdx = html.indexOf('</tr>', start);
  if (endIdx === -1) return null;
  return { start, end: endIdx + 5, outer: html.slice(start, endIdx + 5) };
}

function makeContainer() {
  let html = '';
  const el = {
    get innerHTML() { return html; },
    set innerHTML(v) { html = v; },
    querySelector(sel) {
      if (!sel.startsWith('#')) return null;
      const id = sel.slice(1);
      const info = extractRow(html, id);
      if (!info) return null;
      const node = {
        getAttribute(name) {
          const cur = extractRow(html, id);
          if (!cur) return null;
          if (name === 'title') {
            const tm = cur.outer.match(/title=["']([^"']*)["']/);
            return tm ? tm[1] : null;
          }
          if (name.startsWith('data-')) {
            const re = new RegExp(name + '=["\']([^"\']*)["\']');
            const tm = cur.outer.match(re);
            return tm ? tm[1] : null;
          }
          return null;
        },
        setAttribute(name, val) {
          const cur = extractRow(html, id);
          if (!cur) return;
          let newOuter;
          if (name === 'title') {
            if (/title=["'][^"']*["']/.test(cur.outer)) {
              newOuter = cur.outer.replace(/title=["'][^"']*["']/, 'title="' + val + '"');
            } else {
              newOuter = cur.outer.replace(/<tr/, '<tr title="' + val + '"');
            }
          } else {
            return;
          }
          html = html.slice(0, cur.start) + newOuter + html.slice(cur.end);
        },
        querySelectorAll(childSel) {
          if (childSel !== 'td') return [];
          // Parse td cells from current outer.
          const cur = extractRow(html, id);
          const cellRe = /<td([^>]*)>([^<]*(?:<(?!\/td)[^<]*)*)<\/td>/g;
          const cells = [];
          let cm;
          while ((cm = cellRe.exec(cur.outer)) !== null) {
            cells.push({ attrs: cm[1], inner: cm[2], matchStart: cm.index, matchText: cm[0] });
          }
          return cells.map((cell, i) => ({
            get textContent() {
              const fresh = extractRow(html, id);
              const freshCells = [];
              let fm;
              while ((fm = cellRe.exec(fresh.outer)) !== null) {
                freshCells.push(fm[2]);
              }
              cellRe.lastIndex = 0;
              return freshCells[i];
            },
            set textContent(v) {
              const fresh = extractRow(html, id);
              let idx = 0;
              const newOuter = fresh.outer.replace(/<td([^>]*)>([^<]*(?:<(?!\/td)[^<]*)*)<\/td>/g, (hit, attrs) => {
                if (idx++ === i) return '<td' + attrs + '>' + v + '</td>';
                return hit;
              });
              html = html.slice(0, fresh.start) + newOuter + html.slice(fresh.end);
            },
            set className(v) {
              const fresh = extractRow(html, id);
              let idx = 0;
              const newOuter = fresh.outer.replace(/<td([^>]*)>([^<]*(?:<(?!\/td)[^<]*)*)<\/td>/g, (hit, attrs, inner) => {
                if (idx++ === i) {
                  let newAttrs;
                  if (/class=["'][^"']*["']/.test(attrs)) {
                    newAttrs = attrs.replace(/class=["'][^"']*["']/, 'class="' + v + '"');
                  } else {
                    newAttrs = ' class="' + v + '"' + attrs;
                  }
                  return '<td' + newAttrs + '>' + inner + '</td>';
                }
                return hit;
              });
              html = html.slice(0, fresh.start) + newOuter + html.slice(fresh.end);
            },
          }));
        },
      };
      return node;
    },
  };
  return el;
}
globalThis.makeContainer = makeContainer;

const modUrl = pathToFileURL(process.cwd() + '/pipeline/terminal/static/js/components/scenario-strip.js').href;
globalThis.scen = await import(modUrl);
"""


def test_regime_flip_row_has_stable_id():
    result = _run_harness(r"""
const c = makeContainer();
scen.render(c, [{spread_pnl_pct: 0.5}, {spread_pnl_pct: -0.2}], {zone: 'RISK-OFF'});
const node = c.querySelector('#scen-regime-flip');
console.log(JSON.stringify({found: node !== null, html_has_id: c.innerHTML.includes('scen-regime-flip')}));
""")
    assert result["found"], "regime-flip row must have stable id #scen-regime-flip"


def test_fetch_fires_with_zone_and_patches_row_on_success():
    result = _run_harness(r"""
globalThis.__fetchImpl = async (url) => {
  globalThis.__fetchCalls.push(url);
  return { ok: true, json: async () => ({ to_zone: 'RISK-OFF', n_flips: 14, percentile: 95, worst_drawdown_pct: -3.48, median_drawdown_pct: -0.5 }) };
};
const c = makeContainer();
scen.render(c, [{spread_pnl_pct: 0.1}, {spread_pnl_pct: 0.2}, {spread_pnl_pct: 0.3}], {zone: 'RISK-OFF'});
await new Promise(r => setTimeout(r, 30));
const node = c.querySelector('#scen-regime-flip');
const tds = node.querySelectorAll('td');
console.log(JSON.stringify({
  fetched_url: globalThis.__fetchCalls[0] || null,
  label: tds[0].textContent,
  value: tds[1].textContent,
  title: node.getAttribute('title'),
}));
""")
    assert "RISK-OFF" in result["fetched_url"]
    assert "/api/risk/regime-flip" in result["fetched_url"]
    # 3 positions * -3.48 = -10.44
    assert "-10.44" in result["value"], f"expected -10.44% aggregate, got {result['value']}"
    assert "N=14" in result["label"]
    assert "into RISK-OFF" in result["label"]
    assert "p95" in result["title"]
    assert "14 historical flips" in result["title"]


def test_zero_flips_shows_na_and_no_historical_label():
    result = _run_harness(r"""
globalThis.__fetchImpl = async (url) => {
  globalThis.__fetchCalls.push(url);
  return { ok: true, json: async () => ({ to_zone: 'CRISIS', n_flips: 0, percentile: 95, worst_drawdown_pct: null }) };
};
const c = makeContainer();
scen.render(c, [{spread_pnl_pct: 0.1}, {spread_pnl_pct: 0.2}], {zone: 'CRISIS'});
await new Promise(r => setTimeout(r, 30));
const node = c.querySelector('#scen-regime-flip');
const tds = node.querySelectorAll('td');
console.log(JSON.stringify({label: tds[0].textContent, value: tds[1].textContent}));
""")
    assert "n/a" in result["value"]
    assert "no historical flips" in result["label"]


def test_fetch_error_falls_back_to_na_without_breaking_other_rows():
    result = _run_harness(r"""
globalThis.__fetchImpl = async () => { throw new Error('network fail'); };
const c = makeContainer();
scen.render(c, [{spread_pnl_pct: 0.1, peak_pnl: 1.0, daily_stop: -2.0}], {zone: 'RISK-OFF'});
await new Promise(r => setTimeout(r, 30));
const node = c.querySelector('#scen-regime-flip');
const tds = node.querySelectorAll('td');
const html = c.innerHTML;
console.log(JSON.stringify({
  value: tds[1].textContent,
  has_peaks_row: html.includes('If all peaks had locked in'),
  has_trails_row: html.includes('All trails triggered'),
  has_stops_row: html.includes('All daily stops hit'),
}));
""")
    assert "n/a" in result["value"]
    assert result["has_peaks_row"] and result["has_trails_row"] and result["has_stops_row"]


def test_no_fetch_when_positions_empty():
    result = _run_harness(r"""
const c = makeContainer();
scen.render(c, [], {zone: 'RISK-OFF'});
await new Promise(r => setTimeout(r, 10));
console.log(JSON.stringify({calls: globalThis.__fetchCalls.length, html: c.innerHTML}));
""")
    assert result["calls"] == 0
    assert result["html"] == ""


def test_unknown_zone_defaults_to_risk_off_query():
    result = _run_harness(r"""
const c = makeContainer();
scen.render(c, [{spread_pnl_pct: 0.1}], {zone: 'UNKNOWN'});
await new Promise(r => setTimeout(r, 30));
console.log(JSON.stringify({url: globalThis.__fetchCalls[0] || ''}));
""")
    assert "to_zone=RISK-OFF" in result["url"]


def test_cache_prevents_refetch_on_same_zone():
    result = _run_harness(r"""
globalThis.__fetchImpl = async (url) => {
  globalThis.__fetchCalls.push(url);
  return { ok: true, json: async () => ({ n_flips: 3, percentile: 95, worst_drawdown_pct: -1.5 }) };
};
const c = makeContainer();
scen.render(c, [{spread_pnl_pct: 0.1}], {zone: 'RISK-OFF'});
await new Promise(r => setTimeout(r, 30));
const first = globalThis.__fetchCalls.length;
scen.render(c, [{spread_pnl_pct: 0.1}, {spread_pnl_pct: 0.2}], {zone: 'RISK-OFF'});
await new Promise(r => setTimeout(r, 30));
const second = globalThis.__fetchCalls.length;
const node = c.querySelector('#scen-regime-flip');
const tds = node.querySelectorAll('td');
console.log(JSON.stringify({first, second, value: tds[1].textContent}));
""")
    assert result["first"] == 1
    assert result["second"] <= 2
    # 2 positions * -1.5 = -3.00
    assert "-3.00" in result["value"]


def test_syntax_smoke():
    """Minimum guard: node --check must succeed on the component file."""
    proc = subprocess.run(
        [_node(), "--check", str(COMPONENT)],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert proc.returncode == 0, f"syntax error: {proc.stderr}"
