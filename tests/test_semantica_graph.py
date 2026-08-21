"""Tests for Semantica integration in CaseGraph (S-GRAPH)."""

import pytest
from forensicagent.pipeline.graph import CaseGraph
from forensicagent.pipeline.semantica_backend import is_available, SemanticaBackend
from forensicagent.models import Source, SourceStatus, Fact, FactStatus, Evidence, Requirement


@pytest.fixture
def sample_source():
    return Source(
        id="SRC-TEST-1",
        path="/tmp/test.txt",
        mime="text/plain",
        status=SourceStatus.USABLE,
        raw_text="Test content",
    )


@pytest.fixture
def sample_fact():
    return Fact(
        id="FACT-TEST-1",
        case_id="TEST-CASE",
        type="PERSON",
        value="Max Mustermann",
        status=FactStatus.CONFIRMED,
        confidence=0.9,
        source_ids=["SRC-TEST-1"],
    )


@pytest.fixture
def sample_evidence():
    return Evidence(
        id="EV-TEST-1",
        source_id="SRC-TEST-1",
        fact_id="FACT-TEST-1",
        snippet="Name: Max Mustermann",
        start_char=6,
        end_char=19,
    )


@pytest.fixture
def sample_requirement():
    return Requirement(
        id="REQ-TEST-1",
        case_id="TEST-CASE",
        domain="general",
        description="Identity verification",
        required_fact_types=["PERSON"],
    )


@pytest.mark.skipif(not is_available(), reason="semantica not installed")
class TestCaseGraphSemanticaAdapter:
    """S-GRAPH: CaseGraph delegates to ContextGraph when backend is provided."""

    def test_graph_accepts_backend(self):
        """CaseGraph can be constructed with a SemanticaBackend."""
        backend = SemanticaBackend("TEST-GRAPH-1")
        graph = CaseGraph("TEST-GRAPH-1", backend=backend)
        assert graph._semantica_backend is not None
        assert graph._semantica_backend.context_graph is not None
        graph.destroy()

    def test_graph_without_backend_legacy(self):
        """CaseGraph without backend uses legacy NetworkX + LMDB."""
        graph = CaseGraph("TEST-LEGACY-1")
        assert graph._semantica_backend is None
        assert graph._graph is not None  # NetworkX DiGraph
        graph.destroy()

    def test_add_source_mirrors_to_context_graph(self, sample_source):
        """add_source() mirrors the source to ContextGraph."""
        backend = SemanticaBackend("TEST-GRAPH-2")
        graph = CaseGraph("TEST-GRAPH-2", backend=backend)
        graph.add_source(sample_source)
        # Source should exist in ContextGraph
        assert backend.context_graph.has_node(sample_source.id)
        graph.destroy()

    def test_add_fact_mirrors_to_context_graph(self, sample_source, sample_fact):
        """add_fact() mirrors the fact to ContextGraph."""
        backend = SemanticaBackend("TEST-GRAPH-3")
        graph = CaseGraph("TEST-GRAPH-3", backend=backend)
        graph.add_source(sample_source)
        graph.add_fact(sample_fact)
        assert backend.context_graph.has_node(sample_fact.id)
        graph.destroy()

    def test_add_evidence_mirrors_to_context_graph(self, sample_source, sample_fact, sample_evidence):
        """add_evidence() mirrors to ContextGraph."""
        backend = SemanticaBackend("TEST-GRAPH-4")
        graph = CaseGraph("TEST-GRAPH-4", backend=backend)
        graph.add_source(sample_source)
        graph.add_fact(sample_fact)
        graph.add_evidence(sample_evidence)
        assert backend.context_graph.has_node(sample_evidence.id)
        graph.destroy()

    def test_all_facts_works_with_backend(self, sample_source, sample_fact):
        """all_facts() returns correct results when using Semantica backend."""
        backend = SemanticaBackend("TEST-GRAPH-5")
        graph = CaseGraph("TEST-GRAPH-5", backend=backend)
        graph.add_source(sample_source)
        graph.add_fact(sample_fact)
        facts = graph.all_facts()
        assert len(facts) == 1
        assert facts[0].id == sample_fact.id
        graph.destroy()

    def test_fact_table_works_with_backend(self, sample_source, sample_fact, sample_evidence):
        """fact_table() returns correct results when using Semantica backend."""
        backend = SemanticaBackend("TEST-GRAPH-6")
        graph = CaseGraph("TEST-GRAPH-6", backend=backend)
        graph.add_source(sample_source)
        graph.add_fact(sample_fact)
        graph.add_evidence(sample_evidence)
        table = graph.fact_table()
        assert len(table) == 1
        assert table[0]["type"] == "PERSON"
        assert table[0]["value"] == "Max Mustermann"
        graph.destroy()

    def test_destroy_clears_backend(self, sample_source):
        """destroy() clears the SemanticaBackend."""
        backend = SemanticaBackend("TEST-GRAPH-7")
        graph = CaseGraph("TEST-GRAPH-7", backend=backend)
        graph.add_source(sample_source)
        graph.destroy()
        # Backend should be destroyed
        assert backend.context_graph is None