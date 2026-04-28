import { get } from '../lib/api.js';
import { renderLeverageCard, renderShadowStrip } from '../components/leverage-matrix.js';
import { renderPhaseCPairedShadowCard } from '../components/phase-c-paired-shadow.js';
import { renderTabHeader, renderEmptyState } from '../components/tab-header.js';

const HEADER_PROPS = {
  title: 'Options',
  subtitle: 'Synthetic-options drift-vs-rent leverage matrices for active spread signals + Phase C paired-options forward-shadow ledger.',
  cadence: 'Vol data refreshes every intraday cycle (15 min). Phase C paired ledger writes at 09:25 OPEN and 14:30 CLOSE daily.',
};

function _isStale(isoTimestamp) {
  if (!isoTimestamp) return false;
  const h = new Date().toLocaleString('en-US', { timeZone: 'Asia/Kolkata', hour: 'numeric', hour12: false });
  const hours = parseInt(h, 10);
  const inMarket = hours >= 9 && hours < 16;
  if (!inMarket) return false;
  return (Date.now() - new Date(isoTimestamp)) / 60000 > 30;
}

export async function render(container) {
  container.innerHTML = renderTabHeader(HEADER_PROPS) + '<div class="skeleton skeleton--card"></div>';
  try {
    const [digestData, shadows, phaseCPairedData] = await Promise.all([
      get('/research/digest'),
      get('/research/options-shadow').catch(() => []),
      get('/research/phase-c-options-shadow').catch(() => null),
    ]);
    const genTime = digestData.generated_at || '';
    const isStale = _isStale(genTime);
    const matrices = digestData.leverage_matrices || [];
    const matrixCards = matrices.length > 0
      ? matrices.map(m => renderLeverageCard(m)).join('')
      : `<div class="digest-card"><p class="text-muted">No spreads scored 65+ conviction in the latest cycle. The leverage matrix is a derivative — it activates when an underlying spread signal qualifies. After 14:30 IST cutoff or in NEUTRAL regime, qualifying signals are rare.</p></div>`;
    const headerHtml = renderTabHeader({
      ...HEADER_PROPS,
      lastUpdated: genTime || null,
      status: isStale ? 'stale' : (matrices.length === 0 ? 'empty' : 'fresh'),
    });
    container.innerHTML = `
      ${headerHtml}
      <div style="display: flex; flex-direction: column; gap: var(--spacing-md);">
        ${matrixCards}
        ${renderShadowStrip(shadows)}
        ${renderPhaseCPairedShadowCard(phaseCPairedData)}
      </div>`;
  } catch (e) {
    container.innerHTML = renderTabHeader(HEADER_PROPS) + renderEmptyState({
      title: 'Failed to load options intelligence',
      reason: `API error: ${e && e.message ? e.message : String(e)}`,
      nextUpdate: 'Check that the terminal server is running.',
    });
  }
}

export function destroy() {}
