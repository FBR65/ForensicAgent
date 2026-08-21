"""Semantica KG query wrapper (S-QUERY).

Wraps ContextGraph's query and traversal methods to provide
AgnoKGToolkit-style tools: query_graph, find_related, find_nodes_by_type,
get_neighbors, export_subgraph.  When no SemanticaBackend is available,
the wrapper is inert and all methods return empty results.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from forensicagent.pipeline.semantica_backend import is_available

logger = logging.getLogger(__name__)


class SemanticaKGQuery:
    """Knowledge-graph query interface over a ContextGraph.

    Created from a :class:`~forensicagent.pipeline.semantica_backend.SemanticaBackend`.
    When *backend* is ``None`` the instance is inert.
    """

    def __init__(self, backend: Optional[Any]) -> None:
        self._backend = backend
        self._cg: Optional[Any] = None

        if backend is not None and is_available():
            self._cg = backend.context_graph
            logger.info("SemanticaKGQuery initialised")

    def is_available(self) -> bool:
        """Return ``True`` if the KG query interface is active."""
        return self._cg is not None

    def query_graph(self, query: str, limit: Optional[int] = None) -> list[dict[str, Any]]:
        """Query the graph by text.  Returns list of node dicts with content and score."""
        if not self.is_available():
            return []
        try:
            return self._cg.query(query, limit=limit) if limit else self._cg.query(query)
        except Exception as exc:
            logger.warning("query_graph failed: %s", exc)
            return []

    def find_related(self, node_id: str, how_many: int = 10) -> list[dict[str, Any]]:
        """Find nodes related to the given node by content similarity."""
        if not self.is_available():
            return []
        try:
            return self._cg.find_related_nodes(node_id, how_many=how_many)
        except Exception as exc:
            logger.warning("find_related failed: %s", exc)
            return []

    def get_neighbors(
        self, node_id: str, hops: int = 1
    ) -> list[dict[str, Any]]:
        """Get neighbors of a node within *hops* hops."""
        if not self.is_available():
            return []
        try:
            return self._cg.get_neighbors(node_id, hops=hops)
        except Exception as exc:
            logger.warning("get_neighbors failed: %s", exc)
            return []

    def find_nodes_by_type(self, node_type: str) -> list[dict[str, Any]]:
        """Find all nodes of a given type/label."""
        if not self.is_available():
            return []
        try:
            return self._cg.get_nodes_by_label(node_type)
        except Exception as exc:
            logger.warning("find_nodes_by_type failed: %s", exc)
            return []

    def find_nodes(self, node_type: Optional[str] = None) -> list[dict[str, Any]]:
        """Find all nodes, optionally filtered by type."""
        if not self.is_available():
            return []
        try:
            return self._cg.find_nodes(node_type=node_type)
        except Exception as exc:
            logger.warning("find_nodes failed: %s", exc)
            return []

    def export_subgraph(self, start_node: str, max_hops: int = 2) -> dict[str, Any]:
        """Export a subgraph starting from *start_node* within *max_hops*.

        Returns a dict with ``nodes`` and ``edges`` lists.
        """
        if not self.is_available():
            return {}
        try:
            # Use multi-hop context assembly for the subgraph
            neighbors = self._cg.get_neighbors(start_node, hops=max_hops)
            nodes: list[dict[str, Any]] = []
            edges: list[dict[str, Any]] = []

            # Include the start node
            start_node_data = self._cg.find_nodes()
            for n in start_node_data:
                if n.get("id") == start_node:
                    nodes.append(n)
                    break

            # Add neighbors as nodes
            for nb in neighbors:
                node_entry = {
                    "id": nb.get("id", ""),
                    "type": nb.get("type", ""),
                    "content": nb.get("content", ""),
                    "hop": nb.get("hop", 1),
                }
                nodes.append(node_entry)
                edge_entry = {
                    "from": start_node,
                    "to": nb.get("id", ""),
                    "relationship": nb.get("relationship", "related_to"),
                    "weight": nb.get("weight", 1.0),
                }
                edges.append(edge_entry)

            return {"nodes": nodes, "edges": edges}
        except Exception as exc:
            logger.warning("export_subgraph failed: %s", exc)
            return {}