// pipeline/terminal/static/js/components/analysis/panel.js
// Shared renderer. Given an envelope, produce a single analysis card's HTML.
// Responsive: CSS (in terminal.css) decides stacked vs header+2col at ≥480px.

import { bandToCssVar, fmtRelative, isStale } from './health.js';

// Browser-or-node HTML escaping — mirror other components' convention.
function _esc(s) {
  if (s == null) return '';
  if (typeof document !== 'undefined') {
    const d = document.createElement('div');
    d.textContent = String(s);
    return d.innerHTML;
  }
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

function _evidenceBar(ev, maxAbs) {
  const v = Number(ev.contribution) || 0;
  const pct = maxAbs > 0 ? Math.abs(v) / maxAbs * 100 : 0;
  const cls = v >= 0 ? 'analysis-card__bar-pos' : 'analysis-card__bar-neg';
  const sign = v >= 0 ? '+' : '−';
  return `
    <div class="analysis-card__bar-row">
      <span class="analysis-card__bar-label">${sign}${Math.abs(v).toFixed(2)}</span>
      <div class="analysis-card__bar-track"><div class="analysis-card__bar ${cls}" style="width:${pct.toFixed(1)}%"></div></div>
      <span class="analysis-card__bar-name">${_esc(ev.name)}</span>
    </div>`;
}

export function renderCardHtml(env, nowIso) {
  const bandVar = bandToCssVar(env.health.band);
  const convictionCls = env.calibration === 'walk_forward'
    ? 'analysis-card__conviction--walk-forward'
    : 'analysis-card__conviction--heuristic';
  const convictionStyle = env.calibration === 'walk_forward'
    ? 'color: var(--accent-gold);'
    : 'color: var(--text-muted); text-decoration: underline dotted;';
  const convictionTitle = env.calibration === 'heuristic'
    ? 'Not calibrated — heuristic mapping from gate/σ.'
    : '';
  const convictionText = (env.conviction_0_100 == null) ? '—' : String(env.conviction_0_100);

  const evidenceHtml = env.evidence.length
    ? (() => {
        const maxAbs = Math.max(1e-9, ...env.evidence.map(e => Math.abs(Number(e.contribution) || 0)));
        return env.evidence.map(e => _evidenceBar(e, maxAbs)).join('');
      })()
    : '';

  const emptyHtml = (env.verdict === 'UNAVAILABLE' && env.empty_state_reason)
    ? `<div class="analysis-card__empty">${_esc(env.empty_state_reason)}</div>` : '';

  const stale = isStale(env.computed_at, env.engine, nowIso);
  const stalePill = stale ? `<span class="analysis-card__stale" title="Older than 2× expected cadence">●</span>` : '';

  return `
    <div class="analysis-card" data-engine="${_esc(env.engine)}">
      <div class="analysis-card__header">
        <div class="analysis-card__id">
          <span class="analysis-card__engine">${_esc(env.engine.toUpperCase())}</span>
          <span class="analysis-card__ticker">${_esc(env.ticker)}</span>
        </div>
        <div class="analysis-card__verdict">${_esc(env.verdict)}</div>
        <div class="analysis-card__conviction ${convictionCls}" style="${convictionStyle}" title="${_esc(convictionTitle)}">${_esc(convictionText)}</div>
      </div>
      <div class="analysis-card__body">
        ${emptyHtml}
        ${evidenceHtml ? `<div class="analysis-card__evidence">${evidenceHtml}</div>` : ''}
        <div class="analysis-card__health">
          <span class="analysis-card__dot" style="background:${bandVar}"></span>
          <span>${_esc(env.health.band)}</span>
          <span class="analysis-card__health-detail">${_esc(env.health.detail)}</span>
        </div>
      </div>
      <div class="analysis-card__footer">
        <span class="analysis-card__freshness">${_esc(fmtRelative(env.computed_at, nowIso))}${stalePill}</span>
        <span class="analysis-card__source">${_esc(env.source || '')}</span>
      </div>
    </div>`;
}

// Render an ordered array of envelopes (the frozen FCS→TA→Spread→Corr order).
export function renderPanel(container, envelopes, nowIso) {
  if (!container) return;
  const html = (envelopes || []).map(e => renderCardHtml(e, nowIso)).join('');
  container.innerHTML = `<div class="analysis-panel">${html}</div>`;
}
