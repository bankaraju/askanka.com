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
    const stop = p.stop_pct != null ? fmtPct(p.stop_pct) : '--';
    const target = p.target_pct != null ? fmtPct(p.target_pct) : '--';
    const opened = p.open_date || (p.open_timestamp ? p.open_timestamp.split('T')[0] : '--');
    const days = p.days_held != null ? `${p.days_held}d` : '--';
    const source = p.source_signal || p.tier || '--';
    const exitTrigger = p.exit_trigger || (p.is_stale ? 'STALE' : '');

    return `<tr>
      <td>${p.spread_name || p.signal_id || '--'}</td>
      <td>${legsHtml(p)}</td>
      <td class="mono">${opened}</td>
      <td class="mono ${pnlClass(pnl)}">${fmtPct(pnl)}</td>
      <td class="mono text-red">${stop}</td>
      <td class="mono text-green">${target}</td>
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
        <th>Stop</th><th>Target</th><th>Held</th><th>Source / Exit</th>
      </tr></thead>
      <tbody>${rows}</tbody>
    </table>`;
}
