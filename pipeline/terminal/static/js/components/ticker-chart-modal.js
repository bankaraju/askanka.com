// Ticker chart modal v2 — research artifact, not just OHLC.
//
// On open, fires two parallel requests:
//   /api/charts/{ticker}      — daily candles (with no-store cache header)
//   /api/ticker/{ticker}/narrative — markers + summary lines for past work
//
// Adds vs v1:
//   - MA20/50/200 overlays (toggle chips), volume histogram pane
//   - 1M / 3M / 6M / 1Y / ALL date-range chips
//   - Expand-to-fullscreen toggle (90vw × 80vh card)
//   - Marker overlay: Phase C signals, spread legs, pattern hits, >2σ moves,
//     volume spikes — colour-coded by source
//   - Narration footer listing the past-work summary so the user can see
//     "what we've said about this ticker before" inline with the chart
//   - Inline "last YYYY-MM-DD (Nd ago)" status — silent staleness becomes loud
//
// Lightweight Charts is loaded globally by index.html; degraded table
// fallback if the library failed to load.

import { getChart, getTickerNarrative } from '../lib/api.js';

let _root = null;
let _titleEl = null;
let _chartHostEl = null;
let _volHostEl = null;
let _statusEl = null;
let _narrationEl = null;
let _rangeChipsEl = null;
let _maChipsEl = null;
let _expandBtn = null;
let _chart = null;
let _volChart = null;
let _series = null;
let _volSeries = null;
let _maSeries = {};  // { '20': series, '50': series, '200': series }
let _escHandler = null;
let _resizeHandler = null;
let _lastTicker = null;
let _expanded = false;
// Module-state caches so range/MA toggles don't re-fetch.
let _allCandles = [];
let _allMarkers = [];

const RANGE_DAYS = { '1M': 22, '3M': 66, '6M': 132, '1Y': 252, 'ALL': null };
let _activeRange = '6M';
const MA_DEFAULTS = { '20': true, '50': true, '200': false };
let _activeMAs = { ...MA_DEFAULTS };

function _ensureMounted() {
  if (_root) return _root;
  _root = document.createElement('div');
  _root.id = 'ticker-chart-modal';
  _root.className = 'ticker-chart-modal';
  _root.style.cssText = 'display:none; position:fixed; inset:0; z-index:9000; '
    + 'background:rgba(0,0,0,0.55); align-items:flex-start; justify-content:center;';
  _root.innerHTML = `
    <div class="ticker-chart-modal__card" role="dialog" aria-modal="true"
         style="margin-top:3rem; width:min(960px, 92vw); background:var(--bg-card, #0f172a);
                border:1px solid var(--border, #1f2937); border-radius:12px;
                box-shadow:0 24px 60px rgba(0,0,0,0.5); padding:0;
                display:flex; flex-direction:column;">
      <div class="ticker-chart-modal__head"
           style="display:flex; align-items:center; justify-content:space-between;
                  padding:0.75rem 1rem; border-bottom:1px solid var(--border, #1f2937);
                  flex-wrap:wrap; gap:0.5rem;">
        <h3 class="ticker-chart-modal__title"
            style="margin:0; font-size:1.05rem; letter-spacing:0.04em;"></h3>
        <div class="ticker-chart-modal__head-controls"
             style="display:flex; align-items:center; gap:0.5rem;">
          <div class="ticker-chart-modal__range-chips"
               style="display:flex; gap:0.25rem;"></div>
          <button type="button" class="ticker-chart-modal__expand"
                  title="Expand"
                  style="background:none; border:1px solid var(--border, #1f2937);
                         color:var(--text-muted, #94a3b8); padding:0.25rem 0.5rem;
                         border-radius:6px; cursor:pointer; font-size:0.85rem;">
            ⤢
          </button>
          <button type="button" class="ticker-chart-modal__close" aria-label="Close"
                  style="background:none; border:none; color:var(--text-muted, #94a3b8);
                         font-size:1.4rem; cursor:pointer; line-height:1;">&times;</button>
        </div>
      </div>
      <div class="ticker-chart-modal__body" style="padding:1rem; overflow-y:auto;">
        <div class="ticker-chart-modal__ma-chips"
             style="display:flex; gap:0.5rem; margin-bottom:0.5rem; font-size:0.78rem;
                    color:var(--text-muted, #94a3b8);"></div>
        <div class="ticker-chart-modal__chart"
             style="width:100%; height:360px; background:var(--bg, #0b1220);
                    border-radius:8px; border:1px solid var(--border, #1f2937);"></div>
        <div class="ticker-chart-modal__volume"
             style="width:100%; height:90px; background:var(--bg, #0b1220);
                    border-radius:8px; border:1px solid var(--border, #1f2937);
                    border-top:none; margin-top:-1px;"></div>
        <div class="ticker-chart-modal__status text-muted"
             style="margin-top:0.5rem; font-size:0.82rem;"></div>
        <div class="ticker-chart-modal__narration"
             style="margin-top:0.75rem; padding:0.75rem 0.85rem;
                    background:var(--bg, #0b1220);
                    border:1px solid var(--border, #1f2937);
                    border-radius:8px; font-size:0.85rem;
                    color:var(--text-muted, #cbd5e1);"></div>
      </div>
    </div>`;
  document.body.appendChild(_root);
  _titleEl = _root.querySelector('.ticker-chart-modal__title');
  _chartHostEl = _root.querySelector('.ticker-chart-modal__chart');
  _volHostEl = _root.querySelector('.ticker-chart-modal__volume');
  _statusEl = _root.querySelector('.ticker-chart-modal__status');
  _narrationEl = _root.querySelector('.ticker-chart-modal__narration');
  _rangeChipsEl = _root.querySelector('.ticker-chart-modal__range-chips');
  _maChipsEl = _root.querySelector('.ticker-chart-modal__ma-chips');
  _expandBtn = _root.querySelector('.ticker-chart-modal__expand');

  _renderRangeChips();
  _renderMAChips();

  const closeBtn = _root.querySelector('.ticker-chart-modal__close');
  if (closeBtn) closeBtn.addEventListener('click', close);
  _expandBtn.addEventListener('click', _toggleExpanded);
  _root.addEventListener('click', (e) => {
    if (e.target === _root) close();
  });
  return _root;
}

