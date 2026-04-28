import { renderTabHeader, renderEmptyState } from '../components/tab-header.js';

const HEADER_PROPS = {
  title: 'Settings',
  subtitle: 'Broker connection, alert routing (Telegram), display preferences, and feature flags. The terminal currently runs in SHADOW mode — no real orders are placed.',
  cadence: 'Static page. Changes apply on next page load.',
};

export function render(container) {
  container.innerHTML = renderTabHeader(HEADER_PROPS) + renderEmptyState({
    title: 'Settings UI not yet wired',
    reason: 'Broker (Kite) session is currently managed by the AnkaRefreshKite scheduled task at 09:00 IST. Telegram alerts are configured via .env. There is no in-terminal switch yet.',
    nextUpdate: 'Coming in Plan 6 — broker connect, alert toggles, mode switch, theme.',
  });
}

export function destroy() {}
