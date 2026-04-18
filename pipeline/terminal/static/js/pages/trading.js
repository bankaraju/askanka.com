import { get } from '../lib/api.js';

let currentSubTab = 'signals';
let chartInstance = null;
let refreshTimer = null;

export async function render(container) {
  container.innerHTML = `
    <div class="main__subtabs">
      <button class="subtab subtab--active" data-subtab="signals">Signals</button>
      <button class="subtab" data-subtab="spreads">Spreads</button>
      <button class="subtab" data-subtab="charts">Charts</button>
      <button class="subtab" data-subtab="ta">TA</button>
    </div>
    <div id="trading-content"></div>`;

  container.querySelectorAll('.subtab').forEach(btn => {
    btn.addEventListener('click', () => {
      container.querySelectorAll('.subtab').forEach(b => b.classList.remove('subtab--active'));
      btn.classList.add('subtab--active');
      switchSubTab(btn.dataset.subtab);
    });
  });

  await switchSubTab('signals');
}

export function destroy() {
  if (refreshTimer) { clearInterval(refreshTimer); refreshTimer = null; }
  if (chartInstance) { chartInstance.remove(); chartInstance = null; }
}

async function switchSubTab(tab) {
  currentSubTab = tab;
  if (refreshTimer) { clearInterval(refreshTimer); refreshTimer = null; }
  if (chartInstance) { chartInstance.remove(); chartInstance = null; }

  const content = document.getElementById('trading-content');
  if (!content) return;

  switch (tab) {
    case 'signals': await renderSignals(content); break;
    case 'spreads': await renderSpreads(content); break;
    case 'charts': await renderCharts(content); break;
    case 'ta': await renderTA(content); break;
  }
}

// ── Signals Sub-Tab ──
async function renderSignals(el) {
  el.innerHTML = '<div class="skeleton skeleton--card"></div>';

  try {
    const data = await get('/signals');
    const allItems = [
      ...(data.positions || []).map(p => ({ ...p, _type: 'position' })),
      ...(data.signals || []).filter(s => !(data.positions || []).some(p => p.signal_id === s.signal_id))
        .map(s => ({ ...s, _type: 'signal' })),
    ];

    if (allItems.length === 0) {
      el.innerHTML = '<div class="empty-state"><p>No active signals or positions</p></div>';
      return;
    }

    const rows = allItems.map(item => {
      if (item._type === 'position') {
        const pnl = item.spread_pnl_pct || 0;
        const pnlClass = pnl >= 0 ? 'text-green' : 'text-red';
        const pnlIcon = pnl >= 0 ? '&#9650;' : '&#9660;';
        const longT = (item.long_legs || []).map(l => `${l.ticker}`).join(', ');
        const shortT = (item.short_legs || []).map(l => `${l.ticker}`).join(', ');
        return `<tr class="clickable" data-ticker="${(item.long_legs||[])[0]?.ticker || ''}">
          <td>${item.spread_name || item.signal_id}</td>
          <td><span class="text-green">L: ${longT}</span> / <span class="text-red">S: ${shortT}</span></td>
          <td><span class="badge badge--gold">${item.tier || 'SIGNAL'}</span></td>
          <td class="mono">${item.open_date || '--'}</td>
          <td class="${pnlClass} mono">${pnlIcon} ${pnl.toFixed(2)}%</td>
        </tr>`;
      } else {
        const hitRate = item.hit_rate ? `${(item.hit_rate * 100).toFixed(0)}%` : '--';
        const longT = (item.long_legs || []).map(l => l.ticker).join(', ');
        const shortT = (item.short_legs || []).map(l => l.ticker).join(', ');
        return `<tr class="clickable" data-ticker="${(item.long_legs||[])[0]?.ticker || ''}">
          <td>${item.spread_name || item.signal_id}</td>
          <td><span class="text-green">L: ${longT}</span> / <span class="text-red">S: ${shortT}</span></td>
          <td><span class="badge badge--${item.tier === 'SIGNAL' ? 'gold' : 'amber'}">${item.tier || '--'}</span></td>
          <td class="mono">${item.open_timestamp ? item.open_timestamp.split('T')[0] : '--'}</td>
          <td class="mono">${hitRate}</td>
        </tr>`;
      }
    }).join('');

    el.innerHTML = `
      <table class="data-table">
        <thead><tr><th>Signal</th><th>Legs</th><th>Tier</th><th>Opened</th><th>P&L / Hit</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>`;

    el.querySelectorAll('tr.clickable').forEach(row => {
      row.addEventListener('click', () => openContextPanel(row.dataset.ticker));
    });

  } catch (err) {
    el.innerHTML = `<div class="empty-state"><p>Failed to load signals</p></div>`;
  }
}

