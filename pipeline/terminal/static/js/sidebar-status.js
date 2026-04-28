// pipeline/terminal/static/js/sidebar-status.js
//
// Polls /api/sidebar-status every 30s and paints per-tab counts + freshness
// dots into the sidebar buttons. Each button has data-badge-for="<tab>" and
// data-dot-for="<tab>" slots provisioned in index.html.
//
// Status → dot class:
//   live    → green pulsing  (within cadence)
//   fresh   → blue           (within 3× cadence)
//   stale   → amber          (older)
//   missing → red, dim       (file absent)
//
// Counts are suppressed when zero or null to keep the sidebar visually quiet
// when nothing is open. The dot is always visible so the user can see at a
// glance whether the underlying data is current.

const POLL_INTERVAL_MS = 30_000;
const STATUS_CLASSES = ['sidebar__dot--live', 'sidebar__dot--fresh', 'sidebar__dot--stale', 'sidebar__dot--missing'];

let pollHandle = null;

function applyTab(tab) {
  const badge = document.querySelector(`[data-badge-for="${tab.tab}"]`);
  if (badge) {
    if (tab.count != null && tab.count > 0) {
      badge.textContent = tab.count > 999 ? '999+' : String(tab.count);
      badge.classList.add('sidebar__badge--has-value');
      // Highlight when fresh data has actionable items (live/fresh status).
      if (tab.status === 'live' || tab.status === 'fresh') {
        badge.classList.add('sidebar__badge--accent');
      } else {
        badge.classList.remove('sidebar__badge--accent');
      }
    } else {
      badge.textContent = '';
      badge.classList.remove('sidebar__badge--has-value', 'sidebar__badge--accent');
    }
  }

  const dot = document.querySelector(`[data-dot-for="${tab.tab}"]`);
  if (dot) {
    dot.classList.remove(...STATUS_CLASSES);
    dot.classList.add(`sidebar__dot--${tab.status}`);
    const ageLabel = tab.age_s == null ? 'unknown' : formatAge(tab.age_s);
    const countLabel = tab.count == null ? '—' : tab.count;
    dot.title = `${tab.status} · ${countLabel} items · updated ${ageLabel} ago`;
  }
}

function formatAge(s) {
  if (s < 60) return `${s}s`;
  if (s < 3600) return `${Math.round(s / 60)}m`;
  if (s < 86400) return `${Math.round(s / 3600)}h`;
  return `${Math.round(s / 86400)}d`;
}

async function refresh() {
  try {
    const res = await fetch('/api/sidebar-status', { cache: 'no-store' });
    if (!res.ok) return;
    const data = await res.json();
    if (Array.isArray(data.tabs)) data.tabs.forEach(applyTab);
  } catch {
    // Silent — endpoint outage shouldn't break the sidebar; dots stay at
    // whatever the last successful fetch set them to.
  }
}

export function start() {
  if (pollHandle != null) return;
  refresh();
  pollHandle = setInterval(refresh, POLL_INTERVAL_MS);
}

export function stop() {
  if (pollHandle != null) {
    clearInterval(pollHandle);
    pollHandle = null;
  }
}
