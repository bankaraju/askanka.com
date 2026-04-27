// pipeline/terminal/static/js/pages/regime.js
// "Where is the market?" surface. Composes from /api/regime + /api/research/digest
// + /api/candidates + /api/signals.
//
// Sections (left = market state, right = what's actually being traded):
//   - ETF zone + score, top drivers, MSI secondary
//   - Phase B stock picks (regime-derived)
//   - Phase C: live trades, not just break count (long/short ticker + P&L)
//   - Spread Watchlist: OPEN trades + score ≥60 only; dormant hidden
//
// Design rule (Bharat 2026-04-27): a row earns its place by being OPEN,
// state-changed today, or close to a threshold. Static inventory is noise.
import { get } from '../lib/api.js';

let _refreshTimer = null;
let _inflight = false;

function _esc(s) {
  if (s == null) return '';
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

export async function render(container) {
  if (_inflight) return;
  _inflight = true;
  if (!container.hasChildNodes()) {
    container.innerHTML = '<div class="skeleton skeleton--card"></div>';
  }
  try {
    const [regime, digest, candidates, signals] = await Promise.allSettled([
      get('/regime'), get('/research/digest'), get('/candidates'), get('/signals'),
    ]);
    const r = regime.status === 'fulfilled' ? regime.value : {};
    const d = digest.status === 'fulfilled' ? digest.value : {};
    const c = candidates.status === 'fulfilled' ? candidates.value : { tradeable_candidates: [] };
    const sigData = signals.status === 'fulfilled' ? signals.value : { positions: [] };
    const positions = sigData.positions || [];

    const driversHtml = (r.top_drivers ?? []).slice(0, 8).map(drv => {
      const cv = drv.contribution;
      const hasC = typeof cv === 'number' && !isNaN(cv);
      const colourCls = hasC ? (cv >= 0 ? 'text-green' : 'text-red') : 'text-muted';
      const sign = hasC && cv >= 0 ? '+' : '';
      const valStr = hasC ? `${sign}${cv.toFixed(3)}` : '--';
      return `<div class="digest-row">
        <span class="digest-row__label">${_esc(drv.symbol || drv.name || '--')}</span>
        <span class="digest-row__value mono ${colourCls}">${valStr}</span>
      </div>`;
    }).join('');

    const phaseBHtml = c.tradeable_candidates
      .filter(x => x.source === 'regime_engine')
      .slice(0, 8)
      .map(p => `<div class="digest-row">
        <span class="digest-row__label">${_esc(p.name)}</span>
        <span class="digest-row__value">${_esc(p.conviction)} (${_esc(p.score)})</span>
      </div>`).join('') || '<p class="text-muted" style="font-size: 0.8125rem;">No Phase B picks today</p>';

    // Spread Watchlist — actionable rule (Bharat 2026-04-27):
    //   1. OPEN trades from open_signals always show at top, with P&L
    //   2. score >= 60 shown — could promote to SIGNAL (>=65) intraday
    //   3. score < 60 hidden — static inventory below threshold is noise
    // The two paths (regime-batch + news-event) are merged: a spread is
    // shown if EITHER engine put it on the live ledger or if its current
    // regime score is >=60.
    const openSpreadNames = new Set(
      positions
        .filter(p => p.category !== 'phase_c')
        .map(p => p.spread_name)
        .filter(Boolean)
    );
    const openSpreadRows = positions
      .filter(p => p.category !== 'phase_c' && p.spread_name)
      .map(p => {
        const pnl = p.spread_pnl_pct ?? p.pnl_pct ?? 0;
        const pnlCls = pnl >= 0 ? 'text-green' : 'text-red';
        const pnlSgn = pnl >= 0 ? '+' : '';
        const opened = (p.open_timestamp || '').slice(11, 16) || '--';
        return `<div class="digest-row" title="opened ${_esc(opened)} IST — currently traded">
          <span class="digest-row__label">
            <span class="badge badge--gold" style="font-size: 0.65rem; margin-right: 0.4em;">OPEN</span>${_esc(p.spread_name)}
          </span>
          <span class="digest-row__value mono ${pnlCls}">${pnlSgn}${pnl.toFixed(2)}%</span>
        </div>`;
      }).join('');

    const watchRows = c.tradeable_candidates
      .filter(x => x.source === 'static_config')
      .filter(x => !openSpreadNames.has(x.name))
      .filter(x => {
        const s = Number(x.score);
        return Number.isFinite(s) && s >= 60;
      })
      .sort((a, b) => Number(b.score) - Number(a.score))
      .map(s => {
        const score = Number(s.score);
        const armed = score >= 65;
        const tierBadge = armed
          ? '<span class="badge" style="font-size: 0.65rem; background: var(--colour-amber, #d4a84b); color: #000; margin-right: 0.4em;">ARMED</span>'
          : '<span class="badge badge--muted" style="font-size: 0.65rem; margin-right: 0.4em;">WATCH</span>';
        return `<div class="digest-row" title="conviction ${_esc(s.conviction)} — score ${score}/100, fires at 65">
          <span class="digest-row__label">${tierBadge}${_esc(s.name)}</span>
          <span class="digest-row__value mono">${score}</span>
        </div>`;
      }).join('');

    const totalConfig = c.tradeable_candidates.filter(x => x.source === 'static_config').length;
    const shownCount = openSpreadNames.size
      + c.tradeable_candidates.filter(x => x.source === 'static_config'
                                           && !openSpreadNames.has(x.name)
                                           && Number(x.score) >= 60).length;
    const dormantCount = Math.max(0, totalConfig - shownCount);
    const dormantFooter = dormantCount > 0
      ? `<p class="text-muted" style="font-size: 0.75rem; margin-top: 0.5em;">+ ${dormantCount} dormant (score &lt; 60) — hidden</p>`
      : '';

    const eligibleHtml = (openSpreadRows + watchRows)
      || '<p class="text-muted" style="font-size: 0.8125rem;">No spreads above the 60 watch threshold</p>';

    // Phase C live trades — show what's actually being traded, not just a
    // count of detected breaks. Bharat 2026-04-27: "we are trading -- those
    // trades must be reflected here -- summary long/short/stock & P&L".
    // Single-leg breaks land in long_legs OR short_legs (not both); the
    // leg ticker is the trade symbol.
    const phaseCTrades = positions.filter(p => p.category === 'phase_c');
    const phaseCRows = phaseCTrades.map(p => {
      const isLong = (p.long_legs || []).length > 0;
      const leg = (isLong ? p.long_legs : p.short_legs)[0] || {};
      const ticker = leg.ticker || p.ticker || '--';
      const dirBadge = isLong
        ? '<span class="badge" style="font-size: 0.65rem; background: var(--colour-green, #4caf50); color: #000; margin-right: 0.4em;">L</span>'
        : '<span class="badge" style="font-size: 0.65rem; background: var(--colour-red, #f44336); color: #fff; margin-right: 0.4em;">S</span>';
      const pnl = p.spread_pnl_pct ?? p.pnl_pct ?? 0;
      const pnlCls = pnl >= 0 ? 'text-green' : 'text-red';
      const pnlSgn = pnl >= 0 ? '+' : '';
      return `<div class="digest-row" title="${_esc(p.spread_name || '')}">
        <span class="digest-row__label">${dirBadge}${_esc(ticker)}</span>
        <span class="digest-row__value mono ${pnlCls}">${pnlSgn}${pnl.toFixed(2)}%</span>
      </div>`;
    }).join('');
    const phaseCAggPnl = phaseCTrades.reduce(
      (s, p) => s + (p.spread_pnl_pct ?? p.pnl_pct ?? 0), 0);
    const phaseCWins = phaseCTrades.filter(
      p => (p.spread_pnl_pct ?? p.pnl_pct ?? 0) > 0).length;
    const phaseCLongs = phaseCTrades.filter(
      p => (p.long_legs || []).length > 0).length;
    const phaseCShorts = phaseCTrades.length - phaseCLongs;
    const aggCls = phaseCAggPnl >= 0 ? 'text-green' : 'text-red';
    const aggSgn = phaseCAggPnl >= 0 ? '+' : '';
    const phaseCSubtitle = phaseCTrades.length > 0
      ? `${phaseCTrades.length} OPEN — ${phaseCLongs}L / ${phaseCShorts}S, ${phaseCWins}W · sum <span class="mono ${aggCls}">${aggSgn}${phaseCAggPnl.toFixed(2)}%</span>`
      : `${(d.correlation_breaks || []).length} breaks detected today, no positions open`;
    const phaseCBody = phaseCTrades.length > 0
      ? phaseCRows
      : '<p class="text-muted" style="font-size: 0.8125rem;">No open Phase C trades. Mechanical close fires at 14:30 IST.</p>';

    const stableLabel = r.stable ? 'LOCKED' : 'UNSTABLE';
    const stableCls = r.stable ? 'text-green' : 'text-amber';

    container.innerHTML = `
      <h2 style="margin-bottom: var(--spacing-md);">Regime — Where is the market?</h2>
      <div class="digest-grid">
        <div>
          <div class="digest-column-header">ETF Engine (Primary)</div>
          <div class="digest-card">
            <div class="digest-card__title">Zone: <span class="badge badge--gold">${_esc(r.zone || 'UNKNOWN')}</span></div>
            <div class="digest-row"><span class="digest-row__label">Score</span>
              <span class="digest-row__value mono">${r.score != null ? r.score.toFixed(3) : '--'}</span></div>
            <div class="digest-row"><span class="digest-row__label">Source</span>
              <span class="digest-row__value">${_esc(r.regime_source || '--')}</span></div>
            <div class="digest-row"><span class="digest-row__label">Stability</span>
              <span class="digest-row__value ${stableCls}">${stableLabel} (${r.consecutive_days ?? 0}d)</span></div>
            <div class="digest-row"><span class="digest-row__label">Updated</span>
              <span class="digest-row__value mono">${_esc(r.updated_at || '--')}</span></div>
          </div>
          <div class="digest-card">
            <div class="digest-card__title">Top Drivers</div>
            ${driversHtml || '<p class="text-muted" style="font-size: 0.8125rem;">No driver data</p>'}
          </div>
          <div class="digest-card">
            <div class="digest-card__title">MSI (Secondary Context)</div>
            <div class="digest-row"><span class="digest-row__label">Score</span>
              <span class="digest-row__value mono">${r.msi_score != null ? r.msi_score.toFixed(2) : '--'}</span></div>
            <div class="digest-row"><span class="digest-row__label">Regime</span>
              <span class="digest-row__value">${_esc(r.msi_regime || '--')}</span></div>
          </div>
        </div>
        <div>
          <div class="digest-column-header">Phase A/B/C (Reverse Regime)</div>
          <div class="digest-card">
            <div class="digest-card__title">Phase B: Stock Picks</div>
            <div class="digest-card__subtitle">Today's regime-derived stock recommendations</div>
            ${phaseBHtml}
          </div>
          <div class="digest-card">
            <div class="digest-card__title">Phase C: Correlation Breaks</div>
            <div class="digest-card__subtitle">${phaseCSubtitle}</div>
            ${phaseCBody}
          </div>
          <div class="digest-card">
            <div class="digest-card__title">Spread Watchlist</div>
            <div class="digest-card__subtitle">OPEN trades + score ≥ 60 (fires at 65). Dormant hidden.</div>
            ${eligibleHtml}
            ${dormantFooter}
          </div>
        </div>
      </div>`;

    if (_refreshTimer) clearInterval(_refreshTimer);
    _refreshTimer = setInterval(() => render(container), 60000);
  } catch (e) {
    console.error('regime render failed', e);
    container.innerHTML = '<div class="empty-state"><p>Failed to load regime data</p></div>';
  } finally {
    _inflight = false;
  }
}

export function destroy() {
  if (_refreshTimer) { clearInterval(_refreshTimer); _refreshTimer = null; }
}
