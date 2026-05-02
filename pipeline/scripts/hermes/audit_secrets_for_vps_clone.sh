#!/usr/bin/env bash
# Pre-VPS-clone secrets audit. Greps tracked files for likely secret patterns.
# Prints suspicious files; exits non-zero if any are found.
#
# Run from anywhere inside the repo. Usage:
#   pipeline/scripts/hermes/audit_secrets_for_vps_clone.sh
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

# Patterns that almost certainly indicate a real secret if present in tracked files.
# Each entry is a regex passed to `git grep -E`.
PATTERNS=(
  'sk-[A-Za-z0-9]{20,}'
  'AIza[A-Za-z0-9_-]{35}'
  'AKIA[0-9A-Z]{16}'
  '-----BEGIN .* PRIVATE KEY-----'
  '"api_key"\s*:\s*"[A-Za-z0-9_-]{16,}"'
  '"access_token"\s*:\s*"[A-Za-z0-9_-]{16,}"'
)

SUSPECT=$(mktemp)
trap 'rm -f "$SUSPECT"' EXIT

for pat in "${PATTERNS[@]}"; do
  # -I skips binary files (parquet/png/etc. can match regexes by random byte coincidence)
  git grep -I -l -E "$pat" -- \
    ':(exclude)*.example' \
    ':(exclude)*.template' \
    ':(exclude)docs/**' \
    ':(exclude)*.md' \
    >> "$SUSPECT" 2>/dev/null || true
done

# Also check for tracked .env-like files (excluding examples/templates)
git ls-files \
  | grep -E '(^|/)\.env($|\.)' \
  | grep -v '\.example$' \
  | grep -v '\.template$' \
  >> "$SUSPECT" || true

sort -u "$SUSPECT" -o "$SUSPECT"

if [[ -s "$SUSPECT" ]]; then
  echo "FAIL: tracked files matched secret patterns:"
  cat "$SUSPECT"
  exit 1
fi

echo "PASS: no tracked secrets detected"
