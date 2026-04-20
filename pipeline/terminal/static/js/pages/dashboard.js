import { get } from '../lib/api.js';
import * as regimeBanner from '../components/regime-banner.js';
import * as kpiCard from '../components/kpi-card.js';
import * as signalsTable from '../components/signals-table.js';

let refreshTimer = null;

export async function render(container) {
  container.innerHTML = `
    <div id="dash-regime"></div>
    <div style="display: grid; grid-template-columns: 1fr 2fr 1fr; gap: var(--spacing-lg);">
      <div id="dash-kpis"></div>
      <div id="dash-signals"></div>
      <div id="dash-quickglance"></div>
    </div>`;

  await loadData();
  refreshTimer = setInterval(loadData, 30000);
}

export function destroy() {
  if (refreshTimer) { clearInterval(refreshTimer); refreshTimer = null; }
}

async function loadData() {
  const [regime, signals, riskGates] = await Promise.allSettled([
    get('/regime'), get('/signals'), get('/risk-gates'),
  ]);

  const regimeData = regime.status === 'fulfilled' ? regime.value : { zone: 'UNKNOWN', stable: false, consecutive_days: 0 };
  const signalsData = signals.status === 'fulfilled' ? signals.value : { signals: [], recommendations: [], positions: [] };
  const riskData = riskGates.status === 'fulfilled' ? riskGates.value : { level: 'L0', sizing_factor: 1.0, cumulative_pnl: 0, allowed: true };

  const regimeEl = document.getElementById('dash-regime');
  if (regimeEl) regimeBanner.render(regimeEl, regimeData);

  const kpiEl = document.getElementById('dash-kpis');
  if (kpiEl) {
    const activeCount = signalsData.signals.filter(s => s.tier === 'SIGNAL').length;
    const posCount = signalsData.positions.length;
    const totalPnl = signalsData.positions.reduce((sum, p) => sum + (p.spread_pnl_pct || 0), 0);

    kpiCard.renderGrid(kpiEl, [
      { label: 'ETF Signal', value: (regimeData.score || 0).toFixed(2), sub: `Source: ${regimeData.regime_source || 'N/A'}` },
      { label: 'Open Positions P&L', value: `${totalPnl >= 0 ? '+' : ''}${totalPnl.toFixed(2)}%`,
        colorClass: totalPnl >= 0 ? 'text-green' : 'text-red', sub: `${posCount} position${posCount !== 1 ? 's' : ''} open` },
      { label: 'Active Signals', value: String(activeCount), sub: 'SIGNAL tier (80+ conviction)', colorClass: 'text-gold' },
      { label: 'Risk Gate', value: riskData.level,
        colorClass: riskData.level === 'L0' ? 'text-green' : riskData.level === 'L1' ? 'text-gold' : 'text-red',
        sub: `Sizing: ${(riskData.sizing_factor * 100).toFixed(0)}% | Cumul: ${riskData.cumulative_pnl.toFixed(1)}%` },
    ]);
  }

  const signalsEl = document.getElementById('dash-signals');
  if (signalsEl) signalsTable.render(signalsEl, signalsData.signals, signalsData.positions);

  const quickEl = document.getElementById('dash-quickglance');
  if (quickEl) {
    const spreads = regimeData.eligible_spreads || {};
    const topSpreads = Object.entries(spreads).sort((a, b) => (b[1].best_win || 0) - (a[1].best_win || 0)).slice(0, 5);
    const convClass = (conv) => {
      if (conv === 'HIGH') return 'text-green';
      if (conv === 'MEDIUM') return 'text-amber';
      if (conv === 'LOW' || conv === 'NONE') return 'text-muted';
      return '';
    };
    const spreadRows = topSpreads.map(([name, s]) => {
      const longs = (s.long_legs || []).join(', ');
      const shorts = (s.short_legs || []).join(', ');
      const legsHtml = (longs || shorts)
        ? `<div style="font-size: 0.7rem; line-height: 1.3; margin-top: 2px;"><span class="text-green">L: ${longs || '—'}</span> &nbsp;<span class="text-red">S: ${shorts || '—'}</span></div>`
        : '';
      const conv = s.conviction || 'NONE';
      const score = (s.score !== undefined && s.score !== null) ? s.score : '—';
      return `
      <tr><td style="font-family: var(--font-body); font-size: 0.8125rem;">
        <div>${name}</div>${legsHtml}
      </td><td class="mono text-green" style="vertical-align: top;">${s.best_win || 0}%</td>
      <td class="mono ${convClass(conv)}" style="vertical-align: top;">${conv}<br><span style="font-size: 0.7rem; opacity: 0.7;">${score}</span></td></tr>`;
    }).join('');

    const recRows = (signalsData.recommendations || []).slice(0, 5).map(r => {
      const dirClass = r.direction === 'LONG' ? 'text-green' : 'text-red';
      const dirIcon = r.direction === 'LONG' ? '&#9650;' : '&#9660;';
      const staleTag = r.is_stale ? ' <span class="badge badge--stale">STALE</span>' : '';
      return `<tr><td style="font-family: var(--font-body); font-size: 0.8125rem;">${r.ticker}${staleTag}</td>
        <td class="${dirClass} mono">${dirIcon} ${r.direction}</td><td class="mono">${r.conviction}</td></tr>`;
    }).join('');

    quickEl.innerHTML = `
      <div class="card" style="margin-bottom: var(--spacing-md);">
        <h3 style="margin-bottom: var(--spacing-sm); font-size: 0.875rem;">Top Eligible Spreads</h3>
        <table class="data-table"><thead><tr><th>Spread / Legs</th><th>Win%</th><th>Today</th></tr></thead>
          <tbody>${spreadRows || '<tr><td colspan="3" class="text-muted">None eligible</td></tr>'}</tbody></table>
      </div>
      <div class="card">
        <h3 style="margin-bottom: var(--spacing-sm); font-size: 0.875rem;">Stock Recommendations</h3>
        <table class="data-table"><thead><tr><th>Ticker</th><th>Dir</th><th>Conv</th></tr></thead>
          <tbody>${recRows || '<tr><td colspan="3" class="text-muted">No recommendations</td></tr>'}</tbody></table>
      </div>`;
  }
}
