// Portfolio aggregates + simple P&L scenarios for the Dashboard footer.
// Inputs: positions array (each with spread_pnl_pct, long_legs, short_legs).

export function render(container, positions, regimeData) {
  if (!positions || positions.length === 0) {
    container.innerHTML = '';
    return;
  }

  const totalPnl = positions.reduce((s, p) => s + (p.spread_pnl_pct ?? p.pnl_pct ?? 0), 0);
  const winners = positions.filter(p => (p.spread_pnl_pct ?? p.pnl_pct ?? 0) > 0).length;
  const losers = positions.filter(p => (p.spread_pnl_pct ?? p.pnl_pct ?? 0) < 0).length;
  const avgPnl = totalPnl / positions.length;

  const regimeFlipPct = -2.0;  // conservative placeholder — TODO: derive from historical EUPHORIA→PANIC spread moves
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
          <tr title="Rough placeholder — assumes ${regimeFlipPct}% per position. TODO: derive from historical regime-flip spread moves.">
            <td>Regime flip from ${regimeData?.zone || '--'} (placeholder: ${regimeFlipPct}%/position)</td>
            <td class="mono text-red">${fmt(positions.length * regimeFlipPct)}</td></tr>
        </tbody>
      </table>
    </div>`;
}
