import { get } from '../lib/api.js';

let chartInstance = null;

export async function render(container) {
  container.innerHTML = '<div class="skeleton skeleton--card"></div>';

  try {
    const [trData, curveData] = await Promise.all([
      get('/track-record'),
      get('/track-record/equity-curve'),
    ]);

    const trades = trData.trades || [];
    const wins = trades.filter(t => (t.final_pnl_pct || 0) > 0).length;
    const losses = trades.length - wins;

    // Calculate Sharpe (simplified)
    const returns = trades.map(t => t.final_pnl_pct || 0);
    const mean = returns.length ? returns.reduce((a, b) => a + b, 0) / returns.length : 0;
    const std = returns.length > 1
      ? Math.sqrt(returns.reduce((s, r) => s + (r - mean) ** 2, 0) / (returns.length - 1))
      : 1;
    const sharpe = std > 0 ? (mean / std * Math.sqrt(252)).toFixed(2) : '--';

    // Max drawdown
    let peak = 0, maxDD = 0;
    let cumul = 0;
    for (const t of trades.sort((a, b) => (a.close_date || '').localeCompare(b.close_date || ''))) {
      cumul += t.final_pnl_pct || 0;
      if (cumul > peak) peak = cumul;
      const dd = peak - cumul;
      if (dd > maxDD) maxDD = dd;
    }

    const sharpeColor = parseFloat(sharpe) > 1.5 ? 'text-green' : parseFloat(sharpe) > 1.0 ? 'text-gold' : 'text-red';

    container.innerHTML = `
      <div class="kpi-grid" style="margin-bottom: var(--spacing-lg);">
        <div class="kpi-card">
          <div class="kpi-card__label">Cumulative Return</div>
          <div class="kpi-card__value ${(curveData.total_return || 0) >= 0 ? 'text-green' : 'text-red'} mono">
            ${(curveData.total_return || 0) >= 0 ? '+' : ''}${(curveData.total_return || 0).toFixed(2)}%
          </div>
          <div class="kpi-card__sub">${trData.total_closed || 0} trades closed</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-card__label">Win Rate</div>
          <div class="kpi-card__value mono">${(trData.win_rate_pct || 0).toFixed(1)}%</div>
          <div class="kpi-card__sub">${wins}W / ${losses}L</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-card__label">Sharpe Ratio</div>
          <div class="kpi-card__value ${sharpeColor} mono">${sharpe}</div>
          <div class="kpi-card__sub">Annualized</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-card__label">Max Drawdown</div>
          <div class="kpi-card__value text-red mono">-${maxDD.toFixed(2)}%</div>
          <div class="kpi-card__sub">Peak to trough</div>
        </div>
      </div>

      <div id="equity-curve" style="height: 300px; background: var(--bg-card); border-radius: var(--radius-md); border: 1px solid var(--border); margin-bottom: var(--spacing-lg);"></div>

      <h3 style="margin-bottom: var(--spacing-md);">Closed Trades</h3>
      <div id="trades-table"></div>`;

    // Equity curve chart
    const curveEl = document.getElementById('equity-curve');
    if (curveEl && window.LightweightCharts && curveData.curve && curveData.curve.length > 0) {
      chartInstance = LightweightCharts.createChart(curveEl, {
        width: curveEl.clientWidth,
        height: 300,
        layout: { background: { color: '#111827' }, textColor: '#94a3b8' },
        grid: { vertLines: { color: '#1e293b' }, horzLines: { color: '#1e293b' } },
        rightPriceScale: { borderColor: '#1e293b' },
        timeScale: { borderColor: '#1e293b' },
      });

      const areaSeries = chartInstance.addAreaSeries({
        topColor: 'rgba(16, 185, 129, 0.4)',
        bottomColor: 'rgba(16, 185, 129, 0.0)',
        lineColor: '#10b981',
        lineWidth: 2,
      });

      areaSeries.setData(curveData.curve.filter(c => c.time));
      chartInstance.timeScale().fitContent();
    } else if (curveEl) {
      curveEl.innerHTML = '<div class="empty-state" style="height: 100%;"><p>Not enough data for equity curve</p></div>';
    }

    // Trades table
    const tableEl = document.getElementById('trades-table');
    if (tableEl) {
      const sorted = [...trades].sort((a, b) => (b.close_date || '').localeCompare(a.close_date || ''));
      const rows = sorted.map(t => {
        const pnl = t.final_pnl_pct || 0;
        const pnlClass = pnl >= 0 ? 'text-green' : 'text-red';
        const pnlIcon = pnl >= 0 ? '&#9650;' : '&#9660;';
        const reasonMap = {
          'target_hit': '<span class="badge badge--green">TARGET</span>',
          'stopped': '<span class="badge badge--red">STOPPED</span>',
          'trailing_stop': '<span class="badge badge--amber">TRAILING</span>',
          'expired': '<span class="badge badge--muted">EXPIRED</span>',
        };
        const reason = reasonMap[(t.close_reason || '').toLowerCase()] || `<span class="badge badge--muted">${t.close_reason || '--'}</span>`;

        return `<tr>
          <td style="font-family: var(--font-body);">${t.spread_name || t.signal_id || '--'}</td>
          <td class="mono">${t.open_date || '--'}</td>
          <td class="mono">${t.close_date || '--'}</td>
          <td class="mono">${t.days_open || '--'}d</td>
          <td class="${pnlClass} mono">${pnlIcon} ${pnl.toFixed(2)}%</td>
          <td class="mono text-muted">${(t.peak_pnl_pct || 0).toFixed(2)}%</td>
          <td>${reason}</td>
        </tr>`;
      }).join('');

      tableEl.innerHTML = `
        <table class="data-table">
          <thead><tr><th>Trade</th><th>Open</th><th>Close</th><th>Days</th><th>P&L</th><th>Peak</th><th>Exit</th></tr></thead>
          <tbody>${rows || '<tr><td colspan="7" class="text-muted">No closed trades yet</td></tr>'}</tbody>
        </table>`;
    }

  } catch (err) {
    container.innerHTML = '<div class="empty-state"><p>Failed to load track record</p></div>';
  }
}

export function destroy() {
  if (chartInstance) { chartInstance.remove(); chartInstance = null; }
}
