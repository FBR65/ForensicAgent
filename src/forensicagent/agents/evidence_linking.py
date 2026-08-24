from __future__ import annotations

import logging
from typing import Any

from forensicagent.agents.base import BaseAgent
from forensicagent.models import Evidence, Fact, FactStatus, Source
from forensicagent.utils.spacy_utils import split_sentences

logger = logging.getLogger(__name__)


class EvidenceLinkingAgent(BaseAgent):
    """For each Fact, create an **atomic Evidence** record — a small text
    fragment (sentence or character span) from the originating Source."""

    name = "evidence_linking"

    def link(self, fact: Fact, source: Source) -> list[Evidence]:
        evidence_items: list[Evidence] = []
        if not source.raw_text:
            return evidence_items

        start = fact.metadata.get("start")
        end = fact.metadata.get("end")

        if start is not None and end is not None:
            snippet = source.raw_text[max(0, start - 20): min(len(source.raw_text), end + 20)]
            page = self._find_page(source.raw_text, start)
            ev = Evidence(
                id=f"E-{self.new_id()}",
                source_id=source.id,
                fact_id=fact.id,
                snippet=snippet,
                page=page,
                start_char=start,
                end_char=end,
                confidence=0.9,
            )
            evidence_items.append(ev)
        else:
            sentences = split_sentences(source.raw_text)
            value_lower = str(fact.value).lower()
            for sent in sentences:
                if value_lower in sent.lower():
                    idx = source.raw_text.find(sent)
                    ev = Evidence(
                        id=f"E-{self.new_id()}",
                        source_id=source.id,
                        fact_id=fact.id,
                        snippet=sent,
                        page=self._find_page(source.raw_text, idx),
                        start_char=idx,
                        end_char=idx + len(sent),
                        confidence=0.8,
                    )
                    evidence_items.append(ev)
                    break

        fact.evidence_ids = [ev.id for ev in evidence_items]
        logger.debug("Linked %d evidence items to fact %s", len(evidence_items), fact.id)
        return evidence_items

    def link_batch(
        self, facts: list[Fact], sources_by_id: dict[str, Source]
    ) -> list[Evidence]:
        all_evidence: list[Evidence] = []
        for fact in facts:
            source = sources_by_id.get(fact.source_ids[0]) if fact.source_ids else None
            if source:
                all_evidence.extend(self.link(fact, source))
        return all_evidence

    def classify_fact(
        self, fact: Fact, source: Source | None
    ) -> FactStatus:
        """Apply deterministic rules to determine the FactStatus."""
        if fact.confidence < 0.5:
            return FactStatus.CANDIDATE
        if not fact.evidence_ids:
            return FactStatus.INCOMPLETE
        if source is None:
            return FactStatus.INCOMPLETE
        if source.status.value == "blocking":
            return FactStatus.REJECTED
        if source.status.value == "requires_review":
            return FactStatus.REVIEW
        if source.classification and source.classification.function == "TEMPLATE":
            return FactStatus.REJECTED
        return FactStatus.CONFIRMED

    @staticmethod
    def _find_page(text: str, char_pos: int) -> int | None:
        page_break = -1
        for boundary in ["\f", "===PAGE===", "---PAGE---"]:
            idx = text.find(boundary)
            if idx >= 0 and idx < char_pos:
                page_break = idx
        if page_break < 0:
            return None
        pages = text[:char_pos].count("\f")
        return pages

    def run(self, *args, **kwargs):
        return {"status": "ok", "data": {}}
