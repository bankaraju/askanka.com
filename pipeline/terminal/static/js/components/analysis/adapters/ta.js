// pipeline/terminal/static/js/components/analysis/adapters/ta.js
import { makeEnvelope } from '../envelope.js';
import { modelEdgePhrases } from '../lay_language.js';

function _verdict(score) {
  if (score == null) return 'UNAVAILABLE';
  if (score >= 60) return 'LONG';
  if (score <= 40) return 'SHORT';
  return 'NEUTRAL';
}

export function adapt(ticker, raw) {
  if (!raw || typeof raw !== 'object') {
    return makeEnvelope({
      engine: 'ta', ticker, verdict: 'UNAVAILABLE',
      empty_state_reason: 'No TA model yet — awaiting fit run.',
      calibration: 'walk_forward',
      health: { band: 'UNAVAILABLE', detail: 'daily bars, EOD cadence' },
    });
  }
  if (raw.score == null || raw.health === 'RED' || raw.health === 'UNAVAILABLE') {
    const reason = raw.health === 'RED'
      ? 'Model unreliable — edge below calibration threshold.'
      : 'Model not calibrated — insufficient history or unstable folds.';
    return makeEnvelope({
      engine: 'ta', ticker, verdict: 'UNAVAILABLE',
      empty_state_reason: reason,
      calibration: 'walk_forward',
      health: { band: raw.health || 'UNAVAILABLE', detail: 'daily bars, EOD cadence' },
    });
  }
  const score = Number.isFinite(raw.score) ? raw.score : null;
  const detailBits = ['daily bars, EOD cadence', ...modelEdgePhrases({
    mean_auc: raw.mean_auc, min_fold_auc: raw.min_fold_auc, n_folds: raw.n_folds,
  })];
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