// ── Spreads Sub-Tab ──
async function renderSpreads(el) {
  el.innerHTML = '<div class="skeleton skeleton--card"></div>';

  try {
    const data = await get('/spreads');

    if (!data.spreads || data.spreads.length === 0) {
      el.innerHTML = `<div class="empty-state"><p>No eligible spreads in ${data.zone || 'current'} regime</p></div>`;
      return;
    }

    const cards = data.spreads.map(s => `
      <div class="card" style="margin-bottom: var(--spacing-md);">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--spacing-sm);">
          <h3 style="font-size: 1rem;">${s.name}</h3>
          <span class="badge badge--gold">${data.zone}</span>
        </div>
        <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: var(--spacing-sm); text-align: center;">
          <div>
            <div class="text-muted" style="font-size: 0.6875rem;">1D Win</div>
            <div class="mono text-green">${s['1d_win']}%</div>
          </div>
          <div>
            <div class="text-muted" style="font-size: 0.6875rem;">3D Win</div>
            <div class="mono text-green">${s['3d_win']}%</div>
          </div>
          <div>
            <div class="text-muted" style="font-size: 0.6875rem;">5D Win</div>
            <div class="mono ${s['5d_win'] >= 50 ? 'text-green' : 'text-red'}">${s['5d_win']}%</div>
          </div>
        </div>
        <div style="margin-top: var(--spacing-sm); font-size: 0.75rem;" class="text-muted">
          Best: ${s.best_win}% win over ${s.best_period}d period
        </div>
      </div>
    `).join('');

    el.innerHTML = `
      <div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: var(--spacing-md);">
        ${cards}
      </div>`;

  } catch (err) {
    el.innerHTML = `<div class="empty-state"><p>Failed to load spreads</p></div>`;
  }
}

// ── Charts Sub-Tab ──
async function renderCharts(el) {
  el.innerHTML = `
    <div style="margin-bottom: var(--spacing-md);">
      <input type="text" id="chart-ticker-input" class="filter-search" placeholder="Enter ticker (e.g., HAL)" style="width: 250px;">
      <button id="chart-load-btn" class="filter-toggle filter-toggle--active" style="margin-left: 8px;">Load Chart</button>
    </div>
    <div id="chart-container" style="height: 400px; background: var(--bg-card); border-radius: var(--radius-md); border: 1px solid var(--border);"></div>
    <div id="chart-volume" style="height: 100px; margin-top: 4px; background: var(--bg-card); border-radius: var(--radius-md); border: 1px solid var(--border);"></div>`;

  const input = document.getElementById('chart-ticker-input');
  const btn = document.getElementById('chart-load-btn');

  const loadChart = async () => {
    const ticker = input.value.trim().toUpperCase();
    if (!ticker) return;
    await createChart(ticker);
  };

  btn.addEventListener('click', loadChart);
  input.addEventListener('keydown', (e) => { if (e.key === 'Enter') loadChart(); });
}

