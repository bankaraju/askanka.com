// pipeline/terminal/static/js/pages/risk.js
// Risk gates dashboard: current level (L0/L1/L2), sizing factor, cumulative P&L,
// trades in window, breach thresholds. Read-only.
import { get } from '../lib/api.js';
import { renderTabHeader, renderEmptyState } from '../components/tab-header.js';

const HEADER_PROPS = {
  title: 'Risk',
  subtitle: 'Capital-preservation gate state (L0 normal / L1 50% sizing / L2 halted) + sizing factor + cumulative P&L over 20-day window vs L1/L2 breach thresholds.',
  cadence: 'Re-evaluated every intraday cycle (15 min) and on each closed trade. In-page polling 60s.',
};

let _refreshTimer = null;
let _inflight = false;

function _esc(s) {
  if (s == null) return '';
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

export async function render(container) {
  if (_inflight) return;
  _inflight = true;
  if (!container.hasChildNodes()) {
    container.innerHTML = '<div class="skeleton skeleton--card"></div>';
  }
  try {
    const data = await get('/risk-gates');
    const levelColors = { L0: 'text-green', L1: 'text-amber', L2: 'text-red' };
    const levelCls = levelColors[_esc(data.level)] || 'text-muted';
    const allowedBadge = data.allowed
      ? '<span class="badge badge--green">TRADING ALLOWED</span>'
      : '<span class="badge badge--red">TRADING HALTED</span>';

    // Guard: sizing_factor may be null
    const sizingPct = data.sizing_factor != null ? (data.sizing_factor * 100).toFixed(0) + '%' : '--';

    // Guard: cumulative_pnl null coerces to 0 causing false-green
    const pnl = data.cumulative_pnl;
    const hasPnl = typeof pnl === 'number' && !isNaN(pnl);
    const pnlCls = hasPnl ? (pnl >= 0 ? 'text-green' : 'text-red') : 'text-muted';
    const pnlStr = hasPnl ? `${pnl >= 0 ? '+' : ''}${pnl}%` : '--';

    // Guard: trades_in_window — use ?? to protect against literal 0
    const tradesInWindow = data.trades_in_window ?? 0;

    container.innerHTML = `
      ${renderTabHeader({ ...HEADER_PROPS, lastUpdated: data.evaluated_at || null, status: 'fresh' })}
      <div class="digest-grid">
        <div>
          <div class="digest-card">
            <div class="digest-card__title">Current Gate</div>
            <div style="display: flex; align-items: baseline; gap: var(--spacing-md); margin-top: var(--spacing-sm);">
              <span class="${levelCls} mono" style="font-size: 2.5rem; font-weight: 700;">${_esc(data.level)}</span>
              ${allowedBadge}
            </div>
            <div class="text-muted" style="font-size: 0.8125rem; margin-top: var(--spacing-sm);">${_esc(data.reason)}</div>
          </div>
          <div class="digest-card">
            <div class="digest-card__title">Sizing Factor</div>
            <div class="mono" style="font-size: 1.5rem; margin-top: var(--spacing-xs);">${sizingPct}</div>
            <div class="text-muted" style="font-size: 0.75rem;">Multiplier applied to all new positions</div>
          </div>
        </div>
        <div>
          <div class="digest-card">
            <div class="digest-card__title">Recent Performance</div>
            <div class="digest-row">
              <span class="digest-row__label">Cumulative P&amp;L (20d)</span>
              <span class="digest-row__value mono ${pnlCls}">${pnlStr}</span>
            </div>
            <div class="digest-row">
              <span class="digest-row__label">Trades in window</span>
              <span class="digest-row__value mono">${tradesInWindow}</span>
            </div>
          </div>
          <div class="digest-card">
            <div class="digest-card__title">Breach Thresholds</div>
            <div class="digest-row">
              <span class="digest-row__label">L1 (50% sizing)</span>
              <span class="digest-row__value mono text-amber">-10.0%</span>
            </div>
            <div class="digest-row">
              <span class="digest-row__label">L2 (halt trading)</span>
              <span class="digest-row__value mono text-red">-15.0%</span>
            </div>
          </div>
        </div>
      </div>`;

    if (_refreshTimer) clearInterval(_refreshTimer);
    _refreshTimer = setInterval(() => render(container), 60000);
  } catch (e) {
    console.error('risk render failed', e);
    container.innerHTML = renderTabHeader(HEADER_PROPS) + renderEmptyState({
      title: 'Failed to load risk gates',
      reason: `API error: ${e && e.message ? e.message : String(e)}`,
      nextUpdate: 'Check that the terminal server is running.',
    });
  } finally {
    _inflight = false;
  }
}

export function destroy() {
  if (_refreshTimer) { clearInterval(_refreshTimer); _refreshTimer = null; }
}
