// LIVE Monitor — open Phase C shadow positions with stops + provenance.
// Polls /api/live_monitor every 10s. Top strip shows engine/data provenance
// badges (the "did the cutover land?" answer); rows show entry, LTP, P&L,
// stops, and time-to-14:30. Status badges colour-code the active risk state.
//
// Why 10s and not 5s: each poll triggers a Kite bulk LTP fetch on the
// server (~2s warm, longer first call). 5s polling stacked requests because
// successive calls landed before the prior one returned. 10s gives the
// server breathing room and still feels live for paper-trade monitoring.
// LTP precision under 10s isn't actionable — the only time-critical event
// is the 14:30 mechanical close, and that fires from the scheduler, not
// the UI.
import { get } from '../lib/api.js';
import { renderTabHeader } from '../components/tab-header.js';

const HEADER_PROPS = {
  title: 'Live Monitor',
  subtitle: 'Open paper positions across Phase C + H-001/H-002. Live LTP, P&L marked-to-LTP (gross + net of round-trip cost), ATR + trail stops, time-to-14:30 mechanical close. Shadow only.',
  cadence: 'Server LTP refresh: every poll, 3s in-process cache. Frontend poll: 10s. Mechanical close: 14:30 IST (AnkaPhaseCShadowClose, AnkaH20260426001PaperClose).',
};

const POLL_INTERVAL_MS = 10000;

let pollHandle = null;
// Sort state persists across polls so the user's chosen ordering survives the
// 5s refresh. `key=null` means "default ordering" (entry_time ascending).
let sortKey = null;
let sortDir = 'asc';

// Column registry. `key` is the field on the row dict; `numeric` decides the
// comparator. `getter` is optional override for derived/composite values.
const COLUMNS = [
  { key: 'engine',        label: 'Engine',     numeric: false },
  { key: 'status',        label: 'Status',     numeric: false },
  { key: 'ticker',        label: 'Ticker',     numeric: false },
  { key: 'sector_display', label: 'Sector',    numeric: false,
    title: 'Normalized sector from sector_taxonomy.json (resolved at module load via SectorMapper).' },
  { key: 'side',          label: 'Side',       numeric: false },
  { key: 'entry',         label: 'Entry',      numeric: true  },
  { key: 'ltp',           label: 'LTP',        numeric: true  },
  { key: 'pnl_pct',       label: 'P&L',        numeric: true  },
  { key: 'atr_stop',      label: 'ATR stop',   numeric: true  },
  { key: 'trail_stop',    label: 'Trail stop', numeric: true  },
  { key: 'zsort',         label: 'Z / σ',      numeric: true,
    getter: (r) => r.z_score != null
      ? Math.abs(r.z_score)
      : sigmaBucketSortKey(r.sigma_bucket) },
  { key: 'geometry',      label: 'Geo',        numeric: false,
    title: 'Pure price-action geometry (LAG = stock behind peer / OVERSHOOT = stock past peer / DEGENERATE = move too small). PCR-free.' },
  { key: 'classification', label: 'Class',     numeric: false,
    title: 'Geometric classification of the break (LAG / OVERSHOOT / DEGENERATE). PCR-free as of 2026-04-27 — per-stock PCR was illiquid and not a gate.' },
  { key: 'filter_tag',    label: 'Filter',     numeric: false,
    title: 'Display-only VWAP-deviation cohort tag (KEEP / DROP / WATCH). Computed from vwap_dev_signed_pct vs frozen tertile cuts. Not yet a live gate per H-001 single-touch holdout discipline.' },
  { key: 'entry_time',    label: 'Open',       numeric: false },
];

// Sigma bucket strings ("[2.0,3.0)", "[3.0,4.0)", ...) sorted by lower bound
// so they order numerically alongside z_score values.
function sigmaBucketSortKey(b) {
  if (!b) return null;
  const m = String(b).match(/[\d.]+/);
  return m ? parseFloat(m[0]) : null;
}

