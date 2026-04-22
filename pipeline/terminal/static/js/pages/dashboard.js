import { get } from '../lib/api.js';
import * as regimeBanner from '../components/regime-banner.js';
import * as positionsTable from '../components/positions-table.js';
import * as scenarioStrip from '../components/scenario-strip.js';
import * as attractiveness from '../components/attractiveness-cell.js';
import { startLivePolling } from '../components/live-ticker.js';

let refreshTimer = null;
let _mounted = false;
// 5s LTP poller stop handle. The live-ticker patches Dashboard LTP + P&L
// cells in-place between the 15-min backend snapshots; it's purely a
// presentation-layer loop and does not rewrite live_status.json.
let _stopLiveTicker = null;

export async function render(container) {
  _mounted = true;
  container.innerHTML = `
    <div id="dash-regime"></div>
    <div id="dash-mode-badge" style="margin: var(--spacing-sm) 0;"></div>
    <div id="dash-positions"></div>
    <div id="dash-scenarios"></div>`;

  await loadData();
  if (!_mounted) return;
  if (refreshTimer) clearInterval(refreshTimer);
  refreshTimer = setInterval(loadData, 30000);

  // Start the 5s LTP poller after the first render so annotated cells exist.
  // live-ticker re-scans the DOM on each tick, so it naturally survives the
  // 30s loadData() re-render that replaces the positions-table innerHTML.
  if (_stopLiveTicker) { _stopLiveTicker(); _stopLiveTicker = null; }
  _stopLiveTicker = startLivePolling(5000);
}

export function destroy() {
  _mounted = false;
  if (refreshTimer) { clearInterval(refreshTimer); refreshTimer = null; }
  if (_stopLiveTicker) { _stopLiveTicker(); _stopLiveTicker = null; }
}

async function loadData() {
  // Fetch regime + signals + attractiveness in parallel. Attractiveness is a
  // soft dependency — if it fails (stale fixture, endpoint down), we still
  // render positions; the per-row badge simply won't appear. Same pattern
  // as trading.js:39-44.
  const [regime, signals, scores] = await Promise.allSettled([
    get('/regime'),
    get('/signals'),
    attractiveness.fetchAll(),
  ]);

  const regimeData = regime.status === 'fulfilled'
    ? regime.value
    : { zone: 'UNKNOWN', stable: false, consecutive_days: 0 };

  // Single snapshot for both header and table — fixes the 5-vs-6 race.
  const positions = signals.status === 'fulfilled'
    ? (signals.value.positions || [])
    : [];

  // Attach per-position attractiveness so positions-table can render the
  // trajectory badge synchronously (see components/attractiveness-badge.js).
  // Multi-leg baskets don't get a per-ticker score — positions-table skips
  // those rows anyway, but we still leave .attractiveness undefined for them.
  const scoreMap = (scores.status === 'fulfilled' && scores.value && scores.value.scores) || {};
  for (const p of positions) {
    const raw = p.long_legs?.[0]?.ticker || p.short_legs?.[0]?.ticker || p.ticker;
    if (!raw) { p.attractiveness = undefined; continue; }
    p.attractiveness = scoreMap[String(raw).toUpperCase()];
  }

  const regimeEl = document.getElementById('dash-regime');
  if (regimeEl) regimeBanner.render(regimeEl, regimeData);

  const modeEl = document.getElementById('dash-mode-badge');
  if (modeEl) {
    modeEl.innerHTML = `<span class="badge badge--muted" style="font-size: 0.6875rem;">MODE: SHADOW</span>`;
  }

  const posEl = document.getElementById('dash-positions');
  if (posEl) positionsTable.render(posEl, positions);

  const scenEl = document.getElementById('dash-scenarios');
  if (scenEl) scenarioStrip.render(scenEl, positions, regimeData);
}
