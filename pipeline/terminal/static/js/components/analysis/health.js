// pipeline/terminal/static/js/components/analysis/health.js
// Band → CSS var + computed_at → relative label.

const BAND_VAR = {
  GREEN: 'var(--accent-green)',
  AMBER: 'var(--accent-gold)',
  RED: 'var(--accent-red)',
  UNAVAILABLE: 'var(--text-muted)',
};

export function bandToCssVar(band) {
  return BAND_VAR[band] || 'var(--text-muted)';
}

// Cadence in minutes per engine (for stale detection).
export const CADENCE_MIN = { fcs: 15, ta: 1440, spread: 15, corr_break: 15 };

export function fmtRelative(isoAt, nowIso) {
  if (!isoAt) return '—';
  const t = new Date(isoAt).getTime();
  const now = nowIso ? new Date(nowIso).getTime() : Date.now();
  if (isNaN(t)) return '—';
  const mins = Math.floor((now - t) / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins} min ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  if (days === 1) return `yesterday ${new Date(isoAt).toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'})}`;
  return `${days}d ago`;
}

export function isStale(isoAt, engine, nowIso) {
  if (!isoAt) return true;
  const cadence = CADENCE_MIN[engine] || 60;
  const mins = (new Date(nowIso || Date.now()).getTime() - new Date(isoAt).getTime()) / 60000;
  return mins > 2 * cadence;
}
