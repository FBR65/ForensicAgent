"""Tests for Semantica query integration (S-QUERY).

Verifies that AgnoKGToolkit (ContextGraph.query / find_related_nodes /
find_nodes / get_neighbors) provides a knowledge graph query interface.
"""

import pytest

from forensicagent.pipeline.semantica_backend import is_available, SemanticaBackend
from forensicagent.pipeline.semantica_query import SemanticaKGQuery
from forensicagent.models import Fact, FactStatus


@pytest.fixture
def backend():
    b = SemanticaBackend("TEST-QUERY-1")
    yield b
    b.destroy()


@pytest.fixture
def populated_backend(backend):
    """Populate ContextGraph with fact nodes and edges."""
    cg = backend.context_graph
    cg.add_node("fact-1", "fact", content="Thomas Becker", value="Thomas Becker", type="PERSON")
    cg.add_node("fact-2", "fact", content="50000", value="50000", type="AMOUNT")
    cg.add_node("fact-3", "fact", content="185.220.101.34", value="185.220.101.34", type="IP_ADDRESS")
    cg.add_edge("fact-1", "fact-2", edge_type="owes")
    cg.add_edge("fact-1", "fact-3", edge_type="accessed_from")
    return backend


@pytest.mark.skipif(not is_available(), reason="semantica not installed")
class TestSemanticaKGQuery:
    """S-QUERY: AgnoKGToolkit query interface over ContextGraph."""

    def test_kg_query_initializes(self, backend):
        """SemanticaKGQuery can be created from a SemanticaBackend."""
        query = SemanticaKGQuery(backend)
        assert query is not None
        assert query.is_available()

    def test_query_graph_returns_relevant_facts(self, populated_backend):
        """query_graph() returns facts relevant to the query string."""
        query = SemanticaKGQuery(populated_backend)
        results = query.query_graph("Thomas Becker")
        assert isinstance(results, list)
        assert len(results) > 0
        # Results should contain fact-1 (Thomas Becker)
        contents = [r.get("content", "") for r in results]
        assert any("Thomas Becker" in c for c in contents)

    def test_find_related_nodes(self, populated_backend):
        """find_related() returns nodes connected to the given node."""
        query = SemanticaKGQuery(populated_backend)
        related = query.find_related("fact-1", how_many=5)
        assert isinstance(related, list)
        assert len(related) > 0
        # fact-2 should be related to fact-1
        related_ids = [r.get("id", "") for r in related]
        assert "fact-2" in related_ids

    def test_get_neighbors(self, populated_backend):
        """get_neighbors() returns direct neighbors with edge info."""
        query = SemanticaKGQuery(populated_backend)
        neighbors = query.get_neighbors("fact-1", hops=1)
        assert isinstance(neighbors, list)
        assert len(neighbors) >= 2  # fact-2 and fact-3
        neighbor_ids = {n.get("id", "") for n in neighbors}
        assert "fact-2" in neighbor_ids
        assert "fact-3" in neighbor_ids

    def test_find_nodes_by_type(self, populated_backend):
        """find_nodes_by_type() returns all nodes of a given type."""
        query = SemanticaKGQuery(populated_backend)
        facts = query.find_nodes_by_type("fact")
        assert isinstance(facts, list)
        assert len(facts) == 3

    def test_export_subgraph(self, populated_backend):
        """export_subgraph() returns a serializable subgraph dict."""
        query = SemanticaKGQuery(populated_backend)
        subgraph = query.export_subgraph("fact-1", max_hops=2)
        assert isinstance(subgraph, dict)
        # Should contain nodes and/or edges
        assert "nodes" in subgraph or "context" in subgraph

    def test_fallback_when_no_backend(self):
        """SemanticaKGQuery with None backend is not available."""
        query = SemanticaKGQuery(None)
        assert not query.is_available()
        results = query.query_graph("test")
        assert results == []