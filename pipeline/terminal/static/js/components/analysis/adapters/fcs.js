// pipeline/terminal/static/js/components/analysis/adapters/fcs.js
import { makeEnvelope } from '../envelope.js';

function _verdict(score) {
  if (score == null) return 'UNAVAILABLE';
  if (score >= 60) return 'LONG';
  if (score <= 40) return 'SHORT';
  return 'NEUTRAL';
}

export function adapt(ticker, raw) {
  if (!raw || typeof raw !== 'object') {
    return makeEnvelope({
      engine: 'fcs', ticker, verdict: 'UNAVAILABLE',
      empty_state_reason: 'No FCS score available for this ticker.',
      calibration: 'walk_forward',
    });
  }
  const score = Number.isFinite(raw.score) ? raw.score : null;
  const detailBits = [];
  if (raw.mean_auc != null) detailBits.push(`mean AUC ${Number(raw.mean_auc).toFixed(2)}`);
  if (raw.min_fold_auc != null) detailBits.push(`min ${Number(raw.min_fold_auc).toFixed(2)}`);
  if (raw.n_folds != null) detailBits.push(`${raw.n_folds} folds`);
  return makeEnvelope({
    engine: 'fcs', ticker,
    verdict: _verdict(score),
    conviction_0_100: score,
    evidence: (raw.top_features || []).slice(0, 3).map(t => ({
      name: t.name, contribution: t.contribution,
      direction: (t.contribution || 0) >= 0 ? 'pos' : 'neg',
    })),
    health: { band: raw.health || 'UNAVAILABLE', detail: detailBits.join(' · ') },
    calibration: 'walk_forward',
    computed_at: raw.computed_at || null,
    source: raw.source || 'own',
  });
}
