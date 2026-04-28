import { get } from '../lib/api.js';
import { renderTabHeader, renderEmptyState } from '../components/tab-header.js';

const HEADER_PROPS = {
  title: 'Track Record',
  subtitle: 'Per-trade averages across every paper engine (Phase C / H-001 / H-002 / Spread / SECRSI / Karpathy / Scanner). Shadow only — no real money. Sum-of-trade-returns shown small as secondary "1 unit/trade" view.',
  cadence: 'Closed-trade ledger refreshes 16:15 IST (AnkaEODTrackRecord) + on every CLOSE during the day. Equity curve recomputes with each new close.',
};

let chartInstance = null;
let _state = { engineFilter: null, trades: [], byEngine: [], curve: [] };

const fmtPct = (n, signed = true) => {
  const v = Number(n) || 0;
  return (signed && v >= 0 ? '+' : '') + v.toFixed(2) + '%';
};
const pnlClass = (n) => ((Number(n) || 0) >= 0 ? 'text-green' : 'text-red');

function sparkline(values, color, w = 120, h = 28) {
  if (!values || values.length < 2) return '';
  const min = Math.min(...values, 0);
  const max = Math.max(...values, 0);
  const span = max - min || 1;
  const stepX = w / (values.length - 1);
  const pts = values.map((v, i) => {
    const x = (i * stepX).toFixed(1);
    const y = (h - ((v - min) / span) * h).toFixed(1);
    return `${x},${y}`;
  }).join(' ');
  const zeroY = (h - ((0 - min) / span) * h).toFixed(1);
  return `<svg class="spark" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}">
    <line x1="0" y1="${zeroY}" x2="${w}" y2="${zeroY}" stroke="rgba(148,163,184,0.25)" stroke-dasharray="2 2"/>
    <polyline points="${pts}" fill="none" stroke="${color}" stroke-width="1.6"/>
  </svg>`;
}

function engineCardHtml(b) {
  // Big number = average P&L per trade (the meaningful per-position return).
  // Sum-of-trade-returns is shown small as a secondary "if 1 unit per trade" view.
  const winColor = b.win_rate_pct >= 50 ? 'text-green' : 'text-amber';
  const avgColor = pnlClass(b.avg_pnl_pct);
  return `
    <div class="engine-card" data-engine="${b.engine_key}" title="${b.description}">
      <div class="engine-card__head">
        <span class="engine-card__dot" style="background:${b.color}"></span>
        <div class="engine-card__title">
          <div class="engine-card__label">${b.label}</div>
          <div class="engine-card__theme">${b.theme}</div>
        </div>
        <div class="engine-card__cum ${avgColor} mono">${fmtPct(b.avg_pnl_pct)}</div>
      </div>
      <div class="engine-card__spark">${sparkline(b.sparkline, b.color)}</div>
      <div class="engine-card__stats">
        <div><span class="engine-card__stat-label">Trades</span><span class="mono">${b.trades}</span></div>
        <div><span class="engine-card__stat-label">Win rate</span><span class="${winColor} mono">${b.win_rate_pct.toFixed(1)}%</span></div>
        <div><span class="engine-card__stat-label">Best</span><span class="text-green mono">${fmtPct(b.best_trade_pct)}</span></div>
        <div><span class="engine-card__stat-label">Worst</span><span class="text-red mono">${fmtPct(b.worst_trade_pct)}</span></div>
      </div>
      <div class="engine-card__footer">
        <span class="engine-card__stat-label">Sum (1 unit/trade)</span>
        <span class="${pnlClass(b.sum_pnl_pct)} mono">${fmtPct(b.sum_pnl_pct)}</span>
      </div>
    </div>`;
}

function metricsRowHtml(m, byEngine) {
  if (!m) return '';
  // Best engine ranked by avg P&L per trade (not sum) — sum is biased by
  // engine activity, average reflects actual per-position edge.
  const bestEngine = byEngine.slice().sort((a, b) => b.avg_pnl_pct - a.avg_pnl_pct)[0];
  const cells = [
    ['Avg Win', fmtPct(m.avg_win_pct), 'text-green'],
    ['Avg Loss', fmtPct(m.avg_loss_pct), 'text-red'],
    ['Best Trade', fmtPct(m.best_trade_pct), 'text-green'],
    ['Worst Trade', fmtPct(m.worst_trade_pct), 'text-red'],
    ['Best Day Avg', fmtPct(m.best_day_avg_pct), 'text-green'],
    ['Worst Day Avg', fmtPct(m.worst_day_avg_pct), 'text-red'],
    ['Avg Hold', `${m.avg_hold_days.toFixed(1)}d`, 'text-muted'],
    ['Win Streak', `${m.win_streak}`, 'text-green'],
    ['Loss Streak', `${m.loss_streak}`, 'text-red'],
    ['Best Engine', bestEngine ? bestEngine.label.split('—')[0].trim() : '--', 'text-gold'],
    ['Sum P&L (1u/trade)', fmtPct(m.sum_pnl_pct), pnlClass(m.sum_pnl_pct)],
    ['Max DD (avg curve)', `-${(m.max_drawdown_pct || 0).toFixed(2)}%`, 'text-red'],
  ];
  return `
    <div class="metrics-row">
      ${cells.map(([k, v, cls]) => `
        <div class="metrics-cell">
          <div class="metrics-cell__label">${k}</div>
          <div class="metrics-cell__value mono ${cls}">${v}</div>
        </div>`).join('')}
    </div>`;
}

