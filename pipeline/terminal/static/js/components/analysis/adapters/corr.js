// pipeline/terminal/static/js/components/analysis/adapters/corr.js
import { makeEnvelope } from '../envelope.js';

export function adapt(ticker, raw) {
  if (!raw || typeof raw !== 'object' || raw.sigma == null) {
    return makeEnvelope({
      engine: 'corr_break', ticker, verdict: 'UNAVAILABLE',
      empty_state_reason: 'No correlation-break observation for this ticker.',
      calibration: 'heuristic',
    });
  }
  const sigma = Number(raw.sigma) || 0;
  const abs = Math.abs(sigma);
  const conviction_0_100 = Math.min(100, Math.round(abs * 25));
  let verdict = 'NEUTRAL';
  if (abs >= 1.5) verdict = sigma < 0 ? 'LONG' : 'SHORT';

  const fields = [
    {name: 'sigma', value: sigma},
    {name: 'sector_divergence', value: Number(raw.sector_divergence) || 0},
    {name: 'volume_anomaly', value: Number(raw.volume_anomaly) || 0},
    {name: 'trust_delta', value: Number(raw.trust_delta) || 0},
  ];
  fields.sort((a, b) => Math.abs(b.value) - Math.abs(a.value));
  const evidence = fields.slice(0, 3).map(f => ({
    name: f.name, contribution: f.value,
    direction: f.value >= 0 ? 'pos' : 'neg',
  }));

  return makeEnvelope({
    engine: 'corr_break', ticker, verdict, conviction_0_100,
    evidence,
    health: { band: 'UNAVAILABLE', detail: 'heuristic — no calibration yet' },
    calibration: 'heuristic',
    computed_at: raw.computed_at || null,
    source: 'own',
  });
}
