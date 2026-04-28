// Karpathy v1 holdout card for Trading tab.
// Renders OPEN + CLOSED rows from /api/research/karpathy-v1.
// Spec: H-2026-04-29-ta-karpathy-v1, holdout 2026-04-29..2026-05-28.
import { get } from '../lib/api.js';

function _esc(s) {
  if (s == null) return '';
  const d = document.createElement('div');
  d.textContent = String(s);
  return d.innerHTML;
}

function _fmtPct(v, digits = 2) {
  if (v == null || !Number.isFinite(v)) return '—';
  const sign = v >= 0 ? '+' : '';
  return `${sign}${v.toFixed(digits)}%`;
}

function _fmtPx(v) {
  if (v == null || !Number.isFinite(v)) return '—';
  return v.toFixed(2);
}

function _fmtProb(v) {
  if (v == null || !Number.isFinite(v)) return '—';
  return v.toFixed(3);
}

function _pnlClass(v) {
  if (v == null || !Number.isFinite(v)) return '';
  if (v > 0) return 'text-green';
  if (v < 0) return 'text-red';
  return 'text-muted';
}

function _statusBadge(row) {
  const s = row.status || '';
  const cls = s === 'OPEN' ? 'badge--gold'
            : s === 'CLOSED' ? 'badge--muted'
            : 'badge--muted';
  const test = row.is_test ? '<span class="badge badge--amber" title="Synthetic test row — purged before holdout">TEST</span>' : '';
  return `<span class="badge ${cls}">${_esc(s)}</span>${test}`;
}

function _rowHtml(row) {
  const sideClass = row.side === 'LONG' ? 'text-green' : 'text-red';
  const pnl = row.pnl_pct;
  return `
    <tr data-ticker="${_esc(row.ticker)}" class="${row.is_test ? 'karp-test' : ''}">
      <td><span class="${sideClass}">${_esc(row.side)}</span></td>
      <td class="karp-ticker" style="cursor:pointer; color:var(--accent-gold);">${_esc(row.ticker)}</td>
      <td class="text-muted">${_esc(row.regime || '—')}</td>
      <td class="num">${_fmtProb(row.p_long)}</td>
      <td class="num">${_fmtProb(row.p_short)}</td>
      <td class="num">${_fmtPx(row.entry_px)}</td>
      <td class="num">${_fmtPx(row.stop_px)}</td>
      <td class="num">${_fmtPx(row.exit_px)}</td>
      <td class="num ${_pnlClass(pnl)}">${_fmtPct(pnl)}</td>
      <td>${_statusBadge(row)}</td>
      <td class="text-muted" style="font-size:0.7rem;">${_esc(row.exit_reason || '')}</td>
    </tr>`;
}

function _summaryHtml(s, doc) {
  const winRate = (s.win_rate_pct == null) ? '—' : `${s.win_rate_pct.toFixed(1)}%`;
  const avgPnl = (s.avg_pnl_pct == null) ? '—' : _fmtPct(s.avg_pnl_pct);
  const holdout = doc.holdout_window || ['?', '?'];
  const holdoutStatus = doc.in_holdout
    ? `<span class="text-green">LIVE</span>`
    : `<span class="text-muted">starts ${_esc(holdout[0])}</span>`;
  return `
    <div class="metrics-row" style="margin-bottom: var(--spacing-sm);">
      <div class="metrics-cell">
        <div class="metrics-cell__label">Engine</div>
        <div class="metrics-cell__value">ta_karpathy_v1</div>
      </div>
      <div class="metrics-cell">
        <div class="metrics-cell__label">Holdout</div>
        <div class="metrics-cell__value">${holdoutStatus}</div>
      </div>
      <div class="metrics-cell">
        <div class="metrics-cell__label">OPEN / CLOSED</div>
        <div class="metrics-cell__value">${s.n_open} / ${s.n_closed}</div>
      </div>
      <div class="metrics-cell">
        <div class="metrics-cell__label">Win rate</div>
        <div class="metrics-cell__value">${winRate}</div>
      </div>
      <div class="metrics-cell">
        <div class="metrics-cell__label">Avg P&L / trade</div>
        <div class="metrics-cell__value ${_pnlClass(s.avg_pnl_pct)}">${avgPnl}</div>
      </div>
      ${s.n_test ? `<div class="metrics-cell"><div class="metrics-cell__label">Test rows</div><div class="metrics-cell__value text-amber">${s.n_test}</div></div>` : ''}
    </div>`;
}

export async function render(container) {
  if (!container) return;
  container.innerHTML = `
    <div style="margin-bottom: var(--spacing-md);">
      <h3 style="margin: 0 0 var(--spacing-xs) 0; font-size: 1rem;">
        Karpathy v1 — per-stock TA Lasso (top-10 NIFTY pilot)
      </h3>
      <div class="text-muted" style="font-size: 0.75rem;">
        Forward holdout 2026-04-29 → 2026-05-28. Per-cell ATR(14)×2 stops, 09:15→15:25 IST.
        Spec: H-2026-04-29-ta-karpathy-v1.
      </div>
    </div>
    <div id="karp-summary"></div>
    <div id="karp-table-wrap"></div>`;

  let doc;
  try {
    doc = await get('/research/karpathy-v1');
  } catch (err) {
    container.querySelector('#karp-table-wrap').innerHTML =
      `<div class="empty-state"><p>Failed to load Karpathy ledger: ${_esc(err.message)}</p></div>`;
    return;
  }

  const rows = doc.rows || [];
  const summary = doc.summary || {};
  container.querySelector('#karp-summary').innerHTML = _summaryHtml(summary, doc);

  const wrap = container.querySelector('#karp-table-wrap');
  if (rows.length === 0) {
    const msg = doc.in_holdout
      ? 'No positions yet today. Card auto-populates after 09:15 IST open.'
      : `Holdout window opens ${_esc(doc.holdout_window?.[0] || '2026-04-29')}.`;
    wrap.innerHTML = `<div class="empty-state"><p>${msg}</p></div>`;
    return;
  }

  const open = rows.filter(r => r.status === 'OPEN');
  const closed = rows.filter(r => r.status === 'CLOSED');
  const ordered = [...open, ...closed];

  wrap.innerHTML = `
    <table class="data-table">
      <thead>
        <tr>
          <th>Side</th>
          <th>Ticker</th>
          <th>Regime</th>
          <th class="num">p_long</th>
          <th class="num">p_short</th>
          <th class="num">Entry</th>
          <th class="num">Stop</th>
          <th class="num">Exit</th>
          <th class="num">P&L</th>
          <th>Status</th>
          <th>Exit reason</th>
        </tr>
      </thead>
      <tbody>
        ${ordered.map(_rowHtml).join('')}
      </tbody>
    </table>`;

  // Click-to-chart on ticker cells (delegated).
  wrap.addEventListener('click', (ev) => {
    const cell = ev.target.closest('.karp-ticker');
    if (!cell) return;
    const tr = cell.closest('tr');
    const ticker = tr?.dataset?.ticker;
    if (!ticker) return;
    const evt = new CustomEvent('open-chart', { detail: { ticker }, bubbles: true });
    cell.dispatchEvent(evt);
  });
}

export function destroy() {}