function chipsHtml(byEngine) {
  const all = `<span class="chip ${_state.engineFilter === null ? 'chip--active' : ''}" data-engine="">All (${_state.trades.length})</span>`;
  const chips = byEngine.map(b => `
    <span class="chip ${_state.engineFilter === b.engine_key ? 'chip--active' : ''}"
          data-engine="${b.engine_key}"
          style="border-color:${b.color}; ${_state.engineFilter === b.engine_key ? `background:${b.color}1f; color:${b.color}` : ''}">
      <span class="chip__dot" style="background:${b.color}"></span>${b.label.split('—')[0].trim()} (${b.trades})
    </span>`).join('');
  return `<div class="chip-row">${all}${chips}</div>`;
}

function _tickerFromTrade(t) {
  // Phase C signal_ids look like BRK-2026-04-23-TATAELXSI; extract last segment
  // and validate as an upper-case ticker. spread_name "Phase C: TATAELXSI ..."
  // also exposes the symbol — use that fallback when signal_id is non-conforming.
  const sid = t.signal_id || '';
  const m = sid.match(/^BRK-\d{4}-\d{2}-\d{2}-([A-Z0-9&-]+)$/);
  if (m) return m[1];
  const sn = (t.spread_name || '');
  const m2 = sn.match(/Phase C:\s+([A-Z0-9&-]+)/);
  if (m2) return m2[1];
  return null;
}

function tradesTableHtml(trades) {
  const rows = trades.map(t => {
    const pnl = t.final_pnl_pct || 0;
    const reasonMap = {
      'target_hit': '<span class="badge badge--green">TARGET</span>',
      'stopped': '<span class="badge badge--red">STOPPED</span>',
      'stopped_out': '<span class="badge badge--red">STOPPED</span>',
      'stopped_out_zcross': '<span class="badge badge--amber">Z-CROSS</span>',
      'stopped_out_time': '<span class="badge badge--muted">TIME</span>',
      'stopped_out_trail': '<span class="badge badge--amber">TRAIL</span>',
      'trailing_stop': '<span class="badge badge--amber">TRAIL</span>',
      'expired': '<span class="badge badge--muted">EXPIRED</span>',
    };
    const reasonKey = (t.close_reason || '').split(':')[0].trim().toLowerCase().replace(/\s/g, '_');
    const reasonBadge = reasonMap[reasonKey] || `<span class="badge badge--muted" title="${(t.close_reason || '').replace(/"/g, '&quot;')}">${(t.close_reason || '--').split(':')[0].slice(0, 14)}</span>`;
    const ticker = _tickerFromTrade(t);
    const tradeCell = ticker
      ? `<a class="ticker-link" data-ticker="${ticker}" href="#" role="button" style="color:inherit; text-decoration:none; border-bottom:1px dotted var(--text-muted);">${t.spread_name || t.signal_id || '--'}</a>`
      : (t.spread_name || t.signal_id || '--');
    return `<tr>
      <td><span class="engine-tag" style="background:${t.engine_color}1f;color:${t.engine_color};border:1px solid ${t.engine_color}40">${(t.engine_label || '').split('—')[0].trim()}</span></td>
      <td style="font-family: var(--font-body);">${tradeCell}</td>
      <td class="mono text-muted">${t.open_date || '--'}</td>
      <td class="mono text-muted">${t.close_date || '--'}</td>
      <td class="mono">${t.days_open == null ? '--' : t.days_open}d</td>
      <td class="${pnlClass(pnl)} mono">${pnl >= 0 ? '▲' : '▼'} ${pnl.toFixed(2)}%</td>
      <td class="mono text-muted">${(t.peak_pnl_pct || 0).toFixed(2)}%</td>
      <td>${reasonBadge}</td>
    </tr>`;
  }).join('');
  return `
    <table class="data-table">
      <thead><tr>
        <th>Engine</th><th>Trade</th><th>Open</th><th>Close</th><th>Days</th><th>P&L</th><th>Peak</th><th>Exit</th>
      </tr></thead>
      <tbody>${rows || '<tr><td colspan="8" class="text-muted">No trades match this filter</td></tr>'}</tbody>
    </table>`;
}

function rerenderTrades() {
  const tableEl = document.getElementById('trades-table');
  const chipsEl = document.getElementById('engine-chips');
  if (!tableEl || !chipsEl) return;
  const filtered = _state.engineFilter
    ? _state.trades.filter(t => t.engine_key === _state.engineFilter)
    : _state.trades;
  chipsEl.innerHTML = chipsHtml(_state.byEngine);
  tableEl.innerHTML = tradesTableHtml(filtered);
  attachChipHandlers();
}

