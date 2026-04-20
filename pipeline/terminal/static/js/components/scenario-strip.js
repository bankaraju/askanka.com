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

  const regimeFlipPct = -2.0;
  const allTargetsPct = positions.reduce((s, p) => s + (p.target_pct || 0), 0);
  const allStopsPct = positions.reduce((s, p) => s + (p.stop_pct || 0), 0);

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
      <h3 style="margin-bottom: var(--spacing-sm); font-size: 0.875rem;">P&L Scenarios</h3>
      <table class="data-table">
        <thead><tr><th>Scenario</th><th>Aggregate P&L</th></tr></thead>
        <tbody>
          <tr><td>All targets hit</td>
            <td class="mono text-green">${allTargetsPct ? fmt(allTargetsPct) : '--'}</td></tr>
          <tr><td>All stops hit</td>
            <td class="mono text-red">${allStopsPct ? fmt(allStopsPct) : '--'}</td></tr>
          <tr><td>Regime flip from ${regimeData?.zone || '--'} (assume ${regimeFlipPct}% per position)</td>
            <td class="mono text-red">${fmt(positions.length * regimeFlipPct)}</td></tr>
        </tbody>
      </table>
    </div>`;
}
