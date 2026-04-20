// pipeline/terminal/static/js/pages/regime.js
// "Where is the market?" surface. Composes from /api/regime + /api/research/digest.
// Sections: ETF zone + score, MSI secondary context, hysteresis state, top drivers,
// eligible spreads (snapshot, full detail lives in Trading), Phase B picks (snapshot).
import { get } from '../lib/api.js';

let _refreshTimer = null;

function _esc(s) {
  if (s == null) return '';
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

export async function render(container) {
  container.innerHTML = '<div class="skeleton skeleton--card"></div>';
  try {
    const [regime, digest, candidates] = await Promise.allSettled([
      get('/regime'), get('/research/digest'), get('/candidates'),
    ]);
    const r = regime.status === 'fulfilled' ? regime.value : {};
    const d = digest.status === 'fulfilled' ? digest.value : {};
    const c = candidates.status === 'fulfilled' ? candidates.value : { tradeable_candidates: [] };

    const driversHtml = (r.top_drivers || []).slice(0, 8).map(drv => `
      <div class="digest-row">
        <span class="digest-row__label">${_esc(drv.symbol || drv.name || '--')}</span>
        <span class="digest-row__value mono ${drv.contribution >= 0 ? 'text-green' : 'text-red'}">${drv.contribution >= 0 ? '+' : ''}${(drv.contribution || 0).toFixed(3)}</span>
      </div>`).join('');

    const phaseBHtml = c.tradeable_candidates
      .filter(x => x.source === 'regime_engine')
      .slice(0, 8)
      .map(p => `<div class="digest-row">
        <span class="digest-row__label">${_esc(p.name)}</span>
        <span class="digest-row__value">${p.conviction} (${p.score})</span>
      </div>`).join('') || '<p class="text-muted" style="font-size: 0.8125rem;">No Phase B picks today</p>';

    const eligibleHtml = c.tradeable_candidates
      .filter(x => x.source === 'static_config')
      .slice(0, 8)
      .map(s => `<div class="digest-row">
        <span class="digest-row__label">${_esc(s.name)}</span>
        <span class="digest-row__value">${s.conviction} (${s.score})</span>
      </div>`).join('') || '<p class="text-muted" style="font-size: 0.8125rem;">No eligible spreads</p>';

    const stableLabel = r.stable ? 'LOCKED' : 'UNSTABLE';
    const stableCls = r.stable ? 'text-green' : 'text-amber';

    container.innerHTML = `
      <h2 style="margin-bottom: var(--spacing-md);">Regime — Where is the market?</h2>
      <div class="digest-grid">
        <div>
          <div class="digest-column-header">ETF Engine (Primary)</div>
          <div class="digest-card">
            <div class="digest-card__title">Zone: <span class="badge badge--gold">${_esc(r.zone || 'UNKNOWN')}</span></div>
            <div class="digest-row"><span class="digest-row__label">Score</span>
              <span class="digest-row__value mono">${r.score != null ? r.score.toFixed(3) : '--'}</span></div>
            <div class="digest-row"><span class="digest-row__label">Source</span>
              <span class="digest-row__value">${_esc(r.regime_source || '--')}</span></div>
            <div class="digest-row"><span class="digest-row__label">Stability</span>
              <span class="digest-row__value ${stableCls}">${stableLabel} (${r.consecutive_days || 0}d)</span></div>
            <div class="digest-row"><span class="digest-row__label">Updated</span>
              <span class="digest-row__value mono">${_esc(r.updated_at || '--')}</span></div>
          </div>
          <div class="digest-card">
            <div class="digest-card__title">Top Drivers</div>
            ${driversHtml || '<p class="text-muted" style="font-size: 0.8125rem;">No driver data</p>'}
          </div>
          <div class="digest-card">
            <div class="digest-card__title">MSI (Secondary Context)</div>
            <div class="digest-row"><span class="digest-row__label">Score</span>
              <span class="digest-row__value mono">${r.msi_score != null ? r.msi_score.toFixed(2) : '--'}</span></div>
            <div class="digest-row"><span class="digest-row__label">Regime</span>
              <span class="digest-row__value">${_esc(r.msi_regime || '--')}</span></div>
          </div>
        </div>
        <div>
          <div class="digest-column-header">Phase A/B/C (Reverse Regime)</div>
          <div class="digest-card">
            <div class="digest-card__title">Phase B: Stock Picks</div>
            <div class="digest-card__subtitle">Today's regime-derived stock recommendations</div>
            ${phaseBHtml}
          </div>
          <div class="digest-card">
            <div class="digest-card__title">Phase C: Correlation Breaks</div>
            <div class="digest-card__subtitle">See Scanner tab for full event feed</div>
            <p class="text-muted" style="font-size: 0.8125rem;">${(d.correlation_breaks || []).length} breaks detected</p>
          </div>
          <div class="digest-card">
            <div class="digest-card__title">Eligible Spreads (snapshot)</div>
            <div class="digest-card__subtitle">Full detail + filters in Trading tab</div>
            ${eligibleHtml}
          </div>
        </div>
      </div>`;

    if (_refreshTimer) clearInterval(_refreshTimer);
    _refreshTimer = setInterval(() => render(container), 60000);
  } catch {
    container.innerHTML = '<div class="empty-state"><p>Failed to load regime data</p></div>';
  }
}

export function destroy() {
  if (_refreshTimer) { clearInterval(_refreshTimer); _refreshTimer = null; }
}
