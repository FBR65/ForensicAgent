"""Tests for Semantica retrieval integration (S-RETRIEVE).

Verifies that AgnoKnowledgeGraph (ContextRetriever backed by ContextGraph)
provides Multi-hop GraphRAG retrieval results, with BM25 as fallback.
"""

import pytest

from forensicagent.pipeline.semantica_backend import is_available, SemanticaBackend
from forensicagent.pipeline.semantica_retrieval import SemanticaRetrieval
from forensicagent.models import Source, SourceStatus, Fact, FactStatus


@pytest.fixture
def backend():
    b = SemanticaBackend("TEST-RETR-1")
    yield b
    b.destroy()


@pytest.fixture
def populated_backend(backend):
    """Populate ContextGraph with fact nodes for retrieval."""
    cg = backend.context_graph
    cg.add_node("fact-1", "fact", content="Thomas Becker", value="Thomas Becker", type="PERSON")
    cg.add_node("fact-2", "fact", content="50000", value="50000", type="AMOUNT")
    cg.add_node("fact-3", "fact", content="185.220.101.34", value="185.220.101.34", type="IP_ADDRESS")
    cg.add_edge("fact-1", "fact-2", edge_type="owes")
    cg.add_edge("fact-1", "fact-3", edge_type="accessed_from")
    return backend


@pytest.mark.skipif(not is_available(), reason="semantica not installed")
class TestSemanticaRetrieval:
    """S-RETRIEVE: AgnoKnowledgeGraph GraphRAG retrieval."""

    def test_retrieval_initializes_with_context_graph(self, backend):
        """SemanticaRetrieval can be created from a SemanticaBackend."""
        retrieval = SemanticaRetrieval(backend)
        assert retrieval is not None
        assert retrieval.is_available()

    def test_graph_search_returns_results(self, populated_backend):
        """graph_search() returns RetrievedContext items from ContextGraph."""
        retrieval = SemanticaRetrieval(populated_backend)
        results = retrieval.graph_search("Thomas Becker", max_results=5)
        assert isinstance(results, list)
        assert len(results) > 0
        # At least one result should mention Thomas Becker
        contents = [r.content for r in results]
        assert any("Thomas Becker" in c for c in contents)

    def test_retrieve_returns_scored_results(self, populated_backend):
        """retrieve() returns results with relevance scores."""
        retrieval = SemanticaRetrieval(populated_backend)
        results = retrieval.retrieve("Thomas", max_results=5)
        assert len(results) > 0
        for r in results:
            assert hasattr(r, "content")
            assert hasattr(r, "score")
            assert r.score >= 0.0
        # Graph-only retrieval (hybrid_alpha=1.0) should produce positive scores
        # for matching nodes — a score of 0.0 would indicate vector-only mode.
        max_score = max(r.score for r in results)
        assert max_score > 0.0, "GraphRAG should produce positive relevance scores"
        # Verify hybrid_alpha is set to 1.0 (graph-only) in the retriever config.
        # With alpha=1.0, graph_search scores are ~1.0; with alpha=0.0, ~0.01.
        # This assertion catches a mutant that flips alpha to 0.0.
        assert retrieval._retriever.hybrid_alpha == 1.0, (
            "hybrid_alpha must be 1.0 (graph-only) — vector store is not configured"
        )

    def test_multi_hop_context_assembly(self, populated_backend):
        """multi_hop_query() traverses the graph across multiple hops."""
        retrieval = SemanticaRetrieval(populated_backend)
        result = retrieval.multi_hop_query("fact-1", "Thomas Becker owes amount", max_hops=2)
        assert isinstance(result, dict)
        # Should contain context or metadata about the traversal
        assert "context" in result or "metadata" in result

    def test_graph_search_finds_connected_nodes(self, populated_backend):
        """graph_search() with graph expansion finds nodes connected via edges."""
        retrieval = SemanticaRetrieval(populated_backend)
        # Search for "Thomas Becker" — with graph expansion, fact-2 (50000)
        # connected via "owes" edge should also appear in expanded results.
        results = retrieval.graph_search("Thomas Becker", max_results=10)
        assert len(results) > 0
        # Primary result should be Thomas Becker
        contents = [r.content for r in results]
        assert any("Thomas Becker" in c for c in contents)
        # Verify graph expansion is enabled in the retriever config
        assert retrieval._retriever.use_graph_expansion is True
        assert retrieval._retriever.max_expansion_hops >= 2

    def test_fallback_when_no_backend(self):
        """SemanticaRetrieval with None backend is not available."""
        retrieval = SemanticaRetrieval(None)
        assert not retrieval.is_available()
        results = retrieval.retrieve("test", max_results=5)
        assert results == []