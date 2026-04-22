// Feature Contribution panel — renders top-3 features as horizontal bars.
// Used by candidate-drawer.js to surface model detail when a candidate row
// is expanded on the Trading tab.
//
// Deviation from plan (Task 15, docs/superpowers/plans/2026-04-22-feature-coincidence-scorer.md):
//   - No pages/ta.js exists; drawer on the Trading tab is the actual integration point.
//   - Reuses `candidate.attractiveness` pre-attached by trading.js (Task 13) when
//     present; falls back to GET /attractiveness/{ticker} otherwise.
import { get } from '../lib/api.js';

function _esc(s) {
  if (s == null) return '';
  const d = (typeof document !== 'undefined') ? document.createElement('div') : null;
  if (d) {
    d.textContent = String(s);
    return d.innerHTML;
  }
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function _fmtTime(iso) {
  if (!iso) return '—';
  try {
    const d = new Date(iso);
    if (isNaN(d.getTime())) return '—';
    return d.toLocaleTimeString();
  } catch {
    return '—';
  }
}

// Renders the Feature Contributions panel into `container` for a given ticker.
// If `row` is provided (e.g. candidate.attractiveness), renders from it directly;
// otherwise fetches /attractiveness/{ticker}. On missing/empty data, renders an
// empty-state block instead of erroring out.
export async function renderPanel(container, ticker, row) {
  if (!container) return;
  if (!ticker) { container.innerHTML = ''; return; }

  let data = row;
  if (!data) {
    try {
      data = await get(`/attractiveness/${encodeURIComponent(ticker)}`);
    } catch {
      container.innerHTML = '<div class="attract-panel attract-panel--empty">No model available for this ticker.</div>';
      return;
    }
  }

  const top = Array.isArray(data && data.top_features) ? data.top_features.slice(0, 3) : [];
  if (top.length === 0) {
    container.innerHTML = '<div class="attract-panel attract-panel--empty">No feature contributions for this ticker.</div>';
    return;
  }

  const max = Math.max(1e-9, ...top.map(f => Math.abs(Number(f.contribution) || 0)));
  const bars = top.map(f => {
    const v = Number(f.contribution) || 0;
    const pct = Math.abs(v) / max * 100;
    const sign = v >= 0 ? '+' : '−';
    const cls = v >= 0 ? 'bar-pos' : 'bar-neg';
    return `
      <div class="feature-bar-row">
        <span class="feature-bar-label">${sign}${Math.abs(v).toFixed(2)}</span>
        <div class="feature-bar-track"><div class="feature-bar ${cls}" style="width:${pct.toFixed(1)}%"></div></div>
        <span class="feature-name">${_esc(f.name)}</span>
      </div>`;
  }).join('');

  container.innerHTML = `
    <div class="attract-panel">
      <div class="panel-head">
        <strong>Feature Contributions — ${_esc(ticker)}</strong>
        <span class="updated">updated ${_esc(_fmtTime(data.computed_at))}</span>
      </div>
      <div class="bars">${bars}</div>
      <div class="health">Model health: ${_esc(data.band || '—')} (${_esc(data.source || '—')})</div>
    </div>`;
}
