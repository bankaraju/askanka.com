// pipeline/terminal/static/js/components/analysis/envelope.js
// Shared envelope: every analysis engine renders through this shape.
// See docs/superpowers/specs/2026-04-23-unified-analysis-panel-design.md

export const VALID_VERDICTS = new Set([
  'LONG', 'SHORT', 'NEUTRAL', 'WATCH', 'NO_SIGNAL', 'UNAVAILABLE',
]);
export const VALID_BANDS = new Set(['GREEN', 'AMBER', 'RED', 'UNAVAILABLE']);
export const VALID_CALIBRATION = new Set(['walk_forward', 'heuristic']);

// Defensive constructor. Any malformed input → UNAVAILABLE envelope.
export function makeEnvelope(raw = {}) {
  const engine = raw.engine || 'unknown';
  const ticker = raw.ticker || '';
  const verdict = VALID_VERDICTS.has(raw.verdict) ? raw.verdict : 'UNAVAILABLE';
  const conviction_0_100 = (typeof raw.conviction_0_100 === 'number'
    && raw.conviction_0_100 >= 0 && raw.conviction_0_100 <= 100)
    ? raw.conviction_0_100 : null;
  const evidence = Array.isArray(raw.evidence) ? raw.evidence.slice(0, 3).map(e => ({
    name: String(e?.name || '—'),
    contribution: typeof e?.contribution === 'number' ? e.contribution : 0,
    direction: e?.direction === 'pos' || e?.direction === 'neg' ? e.direction
      : ((e?.contribution || 0) >= 0 ? 'pos' : 'neg'),
  })) : [];
  const rawBand = raw.health?.band;
  const band = VALID_BANDS.has(rawBand) ? rawBand : 'UNAVAILABLE';
  const calibration = VALID_CALIBRATION.has(raw.calibration) ? raw.calibration : 'heuristic';
  return {
    engine, ticker, verdict, conviction_0_100, evidence,
    health: { band, detail: String(raw.health?.detail || '') },
    calibration,
    computed_at: raw.computed_at || null,
    source: raw.source || null,
    empty_state_reason: raw.empty_state_reason || null,
  };
}
