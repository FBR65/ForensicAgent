"""Tests for the knowledge-base authoring assistant."""
import tempfile

from forensicagent.agents.knowledge_base import KnowledgeBaseAgent
from forensicagent.pipeline.orchestrator import ForensicPipeline


def test_kb_agent_deterministic():
    """Without an LLM key, the agent stores the raw description as a doc."""
    with tempfile.TemporaryDirectory() as tmp:
        agent = KnowledgeBaseAgent("TEST-KB", kb_dirs=[tmp])
        doc = agent.draft_from_description(
            "A device identifier is only usable if linked to a timestamp.",
            domain="cyber",
        )
        assert doc["id"]
        assert doc["tags"] == ["cyber"]
        assert "timestamp" in doc["body"].lower()

        path = agent.add_document(doc)
        assert path.exists()
        assert path.suffix == ".json"


def test_kb_agent_add_from_description():
    with tempfile.TemporaryDirectory() as tmp:
        agent = KnowledgeBaseAgent("TEST-KB", kb_dirs=[tmp])
        doc, path = agent.add_document_from_description(
            "IP addresses require a log entry as evidence.",
            domain="general",
        )
        assert path.exists()
        content = path.read_text(encoding="utf-8")
        assert "IP" in content or "IP" in doc["body"]


def test_kb_via_pipeline_and_rag():
    """Adding a doc via the pipeline makes it immediately searchable."""
    with tempfile.TemporaryDirectory() as tmp:
        pipe = ForensicPipeline(case_id="KB-E2E", kb_dirs=[tmp])
        res = pipe.build_kb_document(
            "Fraud indicators include missing receipts and conflicting timelines.",
            domain="general",
        )
        assert res["path"]
        hits = pipe._knowledge.retrieve("missing receipts conflicting timelines")
        assert any(h["id"] == res["document"]["id"] for h in hits)
        pipe.close()


def test_kb_agent_without_dirs_raises():
    agent = KnowledgeBaseAgent("TEST-KB", kb_dirs=[])
    try:
        agent.add_document({"id": "x", "body": "y"})
        assert False, "expected RuntimeError"
    except RuntimeError:
        pass
