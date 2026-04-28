// Portfolio aggregates + simple P&L scenarios for the Dashboard footer.
// Inputs: positions array (each with spread_pnl_pct, long_legs, short_legs).
import { get } from '../lib/api.js';

// Cache by zone so the 30s dashboard re-render doesn't re-spam the endpoint.
const _flipCache = new Map();
const _inflight = new Map();

function _fetchFlip(zone, container, fmt, cls) {
  if (_inflight.get(zone)) return;
  _inflight.set(zone, true);
  get(`/risk/regime-flip?to_zone=${encodeURIComponent(zone)}`)
    .then((data) => {
      // Only cache successful responses, so a transient failure doesn't
      // pin a broken state until zone changes or the page reloads.
      _flipCache.set(zone, data);
      _patchRow(container, zone, data, fmt, cls);
    })
    .catch(() => {
      // Render the fallback row, but do NOT pollute the cache — the next
      // 30s re-render should retry the fetch cleanly.
      _patchRow(container, zone, { __error: true }, fmt, cls);
    })
    .finally(() => { _inflight.delete(zone); });
}

function _flipRowContent(zone, data, positionCount, fmt, cls) {
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
  const pct = data.percentile ?? 95;
  return {
    label: `Regime flip into ${zone} (p${pct} of N=${nFlips} historical flips)`,
    labelCls: '',
    value: fmt(worst),
    valueCls: `mono ${cls(worst)}`,
    title: `p${pct} worst Nifty 5d-after across ${nFlips} historical flips into ${zone}. Proxy: per-position Nifty drawdown.`,
  };
}

function _patchRow(container, zone, data, fmt, cls) {
  const row = container.querySelector('#scen-regime-flip');
  if (!row) return;
  const posCount = Number(row.getAttribute('data-pos-count') || '0');
  const content = _flipRowContent(zone, data, posCount, fmt, cls);
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

  // Per-trade % is the unit. SUM across N positions overstates the picture
  // (74.5% across 60 trades is +1.24% / trade, not +74.5% portfolio). We
  // headline the per-trade average and keep SUM as a secondary 1u/trade view.
  const pnlOf = (p) => (p.spread_pnl_pct ?? p.pnl_pct ?? 0);
  const pnls = positions.map(pnlOf);
  const totalPnl = pnls.reduce((s, v) => s + v, 0);
  const avgPnl = totalPnl / positions.length;
  const winners = pnls.filter(v => v > 0).length;
  const losers = pnls.filter(v => v < 0).length;
  const flat = pnls.filter(v => v === 0).length;

  // Each scenario is per-trade AVERAGE across the basket — a position-sized
  // 1u/trade portfolio. Summing per-trade % overstates risk by N×.
  const avgOf = (key, fallbackKey) => {
    const vals = positions.map(p => p[key] ?? p._data_levels?.[fallbackKey ?? key] ?? 0);
    return vals.reduce((s, v) => s + v, 0) / positions.length;
  };
  const allStopsPct = avgOf('daily_stop');
  const allTrailsHitPct = positions
    .map(p => p.trail_stop ?? p._data_levels?.trail_stop)
    .filter(v => v != null)
    .reduce((s, v, _, arr) => s + v / arr.length, 0);
  const currentPeakPct = avgOf('peak_pnl', 'peak');

  const cls = (v) => v >= 0 ? 'text-green' : 'text-red';
  const fmt = (v) => `${v >= 0 ? '+' : ''}${v.toFixed(2)}%`;

  const zoneRaw = regimeData?.zone;
  const zone = (zoneRaw && zoneRaw !== 'UNKNOWN') ? zoneRaw : 'RISK-OFF';
  const cached = _flipCache.get(zone);
  const initial = cached
    ? _flipRowContent(zone, cached, positions.length, fmt, cls)
    : { label: `Regime flip into ${zone}`, labelCls: 'text-muted', value: 'computing…', valueCls: 'mono text-muted', title: `Fetching p95 worst Nifty 5d-after for flips into ${zone}.` };

  const flatNote = flat > 0
    ? `<span class="text-muted" style="font-size: 0.625rem; margin-left: 4px;">(${flat} unmoved)</span>`
    : '';
  const sumNote = `<span class="text-muted" style="font-size: 0.625rem; margin-left: 4px;">(1u/trade sum: ${fmt(totalPnl)})</span>`;

  container.innerHTML = `
    <div class="card" style="margin-top: var(--spacing-md);">
      <h3 style="margin-bottom: var(--spacing-sm); font-size: 0.875rem;">
        Portfolio Aggregates
        <span class="text-muted" style="font-size: 0.6875rem; font-weight: normal;">
          — per-position averages (each trade is 1 unit)
        </span>
      </h3>
      <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: var(--spacing-md);">
        <div><div class="text-muted" style="font-size: 0.6875rem;">POSITIONS</div>
          <div class="mono" style="font-size: 1.25rem;">${positions.length}</div></div>
        <div title="Per-trade average P&L across all ${positions.length} open positions."><div class="text-muted" style="font-size: 0.6875rem;">AVG P&L / TRADE</div>
          <div class="mono ${cls(avgPnl)}" style="font-size: 1.25rem;">${fmt(avgPnl)} ${sumNote}</div></div>
        <div><div class="text-muted" style="font-size: 0.6875rem;">WIN / FLAT / LOSS</div>
          <div class="mono" style="font-size: 1.25rem;">
            <span class="text-green">${winners}</span> /
            <span class="text-muted">${flat}</span> /
            <span class="text-red">${losers}</span>${flatNote}
          </div></div>
        <div title="${flat > 0 ? `${flat} positions have entry == current — likely intraday rows the LTP refresher hasn't marked yet.` : 'All positions are marked.'}">
          <div class="text-muted" style="font-size: 0.6875rem;">MARK FRESHNESS</div>
          <div class="mono" style="font-size: 1.25rem;">
            ${flat === 0 ? '<span class="text-green">all marked</span>' : `<span class="text-yellow">${positions.length - flat} / ${positions.length} marked</span>`}
          </div></div>
      </div>
    </div>
    <div class="card" style="margin-top: var(--spacing-sm);">
      <h3 style="margin-bottom: var(--spacing-sm); font-size: 0.875rem;">
        P&L Scenarios
        <span class="text-muted" style="font-size: 0.75rem; font-weight: normal;">
          — per-trade average across ${positions.length} position${positions.length === 1 ? '' : 's'}
        </span>
      </h3>
      <table class="data-table">
        <thead><tr><th>Scenario</th><th>Avg P&L / trade</th></tr></thead>
        <tbody>
          <tr title="Mean current peak P&L across all open positions. If every winner had locked in at its peak.">
            <td>If all peaks had locked in</td>
            <td class="mono ${cls(currentPeakPct)}">${fmt(currentPeakPct)}</td></tr>
          <tr title="Mean trail-stop level across positions with an armed trail. If every armed position exited on its trail today.">
            <td>All armed trails triggered</td>
            <td class="mono ${cls(allTrailsHitPct)}">${allTrailsHitPct !== 0 ? fmt(allTrailsHitPct) : '--'}</td></tr>
          <tr title="Mean per-spread daily_stop level. Worst-case 1-day outcome per trade if every position hits its daily stop simultaneously.">
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
  _fetchFlip(zone, container, fmt, cls);
}
