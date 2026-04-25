from pipeline.autoresearch.etf_stock_tail.verdict import build_gate_checklist, render_verdict_md


def test_pass_when_all_gates_pass():
    inputs = {
        "model_ce": 0.985,
        "baseline_ces": {"B0_always_prior": 1.10, "B1_regime_logistic": 1.04, "B2_interactions_logistic": 1.00},
        "perm_p_value": 0.002,
        "fragility_verdict": "STABLE",
        "calibration_residualized_ce": 0.99,
        "calibration_residualized_baseline_min_ce": 1.01,
        "holdout_pct": 0.17,
        "n_holdout": 50_000,
    }
    cl = build_gate_checklist(inputs)
    assert cl["decision"] == "PASS"
    rows = {r["section"]: r["status"] for r in cl["rows"]}
    assert rows["§9B.1"] == "PASS"
    assert rows["§9B.2"] == "PASS"
    assert rows["§9A"] == "PASS"
    assert rows["§10"] == "PARTIAL"


def test_fail_when_model_loses_to_baseline():
    inputs = {
        "model_ce": 1.020,
        "baseline_ces": {"B0_always_prior": 1.10, "B1_regime_logistic": 1.04, "B2_interactions_logistic": 1.00},
        "perm_p_value": 0.20,
        "fragility_verdict": "STABLE",
        "calibration_residualized_ce": 1.05,
        "calibration_residualized_baseline_min_ce": 1.01,
        "holdout_pct": 0.17,
        "n_holdout": 50_000,
    }
    cl = build_gate_checklist(inputs)
    assert cl["decision"] == "FAIL"


def test_render_verdict_md_has_sections():
    cl = {
        "decision": "PASS",
        "rows": [{"section": "§9B.1", "status": "PASS", "note": "Δ=0.015 nats"}],
        "perm_p_value": 0.002,
        "model_ce": 0.985,
        "baseline_ces": {"B0_always_prior": 1.10, "B2_interactions_logistic": 1.00},
        "fragility_verdict": "STABLE",
    }
    md = render_verdict_md(cl, hypothesis_id="H-2026-04-25-002", run_id="abc123")
    assert "H-2026-04-25-002" in md
    assert "PASS" in md
    assert "§9B.1" in md
