"""Tests for the full forensic pipeline end-to-end."""
import tempfile

import pytest

from forensicagent.pipeline.orchestrator import ForensicPipeline


@pytest.fixture
def pipeline():
    with tempfile.TemporaryDirectory() as tmpdir:
        kb_dir = "sample_cases/insurance_fraud_001/domains/general"
        pipe = ForensicPipeline(
            case_id="TEST-E2E",
            domain="general",
            kb_dirs=[kb_dir],
            session_dir=tmpdir,
        )
        yield pipe
        pipe.close()


def test_full_pipeline(pipeline):
    sources = pipeline.ingest([
        "sample_cases/insurance_fraud_001/evidence/claim_file.txt",
        "sample_cases/insurance_fraud_001/evidence/police_report.txt",
    ])
    assert len(sources) == 2
    assert all(s.status.value == "usable" for s in sources)

    pipeline.index_keywords()
    facts, evidence = pipeline.extract_and_link()
    assert len(facts) > 0
    # After dedup, there may be more evidence items than facts
    # (multiple evidence point to the same merged fact).
    assert len(evidence) >= len(facts)

    pipeline.build_graph()

    # Check key facts are extracted.
    all_facts = pipeline.graph.all_facts()
    fact_types = {f.type for f in all_facts}
    assert "PERSON" in fact_types
    assert "TAX_ID" in fact_types
    assert "DATE" in fact_types
    assert "IBAN" in fact_types

    # Check PERSON values.
    persons = [f for f in all_facts if f.type == "PERSON"]
    person_values = {f.value for f in persons}
    assert "Max Mustermann" in person_values
    assert "Anna Schmidt" in person_values

    # Check tax ID.
    tax_ids = [f for f in all_facts if f.type == "TAX_ID"]
    assert any("MSTRRT56L21F205R" in f.value for f in tax_ids)

    # Requirements.
    reqs = pipeline.graph.all_requirements()
    assert len(reqs) >= 1


def test_query_returns_answer(pipeline):
    pipeline.ingest([
        "sample_cases/insurance_fraud_001/evidence/claim_file.txt",
    ])
    pipeline.index_keywords()
    pipeline.extract_and_link()
    pipeline.build_graph()

    result = pipeline.query("insurance fraud indicators")
    assert "answer" in result
    assert result["grounding"]["passed"]


def test_grounding_catches_hallucination(pipeline):
    """Verify the grounding agent would reject ungrounded claims."""
    pipeline.ingest([
        "sample_cases/insurance_fraud_001/evidence/claim_file.txt",
    ])
    pipeline.index_keywords()
    pipeline.extract_and_link()
    pipeline.build_graph()

    from forensicagent.agents.grounding import GroundingAgent
    grounder = pipeline._grounder
    result = grounder.verify("The total liability is $999,999.99")
    assert not result.passed
    assert any(c["type"] == "AMOUNT" for c in result.ungrounded_claims)


def test_grounding_accepts_confirmed_values(pipeline):
    pipeline.ingest([
        "sample_cases/insurance_fraud_001/evidence/police_report.txt",
    ])
    pipeline.index_keywords()
    pipeline.extract_and_link()
    pipeline.build_graph()

    from forensicagent.agents.grounding import GroundingAgent
    grounder = pipeline._grounder
    result = grounder.verify("The IBAN is DE44720300001234567890.")
    assert result.passed


def test_session_destruction(pipeline):
    pipeline.ingest([
        "sample_cases/insurance_fraud_001/evidence/claim_file.txt",
    ])
    pipeline.index_keywords()
    pipeline.extract_and_link()
    pipeline.build_graph()
    pipeline.graph.checkpoint()
    n_facts_before = len(pipeline.graph.all_facts())
    pipeline.close()
    assert n_facts_before > 0