function attachChipHandlers() {
  document.querySelectorAll('#engine-chips .chip').forEach(chip => {
    chip.addEventListener('click', () => {
      const k = chip.dataset.engine || null;
      _state.engineFilter = (_state.engineFilter === k || k === '') ? null : k;
      rerenderTrades();
    });
  });
}

export async function render(container) {
  container.innerHTML = '<div class="skeleton skeleton--card"></div>';

  try {
    const [trData, curveData] = await Promise.all([
      get('/track-record'),
      get('/track-record/equity-curve'),
    ]);

    const trades = trData.trades || [];
    const byEngine = trData.by_engine || [];
    const m = trData.metrics || {};
    _state = { engineFilter: null, trades, byEngine, curve: curveData.curve || [] };

    const sharpeColor = m.sharpe == null ? 'text-muted' : (m.sharpe > 1.5 ? 'text-green' : m.sharpe > 1.0 ? 'text-gold' : 'text-red');
    const pf = m.profit_factor;
    const pfDisplay = pf == null ? '--' : (pf === Infinity ? '∞' : pf.toFixed(2));
    const pfColor = pf != null && pf > 1 ? 'text-green' : 'text-red';
    const wins = trades.filter(t => (t.final_pnl_pct || 0) > 0).length;

    // The hero strip surfaces per-trade metrics, not portfolio aggregates.
    // Each closed signal is a standalone paper position at 1 unit of
    // notional, so summing per-trade returns into a "cumulative" headline
    // overstates what a real portfolio would have done. Average is honest.
    container.innerHTML = `
      ${renderTabHeader({ ...HEADER_PROPS, lastUpdated: trData.generated_at || null, status: trades.length === 0 ? 'empty' : 'fresh' })}
      <div class="kpi-grid kpi-grid--5" style="margin-bottom: var(--spacing-lg);">
        <div class="kpi-card">
          <div class="kpi-card__label">Avg P&L per Trade</div>
          <div class="kpi-card__value ${pnlClass(trData.avg_pnl_pct)} mono">${fmtPct(trData.avg_pnl_pct)}</div>
          <div class="kpi-card__sub">${trData.total_closed || 0} trades closed</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-card__label">Win Rate</div>
          <div class="kpi-card__value mono">${(trData.win_rate_pct || 0).toFixed(1)}%</div>
          <div class="kpi-card__sub">${wins}W / ${trades.length - wins}L</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-card__label">Profit Factor</div>
          <div class="kpi-card__value ${pfColor} mono">${pfDisplay}</div>
          <div class="kpi-card__sub">Wins ÷ |Losses|</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-card__label">Sharpe</div>
          <div class="kpi-card__value ${sharpeColor} mono">${m.sharpe == null ? '--' : m.sharpe.toFixed(2)}</div>
          <div class="kpi-card__sub">Per-trade, annualised</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-card__label">Best / Worst Trade</div>
          <div class="kpi-card__value mono"><span class="text-green">${fmtPct(m.best_trade_pct)}</span> <span class="text-muted">/</span> <span class="text-red">${fmtPct(m.worst_trade_pct)}</span></div>
          <div class="kpi-card__sub">Range across all closes</div>
        </div>
      </div>

      <h3 class="section-heading">Trade Engines
        <span class="section-heading__sub">— each engine has its own thesis and risk profile</span>
      </h3>
      <div class="engine-grid">${byEngine.map(engineCardHtml).join('')}</div>

      <h3 class="section-heading" style="margin-top: var(--spacing-lg);">Portfolio Metrics</h3>
      ${metricsRowHtml(m, byEngine)}

      <h3 class="section-heading" style="margin-top: var(--spacing-lg);">Avg P&L per Trade — Over Time
        <span class="section-heading__sub">— running mean of per-trade returns; flat = consistent edge</span>
      </h3>
      <div id="equity-curve" style="height: 280px; background: var(--bg-card); border-radius: var(--radius-md); border: 1px solid var(--border); margin-bottom: var(--spacing-lg);"></div>

      <h3 class="section-heading">Closed Trades <span class="section-heading__sub">— click an engine chip to filter</span></h3>
      <div id="engine-chips"></div>
      <div id="trades-table"></div>`;

    // Equity curve.
    const curveEl = document.getElementById('equity-curve');
    if (curveEl && window.LightweightCharts && curveData.curve && curveData.curve.length > 0) {
      chartInstance = LightweightCharts.createChart(curveEl, {
        width: curveEl.clientWidth,
        height: 280,
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

    rerenderTrades();

  } catch (err) {
    console.error('track-record render error:', err);
    container.innerHTML = renderTabHeader(HEADER_PROPS) + renderEmptyState({
      title: 'Failed to load track record',
      reason: `API error: ${err && err.message ? err.message : String(err)}`,
      nextUpdate: 'Check that the terminal server is running and track_record.json exists.',
    });
  }
}

export function destroy() {
  if (chartInstance) { chartInstance.remove(); chartInstance = null; }
  _state = { engineFilter: null, trades: [], byEngine: [], curve: [] };
}