function _renderRangeChips() {
  _rangeChipsEl.innerHTML = '';
  Object.keys(RANGE_DAYS).forEach((label) => {
    const b = document.createElement('button');
    b.type = 'button';
    b.textContent = label;
    b.dataset.range = label;
    b.style.cssText = 'background:none; border:1px solid var(--border, #1f2937); '
      + 'color:var(--text-muted, #94a3b8); padding:0.2rem 0.55rem; border-radius:6px; '
      + 'cursor:pointer; font-size:0.75rem;';
    if (label === _activeRange) {
      b.style.background = '#1e293b';
      b.style.color = '#e2e8f0';
    }
    b.addEventListener('click', () => {
      _activeRange = label;
      _renderRangeChips();
      _redrawFromCache();
    });
    _rangeChipsEl.appendChild(b);
  });
}

function _renderMAChips() {
  _maChipsEl.innerHTML = '<span style="opacity:0.7;">Overlays:</span>';
  Object.keys(_activeMAs).forEach((win) => {
    const b = document.createElement('button');
    b.type = 'button';
    b.textContent = `MA${win}`;
    b.style.cssText = 'background:none; border:1px solid var(--border, #1f2937); '
      + 'color:var(--text-muted, #94a3b8); padding:0.15rem 0.45rem; border-radius:6px; '
      + 'cursor:pointer; font-size:0.75rem;';
    if (_activeMAs[win]) {
      b.style.background = '#1e293b';
      b.style.color = '#e2e8f0';
    }
    b.addEventListener('click', () => {
      _activeMAs[win] = !_activeMAs[win];
      _renderMAChips();
      _redrawFromCache();
    });
    _maChipsEl.appendChild(b);
  });
}

function _setStatus(msg) {
  if (_statusEl) _statusEl.textContent = msg || '';
}

function _setNarration(summary, markerCount) {
  if (!_narrationEl) return;
  if (!summary || !summary.length) {
    _narrationEl.innerHTML = '<em style="opacity:0.6;">No prior signals, spread legs, or major movements catalogued for this ticker.</em>';
    return;
  }
  const items = summary.map((s) => `<li style="margin:0.15rem 0;">${_escape(s)}</li>`).join('');
  _narrationEl.innerHTML = `
    <div style="font-weight:600; margin-bottom:0.4rem; color:#e2e8f0;">
      What we've said about this ticker — ${markerCount} marker${markerCount === 1 ? '' : 's'} on chart
    </div>
    <ul style="margin:0; padding-left:1.1rem;">${items}</ul>`;
}

