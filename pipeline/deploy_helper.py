"""Route website-facing commits to the `master` branch via a dedicated
worktree, regardless of which branch the pipeline is currently running from.

WHY: GitHub Pages serves from `master`. Both `website_exporter.deploy_to_site`
and `daily_articles.py` used to `git push` on the active dev branch, which
meant weeks of data-refresh + article commits stayed invisible to the public
site while we lived on `feat/phase-c-v5`. See the cross-branch firefight on
2026-04-23 (commits 92c6e30, ec3e072) for what that looked like at the sharp
end.

Design: one sibling worktree `.askanka-deploy-master/` permanently checked out
at master. Before each publish we fetch origin/master and hard-reset the
worktree to origin/master (so other publishes from parallel runners don't
collide). We copy the declared files from the active dev worktree into the
master worktree, commit them there, and push. The active dev worktree is
never touched.
"""
from __future__ import annotations
import subprocess
from pathlib import Path


WEBSITE_BRANCH = "master"
REPO_ROOT = Path(__file__).resolve().parent.parent
# Sibling to the repo. Placing it outside the repo avoids git-inside-git
# weirdness and keeps `git status` on the dev worktree clean.
DEPLOY_WORKTREE = REPO_ROOT.parent / ".askanka-deploy-master"


class DeployError(RuntimeError):
    pass


def _run(cmd: list[str], cwd: Path, timeout: float | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True,
                          timeout=timeout, check=False)


def ensure_worktree() -> Path:
    """Make sure the master deploy worktree exists and is at origin/master.
    Returns the worktree path. Raises DeployError on fatal git failures.
    """
    if not DEPLOY_WORKTREE.exists():
        res = _run(["git", "worktree", "add", str(DEPLOY_WORKTREE), WEBSITE_BRANCH],
                   cwd=REPO_ROOT)
        if res.returncode != 0:
            raise DeployError(f"worktree add failed: {res.stderr.strip()[:200]}")

    fetch = _run(["git", "fetch", "origin", WEBSITE_BRANCH],
                 cwd=DEPLOY_WORKTREE, timeout=60)
    if fetch.returncode != 0:
        raise DeployError(f"fetch failed: {fetch.stderr.strip()[:200]}")

    reset = _run(["git", "reset", "--hard", f"origin/{WEBSITE_BRANCH}"],
                 cwd=DEPLOY_WORKTREE)
    if reset.returncode != 0:
        raise DeployError(f"reset failed: {reset.stderr.strip()[:200]}")

    return DEPLOY_WORKTREE


def publish(files_rel: list[str], commit_message: str) -> dict:
    """Copy `files_rel` (repo-relative paths) from the active worktree into
    the master worktree, commit them there with `commit_message`, and push
    origin master.

    Returns a dict: {"pushed": bool, "reason": str, "files": list[str]}.
    Never raises on a publish-only failure — a failed push leaves the dev
    worktree unchanged and returns {"pushed": False, "reason": "..."}.
    Raises DeployError only for setup failures that indicate a broken repo
    (missing worktree, fetch failure) — those deserve a stack trace upstream.
    """
    existing = [f for f in files_rel if (REPO_ROOT / f).exists()]
    if not existing:
        return {"pushed": False, "reason": "no files to publish", "files": []}

    wt = ensure_worktree()

    for rel in existing:
        src = REPO_ROOT / rel
        dst = wt / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(src.read_bytes())

    add = _run(["git", "add", "--"] + existing, cwd=wt)
    if add.returncode != 0:
        return {"pushed": False, "reason": f"add failed: {add.stderr.strip()[:200]}",
                "files": existing}

    diff = _run(["git", "diff", "--cached", "--quiet", "--"] + existing, cwd=wt)
    if diff.returncode == 0:
        return {"pushed": False, "reason": "no data changes", "files": existing}

    commit = _run(["git", "commit", "-m", commit_message], cwd=wt)
    if commit.returncode != 0:
        return {"pushed": False, "reason": f"commit failed: {commit.stderr.strip()[:200]}",
                "files": existing}

    push = _run(["git", "push", "origin", WEBSITE_BRANCH], cwd=wt, timeout=60)
    if push.returncode != 0:
        return {"pushed": False, "reason": f"push failed: {push.stderr.strip()[:200]}",
                "files": existing}

    return {"pushed": True, "reason": commit_message, "files": existing}
