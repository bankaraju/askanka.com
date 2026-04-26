// LIVE Monitor — open Phase C shadow positions with stops + provenance.
// Polls /api/live_monitor every 5s. Top strip shows engine/data provenance
// badges (the "did the cutover land?" answer); rows show entry, LTP, P&L,
// stops, and time-to-14:30. Status badges colour-code the active risk state.
import { get } from '../lib/api.js';

const POLL_INTERVAL_MS = 5000;

let pollHandle = null;

export async function render(container) {
  container.innerHTML = `
    <div class="live-monitor">
      <div id="live-monitor-strip" class="live-monitor__strip">
        <div class="skeleton skeleton--row"></div>
      </div>
      <div id="live-monitor-table-wrap"></div>
    </div>
  `;
  await tick();
  if (pollHandle) clearInterval(pollHandle);
  pollHandle = setInterval(tick, POLL_INTERVAL_MS);
}

export function destroy() {
  if (pollHandle) {
    clearInterval(pollHandle);
    pollHandle = null;
  }
}

async function tick() {
  let data;
  try {
    data = await get('/live_monitor');
  } catch (e) {
    document.getElementById('live-monitor-strip').innerHTML =
      `<div class="alert alert--error">Failed to fetch /api/live_monitor: ${escapeHtml(e.message)}</div>`;
    return;
  }
  renderStrip(data);
  renderTable(data);
}

function renderStrip(data) {
  const ttc = data.time_to_close_seconds;
  const ttcStr = ttc == null
    ? 'after 14:30'
    : `${Math.floor(ttc / 3600)}h ${Math.floor((ttc % 3600) / 60)}m to 14:30`;
  const agg = data.aggregate || {};
  const totalPnl = (agg.realized_pnl_pp_sum || 0) + (agg.open_marked_pnl_pp_sum || 0);
  const pnlClass = totalPnl >= 0 ? 'text-green' : 'text-red';

  const badges = data.badges || {};
  const badgeHtml = Object.entries(badges).map(([key, b]) => renderBadge(key, b)).join('');

  document.getElementById('live-monitor-strip').innerHTML = `
    <div class="live-monitor__top">
      <div class="live-monitor__regime">
        <span class="live-monitor__label">Regime</span>
        <span class="live-monitor__regime-value">${escapeHtml(data.regime || 'UNKNOWN')}</span>
      </div>
      <div class="live-monitor__pnl">
        <span class="live-monitor__label">Today P&amp;L (mark-to-LTP)</span>
        <span class="live-monitor__pnl-value mono ${pnlClass}">
          ${totalPnl >= 0 ? '+' : ''}${totalPnl.toFixed(2)}pp
        </span>
        <span class="live-monitor__sub">
          ${agg.n_open || 0} open · ${agg.n_closed || 0} closed · ${agg.n_no_ltp || 0} no LTP
        </span>
      </div>
      <div class="live-monitor__time">
        <span class="live-monitor__label">Mechanical close</span>
        <span class="live-monitor__time-value mono">${ttcStr}</span>
      </div>
    </div>
    <div class="live-monitor__badges">
      ${badgeHtml}
    </div>
  `;
}

function renderBadge(key, b) {
  const color = b.color || 'unknown';
  const ageStr = b.output_age_seconds == null ? 'n/a' : ageHuman(b.output_age_seconds);
  const ver = b.engine_version || '<unknown>';
  const expected = b.expected_engine_version || '';
  const titleParts = [
    `task: ${b.task_name || 'unknown'}`,
    `engine: ${ver}${expected && expected !== ver ? ` (config expects ${expected})` : ''}`,
    `started: ${b.started_at || 'unknown'}`,
    `age: ${ageStr}`,
    `reason: ${b.reason || ''}`,
  ];
  return `
    <div class="provenance-badge provenance-badge--${color}" title="${escapeHtml(titleParts.join('\n'))}">
      <span class="provenance-badge__dot"></span>
      <span class="provenance-badge__name">${escapeHtml(prettyKey(key))}</span>
      <span class="provenance-badge__ver mono">${escapeHtml(ver)}</span>
      <span class="provenance-badge__age mono">${escapeHtml(ageStr)}</span>
    </div>
  `;
}

