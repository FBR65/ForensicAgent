from __future__ import annotations

import logging
from typing import Any

from forensicagent.agents.base import BaseAgent
from forensicagent.models import Fact, Requirement, Source
from forensicagent.pipeline.graph import CaseGraph
from forensicagent.agents.retrieval import KnowledgeRetrievalAgent

logger = logging.getLogger(__name__)


class ContextBuilderAgent(BaseAgent):
    """Assembles the *controlled context* that is passed to the LLM.

    The context contains only:
    - Facts whose status is CONFIRMED or APPROVED (never CANDIDATE / REJECTED)
    - Requirement satisfaction map
    - Domain rules
    - Relevant knowledge-base snippets (retrieved via BM25)

    Rejected or unproven data is explicitly *excluded*.
    """

    name = "context_builder"

    def build_context(
        self,
        graph: CaseGraph,
        query: str,
        knowledge_agent: KnowledgeRetrievalAgent | None = None,
        max_facts: int = 50,
        max_kb_snippets: int = 5,
    ) -> str:
        usable_facts = graph.usable_facts()[:max_facts]
        fact_lines: list[str] = []
        for f in usable_facts:
            snippet = ""
            evs = graph.evidence_for_fact(f.id)
            if evs:
                snippet = evs[0].snippet[:300].replace("\n", " ")
            fact_lines.append(
                f"  - [fact:{f.id}] type={f.type}, value={f.value!r}, "
                f"confidence={f.confidence:.2f}, evidence_snippet=\"{snippet}\""
            )

        req_lines: list[str] = []
        for req in graph.all_requirements():
            req = graph.update_requirement_status(req)
            req_lines.append(
                f"  - {req.description} [{req.status.value}] "
                f"(missing: {req.missing_fact_types})"
            )

        kb_lines: list[str] = []
        if knowledge_agent:
            kb_results = knowledge_agent.retrieve(query, top_k=max_kb_snippets)
            for r in kb_results:
                body = r.get("body", "")[:500].replace("\n", " ")
                kb_lines.append(f"  - [{r['id']}] {body}")

        sources = graph.all_sources()
        src_summary = "\n".join(
            f"  - {s.id}: {s.metadata.get('filename', 'unknown')} "
            f"(type={s.classification.category if s.classification else '?'}, "
            f"function={s.classification.function if s.classification else '?'}, "
            f"status={s.status.value})"
            for s in sources
        )

        context = (
            "# FORENSIC CASE CONTEXT (evidence-constrained)\n\n"
            "## IMPORTANT RULES\n"
            "- Use ONLY facts marked CONFIRMED or APPROVED.\n"
            "- Cite the fact id and evidence id for every claim you make.\n"
            "- Never invent amounts, identifiers, courts, or dates.\n"
            "- If a fact is missing or uncertain, say so explicitly.\n\n"
            f"## CASE OVERVIEW\n"
            f"Case ID: {graph.case_id}\n"
            f"Sources: {len(sources)}\n"
            f"Confirmed/approved facts: {len(usable_facts)}\n\n"
            f"## SOURCES\n{src_summary}\n\n"
            f"## CONFIRMED FACTS\n" + "\n".join(fact_lines) + "\n\n"
            f"## REQUIREMENTS\n" + "\n".join(req_lines) + "\n\n"
            f"## DOMAIN KNOWLEDGE (retrieved)\n" + "\n".join(kb_lines) + "\n\n"
            f"## QUERY\n{query}\n\n"
            "## ANSWER (cite fact ids):\n"
        )
        return context

    def run(self, *args, **kwargs):
        return {"status": "ok", "data": {}}
