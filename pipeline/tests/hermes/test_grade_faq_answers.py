from pipeline.scripts.hermes.grade_faq_answers import (
    build_grader_prompt,
    parse_grader_response,
    score_record,
)


def test_grader_prompt_includes_question_and_answer():
    record = {
        "id": "T1Q3", "tier": 1, "topic": "BH-FDR",
        "q": "What is BH-FDR?",
        "answer_text": "BH-FDR is...",
        "citations": ["docs/superpowers/specs/backtesting-specs.txt"],
        "quotes": [{"text": "0/448 passed", "source": "x.md"}],
    }
    sources_content = {"docs/superpowers/specs/backtesting-specs.txt": "section §6 BH-FDR..."}
    prompt = build_grader_prompt(record, sources_content)
    assert "What is BH-FDR?" in prompt
    assert "BH-FDR is..." in prompt
    assert "section §6" in prompt
    assert "JSON" in prompt


def test_parse_grader_response_extracts_scores():
    raw = """Some preamble.
{"citation": 1, "faithfulness": 2, "completeness": 1, "no_hallucination": 1,
 "notes": "Tier 1 needed 2 quotes; got 2."}
Trailing text."""
    r = parse_grader_response(raw)
    assert r["citation"] == 1
    assert r["faithfulness"] == 2
    assert r["completeness"] == 1
    assert r["no_hallucination"] == 1
    assert "2 quotes" in r["notes"]


def test_score_record_returns_per_dim_max_6():
    scored = {
        "citation": 1, "faithfulness": 2, "completeness": 2, "no_hallucination": 1,
        "notes": "clean"
    }
    record = {"id": "T1Q3", "tier": 1, "n_quotes_loose": 2}
    out = score_record(record, scored)
    assert out["score"] == 6
    assert out["max"] == 6
    assert out["pass"] is True


def test_tier1_zero_quotes_forces_zero_citation():
    """Tier 1 with <2 loose quotes -> automatic 0 on citation regardless of grader."""
    scored = {"citation": 1, "faithfulness": 2, "completeness": 2, "no_hallucination": 1, "notes": ""}
    record = {"id": "T1Q5", "tier": 1, "n_quotes_loose": 1}
    out = score_record(record, scored)
    assert out["citation_override"] == 0
    assert out["score"] == 5
