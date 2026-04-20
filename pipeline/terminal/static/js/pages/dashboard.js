import { get } from '../lib/api.js';
import * as regimeBanner from '../components/regime-banner.js';
import * as positionsTable from '../components/positions-table.js';
import * as scenarioStrip from '../components/scenario-strip.js';

let refreshTimer = null;
let _mounted = false;

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
}

export function destroy() {
  _mounted = false;
  if (refreshTimer) { clearInterval(refreshTimer); refreshTimer = null; }
}

async function loadData() {
  const [regime, signals] = await Promise.allSettled([
    get('/regime'), get('/signals'),
  ]);

  const regimeData = regime.status === 'fulfilled'
    ? regime.value
    : { zone: 'UNKNOWN', stable: false, consecutive_days: 0 };

  // Single snapshot for both header and table — fixes the 5-vs-6 race.
  const positions = signals.status === 'fulfilled'
    ? (signals.value.positions || [])
    : [];

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
