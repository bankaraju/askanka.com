// Phase C Paired Shadow card -- consumes /api/research/phase-c-options-shadow.
// Static analysis only -- informational, not actionable. Per spec §11.3.

function _esc(s) {
  if (s == null) return '';
  const d = document.createElement('div');
  d.textContent = String(s);
  return d.innerHTML;
}

function _pct(v) {
  if (v == null) return '--';
  const sign = v >= 0 ? '+' : '';
  return `${sign}${(v * 100).toFixed(2)}%`;
}

function _winPct(v) {
  if (v == null) return '--';
  return `${(v * 100).toFixed(0)}%`;
}

function _tierBadge(tier) {
  switch (tier) {
    case 'HIGH-ALPHA SYNTHETIC':
      return '<span class="badge badge--green">HA</span>';
    case 'EXPERIMENTAL':
      return '<span class="badge badge--amber">EXP</span>';
    case 'NEGATIVE CARRY':
      return '<span class="badge badge--red">NC</span>';
    default:
      return '<span class="badge badge--muted">?</span>';
  }
}

function _renderOpenPairs(open) {
  if (!open || open.length === 0) {
    return '<p class="text-muted" style="margin: 0.5rem 0;">No live OPEN pairs.</p>';
  }
  const rows = open.map(p => {
    const expiry = p.expiry_date
      ? new Date(p.expiry_date).toLocaleDateString('en-IN', { month: 'numeric', day: 'numeric' })
      : '--';
    const strike = p.option_type
      ? `${_esc(p.option_type)} ${_esc(p.strike || '')}`
      : '--';
    const shortId = _esc((p.signal_id || '').slice(-8));
    return `<tr>
      <td class="mono" style="font-size:0.72rem;" title="${_esc(p.signal_id)}">${shortId}</td>
      <td>${_esc(p.symbol)}</td>
      <td>${_esc(p.side)}</td>
      <td class="mono">${strike}</td>
      <td class="mono">${_esc(expiry)}</td>
      <td>${_tierBadge(p.drift_vs_rent_tier)}</td>
    </tr>`;
  }).join('');
  return `
    <table style="width:100%; border-collapse:collapse; font-size:0.8rem; margin-top:0.4rem;">
      <thead>
        <tr style="color:var(--text-secondary); font-size:0.72rem;">
          <th style="text-align:left; padding:0.2rem 0.4rem;">Signal</th>
          <th style="text-align:left; padding:0.2rem 0.4rem;">Symbol</th>
          <th style="text-align:left; padding:0.2rem 0.4rem;">Side</th>
          <th style="text-align:left; padding:0.2rem 0.4rem;">Strike</th>
          <th style="text-align:left; padding:0.2rem 0.4rem;">Expiry</th>
          <th style="text-align:left; padding:0.2rem 0.4rem;">Tier</th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>`;
}

function _renderCumulative(cum) {
  const n = cum.n_closed || 0;
  const unmatched = cum.n_unmatched || 0;
  if (n === 0) {
    return '<p class="text-muted" style="margin:0.5rem 0;">No closed pairs yet -- accumulating forward-only OOS.</p>';
  }
  const byTier = cum.by_tier || {};
  const tierRows = Object.entries(byTier).map(([tier, s]) => {
    const cls = s.mean_options_pnl_pct >= 0 ? 'text-green' : 'text-red';
    return `<tr style="font-size:0.78rem;">
      <td style="padding:0.15rem 0.4rem;">${_tierBadge(tier)} <span>${_esc(tier)}</span></td>
      <td class="mono" style="padding:0.15rem 0.4rem; text-align:right;">N=${_esc(s.n)}</td>
      <td class="mono" style="padding:0.15rem 0.4rem; text-align:right;">win=${_esc(_winPct(s.win_rate))}</td>
      <td class="mono ${cls}" style="padding:0.15rem 0.4rem; text-align:right;">${_esc(_pct(s.mean_options_pnl_pct))}</td>
    </tr>`;
  }).join('');

  const byExp = cum.by_expiry_day || {};
  const expRows = [
    { label: 'Yes (expiry)', key: 'true' },
    { label: 'No', key: 'false' },
  ].map(({ label, key }) => {
    const s = byExp[key] || { n: 0, win_rate: 0, mean_options_pnl_pct: 0 };
    const cls = s.mean_options_pnl_pct >= 0 ? 'text-green' : 'text-red';
    return `<tr style="font-size:0.78rem;">
      <td style="padding:0.15rem 0.4rem; color:var(--text-secondary);">${_esc(label)}</td>
      <td class="mono" style="padding:0.15rem 0.4rem; text-align:right;">N=${_esc(s.n)}</td>
      <td class="mono" style="padding:0.15rem 0.4rem; text-align:right;">win=${_esc(_winPct(s.win_rate))}</td>
      <td class="mono ${cls}" style="padding:0.15rem 0.4rem; text-align:right;">${_esc(_pct(s.mean_options_pnl_pct))}</td>
    </tr>`;
  }).join('');

  return `
    <p style="font-size:0.78rem; color:var(--text-secondary); margin:0.4rem 0 0.2rem;">
      Cumulative (N_closed=${_esc(n)}, N_unmatched=${_esc(unmatched)})
    </p>
    <p style="font-size:0.72rem; color:var(--text-muted); margin:0.2rem 0 0;">By tier:</p>
    <table style="width:100%; border-collapse:collapse; margin-bottom:0.4rem;">
      <tbody>${tierRows}</tbody>
    </table>
    <p style="font-size:0.72rem; color:var(--text-muted); margin:0.2rem 0 0;">By expiry day:</p>
    <table style="width:100%; border-collapse:collapse;">
      <tbody>${expRows}</tbody>
    </table>`;
}

export function renderPhaseCPairedShadowCard(payload) {
  // Returns empty string if payload is null (endpoint failed, .catch(() => null)).
  if (!payload) return '';
  const open = payload.open_pairs || [];
  const cum = payload.cumulative || { n_closed: 0, n_unmatched: 0, by_tier: {}, by_expiry_day: {} };
  const openLabel = `Live OPEN pairs (${open.length})`;
  return `
    <div class="digest-card">
      <div class="digest-card__title">Phase C Paired Shadow &mdash; Forensic Layer</div>
      <div class="digest-card__subtitle" style="margin-bottom:0.5rem;">${_esc(openLabel)}</div>
      ${_renderOpenPairs(open)}
      ${_renderCumulative(cum)}
    </div>`;
}
