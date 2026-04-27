import { get } from '../lib/api.js';
import { renderLeverageCard, renderShadowStrip } from '../components/leverage-matrix.js';
import { renderPhaseCPairedShadowCard } from '../components/phase-c-paired-shadow.js';

function _isStale(isoTimestamp) {
  if (!isoTimestamp) return false;
  const h = new Date().toLocaleString('en-US', { timeZone: 'Asia/Kolkata', hour: 'numeric', hour12: false });
  const hours = parseInt(h, 10);
  const inMarket = hours >= 9 && hours < 16;
  if (!inMarket) return false;
  return (Date.now() - new Date(isoTimestamp)) / 60000 > 30;
}

export async function render(container) {
  container.innerHTML = '<div class="skeleton skeleton--card"></div>';
  try {
    const [digestData, shadows, phaseCPairedData] = await Promise.all([
      get('/research/digest'),
      get('/research/options-shadow').catch(() => []),
      get('/research/phase-c-options-shadow').catch(() => null),
    ]);
    const genTime = digestData.generated_at || '';
    const isStale = _isStale(genTime);
    const timeStr = genTime ? new Date(genTime).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata' }) : '--';
    const staleBadge = isStale ? ' <span class="badge badge--stale">STALE</span>' : '';
    const matrices = digestData.leverage_matrices || [];
    const matrixCards = matrices.length > 0
      ? matrices.map(m => renderLeverageCard(m)).join('')
      : '<div class="digest-card"><p class="text-muted">No spreads with 65+ conviction — leverage matrix requires qualifying signals</p></div>';
    container.innerHTML = `
      <div class="digest-header">
        <h2 class="digest-header__title">Synthetic Options — Drift vs Rent</h2>
        <span class="digest-header__time">Vol data: ${timeStr}${staleBadge}</span>
      </div>
      <div style="display: flex; flex-direction: column; gap: var(--spacing-md);">
        ${matrixCards}
        ${renderShadowStrip(shadows)}
        ${renderPhaseCPairedShadowCard(phaseCPairedData)}
      </div>`;
  } catch {
    container.innerHTML = '<div class="empty-state"><p>Failed to load options intelligence</p></div>';
  }
}

export function destroy() {}