async function createChart(ticker) {
  const container = document.getElementById('chart-container');
  const volContainer = document.getElementById('chart-volume');
  if (!container) return;

  if (chartInstance) { chartInstance.remove(); chartInstance = null; }

  container.innerHTML = '<div class="skeleton skeleton--chart" style="height: 100%;"></div>';
  volContainer.innerHTML = '';

  try {
    const data = await get(`/charts/${ticker}`);

    if (!data.candles || data.candles.length === 0) {
      container.innerHTML = `<div class="empty-state" style="height: 100%;"><p>No chart data for ${ticker}</p></div>`;
      return;
    }

    container.innerHTML = '';

    if (!window.LightweightCharts) {
      container.innerHTML = `<div class="empty-state" style="height: 100%;"><p>Lightweight Charts not loaded</p></div>`;
      return;
    }

    chartInstance = LightweightCharts.createChart(container, {
      width: container.clientWidth,
      height: 400,
      layout: { background: { color: '#111827' }, textColor: '#94a3b8' },
      grid: { vertLines: { color: '#1e293b' }, horzLines: { color: '#1e293b' } },
      crosshair: { mode: LightweightCharts.CrosshairMode?.Normal || 0 },
      rightPriceScale: { borderColor: '#1e293b' },
      timeScale: { borderColor: '#1e293b', timeVisible: false },
    });

    const candleSeries = chartInstance.addCandlestickSeries({
      upColor: '#10b981', downColor: '#ef4444',
      borderUpColor: '#10b981', borderDownColor: '#ef4444',
      wickUpColor: '#10b981', wickDownColor: '#ef4444',
    });

    candleSeries.setData(data.candles.map(c => ({
      time: c.time, open: c.open, high: c.high, low: c.low, close: c.close,
    })));

    // Volume chart
    volContainer.innerHTML = '';
    const volChart = LightweightCharts.createChart(volContainer, {
      width: volContainer.clientWidth,
      height: 100,
      layout: { background: { color: '#111827' }, textColor: '#94a3b8' },
      grid: { vertLines: { color: '#1e293b' }, horzLines: { color: '#1e293b' } },
      rightPriceScale: { borderColor: '#1e293b' },
      timeScale: { borderColor: '#1e293b', timeVisible: false, visible: false },
    });

    const volSeries = volChart.addHistogramSeries({
      color: 'rgba(245, 158, 11, 0.3)',
      priceFormat: { type: 'volume' },
    });

    volSeries.setData(data.candles.map(c => ({
      time: c.time, value: c.volume,
      color: c.close >= c.open ? 'rgba(16, 185, 129, 0.4)' : 'rgba(239, 68, 68, 0.4)',
    })));

    chartInstance.timeScale().fitContent();
    volChart.timeScale().fitContent();

    // Sync time scales
    chartInstance.timeScale().subscribeVisibleLogicalRangeChange(range => {
      if (range) volChart.timeScale().setVisibleLogicalRange(range);
    });

  } catch (err) {
    container.innerHTML = `<div class="empty-state" style="height: 100%;"><p>Failed to load chart for ${ticker}</p></div>`;
  }
}

// ── TA Sub-Tab ──
async function renderTA(el) {
  el.innerHTML = `
    <div style="margin-bottom: var(--spacing-md);">
      <input type="text" id="ta-ticker-input" class="filter-search" placeholder="Enter ticker (e.g., RELIANCE)" style="width: 250px;">
      <button id="ta-load-btn" class="filter-toggle filter-toggle--active" style="margin-left: 8px;">Load TA</button>
    </div>
    <div id="ta-content"><div class="empty-state"><p>Enter a ticker to view technical analysis fingerprint</p></div></div>`;

  const input = document.getElementById('ta-ticker-input');
  const btn = document.getElementById('ta-load-btn');

  const loadTA = async () => {
    const ticker = input.value.trim().toUpperCase();
    if (!ticker) return;
    await renderTAData(ticker);
  };

  btn.addEventListener('click', loadTA);
  input.addEventListener('keydown', (e) => { if (e.key === 'Enter') loadTA(); });
}

