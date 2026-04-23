import { get } from '../lib/api.js';

let _refreshTimer = null;

function _esc(s) {
  if (s == null) return '';
  const d = document.createElement('div');
  d.textContent = String(s);
  return d.innerHTML;
}

function _istHour() {
  const h = new Date().toLocaleString('en-US', { timeZone: 'Asia/Kolkata', hour: 'numeric', hour12: false });
  return parseInt(h, 10);
}

function _isStale(isoTimestamp) {
  if (!isoTimestamp) return true;
  const hours = _istHour();
  const inMarket = hours >= 9 && hours < 16;
  if (!inMarket) return false;
  const ageMinutes = (Date.now() - new Date(isoTimestamp)) / 60000;
  if (Number.isNaN(ageMinutes)) return true;
  return ageMinutes > 30;
}

function _fmt(n) {
  if (n == null) return '--';
  return n.toLocaleString('en-IN', { maximumFractionDigits: 1 });
}

function _digestHeader(genTime, isStale) {
  const timeStr = genTime ? new Date(genTime).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata' }) : '--';
  const staleBadge = isStale ? ' <span class="badge badge--stale">STALE</span>' : '';
  return `<div class="digest-header">
    <h2 class="digest-header__title">Intelligence Digest</h2>
    <span class="digest-header__time">Last computed: ${timeStr}${staleBadge}</span>
  </div>`;
}

function _regimeCard(r) {
  if (!r) return '<div class="digest-card"><p class="text-muted">No regime data</p></div>';
  const groundBadge = r.grounding_ok === false ? '<span class="badge badge--red">GROUNDING FAILURE</span>' : '';
  return `<div class="digest-card">
    <div style="display: flex; justify-content: space-between; align-items: center;">
      <div class="digest-card__title">Regime Thesis</div>${groundBadge}
    </div>
    <div class="digest-card__subtitle">Why are we in ${_esc(r.zone)}?</div>
    <div class="digest-row"><span class="digest-row__label">Zone</span>
      <span class="digest-row__value"><span class="badge badge--gold">${_esc(r.zone)}</span></span></div>
    <div class="digest-row"><span class="digest-row__label">Source</span>
      <span class="digest-row__value">${_esc(r.regime_source || '--')}</span></div>
    <div class="digest-row"><span class="digest-row__label">FII Net</span>
      <span class="digest-row__value ${r.fii_net != null ? (r.fii_net >= 0 ? 'text-green' : 'text-red') : 'text-muted'}">₹${_fmt(r.fii_net)}cr</span></div>
    <div class="digest-row"><span class="digest-row__label">DII Net</span>
      <span class="digest-row__value ${r.dii_net != null ? (r.dii_net >= 0 ? 'text-green' : 'text-red') : 'text-muted'}">₹${_fmt(r.dii_net)}cr</span></div>
    <div class="digest-row"><span class="digest-row__label">MSI Score</span>
      <span class="digest-row__value">${r.msi_score != null ? r.msi_score.toFixed(2) : '--'}</span></div>
    <div class="digest-row"><span class="digest-row__label">Stability</span>
      <span class="digest-row__value">${r.stability_days}d ${r.stable ? '(locked)' : '(unstable)'}</span></div>
    ${r.flip_triggers && r.flip_triggers.length > 0 ? `
      <div style="margin-top: var(--spacing-sm); font-size: 0.75rem; color: var(--text-muted);">
        <strong>Flip triggers:</strong> ${(r.flip_triggers || []).map(_esc).join(' · ')}
      </div>` : ''}
  </div>`;
}

function _spreadCards(spreads) {
  if (!spreads || spreads.length === 0) return '<div class="digest-card"><p class="text-muted">No active spreads</p></div>';
  return spreads.map(s => {
    const badges = (s.caution_badges || []).map(b => {
      const cls = b.type === 'blocked' ? 'badge--blocked' : b.type === 'caution' ? 'badge--amber' : 'badge--muted';
      return `<span class="badge ${cls}" title="${_esc(b.detail || '')}">${_esc(b.label)}</span>`;
    }).join(' ');
    const cardCls = s.caution_badges?.some(b => b.type === 'blocked') ? 'digest-card--blocked'
      : s.caution_badges?.length > 0 ? 'digest-card--caution' : '';
    const actionCls = s.action === 'ENTER' ? 'text-green' : s.action === 'EXIT' ? 'text-red' : 'text-secondary';
    return `<div class="digest-card ${cardCls}">
      <div style="display: flex; justify-content: space-between; align-items: center;">
        <div class="digest-card__title">${_esc(s.name)}</div><div>${badges}</div>
      </div>
      <div class="digest-card__subtitle">Spread thesis</div>
      <div class="digest-row"><span class="digest-row__label">Action</span>
        <span class="digest-row__value ${actionCls}">${_esc(s.action)}</span></div>
      <div class="digest-row"><span class="digest-row__label">Conviction</span>
        <span class="digest-row__value">${_esc(s.conviction)} (${_esc(s.score)})</span></div>
      <div class="digest-row"><span class="digest-row__label">Z-Score</span>
        <span class="digest-row__value">${s.z_score != null ? s.z_score.toFixed(2) + 'σ' : '--'}</span></div>
      <div class="digest-row"><span class="digest-row__label">Regime Fit</span>
        <span class="digest-row__value">${s.regime_fit ? '✓' : '✗'}</span></div>
      <div class="digest-row"><span class="digest-row__label">Gate</span>
        <span class="digest-row__value">${_esc(s.gate_status)}</span></div>
    </div>`;
  }).join('');
}

