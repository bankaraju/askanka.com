// pipeline/terminal/static/js/pages/scanner.js
// Scanner (TA) tab — pattern-occurrence engine. Daily Top-10 candlestick /
// structural / momentum fires across the F&O universe, fortified with
// per-(ticker x pattern) historical stats (n, win-rate, z-score against
// random, walk-forward fold-stability, mean P&L). Click-to-chart on every
// ticker (was regression #269 — restored).
//
// Spec: docs/superpowers/specs/2026-04-27-ta-scanner-pattern-paired-shadow-design.md
import { get } from '../lib/api.js';

let _refreshTimer = null;
let _inflight = false;

function _esc(s) {
  if (s == null) return '';
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

function _fmtPct(v) {
  if (v == null || isNaN(v)) return '--';
  const sign = v >= 0 ? '+' : '';
  return `${sign}${(v * 100).toFixed(2)}%`;
}

function _dirBadge(dir) {
  if (dir === 'LONG') {
    return '<span class="badge" style="font-size: 0.65rem; background: var(--colour-green, #4caf50); color: #000; margin-right: 0.4em;">L</span>';
  }
  return '<span class="badge" style="font-size: 0.65rem; background: var(--colour-red, #f44336); color: #fff; margin-right: 0.4em;">S</span>';
}

function _zClass(z) {
  if (z == null || isNaN(z)) return 'text-muted';
  if (z >= 3.0) return 'text-green';
  if (z >= 2.0) return 'text-amber';
  return 'text-muted';
}

function _navigateToChart(ticker) {
  // Existing chart route — set hash; ticker-chart-modal listens.
  window.location.hash = `#chart/${encodeURIComponent(ticker)}`;
}

function _renderTopRow(s) {
  const dirBadge = _dirBadge(s.direction);
  const zCls = _zClass(s.z_score);
  return `<tr class="scanner-row" data-ticker="${_esc(s.ticker)}"
              title="composite ${s.composite_score} | n=${s.n_occurrences} | last seen ${_esc(s.last_seen)}"
              style="cursor: pointer;">
    <td>${dirBadge}</td>
    <td class="mono"><a href="#chart/${encodeURIComponent(s.ticker)}"
                       class="text-primary" style="text-decoration: none;">${_esc(s.ticker)}</a></td>
    <td>${_esc(s.pattern_id)}</td>
    <td class="mono">${s.n_occurrences}</td>
    <td class="mono">${(s.win_rate * 100).toFixed(0)}%</td>
    <td class="mono ${zCls}">${s.z_score.toFixed(2)}</td>
    <td class="mono">${_fmtPct(s.mean_pnl_pct)}</td>
    <td class="mono">${(s.fold_stability * 100).toFixed(0)}%</td>
    <td class="mono text-muted">${_esc(s.last_seen)}</td>
  </tr>`;
}

export async function render(container) {
  if (_inflight) return;
  _inflight = true;
  if (!container.hasChildNodes()) {
    container.innerHTML = '<div class="skeleton skeleton--card"></div>';
  }
  try {
    // Endpoint: /api/scanner/pattern-signals
    const data = await get('/scanner/pattern-signals');
    const top10 = data.top_10 || [];
    const cum = data.cumulative_paired_shadow || {};

    const tableHtml = top10.length === 0
      ? '<p class="text-muted" style="font-size: 0.875rem;">No qualified pattern fires today.</p>'
      : `<table class="scanner-table">
          <thead><tr>
            <th>Dir</th><th>Ticker</th><th>Pattern</th>
            <th>N</th><th>Win%</th><th>Z</th>
            <th>μ P&L</th><th>Fold-stability</th><th>Last seen</th>
          </tr></thead>
          <tbody>${top10.map(_renderTopRow).join('')}</tbody>
        </table>`;

    const dormantFooter = (data.below_threshold_count || 0) > 0
      ? `<p class="text-muted" style="font-size: 0.75rem; margin-top: 0.5em;">+ ${data.below_threshold_count} below threshold (n &lt; 30 or unstable folds) — hidden</p>`
      : '';

    const cumHtml = (cum.n_closed || 0) > 0
      ? `<div class="digest-card" style="margin-top: 1em;">
          <div class="digest-card__title">Paired-shadow rollup (cumulative)</div>
          <div class="digest-row"><span class="digest-row__label">Closed trades</span>
            <span class="digest-row__value mono">${cum.n_closed}</span></div>
          <div class="digest-row"><span class="digest-row__label">Win rate</span>
            <span class="digest-row__value mono">${(cum.win_rate * 100).toFixed(1)}%</span></div>
          <div class="digest-row"><span class="digest-row__label">μ Options P&L</span>
            <span class="digest-row__value mono">${_fmtPct(cum.mean_options_pnl_pct)}</span></div>
          <div class="digest-row"><span class="digest-row__label">μ Futures P&L</span>
            <span class="digest-row__value mono">${_fmtPct(cum.mean_futures_pnl_pct)}</span></div>
          <div class="digest-row"><span class="digest-row__label">Paired diff</span>
            <span class="digest-row__value mono">${_fmtPct(cum.mean_paired_diff)}</span></div>
        </div>`
      : '';

    container.innerHTML = `
      <h2 style="margin-bottom: var(--spacing-md);">Scanner (TA) — Today's Top Patterns</h2>
      <div class="digest-card">
        <div class="digest-card__title">Top ${top10.length} of ${data.qualified_count} qualified fires</div>
        <div class="digest-card__subtitle">Universe ${data.universe_size} F&amp;O stocks | as of ${_esc(data.as_of?.slice(0, 16) || '--')}</div>
        ${tableHtml}
        ${dormantFooter}
      </div>
      ${cumHtml}`;

    // Click handler for entire row -> chart
    container.querySelectorAll('tr.scanner-row').forEach(tr => {
      tr.addEventListener('click', e => {
        // Don't double-fire if user clicked the anchor inside
        if (e.target.tagName === 'A') return;
        _navigateToChart(tr.dataset.ticker);
      });
    });

    if (_refreshTimer) clearInterval(_refreshTimer);
    _refreshTimer = setInterval(() => render(container), 60000);
  } catch (e) {
    console.error('scanner render failed', e);
    container.innerHTML = '<div class="empty-state"><p>Failed to load scanner data</p></div>';
  } finally {
    _inflight = false;
  }
}

export function destroy() {
  if (_refreshTimer) { clearInterval(_refreshTimer); _refreshTimer = null; }
}
