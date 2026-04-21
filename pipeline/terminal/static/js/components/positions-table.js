// Renders the Open Positions table for Dashboard.
// Shows entry, current, P&L, stop, target, exit triggers, days held, source signal.

export function render(container, positions) {
  if (!positions || positions.length === 0) {
    container.innerHTML = `
      <div class="empty-state"><p>No open positions</p>
      <p class="text-muted">When a signal fires and executes, it will appear here.</p></div>`;
    return;
  }

  function legsHtml(item) {
    const longs = (item.long_legs || []).map(l => l.ticker || l).join(', ');
    const shorts = (item.short_legs || []).map(l => l.ticker || l).join(', ');
    if (longs && !shorts) return `<span class="text-green"><b>LONG</b> ${longs}</span>`;
    if (shorts && !longs) return `<span class="text-red"><b>SHORT</b> ${shorts}</span>`;
    return `<span class="text-green">L: ${longs}</span><br><span class="text-red">S: ${shorts}</span>`;
  }

  function fmtPct(v) {
    if (v == null) return '--';
    return `${v >= 0 ? '+' : ''}${Number(v).toFixed(2)}%`;
  }

  function pnlClass(v) {
    if (v == null) return '';
    return v >= 0 ? 'text-green' : 'text-red';
  }

  const rows = positions.map(p => {
    const pnl = p.spread_pnl_pct ?? p.pnl_pct ?? 0;
    // Per-spread stop levels are computed by signal_tracker.check_signal_status
    // and stored on each signal under _data_levels. See:
    //   docs/superpowers/plans/2026-04-15-trailing-stop-and-replay.md
    //   pipeline/signal_tracker.py:10-20  (live trail config + backtest cite)
    const lvl = p._data_levels || {};
    const stop = lvl.daily_stop != null ? fmtPct(lvl.daily_stop) : '--';
    const trail = lvl.trail_stop != null ? fmtPct(lvl.trail_stop) : '--';
    const peak = lvl.peak != null ? fmtPct(lvl.peak) : '--';
    const opened = p.open_date || (p.open_timestamp ? p.open_timestamp.split('T')[0] : '--');
    const days = p.days_held != null ? `${p.days_held}d` : '--';
    const source = p.source || p.source_signal || p.tier || '--';
    const exitTrigger = p.exit_trigger || (p.is_stale ? 'STALE' : '');

    return `<tr>
      <td>${p.spread_name || p.signal_id || '--'}</td>
      <td>${legsHtml(p)}</td>
      <td class="mono">${opened}</td>
      <td class="mono ${pnlClass(pnl)}">${fmtPct(pnl)}</td>
      <td class="mono text-red" title="Daily stop = -(avg_favorable × 0.50). Per-spread, from 1mo history.">${stop}</td>
      <td class="mono ${pnlClass(lvl.trail_stop)}" title="Trail stop = peak - (avg_favorable × sqrt(days_since_check)). Arms when peak ≥ budget.">${trail}</td>
      <td class="mono text-green" title="Running peak P&L since entry — trail stop ratchets off this.">${peak}</td>
      <td class="mono">${days}</td>
      <td><span class="badge badge--gold">${source}</span>${exitTrigger ? ` <span class="badge badge--amber">${exitTrigger}</span>` : ''}</td>
    </tr>`;
  }).join('');

  const totalPnl = positions.reduce((sum, p) => sum + (p.spread_pnl_pct ?? p.pnl_pct ?? 0), 0);
  const headerCls = totalPnl >= 0 ? 'text-green' : 'text-red';

  container.innerHTML = `
    <div style="display: flex; justify-content: space-between; align-items: baseline; margin-bottom: var(--spacing-md);">
      <h3 style="margin: 0;">Open Positions <span class="text-muted" style="font-size: 0.875rem;">(${positions.length})</span></h3>
      <div class="mono ${headerCls}" style="font-size: 1rem;">Total P&L: ${fmtPct(totalPnl)}</div>
    </div>
    <table class="data-table">
      <thead><tr>
        <th>Name</th><th>Legs</th><th>Opened</th><th>P&L</th>
        <th title="Daily stop level — per-spread, from 1mo favorable-move history">Stop</th>
        <th title="Trailing stop level — locks in profit as peak ratchets up">Trail</th>
        <th title="Running peak P&L since entry">Peak</th>
        <th>Held</th><th>Source / Exit</th>
      </tr></thead>
      <tbody>${rows}</tbody>
    </table>`;
}
