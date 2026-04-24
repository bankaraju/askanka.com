# Deprecations — 2026-04-24

## Hard retirements (DEAD, cannot re-enter engine without new hypothesis)

### Phase C cross-sectional geometry
- **Packages:** `pipeline/autoresearch/phase_c_cross_sectional/`
- **Evidence:** H-2026-04-24-002 abandoned at n=116; H-2026-04-24-003 FAIL (margin −4.98, p=0.81, Fragility STABLE 26/27). Tag: `H-2026-04-24-003-FAIL`.
- **Retirement scope:** geometry as originally framed (asymmetric-threshold persistent-break Lasso on the full 213-ticker F&O panel). The artefact directory stays for reproducibility; no live code references this strategy for signal generation.

## Phantom-data code paths fixed in the same commit

All production code that previously could have read `pipeline/data/regime_history.csv` now reads the causal file produced by Task 0a of the regime-aware autoresearch engine. As of the 2026-04-24 sweep, no Python code under `pipeline/` (excluding the new `regime_autoresearch/` tree) reads `regime_history.csv` by that exact filename — verified via `grep -rn "regime_history.csv" pipeline/`. Historical phantom readers either never existed under that name or have been cleaned up.

Related but distinct files that do exist and are actively read:
- `pipeline/data/msi_history.json` — read by `pipeline/feature_scorer/fit_universe.py::_load_regime_history` (name is coincidental; this reads the MSI regime series, not the ETF regime).
- `pipeline/data/regime_history.json` — read by `pipeline/unified_regime_engine.py` (rolling 100-entry window of regime calls with metadata, distinct purpose from the Task 0a causal CSV).

## Policy going forward

Any new trading-rule file in `pipeline/` must be accompanied by a `docs/superpowers/hypothesis-registry.jsonl` entry with `status ∈ {PRE_REGISTERED, LIVE}`. This is enforced by the pre-commit hook added in Task 7 of the regime-aware autoresearch plan.
