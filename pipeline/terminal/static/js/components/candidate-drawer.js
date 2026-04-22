// pipeline/terminal/static/js/components/candidate-drawer.js
// Renders the expandable inline drawer beneath a candidate row.
// v1 of Unified Analysis Panel: loops over candidate.analyses_raw, runs each
// through its adapter, renders the shared panel. Replaces the hardcoded
// 5-layer narration block.
import { renderPanel } from './analysis/panel.js';
import { adapt as adaptFcs } from './analysis/adapters/fcs.js';
import { adapt as adaptTa } from './analysis/adapters/ta.js';
import { adapt as adaptSpread } from './analysis/adapters/spread.js';
import { adapt as adaptCorr } from './analysis/adapters/corr.js';

function _esc(s) {
  if (s == null) return '';
  const d = document.createElement('div');
  d.textContent = String(s);
  return d.innerHTML;
}

export async function render(container, candidate) {
  const tkr = String(
    (candidate.long_legs && candidate.long_legs[0]) ||
    (candidate.short_legs && candidate.short_legs[0]) ||
    candidate.ticker || ''
  ).toUpperCase();

  const raw = candidate.analyses_raw || {};
  // Frozen render order: FCS → TA → Spread → Corr Break.
  const envelopes = [
    adaptFcs(tkr, raw.fcs),
    adaptTa(tkr, raw.ta),
    adaptSpread(tkr, raw.spread),
    adaptCorr(tkr, raw.corr),
  ];

  const narration = candidate.reason || '';
  const sizingLine = candidate.sizing_basis
    ? `<div><span class="text-muted">Sizing basis:</span> <span class="mono">${_esc(candidate.sizing_basis)}</span></div>`
    : '';
  const horizonLine = `<div><span class="text-muted">Horizon:</span> <span class="mono">${_esc(candidate.horizon_days)}d (${_esc(candidate.horizon_basis)})</span></div>`;

  const panelMountId = `uap-${Math.random().toString(36).slice(2, 8)}`;

  container.innerHTML = `
    <div style="padding: var(--spacing-md); background: var(--bg-elevated); border-left: 3px solid var(--accent-gold);">
      <div style="font-size: 0.875rem; line-height: 1.6;">${_esc(narration)}</div>
      <div style="margin-top: var(--spacing-sm); display: grid; grid-template-columns: repeat(2, 1fr); gap: var(--spacing-xs); font-size: 0.75rem;">
        ${horizonLine}
        ${sizingLine}
        <div><span class="text-muted">Source:</span> <span class="mono">${_esc(candidate.source)}</span></div>
        <div><span class="text-muted">Conviction:</span> <span class="mono">${_esc(candidate.conviction)}</span></div>
      </div>
      <div id="${panelMountId}" style="margin-top: var(--spacing-md);"></div>
    </div>`;

  const mount = container.querySelector(`#${panelMountId}`);
  if (mount) {
    renderPanel(mount, envelopes, new Date().toISOString());
  }
}
