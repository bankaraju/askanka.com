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

function _fmtINR(n) {
  if (n == null) return '--';
  if (n >= 1e7) return `₹${(n / 1e7).toFixed(2)}Cr`;
  if (n >= 1e5) return `₹${(n / 1e5).toFixed(2)}L`;
  if (n >= 1e3) return `₹${(n / 1e3).toFixed(1)}K`;
  return `₹${Math.round(n)}`;
}

function _fmtPrem(n) {
  if (n == null) return '--';
  return `₹${Number(n).toFixed(2)}`;
}

function _fmtIV(iv) {
  if (iv == null) return '--';
  return `${(Number(iv) * 100).toFixed(1)}%`;
}

function _fmtGreek(g) {
  if (g == null) return '--';
  return Number(g).toFixed(3);
}

function _fmtEdge1m(e) {
  // net_edge_pct from drift_vs_rent_matrix is already in percent form
  // (synthetic_options.py emits drift_pct/rent_pct/net_edge_pct in percent
  // units, not decimals). No *100 conversion.
  if (e == null) return '--';
  const pct = Number(e);
  const cls = pct >= 0 ? 'text-green' : 'text-red';
  const sign = pct >= 0 ? '+' : '';
  return `<span class="${cls} mono">${sign}${pct.toFixed(2)}%</span>`;
}

function _copyableSymbol(sym) {
  if (!sym) return '--';
  const safe = _esc(sym);
  return `<button class="copy-symbol mono" data-clipboard="${safe}" title="Copy ${safe} to clipboard for Kite paste">${safe}</button>`;
}

