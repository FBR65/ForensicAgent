"""Tests for fact extraction and evidence linking agents."""
from forensicagent.agents.fact_extraction import FactExtractionAgent
from forensicagent.agents.evidence_linking import EvidenceLinkingAgent
from forensicagent.models import Fact, FactStatus, Source, SourceStatus

SAMPLE_TEXT = """
Insured Person: Max Mustermann
Tax ID: MSTRRT56L21F205R
Date of Birth: 15.03.1985
Residence: Berliner Str. 45, 10115 Berlin, Germany
Phone: +49 30 98765432
Email: max.mustermann@email.de

Vehicle: VW Golf VII, VIN: WVWZZZ1JZ2N001234
Date of Loss: 02.07.2026
"""


def test_fact_extraction():
    agent = FactExtractionAgent("TEST-FACT")
    src = Source(id="S-1", path="test.txt", mime="text/plain", raw_text=SAMPLE_TEXT)
    facts = agent.extract(src, "TEST-CASE")
    types = {f.type for f in facts}
    assert "PERSON" in types
    assert "TAX_ID" in types
    assert "DATE" in types
    assert "PHONE" in types
    assert "EMAIL" in types
    persons = [f for f in facts if f.type == "PERSON"]
    assert any(f.value == "Max Mustermann" for f in persons)
    tax_ids = [f for f in facts if f.type == "TAX_ID"]
    assert any(f.value == "MSTRRT56L21F205R" for f in tax_ids)


def test_evidence_linking():
    agent = EvidenceLinkingAgent("TEST-EVID")
    src = Source(id="S-1", path="test.txt", mime="text/plain", raw_text=SAMPLE_TEXT)
    fact_extractor = FactExtractionAgent("TEST-FACT")
    facts = fact_extractor.extract(src, "TEST-CASE")
    evidence = agent.link_batch(facts, {"S-1": src})
    assert len(evidence) > 0
    for ev in evidence:
        assert ev.source_id == "S-1"
        assert len(ev.snippet) > 0


def test_classify_fact_usable():
    agent = EvidenceLinkingAgent("TEST-EVID")
    from forensicagent.models import DocumentClass
    src = Source(
        id="S-1", path="test.txt", mime="text/plain", raw_text=SAMPLE_TEXT,
        status=SourceStatus.USABLE,
    )
    src.classification = DocumentClass(category="identity_document", function="PRIMARY", weight=5)
    fact = Fact(id="F-1", case_id="TEST", type="PERSON", value="Max Mustermann",
                confidence=0.9, source_ids=["S-1"], evidence_ids=["E-1"])
    status = agent.classify_fact(fact, src)
    assert status == FactStatus.CONFIRMED


def test_classify_fact_rejected_on_template():
    agent = EvidenceLinkingAgent("TEST-EVID")
    src = Source(
        id="S-1", path="test.txt", mime="text/plain", raw_text=SAMPLE_TEXT,
        status=SourceStatus.USABLE,
    )
    from forensicagent.models import DocumentClass
    src.classification = DocumentClass(category="template", function="TEMPLATE", weight=2)
    fact = Fact(id="F-1", case_id="TEST", type="PERSON", value="Template Name",
                confidence=0.9, source_ids=["S-1"], evidence_ids=["E-1"])
    status = agent.classify_fact(fact, src)
    assert status == FactStatus.REJECTED


def test_validation_agent():
    from forensicagent.agents.validation import ValidationAgent

    agent = ValidationAgent("TEST-VAL", domain="general")
    fact_ok = Fact(id="F-1", case_id="TEST", type="PERSON", value="Max Mustermann",
                   confidence=0.9, status=FactStatus.CONFIRMED,
                   source_ids=["S-1"], evidence_ids=["E-1"])
    # AMOUNT with no evidence → fails error-level rule.
    fact_low_conf = Fact(id="F-2", case_id="TEST", type="AMOUNT", value="999.99",
                         confidence=0.3, source_ids=["S-1"], evidence_ids=[])
    r1 = agent.validate_fact(fact_ok)
    assert r1.final_status == FactStatus.CONFIRMED
    r2 = agent.validate_fact(fact_low_conf)
    assert r2.final_status == FactStatus.REJECTED