export async function render(container) {
  container.innerHTML = `
    ${renderTabHeader(HEADER_PROPS)}
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
  const meanGross = agg.mean_pnl_pct_gross == null ? 0 : agg.mean_pnl_pct_gross;
  const meanNet = agg.mean_pnl_pct_net == null ? 0 : agg.mean_pnl_pct_net;
  const pnlClass = meanGross >= 0 ? 'text-green' : 'text-red';
  const pnlClassNet = meanNet >= 0 ? 'text-green' : 'text-red';
  const rtCost = agg.round_trip_cost_pct == null ? 0.10 : agg.round_trip_cost_pct;
  const nWithPnl = agg.n_with_pnl || 0;
  const nTrades = (agg.n_open || 0) + (agg.n_closed || 0);

  const badges = data.badges || {};
  const badgeHtml = Object.entries(badges).map(([key, b]) => renderBadge(key, b)).join('');

  document.getElementById('live-monitor-strip').innerHTML = `
    <div class="live-monitor__top">
      <div class="live-monitor__regime">
        <span class="live-monitor__label">Regime</span>
        <span class="live-monitor__regime-value">${escapeHtml(data.regime || 'UNKNOWN')}</span>
      </div>
      <div class="live-monitor__pnl">
        <span class="live-monitor__label">Avg P&amp;L per trade (mark-to-LTP)</span>
        <span class="live-monitor__pnl-value mono ${pnlClass}" title="Equal-weighted average across ${nWithPnl} marked trades. Same as portfolio % return if sized equally.">
          ${meanGross >= 0 ? '+' : ''}${meanGross.toFixed(2)}% <span class="live-monitor__pnl-tag">gross</span>
        </span>
        <span class="live-monitor__pnl-net mono ${pnlClassNet}" title="Net of ${(rtCost * 100).toFixed(0)} bps round-trip cost per trade. Covers brokerage + STT + exchange + SEBI + stamp duty + GST.">
          ${meanNet >= 0 ? '+' : ''}${meanNet.toFixed(2)}% <span class="live-monitor__pnl-tag">net</span>
        </span>
        <span class="live-monitor__sub">
          ${agg.n_open || 0} open · ${agg.n_closed || 0} closed · ${agg.n_no_ltp || 0} no LTP
          · ${nWithPnl} marked · cost ${(rtCost * 100).toFixed(0)} bps/trade
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
        <p>No open paper positions for today.</p>
        <p class="empty-state__sub">
          Phase C shadow opens at 09:25 IST and H-001/H-002 paper opens at 09:30 IST.
          If today is a trading day past those times and this is empty, check the
          provenance badges above.
        </p>
      </div>
    `;
    return;
  }
  // Engine breakdown for the small caption above the table.
  const byEngine = rows.reduce((acc, r) => {
    const e = r.engine || 'Phase C';
    acc[e] = (acc[e] || 0) + 1;
    return acc;
  }, {});
  const breakdownStr = Object.entries(byEngine)
    .map(([e, n]) => `<span class="engine-pill engine-pill--${e.toLowerCase().replace(/[^a-z0-9]/g,'')}">${escapeHtml(e)} ${n}</span>`)
    .join(' ');
  const sortedRows = sortRows(rows);
  const headHtml = COLUMNS.map((c) => {
    const isActive = sortKey === c.key;
    const arrow = isActive ? (sortDir === 'asc' ? ' ▲' : ' ▼') : '';
    const cls = `sortable${isActive ? ' sortable--active' : ''}`;
    const title = c.title ? ` title="${escapeHtml(c.title)}"` : '';
    return `<th class="${cls}" data-sort-key="${escapeHtml(c.key)}"${title}>${escapeHtml(c.label)}${arrow}</th>`;
  }).join('');
  wrap.innerHTML = `
    <div class="live-monitor__engine-breakdown">${breakdownStr}</div>
    <table class="data-table data-table--live">
      <thead>
        <tr>${headHtml}</tr>
      </thead>
      <tbody>
        ${sortedRows.map(renderRow).join('')}
      </tbody>
    </table>
  `;
  wrap.querySelectorAll('th.sortable').forEach((th) => {
    th.addEventListener('click', () => {
      const k = th.getAttribute('data-sort-key');
      if (sortKey === k) {
        sortDir = sortDir === 'asc' ? 'desc' : 'asc';
      } else {
        sortKey = k;
        // Numeric columns default desc (highest first — most useful for P&L);
        // text columns default asc (alphabetical).
        const col = COLUMNS.find((c) => c.key === k);
        sortDir = col && col.numeric ? 'desc' : 'asc';
      }
      renderTable(data);
    });
  });
}

function sortRows(rows) {
  if (!sortKey) {
    return [...rows].sort((a, b) => (a.entry_time || '').localeCompare(b.entry_time || ''));
  }
  const col = COLUMNS.find((c) => c.key === sortKey);
  if (!col) return rows;
  const getter = col.getter || ((r) => r[col.key]);
  const dir = sortDir === 'asc' ? 1 : -1;
  return [...rows].sort((a, b) => {
    const va = getter(a);
    const vb = getter(b);
    // Nulls always sort last regardless of direction — keeps "no LTP" rows
    // out of the way whether you want best-first or worst-first.
    const aNull = va == null || va === '';
    const bNull = vb == null || vb === '';
    if (aNull && bNull) return 0;
    if (aNull) return 1;
    if (bNull) return -1;
    if (col.numeric) return (va - vb) * dir;
    return String(va).localeCompare(String(vb)) * dir;
  });
}

function renderRow(r) {
  const statusClass = `status status--${(r.status || 'UNKNOWN').toLowerCase()}`;
  const pnlClass = r.pnl_pct == null ? '' : (r.pnl_pct >= 0 ? 'text-green' : 'text-red');
  const pnlStr = r.pnl_pct == null ? '—' : `${r.pnl_pct >= 0 ? '+' : ''}${r.pnl_pct.toFixed(2)}%`;
  const sideClass = r.side === 'LONG' ? 'side side--long' : 'side side--short';
  const engine = r.engine || 'PhaseC';
  const enginePill = engine === 'H-001'
    ? (r.regime_gate_pass ? 'H-001/H-002' : 'H-001')
    : 'Phase C';
  const engineCls = engine.toLowerCase().replace(/[^a-z0-9]/g,'');
  // For H-001 use sigma_bucket as the "Z / σ" cell (no z_score available).
  const zCell = r.z_score != null
    ? r.z_score.toFixed(1)
    : (r.sigma_bucket || '—');
  // Geo cell: pure-price-action classification (PCR-free). Empty when the
  // ticker is no longer in correlation_breaks.json (|z| dropped below 2.0
  // since entry).
  const geoCell = r.geometry
    ? `<span class="geo-pill geo-pill--${r.geometry.toLowerCase()}">${escapeHtml(r.geometry)}</span>`
    : '<span class="geo-pill geo-pill--stale" title="No longer in current breaks scan — may have reverted below 2σ">—</span>';
  // Class cell: PCR-free geometric classification (LAG / OVERSHOOT / DEGENERATE).
  const classCell = r.classification
    ? `<span title="${escapeHtml(r.classification)}">${escapeHtml(r.classification)}</span>`
    : '—';
  // Filter cell: VWAP-deviation cohort tag (KEEP / DROP / WATCH). Display-only;
  // not yet a live gate during the H-001 single-touch holdout. Tooltip shows
  // the raw signed VWAP deviation so the badge is auditable at a glance.
  // vwap_dev_signed_pct is already in percent units (computed as
  // (px - vwap)/vwap * 100 at source in intraday_panel_v1.py:92), so we
  // just format — no extra multiply.
  const vwapPctStr = r.vwap_dev_signed_pct != null
    ? `${parseFloat(r.vwap_dev_signed_pct).toFixed(2)}%`
    : 'n/a';
  const filterTag = r.filter_tag || null;
  const filterCell = filterTag
    ? `<span class="filter-pill filter-pill--${filterTag.toLowerCase()}" title="VWAP signed dev: ${vwapPctStr}">${escapeHtml(filterTag)}</span>`
    : '<span class="filter-pill filter-pill--none" title="No filter tag (Phase C row or VWAP unavailable)">—</span>';
  return `
    <tr class="row--${(r.status || 'unknown').toLowerCase()} row--engine-${engineCls}">
      <td><span class="engine-pill engine-pill--${engineCls}">${escapeHtml(enginePill)}</span></td>
      <td><span class="${statusClass}">${escapeHtml(r.status || '—')}</span></td>
      <td class="mono">${r.ticker
        ? `<a class="ticker-link" data-ticker="${escapeHtml(r.ticker)}" href="#" role="button">${escapeHtml(r.ticker)}</a>`
        : ''}</td>
      <td>${r.sector_display
        ? `<span class="sector-pill" title="${escapeHtml(r.sector || '')}">${escapeHtml(r.sector_display)}</span>`
        : '<span class="sector-pill sector-pill--unknown">—</span>'}</td>
      <td><span class="${sideClass}">${escapeHtml(r.side || '')}</span></td>
      <td class="mono">${fmtPrice(r.entry)}</td>
      <td class="mono">${fmtPrice(r.ltp)}</td>
      <td class="mono ${pnlClass}">${pnlStr}</td>
      <td class="mono">${fmtPrice(r.atr_stop)}</td>
      <td class="mono">${fmtPrice(r.trail_stop)}</td>
      <td class="mono">${escapeHtml(String(zCell))}</td>
      <td>${geoCell}</td>
      <td>${classCell}</td>
      <td>${filterCell}</td>
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
