#!/usr/bin/env bash
# Push every local branch ahead of its upstream to origin.
# Idempotent. Designed to be called by systemd timer every 10 min.
# Logs to journalctl via stdout/stderr.
set -euo pipefail

REPO="${ANKA_REPO_ROOT:-/home/anka/askanka.com}"
cd "$REPO"

git fetch --prune --quiet origin || {
    echo "[auto-push] fetch failed — aborting cycle"
    exit 1
}

pushed=0
skipped=0
errored=0

while IFS= read -r branch; do
    [ -z "$branch" ] && continue

    upstream=$(git rev-parse --abbrev-ref --symbolic-full-name "${branch}@{u}" 2>/dev/null || true)
    if [ -z "$upstream" ]; then
        if git push --quiet -u origin "$branch" 2>/dev/null; then
            echo "[auto-push] new branch published: $branch"
            pushed=$((pushed + 1))
        else
            echo "[auto-push] FAILED to publish new branch: $branch"
            errored=$((errored + 1))
        fi
        continue
    fi

    ahead=$(git rev-list --count "${upstream}..${branch}" 2>/dev/null || echo 0)
    if [ "$ahead" -eq 0 ]; then
        skipped=$((skipped + 1))
        continue
    fi

    if git push --quiet origin "$branch" 2>/dev/null; then
        echo "[auto-push] pushed $ahead commits on $branch"
        pushed=$((pushed + 1))
    else
        echo "[auto-push] FAILED to push $branch (likely diverged — needs manual attention)"
        errored=$((errored + 1))
    fi
done < <(git for-each-ref --format='%(refname:short)' refs/heads/)

echo "[auto-push] summary: pushed=$pushed skipped=$skipped errored=$errored"
[ "$errored" -eq 0 ]
