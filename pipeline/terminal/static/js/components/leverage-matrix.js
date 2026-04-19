/**
 * Leverage Matrix card — renders 3-tier Drift vs Rent grid for a spread.
 *
 * Usage: renderLeverageCard(matrix) → HTML string
 */

const VERDICT_STYLES = {
  'HIGH-ALPHA SYNTHETIC': { cls: 'badge--green', label: 'HIGH-ALPHA' },
  'NEGATIVE CARRY': { cls: 'badge--red', label: 'NEG CARRY' },
  'EXPERIMENTAL': { cls: 'badge--amber', label: 'EXPERIMENTAL' },
};

const BADGE_STYLES = {
  'NEGATIVE_CARRY': { cls: 'badge--red', label: 'NEGATIVE CARRY' },
  'LOW_CONVICTION_GAMMA': { cls: 'badge--amber', label: 'LOW CONVICTION GAMMA' },
  'DRIFT_EXCEEDS_RENT': { cls: 'badge--green', label: 'DRIFT > RENT' },
};

export function renderLeverageCard(matrix) {
  if (!matrix) return '';

  if (!matrix.grounding_ok) {
    return `
      <div class="digest-card" style="opacity: 0.5;">
        <div class="digest-card__title">${esc(matrix.spread_name || '?')}</div>
        <div class="text-muted" style="font-size: 0.8125rem;">
          Vol data unavailable — ${esc(matrix.reason || 'Kite session may be stale')}
        </div>
      </div>`;
  }

  const convBadge = matrix.conviction_score >= 65
    ? `<span class="badge badge--green">${matrix.conviction_score}</span>`
    : `<span class="badge badge--amber">${matrix.conviction_score}</span>`;

  const tierRows = (matrix.tiers || []).map(t => {
    const v = VERDICT_STYLES[t.classification] || { cls: 'badge--muted', label: t.classification };
    const edgeCls = t.net_edge_pct > 0 ? 'text-green' : 'text-red';
    const edgeSign = t.net_edge_pct > 0 ? '+' : '';
    return `
      <tr>
        <td class="mono">${formatHorizon(t.horizon)}</td>
        <td class="mono">${t.premium_cost_pct.toFixed(2)}%</td>
        <td class="mono">${t.total_rent_pct.toFixed(2)}%</td>
        <td class="mono">${t.expected_drift_pct.toFixed(2)}%</td>
        <td class="mono ${edgeCls}">${edgeSign}${t.net_edge_pct.toFixed(2)}%</td>
        <td><span class="badge ${v.cls}">${v.label}</span></td>
      </tr>`;
  }).join('');

  const badgesHtml = (matrix.caution_badges || []).map(b => {
    const s = BADGE_STYLES[b] || { cls: 'badge--muted', label: b };
    return `<span class="badge ${s.cls}">${s.label}</span>`;
  }).join(' ');

  const volInfo = matrix.long_side_vol != null
    ? `<span class="text-muted" style="font-size: 0.6875rem;">
        Long vol: ${(matrix.long_side_vol * 100).toFixed(1)}% · Short vol: ${(matrix.short_side_vol * 100).toFixed(1)}%
       </span>`
    : '';

  return `
    <div class="digest-card">
      <div style="display: flex; justify-content: space-between; align-items: center;">
        <div class="digest-card__title">${esc(matrix.spread_name)}</div>
        ${convBadge}
      </div>
      <div class="digest-card__subtitle">Drift vs Rent — Leverage Matrix</div>
      <table class="data-table" style="margin-top: var(--spacing-sm);">
        <thead>
          <tr>
            <th>Tier</th><th>Premium</th><th>5d Rent</th>
            <th>Exp. Drift</th><th>Net Edge</th><th>Verdict</th>
          </tr>
        </thead>
        <tbody>${tierRows}</tbody>
      </table>
      ${badgesHtml ? `<div style="margin-top: var(--spacing-sm);">${badgesHtml}</div>` : ''}
      ${volInfo ? `<div style="margin-top: var(--spacing-xs);">${volInfo}</div>` : ''}
    </div>`;
}

export function renderShadowStrip(shadows) {
  if (!shadows || shadows.length === 0) {
    return `
      <div class="digest-card">
        <div class="digest-card__title">Forward Test</div>
        <div class="digest-card__subtitle">No synthetic options trades tracked yet</div>
        <p class="text-muted" style="font-size: 0.8125rem;">
          Shadow entries appear when 65+ conviction signals show positive net edge
        </p>
      </div>`;
  }

  const rows = shadows.map(s => {
    const legs = [...(s.long_legs || []), ...(s.short_legs || [])];
    const tickers = legs.map(l =>
      `<span class="clickable-ticker" data-ticker="${esc(l.ticker)}" style="cursor:pointer; text-decoration: underline;">${esc(l.ticker)}</span>`
    ).join(', ');

    const daysHeld = s.daily_marks ? s.daily_marks.length : 0;
    const lastMark = s.daily_marks && s.daily_marks.length > 0 ? s.daily_marks[s.daily_marks.length - 1] : {};

    const futPnl = s.final_pnl_futures_pct != null ? s.final_pnl_futures_pct : (lastMark.spread_move_pct || 0);
    const opt1m = s.final_pnl_1m_options_pct != null ? s.final_pnl_1m_options_pct : (lastMark.repriced_1m_pnl_pct || 0);
    const opt15d = s.final_pnl_15d_options_pct != null ? s.final_pnl_15d_options_pct : (lastMark.repriced_15d_pnl_pct || 0);

    const pnlCls = v => v >= 0 ? 'text-green' : 'text-red';
    const pnlFmt = v => `${v >= 0 ? '+' : ''}${v.toFixed(2)}%`;
    const statusBadge = s.status === 'OPEN'
      ? '<span class="badge badge--blue">OPEN</span>'
      : `<span class="badge badge--muted">${s.status}</span>`;

    return `
      <tr>
        <td>${esc(s.spread_name)}</td>
        <td>${tickers}</td>
        <td class="mono">${(s.entry_timestamp || '').slice(0, 10)}</td>
        <td class="mono">${daysHeld}d</td>
        <td class="mono ${pnlCls(futPnl)}">${pnlFmt(futPnl)}</td>
        <td class="mono ${pnlCls(opt1m)}">${pnlFmt(opt1m)}</td>
        <td class="mono ${pnlCls(opt15d)}">${pnlFmt(opt15d)}</td>
        <td>${statusBadge}</td>
      </tr>`;
  }).join('');

  return `
    <div class="digest-card">
      <div class="digest-card__title">Forward Test — Options vs Futures</div>
      <div class="digest-card__subtitle">Would options have beaten futures?</div>
      <table class="data-table" style="margin-top: var(--spacing-sm);">
        <thead>
          <tr>
            <th>Spread</th><th>Tickers</th><th>Entry</th><th>Held</th>
            <th>Futures</th><th>1M Opt</th><th>15D Opt</th><th>Status</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    </div>`;
}

function formatHorizon(h) {
  return { '1_month': '1-Month', '15_day': '15-Day', 'same_day': 'Same-Day' }[h] || h;
}

function esc(s) {
  if (!s) return '';
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}
