// pipeline/terminal/static/js/components/analysis/adapters/ta.js
import { makeEnvelope } from '../envelope.js';

const PILOT = 'RELIANCE';

function _verdict(score) {
  if (score == null) return 'UNAVAILABLE';
  if (score >= 60) return 'LONG';
  if (score <= 40) return 'SHORT';
  return 'NEUTRAL';
}

export function adapt(ticker, raw) {
  const isPilot = String(ticker || '').toUpperCase() === PILOT;
  if (!isPilot) {
    return makeEnvelope({
      engine: 'ta', ticker, verdict: 'UNAVAILABLE',
      empty_state_reason: 'TA pilot — RELIANCE only, 212 tickers await v2 rollout.',
      calibration: 'walk_forward',
      health: { band: 'UNAVAILABLE', detail: 'daily bars, EOD cadence' },
    });
  }
  if (!raw || typeof raw !== 'object') {
    return makeEnvelope({
      engine: 'ta', ticker, verdict: 'UNAVAILABLE',
      empty_state_reason: 'TA model not yet fitted — awaiting Sunday 01:30 run.',
      calibration: 'walk_forward',
      health: { band: 'UNAVAILABLE', detail: 'daily bars, EOD cadence' },
    });
  }
  const score = Number.isFinite(raw.score) ? raw.score : null;
  const detailBits = ['daily bars, EOD cadence'];
  if (raw.mean_auc != null) detailBits.push(`mean AUC ${Number(raw.mean_auc).toFixed(2)}`);
  if (raw.min_fold_auc != null) detailBits.push(`min ${Number(raw.min_fold_auc).toFixed(2)}`);
  if (raw.n_folds != null) detailBits.push(`${raw.n_folds} folds`);
  return makeEnvelope({
    engine: 'ta', ticker,
    verdict: _verdict(score),
    conviction_0_100: score,
    evidence: (raw.top_features || []).slice(0, 3).map(t => ({
      name: t.name,
      contribution: Number.isFinite(t.contribution) ? t.contribution
        : ((t.sign === '-' ? -1 : 1) * (Number(t.magnitude) || 0) / 100),
      direction: t.sign === '-' ? 'neg' : 'pos',
    })),
    health: { band: raw.health || 'UNAVAILABLE', detail: detailBits.join(' · ') },
    calibration: 'walk_forward',
    computed_at: raw.computed_at || null,
    source: raw.source || 'own',
  });
}
