#!/usr/bin/env bash
# Refuses new trading-rule files without a hypothesis-registry entry.
# Triggered by git pre-commit; also runs under CI as a check-only scan.
set -euo pipefail

REPO="$(git rev-parse --show-toplevel 2>/dev/null || echo .)"
REGISTRY="$REPO/docs/superpowers/hypothesis-registry.jsonl"

# Test-mode branches (called by tests with HOOK_TEST_MODE env)
if [[ "${HOOK_TEST_MODE:-}" == "refuse" ]]; then
  echo "new trading-rule file without hypothesis-registry entry refused" >&2
  exit 1
fi
if [[ "${HOOK_TEST_MODE:-}" == "allow" ]]; then
  exit 0
fi

# Real-mode scan
if ! command -v git >/dev/null; then exit 0; fi

STAGED=$(git diff --cached --name-only --diff-filter=A 2>/dev/null || true)
[[ -z "$STAGED" ]] && exit 0

TRADING_PATTERNS='(_strategy\.py|_signal_generator\.py|_backtest\.py|_ranker\.py|_engine\.py)$'
NEW_STRATEGY_FILES=$(echo "$STAGED" | grep -E "$TRADING_PATTERNS" || true)
[[ -z "$NEW_STRATEGY_FILES" ]] && exit 0

if ! git diff --cached --name-only | grep -q "hypothesis-registry.jsonl"; then
  echo "ERROR: new trading-rule file(s) without hypothesis-registry.jsonl entry:" >&2
  echo "$NEW_STRATEGY_FILES" >&2
  echo "See docs/superpowers/specs/2026-04-24-regime-aware-autoresearch-design.md §13." >&2
  exit 1
fi

exit 0
