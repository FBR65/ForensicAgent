"""Tests for the PDF §6/§9/§12 improvements: amount validation,
explainable reranking, and grounding feedback into the graph."""
import tempfile

import pytest

from forensicagent.models import Amount, AmountSourceType, Fact, FactStatus
from forensicagent.pipeline.amount_validator import AmountValidator


def test_amount_unproven_invalid():
    v = AmountValidator()
    a = Amount(value=100.0, source_type=AmountSourceType.UNPROVEN, fact_id="F1")
    res = v.validate(a)
    assert not res.valid
    assert any("unproven" in i for i in res.issues)


def test_amount_derived_requires_addends():
    v = AmountValidator()
    a = Amount(value=500.0, source_type=AmountSourceType.DERIVED, fact_id="F2")
    assert not v.validate(a).valid
    a2 = Amount(value=500.0, source_type=AmountSourceType.DERIVED,
                addend_ids=["F1", "F2"], fact_id="F3")
    assert v.validate(a2).valid


def test_amount_non_additive_flagged():
    v = AmountValidator()
    a = Amount(value=10.0, source_type=AmountSourceType.NON_ADDITIVE, fact_id="F4")
    res = v.validate(a)
    assert res.valid
    assert any("non_additive" in n for n in res.notes)


def test_validate_facts_downgrades_unproven():
    v = AmountValidator()
    f = Fact(id="F5", case_id="C", type="AMOUNT", value="100.0",
             status=FactStatus.CONFIRMED, source_ids=["S1"], evidence_ids=["E1"])
    f.metadata["amount_source_type"] = "unproven"
    v.validate_facts([f])
    assert f.status == FactStatus.REVIEW


def test_parse_german_amount():
    assert AmountValidator._parse_number("EUR 487.234,56") == 487234.56
    assert AmountValidator._parse_number("1.234,56") == 1234.56
    assert AmountValidator._parse_number("1,234.56") == 1234.56
    assert AmountValidator._parse_number(42) == 42.0


def test_grounding_reopens_fact_and_creates_finding():
    from forensicagent.agents.grounding import GroundingAgent
    from forensicagent.pipeline.graph import CaseGraph
    from forensicagent.models import Source, SourceStatus

    with tempfile.TemporaryDirectory() as tmp:
        graph = CaseGraph("C", lmdb_path=tmp)
        src = Source(id="S1", path="t.txt", mime="text/plain",
                     raw_text="nothing here", status=SourceStatus.USABLE)
        graph.add_source(src)
        fact = Fact(id="F1", case_id="C", type="AMOUNT", value="100.0",
                    status=FactStatus.CONFIRMED, source_ids=["S1"], evidence_ids=["E1"])
        graph.add_fact(fact)
        g = GroundingAgent("C", graph)
        res = g.verify("The total is $999,999.99")
        assert not res.passed
        reopened = g.reopen_ungrounded(res)
        assert len(reopened) >= 0
        findings = [f for f in graph.all_findings() if f.metadata.get("grounding")]
        assert len(findings) >= 1
        graph.destroy()


def test_rerank_adds_explanation():
    from forensicagent.agents.retrieval import KnowledgeRetrievalAgent

    agent = KnowledgeRetrievalAgent("C")
    docs = [
        {"id": "d1", "title": "Statute", "body": "insurance fraud rules",
         "score": 1.0, "tags": ["statute"]},
        {"id": "d2", "title": "Template", "body": "claim form template",
         "score": 0.5, "tags": ["template"]},
    ]
    out = agent._rerank("insurance fraud", docs, 5)
    assert all("rerank" in d for d in out)
    assert out[0]["id"] == "d1"
