// Renders the expandable inline drawer beneath a candidate row.
// For static_config + dynamic_pair_engine spreads, fetches the 5-layer narration
// (regime gate → scorecard delta → technicals → news → composer) from
// /api/research/digest spread_theses where available; falls back to the basic
// reason field for other sources.
import { get } from '../lib/api.js';

function _esc(s) {
  if (s == null) return '';
  const d = document.createElement('div');
  d.textContent = String(s);
  return d.innerHTML;
}

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
    ? `<div><span class="text-muted">Sizing basis:</span> <span class="mono">${_esc(candidate.sizing_basis)}</span></div>`
    : '';

  const horizonLine = `<div><span class="text-muted">Horizon:</span> <span class="mono">${_esc(candidate.horizon_days)}d (${_esc(candidate.horizon_basis)})</span></div>`;

  let layersHtml = '';
  if (layers) {
    layersHtml = `
      <div style="margin-top: var(--spacing-md);">
        <div class="text-muted" style="font-size: 0.6875rem; margin-bottom: 4px;">5-LAYER NARRATION</div>
        <div class="mono" style="font-size: 0.75rem; line-height: 1.6;">
          <div>1. Regime gate: <strong>${layers.regime_fit ? 'PASS' : 'FAIL'}</strong></div>
          <div>2. Scorecard / Conviction: <strong>${_esc(layers.conviction ?? '--')} (${_esc(layers.score ?? '--')})</strong></div>
          <div>3. Z-score: <strong>${layers.z_score != null ? layers.z_score.toFixed(2) + 'σ' : '--'}</strong></div>
          <div>4. Action: <strong>${_esc(layers.action ?? '--')}</strong></div>
          <div>5. Gate status: <strong>${_esc(layers.gate_status ?? '--')}</strong></div>
        </div>
      </div>`;
  }

  container.innerHTML = `
    <div style="padding: var(--spacing-md); background: var(--bg-elevated); border-left: 3px solid var(--accent-gold);">
      <div style="font-size: 0.875rem; line-height: 1.6;">${_esc(narration)}</div>
      <div style="margin-top: var(--spacing-sm); display: grid; grid-template-columns: repeat(2, 1fr); gap: var(--spacing-xs); font-size: 0.75rem;">
        ${horizonLine}
        ${sizingLine}
        <div><span class="text-muted">Source:</span> <span class="mono">${_esc(candidate.source)}</span></div>
        <div><span class="text-muted">Conviction:</span> <span class="mono">${_esc(candidate.conviction)}</span></div>
      </div>
      ${layersHtml}
    </div>`;
}
