"""Verifies the H-2026-04-29 intraday-v1 module imports cleanly and
that the registered hypothesis metadata is well-formed."""
from __future__ import annotations

import json
from pathlib import Path

MODULE_ROOT = Path(__file__).resolve().parents[1]


def test_package_imports():
    import pipeline.research.intraday_v1 as v1
    assert v1.__doc__ is not None
    assert "H-2026-04-29-intraday-data-driven-v1" in v1.__doc__


def test_hypothesis_json_has_twin_entries():
    p = MODULE_ROOT / "hypothesis.json"
    d = json.loads(p.read_text(encoding="utf-8"))
    assert "stocks" in d
    assert "indices" in d
    for pool in ("stocks", "indices"):
        h = d[pool]
        assert h["hypothesis_id"].endswith(f"v1-{pool}")
        assert h["holdout_start"] == "2026-04-29"
        assert h["holdout_end"] == "2026-06-27"
        assert h["status"] == "PRE_REGISTERED"


def test_registry_jsonl_has_twin_entries():
    registry = Path("docs/superpowers/hypothesis-registry.jsonl")
    lines = [json.loads(ln) for ln in registry.read_text(encoding="utf-8").splitlines() if ln.strip()]
    ids = {ln["hypothesis_id"] for ln in lines if "hypothesis_id" in ln}
    assert "H-2026-04-29-intraday-data-driven-v1-stocks" in ids
    assert "H-2026-04-29-intraday-data-driven-v1-indices" in ids
