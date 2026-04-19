import { get } from '../lib/api.js';

let currentSubTab = 'signals';
let chartInstance = null;
let refreshTimer = null;
let _tickerCache = null;

let _activeTicker = null;
let _activeContainer = null;
let _scannerFilters = { min_win: 60, direction: 'ALL', min_occ: 10, sort: 'win_rate' };

function setActiveTicker(symbol) {
  _activeTicker = symbol ? symbol.toUpperCase() : null;
  _renderTickerBadge();
}

function getActiveTicker() { return _activeTicker; }

function clearActiveTicker() {
  _activeTicker = null;
  _renderTickerBadge();
}

function _renderTickerBadge() {
  const badge = document.getElementById('active-ticker-badge');
  if (!badge) return;
  if (!_activeTicker) { badge.style.display = 'none'; badge.innerHTML = ''; return; }
  const name = _tickerCache ? (_tickerCache.find(t => t.symbol === _activeTicker) || {}).name || '' : '';
  badge.style.display = 'flex';
  badge.innerHTML = `
    <span class="ticker-badge__label">Viewing</span>
    <span class="ticker-badge__symbol">${_activeTicker}</span>
    ${name ? `<span class="ticker-badge__name">${name}</span>` : ''}
    <span class="ticker-badge__clear" id="ticker-badge-clear">&times;</span>`;
  document.getElementById('ticker-badge-clear')?.addEventListener('click', () => { clearActiveTicker(); switchSubTab(currentSubTab); });
}

async function _loadTickers() {
  if (_tickerCache) return _tickerCache;
  try {
    const data = await get('/tickers');
    _tickerCache = data.tickers || [];
  } catch { _tickerCache = []; }
  return _tickerCache;
}

function _setupTickerSearch(inputId, onSelect) {
  const input = document.getElementById(inputId);
  if (!input) return;

  const listId = inputId + '-list';
  let dropdown = document.getElementById(listId);
  if (!dropdown) {
    dropdown = document.createElement('div');
    dropdown.id = listId;
    dropdown.style.cssText = 'position:absolute;z-index:50;background:var(--bg-elevated);border:1px solid var(--border);border-radius:var(--radius-sm);max-height:240px;overflow-y:auto;width:350px;display:none;';
    input.parentElement.style.position = 'relative';
    input.parentElement.appendChild(dropdown);
  }

  input.addEventListener('input', async () => {
    const q = input.value.trim().toLowerCase();
    if (q.length < 1) { dropdown.style.display = 'none'; return; }
    const tickers = await _loadTickers();
    const matches = tickers.filter(t =>
      t.symbol.toLowerCase().includes(q) || t.name.toLowerCase().includes(q)
    ).slice(0, 15);

    if (matches.length === 0) { dropdown.style.display = 'none'; return; }

    dropdown.innerHTML = matches.map(t => `
      <div class="ticker-option" data-sym="${t.symbol}" style="padding:6px 12px;cursor:pointer;font-size:0.8125rem;display:flex;justify-content:space-between;">
        <span class="mono" style="color:var(--accent-gold);">${t.symbol}</span>
        <span class="text-muted">${t.name}</span>
      </div>`).join('');
    dropdown.style.display = 'block';

    dropdown.querySelectorAll('.ticker-option').forEach(opt => {
      opt.addEventListener('mousedown', (e) => {
        e.preventDefault();
        const sym = opt.dataset.sym;
        input.value = sym;
        dropdown.style.display = 'none';
        onSelect(sym);
      });
      opt.addEventListener('mouseenter', () => { opt.style.background = 'var(--bg-card)'; });
      opt.addEventListener('mouseleave', () => { opt.style.background = 'none'; });
    });
  });

  input.addEventListener('blur', () => { setTimeout(() => { dropdown.style.display = 'none'; }, 200); });
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      dropdown.style.display = 'none';
      const ticker = input.value.trim().toUpperCase();
      if (ticker) onSelect(ticker);
    }
  });
}

