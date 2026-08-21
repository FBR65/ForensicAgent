"""Integration tests for Semantica phases 7-9 in the pipeline agents.

These verify that the agent-level modifications correctly use the
Semantica wrappers (S-RETRIEVE, S-ASSESS, S-DECISION, S-QUERY) and that
the orchestrator wires them together properly.
"""

import tempfile
import pytest

from forensicagent.pipeline.semantica_backend import is_available, SemanticaBackend
from forensicagent.pipeline.semantica_retrieval import SemanticaRetrieval
from forensicagent.pipeline.semantica_assessment import SemanticaDecisionKit
from forensicagent.pipeline.semantica_query import SemanticaKGQuery
from forensicagent.pipeline.graph import CaseGraph
from forensicagent.agents.retrieval import KnowledgeRetrievalAgent
from forensicagent.agents.assessment import AssessmentAgent
from forensicagent.agents.context_builder import ContextBuilderAgent
from forensicagent.models import Source, SourceStatus, Fact, FactStatus, Evidence


@pytest.fixture
def backend():
    b = SemanticaBackend("TEST-INTEG-1")
    yield b
    b.destroy()


@pytest.fixture
def graph_with_facts(backend):
    """Build a CaseGraph with Semantica backend and populate it."""
    graph = CaseGraph("TEST-INTEG-1", backend=backend)

    src = Source(
        id="SRC-1", path="/tmp/test.txt", mime="text/plain",
        status=SourceStatus.USABLE, raw_text="Thomas Becker owes 50000 EUR",
    )
    fact = Fact(
        id="FACT-1", case_id="TEST-INTEG-1", type="PERSON",
        value="Thomas Becker", status=FactStatus.CONFIRMED,
        confidence=0.9, source_ids=["SRC-1"],
    )
    fact2 = Fact(
        id="FACT-2", case_id="TEST-INTEG-1", type="AMOUNT",
        value="50000", status=FactStatus.CONFIRMED,
        confidence=0.9, source_ids=["SRC-1"],
    )
    ev = Evidence(
        id="EV-1", source_id="SRC-1", fact_id="FACT-1",
        snippet="Thomas Becker", start_char=0, end_char=13,
    )
    graph.add_source(src)
    graph.add_fact(fact)
    graph.add_fact(fact2)
    graph.add_evidence(ev)
    return graph, backend


@pytest.mark.skipif(not is_available(), reason="semantica not installed")
class TestAgentIntegration:
    """Verify agents use Semantica wrappers correctly."""

    def test_retrieval_agent_uses_semantica(self, backend):
        """KnowledgeRetrievalAgent accepts semantica_retrieval and uses it."""
        retrieval = SemanticaRetrieval(backend)
        agent = KnowledgeRetrievalAgent("TEST-INTEG-1", semantica_retrieval=retrieval)
        # Without KB dirs, BM25 is empty, but semantica is available
        assert agent._semantica_retrieval is not None
        assert agent._semantica_retrieval.is_available()

    def test_retrieval_agent_fallback_without_semantica(self):
        """KnowledgeRetrievalAgent without semantica_retrieval falls back to BM25."""
        agent = KnowledgeRetrievalAgent("TEST-INTEG-2")
        assert agent._semantica_retrieval is None

    def test_assessment_agent_records_decision(self, graph_with_facts):
        """AssessmentAgent records a decision in Semantica when decision_kit is provided."""
        graph, backend = graph_with_facts
        kit = SemanticaDecisionKit(backend)
        agent = AssessmentAgent("TEST-INTEG-1", graph, decision_kit=kit)

        # Run assessment in deterministic mode (no OPENAI_API_KEY)
        result = agent.assess("Thomas Becker", "test context")
        assert result["mode"] == "deterministic"

        # The decision should have been recorded in the ContextGraph.
        # Verify by checking that the ContextGraph has at least one decision.
        cg = backend.context_graph
        summary = cg.get_graph_summary()
        # ContextGraph stores decisions as nodes; check that a decision node exists
        all_nodes = cg.find_nodes()
        decision_nodes = [n for n in all_nodes if n.get("type") == "decision"]
        assert len(decision_nodes) >= 1, "AssessmentAgent should have recorded a decision"

    def test_assessment_agent_fallback_without_kit(self, graph_with_facts):
        """AssessmentAgent without decision_kit still works (fallback)."""
        graph, _ = graph_with_facts
        agent = AssessmentAgent("TEST-INTEG-1", graph, decision_kit=None)
        result = agent.assess("Thomas Becker", "test context")
        assert result["mode"] == "deterministic"

    def test_context_builder_uses_kg_query(self, graph_with_facts):
        """ContextBuilderAgent includes graph query results when kg_query is available."""
        graph, backend = graph_with_facts
        kg_query = SemanticaKGQuery(backend)
        builder = ContextBuilderAgent("TEST-INTEG-1", kg_query=kg_query)

        context = builder.build_context(graph, "Thomas Becker")
        assert "GRAPH QUERY RESULTS" in context
        # The graph query section should contain at least one result line
        # (not just the empty header)
        graph_section = context.split("GRAPH QUERY RESULTS")[1].split("## QUERY")[0]
        graph_lines = [l for l in graph_section.strip().split("\n") if l.strip().startswith("- [graph:")]
        assert len(graph_lines) > 0, "Context builder should include graph query result lines"

    def test_context_builder_fallback_without_kg_query(self, graph_with_facts):
        """ContextBuilderAgent without kg_query still works (fallback)."""
        graph, _ = graph_with_facts
        builder = ContextBuilderAgent("TEST-INTEG-1", kg_query=None)
        context = builder.build_context(graph, "Thomas Becker")
        # The GRAPH QUERY RESULTS section should be empty but present
        assert "GRAPH QUERY RESULTS" in context

    def test_orchestrator_wires_semantica_components(self):
        """ForensicPipeline wires retrieval, decision_kit, and kg_query when Semantica is available."""
        from forensicagent.pipeline.orchestrator import ForensicPipeline

        with tempfile.TemporaryDirectory() as tmpdir:
            pipeline = ForensicPipeline(
                case_id="TEST-ORCH-1",
                domain="general",
                session_dir=tmpdir,
            )
            if is_available():
                assert pipeline.semantica_retrieval is not None
                assert pipeline.decision_kit is not None
                assert pipeline.kg_query is not None
            else:
                assert pipeline.semantica_retrieval is None
                assert pipeline.decision_kit is None
                assert pipeline.kg_query is None
            pipeline.close()

    def test_orchestrator_trace_decision(self):
        """ForensicPipeline.trace_decision returns a dict with chain info."""
        from forensicagent.pipeline.orchestrator import ForensicPipeline

        with tempfile.TemporaryDirectory() as tmpdir:
            pipeline = ForensicPipeline(
                case_id="TEST-ORCH-2",
                domain="general",
                session_dir=tmpdir,
            )
            if is_available():
                # Record a decision manually
                kit = pipeline.decision_kit
                dec_id = kit.record_decision(
                    category="test", scenario="test", reasoning="test",
                    outcome="test", confidence=0.5, entities=[],
                )
                result = pipeline.trace_decision(dec_id)
                assert isinstance(result, dict)
                assert "decision_id" in result
                assert result["decision_id"] == dec_id
            else:
                result = pipeline.trace_decision("nonexistent")
                assert result == {}
            pipeline.close()