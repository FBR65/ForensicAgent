from __future__ import annotations

import json
import logging
from typing import Any, Optional

from forensicagent.agents.base import BaseAgent, llm_config, llm_enabled
from forensicagent.pipeline.graph import CaseGraph

logger = logging.getLogger(__name__)

_AGNO_AVAILABLE = False
try:
    from agno.agent import Agent
    from agno.models.openai import OpenAIChat
    _AGNO_AVAILABLE = True
except Exception:
    pass


class AssessmentAgent(BaseAgent):
    """The ONLY agent that may invoke an LLM.

    The LLM is given a tightly controlled context built by
    ``ContextBuilderAgent`` and is forbidden to use any data that has not
    been confirmed/approved in the evidentiary graph.

    If no OpenAI API key is set, the agent falls back to a deterministic
    graph-reasoning mode that simply queries confirmed facts.

    S-ASSESS / S-DECISION: When a
    :class:`~forensicagent.pipeline.semantica_assessment.SemanticaDecisionKit`
    is supplied, decisions are recorded in the Semantica ContextGraph with
    causal chains, enabling ``trace_decision_chain()`` and
    ``find_precedents()``.
    """

    name = "assessment"

    def __init__(
        self,
        case_id: str,
        graph: CaseGraph,
        decision_kit: Optional[Any] = None,
        llm_overrides: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(case_id)
        self._graph = graph
        self._decision_kit = decision_kit
        self._llm: Agent | None = None
        cfg = llm_config(llm_overrides)
        if _AGNO_AVAILABLE and cfg:
            self._llm = Agent(
                name="forensic-assessment-agent",
                model=OpenAIChat(
                    id=cfg["model_id"],
                    api_key=cfg["api_key"],
                    base_url=cfg.get("base_url"),
                ),
                instructions=[
                    "You are a forensic reasoning assistant.",
                    "Use ONLY facts whose status is CONFIRMED or APPROVED.",
                    "Cite the fact id and evidence id for every claim.",
                    "Never invent amounts, identifiers, courts, or dates.",
                    "If a fact is missing, say so explicitly rather than guessing.",
                    "Keep answers concise and cite sources.",
                ],
                markdown=True,
            )

    def assess(self, query: str, context: str) -> dict[str, Any]:
        if self._llm is not None:
            try:
                response = self._llm.run(context, stream=False)
                answer = response.content if hasattr(response, "content") else str(response)
                result = {"mode": "llm", "answer": answer, "context_used": True}
                # S-ASSESS: record the LLM-based decision.
                self._record_assessment(query, answer, "llm")
                return result
            except Exception as exc:
                logger.warning("LLM failed, falling back to deterministic mode: %s", exc)

        # Deterministic fallback: query confirmed facts.
        usable = self._graph.usable_facts()
        q_lower = query.lower()
        # Meaningful query terms (skip short/common words after strip).
        q_terms = [
            w.strip(".,?;:!'\"")
            for w in q_lower.split()
            if len(w.strip(".,?;:!'\"")) >= 3
        ]

        import re as _re
        relevant = [
            f for f in usable
            if any(
                # Types are controlled vocabulary — looser substring match.
                t in f.type.lower()
                # Values use word-boundary matching to avoid false hits.
                or _re.search(rf"\b{_re.escape(t)}\b", str(f.value).lower())
                for t in q_terms
            )
        ]
        if relevant:
            answer = "Based on confirmed evidence: " + "; ".join(
                f"[{f.id}] {f.type}={f.value}" for f in relevant[:10]
            )
        else:
            confirmed_types = list({f.type for f in usable})
            answer = (
                f"No confirmed facts match '{query}'. "
                f"Confirmed fact types available: {confirmed_types}. "
                "Further investigation is required."
            )
        result = {"mode": "deterministic", "answer": answer, "confirmed_facts": [f.id for f in relevant]}
        # S-ASSESS: record the deterministic decision.
        self._record_assessment(query, answer, "deterministic", relevant)
        return result

    def _record_assessment(
        self,
        query: str,
        answer: str,
        mode: str,
        relevant_facts: list | None = None,
    ) -> None:
        """S-ASSESS/S-DECISION: Record this assessment as a decision in the
        Semantica ContextGraph.  No-op when no decision kit is available.
        """
        if self._decision_kit is None or not self._decision_kit.is_available():
            return
        try:
            entities = [f.id for f in (relevant_facts or [])]
            dec_id = self._decision_kit.record_decision(
                category="assessment",
                scenario=query[:200],
                reasoning=answer[:500],
                outcome=mode,
                confidence=0.85 if mode == "llm" else 0.75,
                entities=entities,
                decision_maker="AssessmentAgent",
            )
            if dec_id:
                logger.info("Assessment decision recorded: %s", dec_id)
        except Exception as exc:
            logger.warning("Failed to record assessment decision: %s", exc)

    def run(self, *args, **kwargs):
        return {"status": "ok", "data": {}}