function _renderOpenPairs(open) {
  if (!open || open.length === 0) {
    return '<p class="text-muted" style="margin: 0.5rem 0;">No live OPEN pairs.</p>';
  }
  // Phase A: surface what the ledger already has — entry premium, lot/notional,
  // max loss bound, IV + Greeks at entry, time-to-expiry, drift-vs-rent edge
  // magnitude. Live MTM (current bid/ask, current Greeks, live P&L) ships in
  // Phase B with /api/research/phase-c-options-shadow-live and Kite quote calls.
  const rows = open.map(p => {
    const expiryShort = p.expiry_date
      ? new Date(p.expiry_date).toLocaleDateString('en-IN', { month: 'short', day: 'numeric' })
      : '--';
    const sideCls = p.side === 'SHORT' ? 'text-red' : 'text-green';
    const position = `<span class="${sideCls}"><b>${_esc(p.side || '')}</b></span> ${_esc(p.option_type || '')} ${_esc(p.strike || '')}`;
    const dte = p.days_to_expiry != null ? `${p.days_to_expiry}d` : '--';
    const dteCls = (p.days_to_expiry != null && p.days_to_expiry <= 7) ? 'text-amber' : '';
    const greeksTitle = `Δ ${_fmtGreek(p.entry_delta)}  θ ${_fmtGreek(p.entry_theta)}/d  ν ${_fmtGreek(p.entry_vega)}  IV ${_fmtIV(p.entry_iv)}  bid/ask ${_fmtPrem(p.entry_bid)}/${_fmtPrem(p.entry_ask)} (spread ${p.spread_pct_at_entry != null ? (p.spread_pct_at_entry * 100).toFixed(2) + '%' : 'n/a'})`;
    const maxLossStr = p.max_loss_inr != null ? _fmtINR(p.max_loss_inr) : '∞';
    const lotsStr = (p.lots != null && p.lot_size != null)
      ? `${p.lots}×${p.lot_size}`
      : '--';

    // Live LTP + live P&L: poll /api/options/live_ltp every 10s, patch the
    // two cells in place. Live P&L sign: SHORT premium (sold) profits when
    // LTP < entry_mid; LONG premium (bought) profits when LTP > entry_mid.
    // We tag the cells with data-live-opt-* so options-live-ticker.js can
    // find them by tradingsymbol after every refresh.
    const ts = p.tradingsymbol || '';
    const entryMidAttr = (p.entry_mid != null) ? p.entry_mid : '';
    const liveAttrs = ts
      ? ` data-live-opt-ts="${_esc(ts)}" data-live-opt-entry="${entryMidAttr}" data-live-opt-side="${_esc(p.side || '')}"`
      : '';
    return `<tr title="${_esc(greeksTitle)}">
      <td>${_esc(p.symbol)}</td>
      <td>${position}</td>
      <td class="mono">${_esc(expiryShort)}</td>
      <td class="mono ${dteCls}">${dte}</td>
      <td>${_copyableSymbol(p.tradingsymbol)}</td>
      <td class="mono">${_fmtPrem(p.entry_mid)}</td>
      <td class="mono"${liveAttrs} data-live-opt-cell="ltp" title="Live last-traded premium (Kite NFO quote, refresh ~10s)">--</td>
      <td class="mono"${liveAttrs} data-live-opt-cell="pnl" title="Live mark-to-market — sign-corrected for SHORT (premium decay = profit)">--</td>
      <td class="mono">${_esc(lotsStr)}</td>
      <td class="mono">${_fmtINR(p.notional_at_entry)}</td>
      <td class="mono text-amber" title="Max-loss bound: SHORT PE caps at strike×notional (underlying → 0). SHORT CE = ∞.">${maxLossStr}</td>
      <td class="mono">${_fmtIV(p.entry_iv)}</td>
      <td class="mono" title="Delta at entry">${_fmtGreek(p.entry_delta)}</td>
      <td class="mono" title="Theta at entry, ₹/day">${_fmtGreek(p.entry_theta)}</td>
      <td title="1-month theoretical edge: drift gain minus theta+IV-decay rent">${_fmtEdge1m(p.net_edge_pct_1m)}</td>
      <td>${_tierBadge(p.drift_vs_rent_tier)}</td>
    </tr>`;
  }).join('');
  return `
    <div class="paired-shadow-table-wrap" style="overflow-x:auto;">
      <table class="data-table" style="font-size:0.78rem; margin-top:0.4rem; min-width: 900px;">
        <thead>
          <tr style="color:var(--text-secondary); font-size:0.7rem;">
            <th title="Underlying F&O ticker — same as Phase C futures leg">Symbol</th>
            <th title="Sold or bought; option type (PE=put, CE=call); strike price">Position</th>
            <th>Expiry</th>
            <th title="Days to expiry — amber when ≤7d (gamma/theta cliff)">DTE</th>
            <th title="Kite tradingsymbol — click to copy">Tradingsymbol</th>
            <th title="Entry premium = (bid+ask)/2 at open">Entry mid</th>
            <th title="Live last-traded premium (Kite NFO quote, ~10s refresh)">LTP</th>
            <th title="Live mark-to-market P&amp;L — SHORT profits when LTP < entry, LONG profits when LTP > entry">Live P&amp;L</th>
            <th title="Lots × lot-size (one-lot bound for paper)">Lots</th>
            <th title="Notional at entry = entry_mid × lot_size × lots">Notional</th>
            <th title="Max loss INR — SHORT PE caps at strike×notional, SHORT CE = ∞, LONG = premium paid">Max loss</th>
            <th title="Implied vol at entry (annualized)">IV</th>
            <th title="Delta at entry">Δ</th>
            <th title="Theta at entry (₹/day decay)">θ</th>
            <th title="1-month drift minus rent — theoretical net edge of holding to expiry">Edge 1m</th>
            <th title="Drift-vs-rent tier — HA: high-alpha, EXP: experimental, NC: negative carry">Tier</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    </div>
    <p class="text-muted" style="font-size:0.7rem; margin:0.4rem 0 0;">
      <b>Forensic only.</b> Greeks/edge shown are <i>at entry</i>. <b>LTP + Live P&amp;L</b> refresh every ~10s from Kite NFO quote.
      Max loss is the position bound, not a stop — ATR-stop on the underlying futures leg is the active risk control.
    </p>`;
}

// ---------------------------------------------------------------------------
// Options live LTP poller — finds every cell tagged data-live-opt-ts on the
// page, batches the unique tradingsymbols, hits /api/options/live_ltp, and
// patches the LTP + Live P&L cells in place. SHORT premium profits when
// LTP < entry_mid; LONG premium profits when LTP > entry_mid. Same lifecycle
// pattern as live-ticker.js but on a separate poll because the equity LTP
// path uses signal_tracker.fetch_current_prices which doesn't support NFO.
// Installed once; survives the parent card's innerHTML re-renders.
// ---------------------------------------------------------------------------

const OPTIONS_POLL_MS = 10000;