function _breaksCard(breaks) {
  if (!breaks || breaks.length === 0) {
    return `<div class="digest-card">
      <div class="digest-card__title">Correlation Breaks</div>
      <div class="digest-card__subtitle">What is behaving wrong?</div>
      <p class="text-muted" style="font-size: 0.8125rem;">No breaks detected</p>
    </div>`;
  }
  const rows = breaks.map(b => {
    const zScore = b.z_score != null ? b.z_score : null;
    const dir = zScore == null ? '' : zScore < 0 ? '▼' : '▲';
    const zStr = zScore != null ? `${zScore > 0 ? '+' : ''}${zScore.toFixed(1)}σ ${dir}` : '--';
    const classification = b.classification || '';
    // Phase C is EXPLORATORY post 2026-04-23 H-2026-04-23-001 compliance FAIL.
    // Only WARNING-family still uses red (defensive signal; colour retained
    // for risk emphasis). OPPORTUNITY-family rendered muted-gold to signal
    // research-tier status, not a tradable signal.
    const cls = classification === 'CONFIRMED_WARNING' ? 'text-red' : 'text-secondary';
    return `<div class="digest-break-row">
      <div style="display: flex; justify-content: space-between; align-items: center;">
        <span class="mono" style="font-size: 0.875rem;">${_esc(b.ticker)}</span>
        <span class="mono ${cls}">${zStr}</span>
      </div>
      <div style="display: flex; justify-content: space-between; font-size: 0.75rem; color: var(--text-muted); margin-top: 2px;">
        <span>OI: ${_esc(b.oi_confirmation)}</span>
        <span class="badge ${classification === 'CONFIRMED_WARNING' ? 'badge--red' : 'badge--muted'}" title="Phase C is exploratory (research-tier) post 2026-04-23 compliance FAIL. Tracked for forward scorecarding only.">${_esc(classification.replace(/_/g, ' '))}${classification.includes('OPPORTUNITY') ? ' · EXPLORATORY' : ''}</span>
      </div>
    </div>`;
  }).join('');
  return `<div class="digest-card">
    <div class="digest-card__title">Correlation Breaks</div>
    <div class="digest-card__subtitle">What is behaving wrong?</div>
    ${rows}
  </div>`;
}

function _backtestCard(backtest) {
  if (!backtest || backtest.length === 0) {
    return `<div class="digest-card">
      <div class="digest-card__title">Backtest Validation</div>
      <p class="text-muted" style="font-size: 0.8125rem;">No backtest data</p>
    </div>`;
  }
  const rows = backtest.map(b => {
    const status = b.status || '';
    const statusCls = status === 'WITHIN_CI' ? 'badge--green'
      : status === 'EDGE_CI' ? 'badge--amber' : 'badge--red';
    const winPct = b.win_rate != null ? (b.win_rate * 100).toFixed(0) + '%' : '--';
    const avgStr = b.avg_return != null
      ? `${b.avg_return >= 0 ? '+' : ''}${(b.avg_return * 100).toFixed(2)}%`
      : '--';
    return `<div style="padding: var(--spacing-sm) 0; border-bottom: 1px solid rgba(30, 41, 59, 0.3);">
      <div style="display: flex; justify-content: space-between; align-items: center;">
        <span style="font-size: 0.875rem;">${_esc(b.spread)}</span>
        <span class="badge ${statusCls}">${_esc(status.replace(/_/g, ' '))}</span>
      </div>
      <div style="display: flex; gap: var(--spacing-lg); font-size: 0.75rem; color: var(--text-secondary); margin-top: 4px;">
        <span>Win: <span class="mono">${winPct}</span></span>
        <span>Period: <span class="mono">${_esc(b.best_period)}</span></span>
        <span>Avg: <span class="mono">${avgStr}</span></span>
      </div>
    </div>`;
  }).join('');
  return `<div class="digest-card">
    <div class="digest-card__title">Backtest Validation</div>
    <div class="digest-card__subtitle">Has this worked before?</div>
    ${rows}
  </div>`;
}

export async function render(container) {
  container.innerHTML = '<div class="skeleton skeleton--card"></div>';
  try {
    const data = await get('/research/digest');
    const genTime = data.generated_at || '';
    const isStale = _isStale(genTime);
    container.innerHTML = `
      ${_digestHeader(genTime, isStale)}
      <div class="digest-grid">
        <div>
          <div class="digest-column-header">Thesis — The Claim</div>
          ${_regimeCard(data.regime_thesis)}
          ${_spreadCards(data.spread_theses)}
        </div>
        <div>
          <div class="digest-column-header">Evidence — The Proof</div>
          ${_breaksCard(data.correlation_breaks)}
          ${_backtestCard(data.backtest_validation)}
        </div>
      </div>`;

    if (_refreshTimer) clearInterval(_refreshTimer);
    const inMarket = _istHour() >= 9 && _istHour() < 16;
    if (inMarket) {
      _refreshTimer = setInterval(() => render(container), 5 * 60 * 1000);
    }
  } catch {
    container.innerHTML = '<div class="empty-state"><p>Failed to load research digest</p></div>';
  }
}

export function destroy() {
  if (_refreshTimer) { clearInterval(_refreshTimer); _refreshTimer = null; }
}
