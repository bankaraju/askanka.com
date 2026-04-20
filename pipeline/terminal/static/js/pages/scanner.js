// pipeline/terminal/static/js/pages/scanner.js
// Top-level page consuming signals[] from /api/candidates.
// Read-only event feed: TA fingerprint hits, OI anomalies, correlation breaks.
//
// Deviation from plan: document.getElementById calls replaced with
// container.querySelector (project convention per Task 9 review CRITICAL 4).
// container is captured via closure so loadData/applyFilters can reference it.
import { get } from '../lib/api.js';
import * as filterChips from '../components/filter-chips.js';

let _allSignals = [];
let _refreshTimer = null;
let _container = null;  // closure capture for loadData / applyFilters
let _mounted = false;

function _esc(s) {
  if (s == null) return '';
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

export async function render(container) {
  _mounted = true;
  _container = container;
  container.innerHTML = `
    <div style="margin-bottom: var(--spacing-md);">
      <h2 style="margin-bottom: var(--spacing-xs); font-size: 1.125rem;">Scanner — Events &amp; Anomalies</h2>
      <div class="text-muted" style="font-size: 0.75rem;">Read-only event feed. Look-at-this items, not trades.</div>
    </div>
    <div id="scanner-filters" style="margin-bottom: var(--spacing-md);"></div>
    <div id="scanner-count" class="text-muted" style="font-size: 0.75rem; margin-bottom: var(--spacing-sm);"></div>
    <div id="scanner-feed"></div>`;

  await loadData();
  if (!_mounted) return;
  if (_refreshTimer) clearInterval(_refreshTimer);
  _refreshTimer = setInterval(loadData, 60000);
}

export function destroy() {
  _mounted = false;
  if (_refreshTimer) { clearInterval(_refreshTimer); _refreshTimer = null; }
  _container = null;
}

async function loadData() {
  try {
    const data = await get('/candidates');
    _allSignals = data.signals || [];
    const sources = [...new Set(_allSignals.map(s => s.source))];
    const filterEl = _container?.querySelector('#scanner-filters');
    if (filterEl) {
      filterChips.render(filterEl, {
        groups: [{ key: 'source', label: 'Source', options: sources }],
      }, applyFilters, 'scanner');
    }
    applyFilters(filterChips.getState('scanner'));
  } catch (err) {
    const feedEl = _container?.querySelector('#scanner-feed');
    if (feedEl) {
      feedEl.innerHTML =
        `<div class="empty-state"><p>Failed to load signals: ${err.message}</p></div>`;
    }
  }
}

function applyFilters(state) {
  const filtered = _allSignals.filter(s => {
    if (state.source?.length && !state.source.includes(s.source)) return false;
    return true;
  });
  const countEl = _container?.querySelector('#scanner-count');
  if (countEl) countEl.textContent = `${filtered.length} of ${_allSignals.length} signals`;
  const feedEl = _container?.querySelector('#scanner-feed');
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
