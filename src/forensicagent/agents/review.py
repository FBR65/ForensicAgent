from __future__ import annotations

import logging
from typing import Any

from forensicagent.agents.base import BaseAgent
from forensicagent.models import Fact, FactStatus
from forensicagent.pipeline.graph import CaseGraph

logger = logging.getLogger(__name__)


class ReviewAgent(BaseAgent):
    """Manages the human-in-the-loop review workflow.

    Professionals can:
    - Override a Fact's status (e.g. promote CANDIDATE → CONFIRMED, or REJECTED → REVIEW).
    - Add a new Evidence record (manual professional integration).
    - Re-evaluate Requirements after corrections.
    """

    name = "review"

    def __init__(self, case_id: str, graph: CaseGraph) -> None:
        super().__init__(case_id)
        self._graph = graph

    def correct_fact_status(self, fact_id: str, new_status: str) -> Fact | None:
        fact = self._graph.get_fact(fact_id)
        if fact is None:
            logger.warning("Fact not found: %s", fact_id)
            return None
        old = fact.status
        fact.status = FactStatus(new_status)
        logger.info("Fact %s status changed: %s → %s", fact_id, old.value, new_status)
        return fact

    def add_manual_evidence(self, fact_id: str, snippet: str, source_id: str, confidence: float = 0.95) -> Any:
        from forensicagent.models import Evidence
        fact = self._graph.get_fact(fact_id)
        source = self._graph.get_source(source_id)
        if fact is None or source is None:
            raise ValueError("Fact or source not found")
        from forensicagent.agents.evidence_linking import EvidenceLinkingAgent
        link_agent = EvidenceLinkingAgent(self.case_id)
        ev = Evidence(
            id=f"E-MANUAL-{link_agent.new_id()}",
            source_id=source_id,
            fact_id=fact_id,
            snippet=snippet,
            confidence=confidence,
            metadata={"manual_review": True},
        )
        fact.evidence_ids.append(ev.id)
        return ev

    def re_evaluate_requirements(self) -> list[dict[str, Any]]:
        results = []
        for req in self._graph.all_requirements():
            req = self._graph.update_requirement_status(req)
            results.append({"requirement": req.id, "status": req.status.value, "missing": req.missing_fact_types})
        return results

    def run(self, *args, **kwargs):
        return {"status": "ok", "data": {}}