async function renderTAData(ticker) {
  const content = document.getElementById('ta-content');
  if (!content) return;

  content.innerHTML = '<div class="skeleton skeleton--card"></div>';

  try {
    const data = await get(`/ta/${ticker}`);
    const patterns = data.patterns || [];
    const active = data.active_patterns || [];

    if (patterns.length === 0) {
      content.innerHTML = `<div class="empty-state"><p>No TA patterns found for ${ticker}</p></div>`;
      return;
    }

    const cards = patterns.map(p => {
      const isActive = p.active || active.some(a => a.name === p.name);
      const borderStyle = isActive ? 'border-left: 3px solid var(--accent-green);' : '';
      const statusBadge = isActive
        ? '<span class="badge badge--green">ACTIVE</span>'
        : '<span class="badge badge--muted">INACTIVE</span>';
      const winRate = p.win_rate != null ? `${(p.win_rate * 100).toFixed(0)}%` : '--';
      const avgReturn = p.avg_return != null ? `${(p.avg_return * 100).toFixed(1)}%` : '--';

      return `
        <div class="card" style="${borderStyle} padding: var(--spacing-md);">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
            <span style="font-size: 0.8125rem; font-weight: 500;">${p.name || p.pattern}</span>
            ${statusBadge}
          </div>
          <div class="text-muted" style="font-size: 0.75rem;">
            Win: <span class="mono">${winRate}</span> |
            Avg: <span class="mono">${avgReturn}</span> |
            Events: <span class="mono">${p.event_count || p.events || '--'}</span>
          </div>
        </div>`;
    }).join('');

    content.innerHTML = `
      <div style="margin-bottom: var(--spacing-md);">
        <span class="text-muted">
          ${active.length} active pattern${active.length !== 1 ? 's' : ''} for ${ticker}
          ${data.updated_at ? ` — updated ${new Date(data.updated_at).toLocaleDateString('en-IN')}` : ''}
        </span>
      </div>
      <div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(250px, 1fr)); gap: var(--spacing-sm);">
        ${cards}
      </div>`;

  } catch (err) {
    content.innerHTML = `<div class="empty-state"><p>No TA fingerprint available for ${ticker}</p></div>`;
  }
}

// ── Context Panel ──
async function openContextPanel(ticker) {
  if (!ticker) return;
  ticker = ticker.toUpperCase();

  const panel = document.getElementById('context-panel');
  const title = document.getElementById('context-panel-title');
  const content = document.getElementById('context-panel-content');
  if (!panel || !content) return;

  title.textContent = ticker;
  content.innerHTML = '<div class="skeleton skeleton--card"></div>';
  panel.classList.add('context-panel--open');

  try {
    const [newsResp, taResp] = await Promise.allSettled([
      get(`/news/${ticker}`),
      get(`/ta/${ticker}`),
    ]);

    let html = '';

    // Trust score placeholder
    html += `<div class="card" style="margin-bottom: var(--spacing-md); padding: var(--spacing-md);">
      <div class="text-muted" style="font-size: 0.75rem; margin-bottom: 4px;">TRUST SCORE</div>
      <div class="mono" style="font-size: 1.25rem;">--</div>
      <div class="text-muted" style="font-size: 0.6875rem;">Loaded in Intelligence tab</div>
    </div>`;

    // Active TA patterns
    if (taResp.status === 'fulfilled') {
      const active = taResp.value.active_patterns || [];
      if (active.length > 0) {
        const patternBadges = active.map(p =>
          `<span class="badge badge--green" style="margin: 2px;">${p.name || p.pattern}</span>`
        ).join('');
        html += `<div style="margin-bottom: var(--spacing-md);">
          <div class="text-muted" style="font-size: 0.75rem; margin-bottom: 4px;">ACTIVE PATTERNS</div>
          ${patternBadges}
        </div>`;
      }
    }

    // News
    if (newsResp.status === 'fulfilled') {
      const items = newsResp.value.items || [];
      if (items.length > 0) {
        const newsHtml = items.slice(0, 5).map(n => `
          <div style="padding: 8px 0; border-bottom: 1px solid var(--border);">
            <div style="font-size: 0.8125rem;">${n.headline || n.title || JSON.stringify(n).slice(0, 80)}</div>
            <div class="text-muted" style="font-size: 0.6875rem;">${n.timestamp || n.date || ''}</div>
          </div>`).join('');
        html += `<div><div class="text-muted" style="font-size: 0.75rem; margin-bottom: 4px;">STOCK NEWS</div>${newsHtml}</div>`;
      } else {
        html += `<div class="text-muted" style="font-size: 0.8125rem;">No recent news for ${ticker}</div>`;
      }
    }

    content.innerHTML = html || `<div class="text-muted">No data available for ${ticker}</div>`;

  } catch {
    content.innerHTML = `<div class="text-muted">Failed to load data for ${ticker}</div>`;
  }
}
