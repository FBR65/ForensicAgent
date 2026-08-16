from __future__ import annotations

import json
import logging
import os
from typing import Any

from forensicagent.agents.base import BaseAgent
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
    """

    name = "assessment"

    def __init__(self, case_id: str, graph: CaseGraph) -> None:
        super().__init__(case_id)
        self._graph = graph
        self._llm: Agent | None = None
        if _AGNO_AVAILABLE and os.getenv("OPENAI_API_KEY"):
            self._llm = Agent(
                name="forensic-assessment-agent",
                model=OpenAIChat(id="gpt-4o-mini"),
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
                return {"mode": "llm", "answer": answer, "context_used": True}
            except Exception as exc:
                logger.warning("LLM failed, falling back to deterministic mode: %s", exc)

        # Deterministic fallback: query confirmed facts.
        usable = self._graph.usable_facts()
        q_lower = query.lower()
        # Meaningful query terms (skip short/common words after strip).
        q_terms = [
            w.strip(".,?;:!\'\"")
            for w in q_lower.split()
            if len(w.strip(".,?;:!\'\"")) >= 3
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
        return {"mode": "deterministic", "answer": answer, "confirmed_facts": [f.id for f in relevant]}

    def run(self, *args, **kwargs):
        return {"status": "ok", "data": {}}