function prettyKey(k) {
  return ({
    live_paper_ledger: 'Phase C ledger',
    regime: 'Regime engine',
    correlation_breaks: 'Phase C breaks',
  })[k] || k;
}

function renderTable(data) {
  const rows = data.rows || [];
  const wrap = document.getElementById('live-monitor-table-wrap');
  if (!rows.length) {
    wrap.innerHTML = `
      <div class="empty-state">
        <p>No open Phase C shadow positions for today.</p>
        <p class="empty-state__sub">
          Phase C shadow opens at 09:25 IST. If today is a trading day past that time
          and this is empty, check the <code>live_paper_ledger.json</code> badge above.
        </p>
      </div>
    `;
    return;
  }
  wrap.innerHTML = `
    <table class="data-table data-table--live">
      <thead>
        <tr>
          <th>Status</th>
          <th>Ticker</th>
          <th>Side</th>
          <th>Entry</th>
          <th>LTP</th>
          <th>P&amp;L</th>
          <th>ATR stop</th>
          <th>Trail stop</th>
          <th>Z</th>
          <th>Class</th>
          <th>Open</th>
        </tr>
      </thead>
      <tbody>
        ${rows.map(renderRow).join('')}
      </tbody>
    </table>
  `;
}

function renderRow(r) {
  const statusClass = `status status--${(r.status || 'UNKNOWN').toLowerCase()}`;
  const pnlClass = r.pnl_pct == null ? '' : (r.pnl_pct >= 0 ? 'text-green' : 'text-red');
  const pnlStr = r.pnl_pct == null ? '—' : `${r.pnl_pct >= 0 ? '+' : ''}${r.pnl_pct.toFixed(2)}%`;
  const sideClass = r.side === 'LONG' ? 'side side--long' : 'side side--short';
  return `
    <tr class="row--${(r.status || 'unknown').toLowerCase()}">
      <td><span class="${statusClass}">${escapeHtml(r.status || '—')}</span></td>
      <td class="mono">${escapeHtml(r.ticker || '')}</td>
      <td><span class="${sideClass}">${escapeHtml(r.side || '')}</span></td>
      <td class="mono">${fmtPrice(r.entry)}</td>
      <td class="mono">${fmtPrice(r.ltp)}</td>
      <td class="mono ${pnlClass}">${pnlStr}</td>
      <td class="mono">${fmtPrice(r.atr_stop)}</td>
      <td class="mono">${fmtPrice(r.trail_stop)}</td>
      <td class="mono">${r.z_score == null ? '—' : r.z_score.toFixed(1)}</td>
      <td>${escapeHtml(r.classification || '')}</td>
      <td class="mono">${escapeHtml(timeOnly(r.entry_time))}</td>
    </tr>
  `;
}

function fmtPrice(v) {
  if (v == null || v === 0) return '—';
  if (v >= 1000) return v.toFixed(1);
  return v.toFixed(2);
}

function timeOnly(s) {
  if (!s) return '—';
  if (typeof s !== 'string') return '';
  if (s.length >= 16 && s.includes('T')) return s.slice(11, 16);
  if (s.length >= 16 && s.includes(' ')) return s.slice(11, 16);
  if (s.length >= 5) return s.slice(0, 5);
  return s;
}

function ageHuman(seconds) {
  if (seconds < 60) return `${Math.round(seconds)}s`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m`;
  if (seconds < 86400) return `${(seconds / 3600).toFixed(1)}h`;
  return `${(seconds / 86400).toFixed(1)}d`;
}

function escapeHtml(s) {
  if (s == null) return '';
  return String(s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}
