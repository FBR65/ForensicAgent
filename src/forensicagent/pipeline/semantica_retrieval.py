"""Semantica retrieval wrapper (S-RETRIEVE).

Wraps ContextRetriever backed by ContextGraph to provide Multi-hop GraphRAG
retrieval.  When no SemanticaBackend is available, the wrapper is inert and
all methods return empty results, allowing the caller to fall back to BM25.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from forensicagent.pipeline.semantica_backend import is_available

logger = logging.getLogger(__name__)

try:
    from semantica.context import ContextRetriever, RetrievedContext
    _SEMANTICA_CTX = True
except ImportError:
    _SEMANTICA_CTX = False
    ContextRetriever = None  # type: ignore[assignment, misc]
    RetrievedContext = None  # type: ignore[assignment, misc]


class SemanticaRetrieval:
    """Multi-hop GraphRAG retrieval over a Semantica ContextGraph.

    Created from a :class:`~forensicagent.pipeline.semantica_backend.SemanticaBackend`.
    When *backend* is ``None`` the instance is inert (``is_available()`` returns
    ``False``) so callers can transparently fall back to BM25.
    """

    def __init__(self, backend: Optional[Any]) -> None:
        self._backend = backend
        self._retriever: Optional[ContextRetriever] = None

        if backend is not None and _SEMANTICA_CTX and is_available():
            try:
                cg = backend.context_graph
                self._retriever = ContextRetriever(
                    knowledge_graph=cg,
                    use_graph_expansion=True,
                    max_expansion_hops=3,
                    hybrid_alpha=1.0,  # graph-only (no vector store)
                )
                logger.info("SemanticaRetrieval initialised with ContextGraph")
            except Exception as exc:
                logger.warning("Failed to init ContextRetriever: %s", exc)
                self._retriever = None

    def is_available(self) -> bool:
        """Return ``True`` if Semantica retrieval is active."""
        return self._retriever is not None

    def graph_search(self, query: str, max_results: int = 5) -> list[Any]:
        """Graph-only search (no vector store).  Returns ``RetrievedContext`` list."""
        if not self.is_available():
            return []
        try:
            return self._retriever.graph_search(query, max_results=max_results)
        except Exception as exc:
            logger.warning("graph_search failed: %s", exc)
            return []

    def retrieve(self, query: str, max_results: int = 5) -> list[Any]:
        """Hybrid retrieval (graph + vector if configured).  Returns ``RetrievedContext`` list."""
        if not self.is_available():
            return []
        try:
            return self._retriever.retrieve(
                query,
                max_results=max_results,
                use_graph_expansion=True,
            )
        except Exception as exc:
            logger.warning("retrieve failed: %s", exc)
            return []

    def multi_hop_query(
        self, start_node: str, query_context: str, max_hops: int = 3
    ) -> dict[str, Any]:
        """Multi-hop context assembly from a start node."""
        if not self.is_available():
            return {}
        try:
            return self._retriever.multi_hop_context_assembly(
                start_node, query_context, max_hops=max_hops
            )
        except Exception as exc:
            logger.warning("multi_hop_query failed: %s", exc)
            return {}