export async function render(container) {
  _activeContainer = container;
  container.innerHTML = `
    <div class="main__subtabs">
      <button class="subtab subtab--active" data-subtab="scanner">Scanner</button>
      <button class="subtab" data-subtab="signals">Signals</button>
      <button class="subtab" data-subtab="spreads">Spreads</button>
      <button class="subtab" data-subtab="charts">Charts</button>
      <button class="subtab" data-subtab="ta">TA</button>
    </div>
    <div id="active-ticker-badge" class="ticker-badge" style="display:none;"></div>
    <div id="trading-content"></div>`;

  container.querySelectorAll('.subtab').forEach(btn => {
    btn.addEventListener('click', () => {
      container.querySelectorAll('.subtab').forEach(b => b.classList.remove('subtab--active'));
      btn.classList.add('subtab--active');
      switchSubTab(btn.dataset.subtab);
    });
  });

  await _loadTickers();
  await switchSubTab('scanner');
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
    case 'scanner': await renderScanner(content); break;
    case 'signals': await renderSignals(content); break;
    case 'spreads': await renderSpreads(content); break;
    case 'charts':
      await renderCharts(content);
      if (_activeTicker) createChart(_activeTicker);
      break;
    case 'ta':
      await renderTA(content);
      if (_activeTicker) renderTAData(_activeTicker);
      break;
  }
}

// ── Scanner Sub-Tab ──
async function renderScanner(el) {
  el.innerHTML = `
    <div class="scanner-filters">
      <div class="scanner-filter-group">
        <div class="scanner-filter-label">Min Win Rate</div>
        <div class="scanner-filter-btns" data-filter="min_win">
          <button class="scanner-filter-btn" data-val="50">≥50%</button>
          <button class="scanner-filter-btn" data-val="60">≥60%</button>
          <button class="scanner-filter-btn" data-val="70">≥70%</button>
          <button class="scanner-filter-btn" data-val="80">≥80%</button>
        </div>
      </div>
      <div class="scanner-filter-group">
        <div class="scanner-filter-label">Direction</div>
        <div class="scanner-filter-btns" data-filter="direction">
          <button class="scanner-filter-btn" data-val="ALL">ALL</button>
          <button class="scanner-filter-btn" data-val="LONG">LONG</button>
          <button class="scanner-filter-btn" data-val="SHORT">SHORT</button>
        </div>
      </div>
      <div class="scanner-filter-group">
        <div class="scanner-filter-label">Min Occurrences</div>
        <div class="scanner-filter-btns" data-filter="min_occ">
          <button class="scanner-filter-btn" data-val="10">≥10</button>
          <button class="scanner-filter-btn" data-val="25">≥25</button>
          <button class="scanner-filter-btn" data-val="50">≥50</button>
        </div>
      </div>
      <div class="scanner-filter-group">
        <div class="scanner-filter-label">Sort By</div>
        <div class="scanner-filter-btns" data-filter="sort">
          <button class="scanner-filter-btn" data-val="win_rate">Win Rate</button>
          <button class="scanner-filter-btn" data-val="avg_return">Avg Return</button>
          <button class="scanner-filter-btn" data-val="occurrences">Occurrences</button>
        </div>
      </div>
      <div class="scanner-count" id="scanner-count"></div>
    </div>
    <div id="scanner-grid" class="scanner-grid"></div>`;

  // Set active state on filter buttons from _scannerFilters
  el.querySelectorAll('.scanner-filter-btns').forEach(group => {
    const filterKey = group.dataset.filter;
    group.querySelectorAll('.scanner-filter-btn').forEach(btn => {
      if (String(_scannerFilters[filterKey]) === btn.dataset.val) {
        btn.classList.add('scanner-filter-btn--active');
      }
      btn.addEventListener('click', () => {
        group.querySelectorAll('.scanner-filter-btn').forEach(b => b.classList.remove('scanner-filter-btn--active'));
        btn.classList.add('scanner-filter-btn--active');
        _scannerFilters[filterKey] = isNaN(btn.dataset.val) ? btn.dataset.val : Number(btn.dataset.val);
        _fetchAndRenderScanner();
      });
    });
  });

  await _fetchAndRenderScanner();
}

