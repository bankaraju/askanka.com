# pipeline/tests/test_etf_v3_eval/test_gate_ladder.py
from pipeline.autoresearch.etf_v3_eval.phase_2.gate_ladder import (
    evaluate_research_to_paper_shadow,
    GateVerdict,
)


def test_pass_when_all_required_gates_pass():
    evidence = {
        "s0_pass": True, "s1_pass": True,
        "data_audit_tag": "CLEAN",
        "survivorship_disclosed": True,
        "entry_timing_pass": True,
        "direction_audit_verdict": "aligned",
        "n_trades": 75, "min_required": 50,
        "fragility_verdict": "stable",
        "naive_benchmark_beaten": True,
        "purged_walkforward": True,
        "alpha_after_beta_pass": True,
        "hypothesis_registered": True,
    }
    v = evaluate_research_to_paper_shadow(evidence)
    assert v.verdict == GateVerdict.PASS
    assert v.failed_gates == []


def test_fail_when_direction_suspect():
    evidence = {
        "s0_pass": True, "s1_pass": True, "data_audit_tag": "CLEAN",
        "survivorship_disclosed": True, "entry_timing_pass": True,
        "direction_audit_verdict": "suspect",
        "n_trades": 75, "min_required": 50,
        "fragility_verdict": "stable", "naive_benchmark_beaten": True,
        "purged_walkforward": True, "alpha_after_beta_pass": True,
        "hypothesis_registered": True,
    }
    v = evaluate_research_to_paper_shadow(evidence)
    assert v.verdict == GateVerdict.FAIL
    assert "direction_audit" in v.failed_gates


import pytest


def _full_evidence_pass():
    return {
        "s0_pass": True, "s1_pass": True,
        "data_audit_tag": "CLEAN",
        "survivorship_disclosed": True,
        "entry_timing_pass": True,
        "direction_audit_verdict": "aligned",
        "n_trades": 75, "min_required": 50,
        "fragility_verdict": "stable",
        "naive_benchmark_beaten": True,
        "purged_walkforward": True,
        "alpha_after_beta_pass": True,
        "hypothesis_registered": True,
    }


def test_missing_evidence_key_raises():
    from pipeline.autoresearch.etf_v3_eval.phase_2.gate_ladder import (
        evaluate_research_to_paper_shadow,
    )
    ev = _full_evidence_pass()
    del ev["s0_pass"]
    with pytest.raises(KeyError, match="s0_pass"):
        evaluate_research_to_paper_shadow(ev)


def test_unknown_data_audit_tag_raises():
    from pipeline.autoresearch.etf_v3_eval.phase_2.gate_ladder import (
        evaluate_research_to_paper_shadow,
    )
    ev = _full_evidence_pass()
    ev["data_audit_tag"] = "MAYBE"
    with pytest.raises(ValueError, match="data_audit_tag"):
        evaluate_research_to_paper_shadow(ev)


def test_unknown_direction_verdict_raises():
    from pipeline.autoresearch.etf_v3_eval.phase_2.gate_ladder import (
        evaluate_research_to_paper_shadow,
    )
    ev = _full_evidence_pass()
    ev["direction_audit_verdict"] = "mostly-aligned"
    with pytest.raises(ValueError, match="direction_audit_verdict"):
        evaluate_research_to_paper_shadow(ev)


def test_data_impaired_passes_data_gate():
    """DATA-IMPAIRED is the warn-but-OK tag; should NOT add data_audit to failed_gates."""
    from pipeline.autoresearch.etf_v3_eval.phase_2.gate_ladder import (
        evaluate_research_to_paper_shadow,
    )
    ev = _full_evidence_pass()
    ev["data_audit_tag"] = "DATA-IMPAIRED"
    rep = evaluate_research_to_paper_shadow(ev)
    assert "data_audit" not in rep.failed_gates


def test_auto_fail_data_audit_fails_gate():
    from pipeline.autoresearch.etf_v3_eval.phase_2.gate_ladder import (
        evaluate_research_to_paper_shadow,
    )
    ev = _full_evidence_pass()
    ev["data_audit_tag"] = "AUTO-FAIL"
    rep = evaluate_research_to_paper_shadow(ev)
    assert "data_audit" in rep.failed_gates


def test_report_dict_is_json_serializable():
    import json
    from pipeline.autoresearch.etf_v3_eval.phase_2.gate_ladder import (
        evaluate_research_to_paper_shadow,
    )
    ev = _full_evidence_pass()
    rep = evaluate_research_to_paper_shadow(ev)
    d = rep.report_dict(ev)
    serialized = json.dumps(d)  # must not raise
    parsed = json.loads(serialized)
    assert parsed["verdict"] == "pass"
    assert parsed["failed_gates"] == []
    assert "timestamp_utc" in parsed
    assert parsed["generator_version"] == "phase_2_v1"