function _escape(s) {
  return String(s).replace(/[&<>]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' })[c]);
}

function _disposeChart() {
  for (const c of [_chart, _volChart]) {
    if (c && typeof c.remove === 'function') {
      try { c.remove(); } catch { /* noop */ }
    }
  }
  _chart = null;
  _volChart = null;
  _series = null;
  _volSeries = null;
  _maSeries = {};
  if (_chartHostEl) _chartHostEl.innerHTML = '';
  if (_volHostEl) _volHostEl.innerHTML = '';
}

function _slice(candles) {
  const n = RANGE_DAYS[_activeRange];
  if (!n) return candles;
  return candles.slice(-n);
}

function _ma(candles, win) {
  const out = [];
  let sum = 0;
  for (let i = 0; i < candles.length; i++) {
    sum += candles[i].close;
    if (i >= win) sum -= candles[i - win].close;
    if (i >= win - 1) {
      out.push({ time: candles[i].time, value: +(sum / win).toFixed(2) });
    }
  }
  return out;
}

function _redrawFromCache() {
  if (!_allCandles.length) return;
  _renderCandles(_allCandles, _allMarkers);
}

function _renderCandles(allCandles, markers) {
  _disposeChart();
  if (!allCandles || allCandles.length === 0) {
    _chartHostEl.innerHTML = '<div class="empty-state" style="padding:2rem; text-align:center;">'
      + '<p>No chart data available</p></div>';
    if (_volHostEl) _volHostEl.style.display = 'none';
    return;
  }
  if (_volHostEl) _volHostEl.style.display = '';

  if (!window.LightweightCharts) {
    const rows = allCandles.slice(-20).map((c) =>
      `<tr><td class="mono">${c.time}</td><td class="mono">${c.close}</td></tr>`
    ).join('');
    _chartHostEl.innerHTML = `<table class="data-table"><thead>
      <tr><th>Date</th><th>Close</th></tr></thead><tbody>${rows}</tbody></table>`;
    return;
  }

  const candles = _slice(allCandles);
  const fromTime = candles[0]?.time;

  _chart = LightweightCharts.createChart(_chartHostEl, {
    width: _chartHostEl.clientWidth,
    height: _chartHostEl.clientHeight,
    layout: { background: { color: '#0b1220' }, textColor: '#94a3b8' },
    grid: { vertLines: { color: '#1e293b' }, horzLines: { color: '#1e293b' } },
    rightPriceScale: { borderColor: '#1e293b' },
    timeScale: { borderColor: '#1e293b', timeVisible: false, rightOffset: 4 },
    crosshair: { mode: 1 },
  });
  _series = _chart.addCandlestickSeries({
    upColor: '#10b981', downColor: '#ef4444',
    borderUpColor: '#10b981', borderDownColor: '#ef4444',
    wickUpColor: '#10b981', wickDownColor: '#ef4444',
  });
  _series.setData(candles);

  // MA overlays — toggleable. Computed off the FULL series (so MA200 is
  // continuous when zooming in to the 1M view) then sliced.
  const maColors = { '20': '#60a5fa', '50': '#fbbf24', '200': '#f472b6' };
  Object.keys(_activeMAs).forEach((win) => {
    if (!_activeMAs[win]) return;
    const ma = _ma(allCandles, +win);
    const sliced = fromTime ? ma.filter((p) => p.time >= fromTime) : ma;
    if (!sliced.length) return;
    const s = _chart.addLineSeries({
      color: maColors[win], lineWidth: 1, priceLineVisible: false, lastValueVisible: false,
    });
    s.setData(sliced);
    _maSeries[win] = s;
  });

  // Markers — only those in the visible window.
  if (markers && markers.length) {
    const visible = fromTime ? markers.filter((m) => m.time >= fromTime) : markers;
    if (visible.length) _series.setMarkers(visible);
  }

  // Volume in its own pane below — separate chart so it scales independently.
  _volChart = LightweightCharts.createChart(_volHostEl, {
    width: _volHostEl.clientWidth,
    height: _volHostEl.clientHeight,
    layout: { background: { color: '#0b1220' }, textColor: '#94a3b8' },
    grid: { vertLines: { color: '#1e293b' }, horzLines: { color: '#1e293b' } },
    rightPriceScale: { borderColor: '#1e293b' },
    timeScale: { borderColor: '#1e293b', timeVisible: false, rightOffset: 4 },
  });
  _volSeries = _volChart.addHistogramSeries({ priceFormat: { type: 'volume' }, priceLineVisible: false });
  _volSeries.setData(candles.map((c, i) => ({
    time: c.time,
    value: c.volume || 0,
    color: i > 0 && c.close >= candles[i - 1].close ? '#10b981' : '#ef4444',
  })));

  // Sync time scales so cursor + zoom stay aligned across panes.
  const syncTo = (src, dst) => {
    src.timeScale().subscribeVisibleLogicalRangeChange((r) => {
      if (r) dst.timeScale().setVisibleLogicalRange(r);
    });
  };
  syncTo(_chart, _volChart);
  syncTo(_volChart, _chart);

  _chart.timeScale().fitContent();
}

function _toggleExpanded() {
  _expanded = !_expanded;
  const card = _root.querySelector('.ticker-chart-modal__card');
  if (_expanded) {
    card.style.width = '94vw';
    card.style.marginTop = '2rem';
    _chartHostEl.style.height = '60vh';
    _volHostEl.style.height = '15vh';
    _expandBtn.textContent = '⤡';
  } else {
    card.style.width = 'min(960px, 92vw)';
    card.style.marginTop = '3rem';
    _chartHostEl.style.height = '360px';
    _volHostEl.style.height = '90px';
    _expandBtn.textContent = '⤢';
  }
  // Re-create the charts so the new container sizes are picked up.
  _redrawFromCache();
}

export async function open(ticker) {
  if (!ticker) return;
  _ensureMounted();
  _lastTicker = String(ticker).toUpperCase();
  _titleEl.textContent = _lastTicker;
  _setStatus('Loading chart…');
  _setNarration([], 0);
  _root.style.display = 'flex';
  if (!_escHandler) {
    _escHandler = (e) => { if (e.key === 'Escape') close(); };
    document.addEventListener('keydown', _escHandler);
  }
  if (!_resizeHandler) {
    _resizeHandler = () => _redrawFromCache();
    window.addEventListener('resize', _resizeHandler);
  }
  try {
    // Fire chart + narrative in parallel; the modal opens with whatever
    // arrives first. Narrative is best-effort — chart still draws if the
    // narrative endpoint 500s, which is the right failure mode.
    const [chartData, narr] = await Promise.allSettled([
      getChart(_lastTicker),
      getTickerNarrative(_lastTicker),
    ]);
    if (_lastTicker !== String(ticker).toUpperCase()) return;  // superseded

    _allCandles = (chartData.status === 'fulfilled' && chartData.value && chartData.value.candles) || [];
    _allMarkers = (narr.status === 'fulfilled' && narr.value && narr.value.markers) || [];
    const summary = (narr.status === 'fulfilled' && narr.value && narr.value.summary) || [];
    const markerCount = (narr.status === 'fulfilled' && narr.value && narr.value.marker_count) || 0;

    _renderCandles(_allCandles, _allMarkers);

    if (_allCandles.length) {
      const last = _allCandles[_allCandles.length - 1].time;
      const ageDays = Math.floor((Date.now() - new Date(last).getTime()) / 86400000);
      const ageLabel = ageDays <= 1 ? 'fresh'
        : ageDays <= 4 ? `${ageDays}d ago`
        : `⚠ ${ageDays}d old`;
      _setStatus(`${_allCandles.length} daily candles · last ${last} (${ageLabel}) · ${_activeRange}`);
    } else {
      _setStatus('No chart data available for this ticker');
    }

    _setNarration(summary, markerCount);
  } catch (err) {
    _renderCandles([], []);
    _setStatus(`Failed to load chart: ${err && err.message ? err.message : err}`);
  }
}

export function close() {
  if (!_root) return;
  _root.style.display = 'none';
  _disposeChart();
  _setStatus('');
  _allCandles = [];
  _allMarkers = [];
  if (_escHandler) {
    document.removeEventListener('keydown', _escHandler);
    _escHandler = null;
  }
  if (_resizeHandler) {
    window.removeEventListener('resize', _resizeHandler);
    _resizeHandler = null;
  }
}

// Expose current state for tests.
export function _peekState() {
  return {
    mounted: !!_root,
    open: !!(_root && _root.style.display === 'flex'),
    lastTicker: _lastTicker,
    expanded: _expanded,
    range: _activeRange,
    activeMAs: { ..._activeMAs },
  };
}