function _fmtOptionPrem(v) {
  if (v == null || !Number.isFinite(v)) return '--';
  return `₹${Number(v).toFixed(2)}`;
}

function _fmtOptionPnl(v) {
  if (v == null || !Number.isFinite(v)) return '--';
  const sign = v >= 0 ? '+' : '';
  return `${sign}${v.toFixed(2)}%`;
}

function _pnlClass(v) {
  if (v == null || !Number.isFinite(v)) return '';
  return v >= 0 ? 'text-green' : 'text-red';
}

async function _pollOptionsLtps() {
  const cells = document.querySelectorAll('[data-live-opt-ts][data-live-opt-cell="ltp"]');
  if (!cells || cells.length === 0) return;
  const seen = new Set();
  const tradingsymbols = [];
  cells.forEach(c => {
    const ts = c.getAttribute('data-live-opt-ts');
    if (ts && !seen.has(ts)) {
      seen.add(ts);
      tradingsymbols.push(ts);
    }
  });
  if (tradingsymbols.length === 0) return;
  let data;
  try {
    const url = `/api/options/live_ltp?tradingsymbols=${encodeURIComponent(tradingsymbols.slice(0, 50).join(','))}`;
    const resp = await fetch(url, { cache: 'no-store' });
    if (!resp.ok) return;
    data = await resp.json();
  } catch (err) {
    console.warn('[options-live] poll failed:', err);
    return;
  }
  // Patch LTP + Live P&L cells. The same data-live-opt-ts attribute appears
  // on BOTH the LTP cell and the P&L cell, so a single querySelectorAll
  // scoped by cell="ltp" / cell="pnl" hits each pair.
  const allCells = document.querySelectorAll('[data-live-opt-ts]');
  allCells.forEach(c => {
    const ts = c.getAttribute('data-live-opt-ts');
    const kind = c.getAttribute('data-live-opt-cell');
    const side = c.getAttribute('data-live-opt-side');
    const entry = parseFloat(c.getAttribute('data-live-opt-entry'));
    const quote = data ? data[ts] : null;
    if (!quote || quote.ltp == null) return;
    const ltp = Number(quote.ltp);
    if (kind === 'ltp') {
      c.textContent = _fmtOptionPrem(ltp);
    } else if (kind === 'pnl') {
      if (!Number.isFinite(entry) || entry <= 0) return;
      // SHORT premium: profit when LTP falls below entry_mid (premium decays).
      // LONG premium: profit when LTP rises above entry_mid.
      const pnlPct = side === 'SHORT'
        ? (1 - ltp / entry) * 100
        : (ltp / entry - 1) * 100;
      c.textContent = _fmtOptionPnl(pnlPct);
      c.className = `mono ${_pnlClass(pnlPct)}`;
    }
  });
}

function _ensureOptionsPollerInstalled() {
  if (window.__phaseCOptionsPollerInstalled) return;
  window.__phaseCOptionsPollerInstalled = true;
  // Fire once immediately so first paint is "live" within ~1 network RTT,
  // then settle into the 10s cadence. Errors are swallowed by the poller.
  _pollOptionsLtps();
  setInterval(_pollOptionsLtps, OPTIONS_POLL_MS);
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

// Delegated click handler — installed once at module load. Handles copy-to-
// clipboard for any .copy-symbol button rendered by _copyableSymbol(). Avoids
// re-binding on every payload refresh and survives the card's innerHTML rerender.
function _ensureCopyHandlerInstalled() {
  if (window.__phaseCPairedCopyHandlerInstalled) return;
  window.__phaseCPairedCopyHandlerInstalled = true;
  document.addEventListener('click', (e) => {
    const btn = e.target.closest('.copy-symbol');
    if (!btn) return;
    e.preventDefault();
    const text = btn.getAttribute('data-clipboard');
    if (!text) return;
    const restore = btn.textContent;
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(() => {
        btn.textContent = '✓ copied';
        setTimeout(() => { btn.textContent = restore; }, 1200);
      }).catch(() => {
        btn.textContent = '✗ failed';
        setTimeout(() => { btn.textContent = restore; }, 1200);
      });
    }
  });
}

export function renderPhaseCPairedShadowCard(payload) {
  // Returns empty string if payload is null (endpoint failed, .catch(() => null)).
  if (!payload) return '';
  _ensureCopyHandlerInstalled();
  _ensureOptionsPollerInstalled();
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
