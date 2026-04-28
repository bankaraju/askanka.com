// Track A #8: Ticker chart modal — opened by the app-level delegated
// handler when any <a.ticker-link> is clicked. One modal lives in the
// DOM (lazy-mounted on first open) and is reused for subsequent tickers.
//
// Shape: backdrop fixed over the viewport, card panel with title + close
// button + LightweightCharts candlestick pane. Closes on ESC, backdrop
// click, or the close button. Absent chart data renders an empty state.
//
// Data: /api/charts/{ticker} → { ticker, candles[{time, open, high, low, close}] }.
// LightweightCharts is loaded globally by index.html; if unavailable we
// render a degraded table of the last 20 candles.

import { getChart } from '../lib/api.js';

let _root = null;
let _titleEl = null;
let _bodyEl = null;
let _chartHostEl = null;
let _chart = null;
let _series = null;
let _escHandler = null;
let _lastTicker = null;

function _ensureMounted() {
  if (_root) return _root;
  _root = document.createElement('div');
  _root.id = 'ticker-chart-modal';
  _root.className = 'ticker-chart-modal';
  _root.style.cssText = 'display:none; position:fixed; inset:0; z-index:9000; '
    + 'background:rgba(0,0,0,0.55); align-items:flex-start; justify-content:center;';
  _root.innerHTML = `
    <div class="ticker-chart-modal__card" role="dialog" aria-modal="true"
         style="margin-top:4rem; width:min(960px, 92vw); background:var(--bg-card, #0f172a);
                border:1px solid var(--border, #1f2937); border-radius:12px;
                box-shadow:0 24px 60px rgba(0,0,0,0.5); padding:0;">
      <div class="ticker-chart-modal__head"
           style="display:flex; align-items:center; justify-content:space-between;
                  padding:0.75rem 1rem; border-bottom:1px solid var(--border, #1f2937);">
        <h3 class="ticker-chart-modal__title"
            style="margin:0; font-size:1.05rem; letter-spacing:0.04em;"></h3>
        <button type="button" class="ticker-chart-modal__close" aria-label="Close"
                style="background:none; border:none; color:var(--text-muted, #94a3b8);
                       font-size:1.4rem; cursor:pointer; line-height:1;">&times;</button>
      </div>
      <div class="ticker-chart-modal__body" style="padding:1rem;">
        <div class="ticker-chart-modal__chart"
             style="width:100%; height:360px; background:var(--bg, #0b1220);
                    border-radius:8px; border:1px solid var(--border, #1f2937);"></div>
        <div class="ticker-chart-modal__status text-muted"
             style="margin-top:0.5rem; font-size:0.82rem;"></div>
      </div>
    </div>`;
  document.body.appendChild(_root);
  _titleEl = _root.querySelector('.ticker-chart-modal__title');
  _bodyEl = _root.querySelector('.ticker-chart-modal__body');
  _chartHostEl = _root.querySelector('.ticker-chart-modal__chart');
  const closeBtn = _root.querySelector('.ticker-chart-modal__close');
  if (closeBtn) closeBtn.addEventListener('click', close);
  _root.addEventListener('click', (e) => {
    if (e.target === _root) close();
  });
  return _root;
}

function _setStatus(msg) {
  const el = _root && _root.querySelector('.ticker-chart-modal__status');
  if (el) el.textContent = msg || '';
}

function _disposeChart() {
  if (_chart && typeof _chart.remove === 'function') {
    try { _chart.remove(); } catch { /* noop */ }
  }
  _chart = null;
  _series = null;
  if (_chartHostEl) _chartHostEl.innerHTML = '';
}

function _renderCandles(candles) {
  _disposeChart();
  if (!candles || candles.length === 0) {
    _chartHostEl.innerHTML = '<div class="empty-state" style="padding:2rem; text-align:center;">'
      + '<p>No chart data available</p></div>';
    return;
  }
  if (!window.LightweightCharts) {
    const rows = candles.slice(-20).map(c =>
      `<tr><td class="mono">${c.time}</td><td class="mono">${c.close}</td></tr>`
    ).join('');
    _chartHostEl.innerHTML = `<table class="data-table"><thead>
      <tr><th>Date</th><th>Close</th></tr></thead><tbody>${rows}</tbody></table>`;
    return;
  }
  _chart = LightweightCharts.createChart(_chartHostEl, {
    width: _chartHostEl.clientWidth,
    height: 360,
    layout: { background: { color: '#0b1220' }, textColor: '#94a3b8' },
    grid: { vertLines: { color: '#1e293b' }, horzLines: { color: '#1e293b' } },
    rightPriceScale: { borderColor: '#1e293b' },
    timeScale: { borderColor: '#1e293b' },
  });
  _series = _chart.addCandlestickSeries({
    upColor: '#10b981', downColor: '#ef4444',
    borderUpColor: '#10b981', borderDownColor: '#ef4444',
    wickUpColor: '#10b981', wickDownColor: '#ef4444',
  });
  _series.setData(candles);
  _chart.timeScale().fitContent();
}

export async function open(ticker) {
  if (!ticker) return;
  _ensureMounted();
  _lastTicker = String(ticker).toUpperCase();
  _titleEl.textContent = _lastTicker;
  _setStatus('Loading chart…');
  _root.style.display = 'flex';
  if (!_escHandler) {
    _escHandler = (e) => { if (e.key === 'Escape') close(); };
    document.addEventListener('keydown', _escHandler);
  }
  try {
    const data = await getChart(_lastTicker);
    if (_lastTicker !== String(ticker).toUpperCase()) return;  // superseded
    const candles = (data && data.candles) || [];
    _renderCandles(candles);
    _setStatus(candles.length
      ? `${candles.length} daily candles`
      : 'No chart data available for this ticker');
  } catch (err) {
    _renderCandles([]);
    _setStatus(`Failed to load chart: ${err && err.message ? err.message : err}`);
  }
}

export function close() {
  if (!_root) return;
  _root.style.display = 'none';
  _disposeChart();
  _setStatus('');
  if (_escHandler) {
    document.removeEventListener('keydown', _escHandler);
    _escHandler = null;
  }
}

// Expose current state for tests.
export function _peekState() {
  return {
    mounted: !!_root,
    open: !!(_root && _root.style.display === 'flex'),
    lastTicker: _lastTicker,
  };
}
