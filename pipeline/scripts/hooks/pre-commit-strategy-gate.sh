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

PATTERNS_FILE="$REPO/pipeline/scripts/hooks/strategy_patterns.txt"
if [[ ! -f "$PATTERNS_FILE" ]]; then
  echo "ERROR: missing $PATTERNS_FILE — repo install incomplete" >&2
  exit 1
fi
TRADING_PATTERNS=$(cat "$PATTERNS_FILE")
NEW_STRATEGY_FILES=$(echo "$STAGED" | grep -E "$TRADING_PATTERNS" || true)
[[ -z "$NEW_STRATEGY_FILES" ]] && exit 0

if ! git diff --cached --name-only | grep -qE '(^|/)hypothesis-registry\.jsonl$'; then
  echo "ERROR: new trading-rule file(s) without hypothesis-registry.jsonl entry:" >&2
  echo "$NEW_STRATEGY_FILES" >&2
  echo "See docs/superpowers/specs/2026-04-24-regime-aware-autoresearch-design.md §13." >&2
  exit 1
fi

exit 0
