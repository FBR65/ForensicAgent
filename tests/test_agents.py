"""Tests for classification, keyword indexing, and quality control."""
from forensicagent.agents.classification import ClassificationAgent
from forensicagent.agents.keyword_index import KeywordIndexAgent
from forensicagent.agents.quality_control import QualityControlAgent
from forensicagent.models import Source


def test_quality_control_usable():
    qc = QualityControlAgent("TEST")
    src = Source(id="S-1", path="doc.txt", mime="text/plain",
                 raw_text="This is a normal document with enough text to be valid.")
    assert qc.assess(src).value == "usable"
    assert src.quality_score == 1.0


def test_quality_control_empty():
    qc = QualityControlAgent("TEST")
    src = Source(id="S-2", path="empty.txt", mime="text/plain", raw_text="")
    assert qc.assess(src).value == "blocking"


def test_classification_identity():
    agent = ClassificationAgent("TEST")
    src = Source(id="S-1", path="id.txt", mime="text/plain",
                 raw_text="Passport number 123456789. Issued on 2020-01-01.")
    cls = agent.classify(src)
    assert cls.category == "identity_document"


def test_classification_template():
    agent = ClassificationAgent("TEST")
    src = Source(id="S-2", path="form.txt", mime="text/plain",
                 raw_text="This is a sample form template. Please fill in your name here.")
    cls = agent.classify(src)
    assert cls.category == "template" or cls.function == "TEMPLATE"


def test_keyword_extraction():
    agent = KeywordIndexAgent("TEST")
    src = Source(id="S-1", path="doc.txt", mime="text/plain",
                 raw_text="Fraud investigation: evidence of fraudulent activity and fraud.")
    agent.index_sources([src])
    keywords = agent.extract_keywords(src, top_k=5)
    assert len(keywords) > 0
    assert "fraud" in keywords