async function _fetchAndRenderScanner() {
  const grid = document.getElementById('scanner-grid');
  const countEl = document.getElementById('scanner-count');
  if (!grid) return;

  grid.innerHTML = '<div class="skeleton skeleton--card"></div>';
  const params = new URLSearchParams({
    min_win: _scannerFilters.min_win,
    direction: _scannerFilters.direction,
    min_occ: _scannerFilters.min_occ,
    sort: _scannerFilters.sort,
  });

  try {
    const data = await get(`/scanner?${params}`);
    if (countEl) countEl.textContent = `${data.total_stocks} stocks · ${data.total_patterns} patterns`;

    if (data.stocks.length === 0) {
      grid.innerHTML = '<div class="empty-state"><p>No patterns match these filters.</p><p class="text-muted">Try lowering the win rate threshold.</p></div>';
      return;
    }

    grid.innerHTML = data.stocks.map(stock => {
      const dirs = new Set(stock.patterns.map(p => p.direction));
      const badgeClass = dirs.size > 1 ? 'mixed' : dirs.has('SHORT') ? 'short' : 'long';
      const badgeLabel = dirs.size > 1 ? `${stock.pattern_count} patterns` : `${stock.pattern_count} ${[...dirs][0].toLowerCase()}`;

      const patternRows = stock.patterns.map(p => {
        const winCls = p.win_rate_5d >= 0.65 ? 'color:var(--green)' : p.win_rate_5d >= 0.55 ? 'color:var(--accent-gold)' : 'color:var(--red)';
        const sign = p.avg_return_5d >= 0 ? '+' : '';
        const dir = p.direction === 'SHORT' ? ' <span style="color:var(--red)">▼</span>' : '';
        return `<div class="scanner-card__pattern-row">
          <span>${p.pattern}${dir}</span>
          <span><span style="${winCls};font-weight:600">${Math.round(p.win_rate_5d * 100)}%</span> · ${sign}${p.avg_return_5d.toFixed(1)}% · ${p.occurrences}×</span>
        </div>`;
      }).join('');

      const bestP = stock.patterns[0];
      const lastDate = bestP.last_occurrence ? new Date(bestP.last_occurrence).toLocaleDateString('en-IN', { month: 'short', day: 'numeric' }) : '—';

      return `<div class="scanner-card" data-symbol="${stock.symbol}">
        <div class="scanner-card__header">
          <span class="scanner-card__symbol">${stock.symbol}</span>
          <span class="scanner-card__badge scanner-card__badge--${badgeClass}">${badgeLabel}</span>
        </div>
        <div class="scanner-card__patterns">${patternRows}</div>
        <div class="scanner-card__footer">Best: ${bestP.pattern} · Last fired ${lastDate}</div>
      </div>`;
    }).join('');

    grid.querySelectorAll('.scanner-card').forEach(card => {
      card.addEventListener('click', () => {
        const sym = card.dataset.symbol;
        setActiveTicker(sym);
        const chartsBtn = _activeContainer?.querySelector('[data-subtab="charts"]');
        if (chartsBtn) {
          _activeContainer.querySelectorAll('.subtab').forEach(b => b.classList.remove('subtab--active'));
          chartsBtn.classList.add('subtab--active');
        }
        switchSubTab('charts');
      });
    });

  } catch (err) {
    grid.innerHTML = `<div class="empty-state"><p>Error loading scanner data.</p><p class="text-muted">${err.message}</p></div>`;
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

// ── Bollinger Bands (20, 2) ──
function _computeBollinger(candles, period = 20, mult = 2) {
  const sma = [], upper = [], lower = [];
  for (let i = 0; i < candles.length; i++) {
    if (i < period - 1) { sma.push(null); upper.push(null); lower.push(null); continue; }
    const slice = candles.slice(i - period + 1, i + 1).map(c => c.close);
    const mean = slice.reduce((a, b) => a + b, 0) / period;
    const variance = slice.reduce((a, b) => a + (b - mean) ** 2, 0) / period;
    const std = Math.sqrt(variance);
    sma.push({ time: candles[i].time, value: mean });
    upper.push({ time: candles[i].time, value: mean + mult * std });
    lower.push({ time: candles[i].time, value: mean - mult * std });
  }
  return { sma: sma.filter(Boolean), upper: upper.filter(Boolean), lower: lower.filter(Boolean) };
}

function _detectPatterns(candles) {
  const markers = [];
  const recent = candles.slice(-60);
  for (let i = 1; i < recent.length; i++) {
    const c = recent[i];
    const p = recent[i - 1];
    const body = Math.abs(c.close - c.open);
    const range = c.high - c.low;
    const upperShadow = c.high - Math.max(c.open, c.close);
    const lowerShadow = Math.min(c.open, c.close) - c.low;
    const isGreen = c.close >= c.open;
    const pBody = Math.abs(p.close - p.open);
    const pGreen = p.close >= p.open;

    if (range > 0 && body < range * 0.1) {
      markers.push({ time: c.time, position: 'aboveBar', color: '#94a3b8', shape: 'diamond', text: 'Doji' });
    } else if (range > 0 && lowerShadow > body * 2 && upperShadow < range * 0.3 && (Math.min(c.open, c.close) - c.low) > range * 0.5) {
      markers.push({ time: c.time, position: 'belowBar', color: '#10b981', shape: 'arrowUp', text: 'Hammer' });
    } else if (range > 0 && upperShadow > body * 2 && lowerShadow < range * 0.3 && (c.high - Math.max(c.open, c.close)) > range * 0.5) {
      markers.push({ time: c.time, position: 'aboveBar', color: '#ef4444', shape: 'arrowDown', text: 'Inv Hammer' });
    }
    if (!pGreen && isGreen && c.open <= p.close && c.close >= p.open && body > pBody) {
      markers.push({ time: c.time, position: 'belowBar', color: '#10b981', shape: 'arrowUp', text: 'Bull Engulf' });
    }
    if (pGreen && !isGreen && c.open >= p.close && c.close <= p.open && body > pBody) {
      markers.push({ time: c.time, position: 'aboveBar', color: '#ef4444', shape: 'arrowDown', text: 'Bear Engulf' });
    }
  }
  return markers;
}

function _detectBBBreakouts(candles, bb) {
  const markers = [];
  const upperMap = new Map(bb.upper.map(d => [d.time, d.value]));
  const lowerMap = new Map(bb.lower.map(d => [d.time, d.value]));
  const recent = candles.slice(-60);
  for (let i = 1; i < recent.length; i++) {
    const c = recent[i], p = recent[i - 1];
    const uCurr = upperMap.get(c.time), lCurr = lowerMap.get(c.time);
    const uPrev = upperMap.get(p.time), lPrev = lowerMap.get(p.time);
    if (!uCurr || !lCurr || !uPrev || !lPrev) continue;
    if (c.close > uCurr && p.close <= uPrev) {
      markers.push({ time: c.time, position: 'aboveBar', color: '#3b82f6', shape: 'arrowUp', text: 'BB Up' });
    }
    if (c.close < lCurr && p.close >= lPrev) {
      markers.push({ time: c.time, position: 'belowBar', color: '#d97706', shape: 'arrowDown', text: 'BB Down' });
    }
  }
  return markers;
}

// ── Charts Sub-Tab ──
async function renderCharts(el) {
  el.innerHTML = `
    <div style="margin-bottom: var(--spacing-md); display: flex; align-items: center; gap: var(--spacing-md); flex-wrap: wrap;">
      <input type="text" id="chart-ticker-input" class="filter-search" placeholder="Search ticker or company name..." style="width: 350px;" autocomplete="off">
      <button id="chart-load-btn" class="filter-toggle filter-toggle--active" style="margin-left: 8px;">Load Chart</button>
      <div class="chart-toggles">
        <label class="chart-toggle"><input type="checkbox" id="toggle-bb" checked> Bollinger</label>
        <label class="chart-toggle"><input type="checkbox" id="toggle-patterns" checked> Patterns</label>
      </div>
    </div>
    <div id="chart-container" style="height: 400px; background: var(--bg-card); border-radius: var(--radius-md); border: 1px solid var(--border);"></div>
    <div id="chart-volume" style="height: 100px; margin-top: 4px; background: var(--bg-card); border-radius: var(--radius-md); border: 1px solid var(--border);"></div>`;

  _setupTickerSearch('chart-ticker-input', (sym) => { setActiveTicker(sym); createChart(sym); });

  document.getElementById('chart-load-btn').addEventListener('click', () => {
    const ticker = document.getElementById('chart-ticker-input').value.trim().toUpperCase();
    if (ticker) { setActiveTicker(ticker); createChart(ticker); }
  });
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

    // Bollinger Bands overlay
    const bb = _computeBollinger(data.candles);
    const showBB = document.getElementById('toggle-bb')?.checked !== false;
    const showPatterns = document.getElementById('toggle-patterns')?.checked !== false;

    const smaSeries = chartInstance.addLineSeries({
      color: '#f59e0b', lineWidth: 1, priceLineVisible: false,
      lastValueVisible: false, visible: showBB,
    });
    smaSeries.setData(bb.sma);

    const upperSeries = chartInstance.addLineSeries({
      color: 'rgba(59, 130, 246, 0.5)', lineWidth: 1, lineStyle: 2,
      priceLineVisible: false, lastValueVisible: false, visible: showBB,
    });
    upperSeries.setData(bb.upper);

    const lowerSeries = chartInstance.addLineSeries({
      color: 'rgba(59, 130, 246, 0.5)', lineWidth: 1, lineStyle: 2,
      priceLineVisible: false, lastValueVisible: false, visible: showBB,
    });
    lowerSeries.setData(bb.lower);

    // Pattern markers (last 60 candles)
    const candlePatterns = _detectPatterns(data.candles);
    const bbBreakouts = _detectBBBreakouts(data.candles, bb);
    const allMarkers = [...candlePatterns, ...bbBreakouts]
      .sort((a, b) => a.time < b.time ? -1 : a.time > b.time ? 1 : 0);

    if (showPatterns && allMarkers.length > 0) {
      candleSeries.setMarkers(allMarkers);
    }

    // Toggle wiring
    document.getElementById('toggle-bb')?.addEventListener('change', (e) => {
      const vis = e.target.checked;
      smaSeries.applyOptions({ visible: vis });
      upperSeries.applyOptions({ visible: vis });
      lowerSeries.applyOptions({ visible: vis });
    });

    document.getElementById('toggle-patterns')?.addEventListener('change', (e) => {
      candleSeries.setMarkers(e.target.checked ? allMarkers : []);
    });

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
      <input type="text" id="ta-ticker-input" class="filter-search" placeholder="Search ticker or company name..." style="width: 350px;" autocomplete="off">
      <button id="ta-load-btn" class="filter-toggle filter-toggle--active" style="margin-left: 8px;">Load TA</button>
    </div>
    <div id="ta-content"><div class="empty-state"><p>Enter a ticker to view technical analysis fingerprint</p></div></div>`;

  _setupTickerSearch('ta-ticker-input', (sym) => { setActiveTicker(sym); renderTAData(sym); });

  document.getElementById('ta-load-btn').addEventListener('click', () => {
    const ticker = document.getElementById('ta-ticker-input').value.trim().toUpperCase();
    if (ticker) { setActiveTicker(ticker); renderTAData(ticker); }
  });
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

    const dirColors = { 'LONG': 'badge--green', 'SHORT': 'badge--red', 'NEUTRAL': 'badge--muted' };
    const sigColors = { 'STRONG': 'badge--gold', 'MODERATE': 'badge--blue', 'WEAK': 'badge--muted' };

    const cards = patterns.map(p => {
      const isStrong = p.significance === 'STRONG' || p.significance === 'MODERATE';
      const borderStyle = isStrong ? 'border-left: 3px solid var(--accent-green);' : '';
      const sigBadge = `<span class="badge ${sigColors[p.significance] || 'badge--muted'}">${p.significance || '?'}</span>`;
      const dirBadge = `<span class="badge ${dirColors[p.direction] || 'badge--muted'}">${p.direction || '?'}</span>`;
      const winRate = p.win_rate_5d != null ? `${(p.win_rate_5d * 100).toFixed(0)}%` : '--';
      const avgReturn = p.avg_return_5d != null ? `${p.avg_return_5d.toFixed(2)}%` : '--';

      return `
        <div class="card" style="${borderStyle} padding: var(--spacing-md);">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
            <span style="font-size: 0.8125rem; font-weight: 500;">${p.pattern}</span>
            <div style="display: flex; gap: 4px;">${dirBadge} ${sigBadge}</div>
          </div>
          <div class="text-muted" style="font-size: 0.75rem;">
            Win 5d: <span class="mono">${winRate}</span> |
            Avg 5d: <span class="mono">${avgReturn}</span> |
            Events: <span class="mono">${p.occurrences || '--'}</span>
            ${p.last_occurrence ? `| Last: <span class="mono">${p.last_occurrence}</span>` : ''}
          </div>
          <div style="font-size:0.6875rem;color:var(--text-muted);margin-top:6px;line-height:1.5;">
            Fired ${p.occurrences || '?'}× in 5 years. Won ${winRate} over 5 days. Avg ${p.avg_return_5d >= 0 ? '+' : ''}${avgReturn}, worst ${(p.avg_drawdown || 0).toFixed(1)}%.${p.avg_return_10d ? ` 10d avg: ${p.avg_return_10d >= 0 ? '+' : ''}${p.avg_return_10d.toFixed(1)}%` : ''}
          </div>
        </div>`;
    }).join('');

    const personality = data.personality ? `<span class="badge badge--gold" style="margin-left: 8px;">${data.personality}</span>` : '';

    content.innerHTML = `
      <div style="margin-bottom: var(--spacing-md); display: flex; align-items: center;">
        <span class="text-muted">
          ${active.length} significant / ${patterns.length} total patterns for ${ticker}
          ${data.updated_at ? ` — ${data.updated_at}` : ''}
        </span>
        ${personality}
      </div>
      <div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: var(--spacing-sm);">
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
