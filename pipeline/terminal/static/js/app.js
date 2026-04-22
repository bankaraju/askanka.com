// pipeline/terminal/static/js/app.js
import { getHealth } from './lib/api.js';
import * as dashboard from './pages/dashboard.js';
import * as trading from './pages/trading.js';
import * as regime from './pages/regime.js';
import * as scanner from './pages/scanner.js';
import * as trust from './pages/trust.js';
import * as news from './pages/news.js';
import * as options from './pages/options.js';
import * as risk from './pages/risk.js';
import * as research from './pages/research.js';
import * as trackRecord from './pages/track-record.js';
import * as settings from './pages/settings.js';

const PAGES = {
  dashboard, trading, regime, scanner, trust, news, options, risk, research,
  'track-record': trackRecord, settings,
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

const IST_CLOCK_FMT = new Intl.DateTimeFormat('en-GB', {
  timeZone: 'Asia/Kolkata',
  hour12: false,
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
});

function updateClock() {
  // Always render IST regardless of the viewer's OS timezone. The prior
  // formula double-added the offset on IST machines (16:47 instead of 11:17),
  // flipping Market status to CLOSED during live hours.
  const parts = IST_CLOCK_FMT.formatToParts(new Date());
  const hh = parts.find(p => p.type === 'hour').value;
  const mm = parts.find(p => p.type === 'minute').value;
  const ss = parts.find(p => p.type === 'second').value;
  document.getElementById('clock').textContent = `${hh}:${mm}:${ss} IST`;
  const totalMin = Number(hh) * 60 + Number(mm);
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
  } catch { /* silent */ }
}

function initKeyboard() {
  const tabKeys = {
    '1': 'dashboard', '2': 'trading', '3': 'regime', '4': 'scanner',
    '5': 'trust', '6': 'news', '7': 'options', '8': 'risk',
    '9': 'research', '0': 'track-record',
  };
  document.addEventListener('keydown', (e) => {
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
    if (tabKeys[e.key]) { e.preventDefault(); switchTab(tabKeys[e.key]); }
    if (e.key === 'Escape') closeContextPanel();
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
