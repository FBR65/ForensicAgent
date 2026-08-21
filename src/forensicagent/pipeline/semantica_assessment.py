"""Semantica assessment wrapper (S-ASSESS, S-DECISION).

Wraps ContextGraph's decision-recording and causal-chain facilities to
provide AgnoDecisionKit-style tools: record_decision, find_precedents,
trace_causal_chain.  When no SemanticaBackend is available, the wrapper is
inert and all methods return empty/None, allowing callers to fall back to
the deterministic assessment mode.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from forensicagent.pipeline.semantica_backend import is_available

logger = logging.getLogger(__name__)


class SemanticaDecisionKit:
    """Decision recording and causal-chain tracing over a ContextGraph.

    Created from a :class:`~forensicagent.pipeline.semantica_backend.SemanticaBackend`.
    When *backend* is ``None`` the instance is inert.
    """

    def __init__(self, backend: Optional[Any]) -> None:
        self._backend = backend
        self._cg: Optional[Any] = None

        if backend is not None and is_available():
            self._cg = backend.context_graph
            logger.info("SemanticaDecisionKit initialised")

    def is_available(self) -> bool:
        """Return ``True`` if the decision kit is active."""
        return self._cg is not None

    def record_decision(
        self,
        category: str,
        scenario: str,
        reasoning: str,
        outcome: str,
        confidence: float,
        entities: Optional[list[str]] = None,
        decision_maker: str = "system",
    ) -> Optional[str]:
        """Record a decision in the ContextGraph.  Returns the decision ID."""
        if not self.is_available():
            return None
        try:
            dec_id = self._cg.record_decision(
                category=category,
                scenario=scenario,
                reasoning=reasoning,
                outcome=outcome,
                confidence=confidence,
                entities=entities,
                decision_maker=decision_maker,
            )
            logger.info("Decision recorded: %s (%s/%s)", dec_id, category, outcome)
            return dec_id
        except Exception as exc:
            logger.warning("record_decision failed: %s", exc)
            return None

    def add_causal_link(
        self, source_decision_id: str, target_decision_id: str,
        relationship_type: str = "CAUSED",
    ) -> bool:
        """Add a causal relationship between two decisions.

        Valid types: ``CAUSED``, ``INFLUENCED``, ``PRECEDENT_FOR``.
        """
        if not self.is_available():
            return False
        try:
            self._cg.add_causal_relationship(
                source_decision_id, target_decision_id, relationship_type
            )
            return True
        except Exception as exc:
            logger.warning("add_causal_link failed: %s", exc)
            return False

    def trace_decision_chain(self, decision_id: str, max_steps: int = 5) -> list[dict[str, Any]]:
        """Trace the causal chain for a decision.  Returns list of chain steps."""
        if not self.is_available():
            return []
        try:
            return self._cg.trace_decision_chain(decision_id, max_steps=max_steps)
        except Exception as exc:
            logger.warning("trace_decision_chain failed: %s", exc)
            return []

    def find_precedents(self, decision_id: str, limit: int = 10) -> list[Any]:
        """Find precedent decisions for the given decision."""
        if not self.is_available():
            return []
        try:
            return self._cg.find_precedents(decision_id, limit=limit)
        except Exception as exc:
            logger.warning("find_precedents failed: %s", exc)
            return []

    def get_causal_chain(
        self, decision_id: str, direction: str = "upstream", max_depth: int = 10
    ) -> list[Any]:
        """Get the causal chain (upstream or downstream) for a decision."""
        if not self.is_available():
            return []
        try:
            return self._cg.get_causal_chain(
                decision_id, direction=direction, max_depth=max_depth
            )
        except Exception as exc:
            logger.warning("get_causal_chain failed: %s", exc)
            return []