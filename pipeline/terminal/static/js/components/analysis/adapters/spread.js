// pipeline/terminal/static/js/components/analysis/adapters/spread.js
import { makeEnvelope } from '../envelope.js';

// Replaces the inline 5-layer narration block in candidate-drawer.js.
// `raw` is one entry from /api/research/digest spread_theses[].
export function adapt(ticker, raw) {
  if (!raw || typeof raw !== 'object') {
    return makeEnvelope({
      engine: 'spread', ticker, verdict: 'UNAVAILABLE',
      empty_state_reason: 'No spread thesis for this ticker.',
      calibration: 'heuristic',
    });
  }
  const pass = String(raw.gate_status || '').toUpperCase() === 'PASS';
  const conviction = String(raw.conviction || '').toUpperCase();
  const convictionMap = {HIGH: 80, MEDIUM: 60, LOW: 40};
  const conviction_0_100 = pass ? (convictionMap[conviction] ?? 40) : 20;

  const upper = String(ticker || '').toUpperCase();
  const isLong = (raw.long_legs || []).some(l => String(l || '').toUpperCase() === upper);
  const isShort = (raw.short_legs || []).some(l => String(l || '').toUpperCase() === upper);
  let verdict;
  if (!pass) verdict = 'WATCH';
  else if (isLong) verdict = 'LONG';
  else if (isShort) verdict = 'SHORT';
  else verdict = 'NEUTRAL';

  const evidence = [
    {name: 'regime_gate', contribution: raw.regime_fit ? 1 : -1, direction: raw.regime_fit ? 'pos' : 'neg'},
    {name: 'scorecard_delta', contribution: (raw.score != null && raw.score >= 70) ? 1 : -1,
      direction: (raw.score != null && raw.score >= 70) ? 'pos' : 'neg'},
    {name: 'z_score', contribution: (raw.z_score != null && Math.abs(raw.z_score) >= 1.5) ? 1 : -1,
      direction: (raw.z_score != null && Math.abs(raw.z_score) >= 1.5) ? 'pos' : 'neg'},
  ];

  return makeEnvelope({
    engine: 'spread', ticker,
    verdict,
    conviction_0_100,
    evidence,
    health: { band: pass ? 'GREEN' : 'AMBER',
              detail: raw.name ? `pair: ${raw.name}` : '' },
    calibration: 'heuristic',
    computed_at: raw.computed_at || null,
    source: 'static_config',
  });
}
