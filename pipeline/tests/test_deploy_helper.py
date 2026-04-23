"""Unit tests for pipeline.deploy_helper.

The helper shells out to `git`, so these tests build a throw-away origin
repo + clone and exercise the real publish flow against it. This keeps the
wiring honest — a subprocess mock would hide exactly the branch-routing
bug this helper was written to fix.
"""
from __future__ import annotations
import subprocess
from pathlib import Path

import pytest


def _run(cmd, cwd, check=True):
    return subprocess.run(cmd, cwd=str(cwd), check=check,
                          capture_output=True, text=True)


@pytest.fixture
def repo_trio(tmp_path, monkeypatch):
    """Build origin (bare) + dev clone with a feature branch checked out.
    Return (origin, dev_repo, helper module reloaded against dev_repo)."""
    origin = tmp_path / "origin.git"
    _run(["git", "init", "--bare", "-b", "master", str(origin)], cwd=tmp_path)

    dev = tmp_path / "dev"
    _run(["git", "clone", str(origin), str(dev)], cwd=tmp_path)
    _run(["git", "config", "user.email", "t@t"], cwd=dev)
    _run(["git", "config", "user.name", "t"], cwd=dev)
    _run(["git", "checkout", "-b", "master"], cwd=dev)
    (dev / "data").mkdir()
    (dev / "data" / "seed.json").write_text('{"seed": 1}')
    _run(["git", "add", "."], cwd=dev)
    _run(["git", "commit", "-m", "seed"], cwd=dev)
    _run(["git", "push", "-u", "origin", "master"], cwd=dev)
    _run(["git", "checkout", "-b", "feat/dev"], cwd=dev)

    monkeypatch.syspath_prepend(str(dev))
    import importlib
    import pipeline.deploy_helper as dh
    monkeypatch.setattr(dh, "REPO_ROOT", dev)
    monkeypatch.setattr(dh, "DEPLOY_WORKTREE", tmp_path / ".deploy-master")
    importlib.reload(dh)  # no-op but keeps state fresh across tests
    monkeypatch.setattr(dh, "REPO_ROOT", dev)
    monkeypatch.setattr(dh, "DEPLOY_WORKTREE", tmp_path / ".deploy-master")
    return origin, dev, dh


def test_publish_routes_to_master_not_feature_branch(repo_trio):
    origin, dev, dh = repo_trio
    # Write a data file on the feature branch worktree — simulates
    # website_exporter producing a fresh JSON while we're on feat/dev.
    (dev / "data" / "new.json").write_text('{"fresh": true}')
    result = dh.publish(["data/new.json"], "data: test publish")
    assert result["pushed"] is True
    assert "data/new.json" in result["files"]

    # Dev branch MUST NOT have the file committed — only the working tree
    # copy should exist there.
    branch = _run(["git", "branch", "--show-current"], cwd=dev).stdout.strip()
    assert branch == "feat/dev"
    on_dev = _run(["git", "log", "--all", "--source", "--", "data/new.json"], cwd=dev).stdout
    # At least one commit touched the file (on master), but not on feat/dev.
    log_feat = _run(["git", "log", "feat/dev", "--oneline", "--", "data/new.json"],
                    cwd=dev, check=False).stdout.strip()
    assert log_feat == "", f"feat branch should not have the file; got: {log_feat}"

    # Origin's master must have it.
    log_origin = _run(["git", "log", "master", "--oneline", "--", "data/new.json"],
                      cwd=dev).stdout
    assert "data: test publish" in log_origin


def test_publish_noop_when_unchanged(repo_trio):
    _, dev, dh = repo_trio
    (dev / "data" / "same.json").write_text('{"x": 1}')
    first = dh.publish(["data/same.json"], "data: first")
    assert first["pushed"] is True

    second = dh.publish(["data/same.json"], "data: second")
    assert second["pushed"] is False
    assert "no data changes" in second["reason"]


def test_publish_skips_missing_files(repo_trio):
    _, _, dh = repo_trio
    result = dh.publish(["data/does_not_exist.json"], "data: ghost")
    assert result["pushed"] is False
    assert result["files"] == []
    assert "no files" in result["reason"]
