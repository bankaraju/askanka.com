import { getHealth } from './lib/api.js';
import * as dashboard from './pages/dashboard.js';
import * as trading from './pages/trading.js';
import * as intelligence from './pages/intelligence.js';
import * as trackRecord from './pages/track-record.js';
import * as settings from './pages/settings.js';

const PAGES = {
  dashboard,
  trading,
  intelligence,
  'track-record': trackRecord,
  settings,
};

let currentPage = null;
let currentTab = 'dashboard';

function switchTab(tab) {
  if (tab === currentTab && currentPage) return;

  const main = document.getElementById('main-content');
  if (currentPage && currentPage.destroy) currentPage.destroy();

  document.querySelectorAll('.sidebar__item').forEach(el => {
    el.classList.toggle('sidebar__item--active', el.dataset.tab === tab);
  });

  const page = PAGES[tab];
  if (page) {
    page.render(main);
    currentPage = page;
    currentTab = tab;
  }
}

function closeContextPanel() {
  document.getElementById('context-panel').classList.remove('context-panel--open');
}

function updateClock() {
  const now = new Date();
  const ist = new Date(now.getTime() + (5.5 * 60 * 60 * 1000 - now.getTimezoneOffset() * 60 * 1000));
  const hh = String(ist.getUTCHours()).padStart(2, '0');
  const mm = String(ist.getUTCMinutes()).padStart(2, '0');
  const ss = String(ist.getUTCSeconds()).padStart(2, '0');
  document.getElementById('clock').textContent = `${hh}:${mm}:${ss} IST`;

  const hour = ist.getUTCHours();
  const min = ist.getUTCMinutes();
  const totalMin = hour * 60 + min;
  let status = 'CLOSED';
  if (totalMin >= 555 && totalMin < 570) status = 'PRE-OPEN';
  else if (totalMin >= 570 && totalMin < 930) status = 'OPEN';
  document.getElementById('market-status').textContent = `Market: ${status}`;
}

async function checkHealth() {
  try {
    const data = await getHealth();
    const staleFiles = Object.values(data.data_files || {}).filter(f => f.stale);
    const indicator = document.getElementById('stale-indicator');
    indicator.style.display = staleFiles.length > 0 ? 'inline-flex' : 'none';
  } catch {
    // health check failed silently
  }
}

function initKeyboard() {
  const tabKeys = { '1': 'dashboard', '2': 'trading', '3': 'intelligence', '4': 'track-record', '5': 'settings' };

  document.addEventListener('keydown', (e) => {
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;

    if (tabKeys[e.key]) {
      e.preventDefault();
      switchTab(tabKeys[e.key]);
    }
    if (e.key === 'Escape') {
      closeContextPanel();
    }
  });
}

function init() {
  document.querySelectorAll('.sidebar__item').forEach(btn => {
    btn.addEventListener('click', () => switchTab(btn.dataset.tab));
  });

  document.getElementById('context-panel-close').addEventListener('click', closeContextPanel);

  if (window.lucide) lucide.createIcons();

  updateClock();
  setInterval(updateClock, 1000);

  checkHealth();
  setInterval(checkHealth, 60000);

  initKeyboard();

  switchTab('dashboard');
}

document.addEventListener('DOMContentLoaded', init);
