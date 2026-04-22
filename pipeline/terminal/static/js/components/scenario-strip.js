// Portfolio aggregates + simple P&L scenarios for the Dashboard footer.
// Inputs: positions array (each with spread_pnl_pct, long_legs, short_legs).
import { get } from '../lib/api.js';

// Cache by zone so the 30s dashboard re-render doesn't re-spam the endpoint.
const _flipCache = new Map();
const _inflight = new Map();

function _fetchFlip(zone, container) {
  if (_inflight.get(zone)) return;
  _inflight.set(zone, true);
  get(`/risk/regime-flip?to_zone=${encodeURIComponent(zone)}`)
    .then((data) => {
      _flipCache.set(zone, data);
      _patchRow(container, zone, data);
    })
    .catch(() => {
      _flipCache.set(zone, { __error: true });
      _patchRow(container, zone, { __error: true });
    })
    .finally(() => { _inflight.delete(zone); });
}

function _flipRowContent(zone, data, positionCount) {
  const nFlips = data?.n_flips ?? 0;
  const worst = data?.worst_drawdown_pct;
  const hasData = !data?.__error && nFlips > 0 && typeof worst === 'number';
  if (!hasData) {
    return {
      label: `Regime flip into ${zone} (no historical flips)`,
      labelCls: 'text-muted',
      value: 'n/a',
      valueCls: 'mono text-muted',
      title: `No historical flips into ${zone} in calm_breaks data (proxy: Nifty 5d-after).`,
    };
  }
  const agg = positionCount * worst;
  const pct = data.percentile ?? 95;
  return {
    label: `Regime flip into ${zone} (p${pct} of N=${nFlips} historical flips)`,
    labelCls: '',
    value: `${agg >= 0 ? '+' : ''}${agg.toFixed(2)}%`,
    valueCls: `mono ${agg >= 0 ? 'text-green' : 'text-red'}`,
    title: `p${pct} worst Nifty 5d-after across ${nFlips} historical flips into ${zone}. Proxy: Nifty index return, not per-position. Aggregate = per-flip × ${positionCount} positions.`,
  };
}

function _patchRow(container, zone, data) {
  const row = container.querySelector('#scen-regime-flip');
  if (!row) return;
  const posCount = Number(row.getAttribute('data-pos-count') || '0');
  const content = _flipRowContent(zone, data, posCount);
  const tds = row.querySelectorAll('td');
  if (tds.length >= 2) {
    tds[0].textContent = content.label;
    tds[0].className = content.labelCls;
    tds[1].textContent = content.value;
    tds[1].className = content.valueCls;
  }
  row.setAttribute('title', content.title);
}

export function render(container, positions, regimeData) {
  if (!positions || positions.length === 0) {
    container.innerHTML = '';
    return;
  }

  const totalPnl = positions.reduce((s, p) => s + (p.spread_pnl_pct ?? p.pnl_pct ?? 0), 0);
  const winners = positions.filter(p => (p.spread_pnl_pct ?? p.pnl_pct ?? 0) > 0).length;
  const losers = positions.filter(p => (p.spread_pnl_pct ?? p.pnl_pct ?? 0) < 0).length;
  const avgPnl = totalPnl / positions.length;

  // System is stops-only by design — no target_pct field exists.
  // Each scenario is SUM across positions, not per-position average.
  const allStopsPct = positions.reduce((s, p) => s + (p.daily_stop ?? p._data_levels?.daily_stop ?? 0), 0);
  const allTrailsHitPct = positions.reduce((s, p) => {
    const trail = p.trail_stop ?? p._data_levels?.trail_stop;
    return s + (trail != null ? trail : 0);
  }, 0);
  const currentPeakPct = positions.reduce((s, p) => s + (p.peak_pnl ?? p._data_levels?.peak ?? 0), 0);

  const cls = (v) => v >= 0 ? 'text-green' : 'text-red';
  const fmt = (v) => `${v >= 0 ? '+' : ''}${v.toFixed(2)}%`;

  const zoneRaw = regimeData?.zone;
  const zone = (zoneRaw && zoneRaw !== 'UNKNOWN') ? zoneRaw : 'RISK-OFF';
  const cached = _flipCache.get(zone);
  const initial = cached
    ? _flipRowContent(zone, cached, positions.length)
    : { label: `Regime flip into ${zone}`, labelCls: 'text-muted', value: 'computing…', valueCls: 'mono text-muted', title: `Fetching p95 worst Nifty 5d-after for flips into ${zone}.` };

  container.innerHTML = `
    <div class="card" style="margin-top: var(--spacing-md);">
      <h3 style="margin-bottom: var(--spacing-sm); font-size: 0.875rem;">Portfolio Aggregates</h3>
      <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: var(--spacing-md);">
        <div><div class="text-muted" style="font-size: 0.6875rem;">POSITIONS</div>
          <div class="mono" style="font-size: 1.25rem;">${positions.length}</div></div>
        <div><div class="text-muted" style="font-size: 0.6875rem;">TOTAL P&L</div>
          <div class="mono ${cls(totalPnl)}" style="font-size: 1.25rem;">${fmt(totalPnl)}</div></div>
        <div><div class="text-muted" style="font-size: 0.6875rem;">AVG P&L</div>
          <div class="mono ${cls(avgPnl)}" style="font-size: 1.25rem;">${fmt(avgPnl)}</div></div>
        <div><div class="text-muted" style="font-size: 0.6875rem;">WIN / LOSS</div>
          <div class="mono" style="font-size: 1.25rem;">${winners} / ${losers}</div></div>
      </div>
    </div>
    <div class="card" style="margin-top: var(--spacing-sm);">
      <h3 style="margin-bottom: var(--spacing-sm); font-size: 0.875rem;">
        P&L Scenarios
        <span class="text-muted" style="font-size: 0.75rem; font-weight: normal;">
          — SUM across ${positions.length} position${positions.length === 1 ? '' : 's'}
        </span>
      </h3>
      <table class="data-table">
        <thead><tr><th>Scenario</th><th>Aggregate P&L</th></tr></thead>
        <tbody>
          <tr title="SUM of current peak P&L across all open positions. If every winner had locked in at its peak.">
            <td>If all peaks had locked in</td>
            <td class="mono ${cls(currentPeakPct)}">${fmt(currentPeakPct)}</td></tr>
          <tr title="SUM of trail-stop levels. If every position exited on its trail today.">
            <td>All trails triggered</td>
            <td class="mono ${cls(allTrailsHitPct)}">${allTrailsHitPct !== 0 ? fmt(allTrailsHitPct) : '--'}</td></tr>
          <tr title="SUM of per-spread daily_stop levels. Worst-case 1-day outcome if every position hits its daily stop simultaneously.">
            <td>All daily stops hit (worst 1-day)</td>
            <td class="mono text-red">${allStopsPct !== 0 ? fmt(allStopsPct) : '--'}</td></tr>
          <tr id="scen-regime-flip" data-pos-count="${positions.length}" title="${initial.title}">
            <td class="${initial.labelCls}">${initial.label}</td>
            <td class="${initial.valueCls}">${initial.value}</td></tr>
        </tbody>
      </table>
    </div>`;

  // Always refresh in background on re-render — cached value is shown instantly,
  // network update lands when it arrives.
  _fetchFlip(zone, container);
}
