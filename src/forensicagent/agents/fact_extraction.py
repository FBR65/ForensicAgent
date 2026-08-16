from __future__ import annotations

import logging
from typing import Any

from forensicagent.agents.base import BaseAgent
from forensicagent.models import Evidence, Fact, FactStatus, Source
from forensicagent.utils.spacy_utils import extract_all_entities, split_sentences

logger = logging.getLogger(__name__)

# Maps spaCy / domain entity labels to internal fact types.
_LABEL_MAP = {
    "PER": "PERSON",
    "PERSON": "PERSON",
    "ORG": "ORGANIZATION",
    "LOC": "LOCATION",
    "GPE": "LOCATION",
    "DATE": "DATE",
    "TIME": "TIME",
    "MONEY": "AMOUNT",
    "AMOUNT": "AMOUNT",
    "TAX_CODE": "TAX_ID",
    "IBAN": "IBAN",
    "EMAIL": "EMAIL",
    "URL": "URL",
    "IP_ADDRESS": "IP_ADDRESS",
    "PHONE": "PHONE",
    "GERMAN_DATE": "DATE",
}


class FactExtractionAgent(BaseAgent):
    """Uses SpaCy (de_dep_news_trf) to extract entities, dates, amounts,
    and relationships from each source's text, producing atomic facts."""

    name = "fact_extraction"

    def extract(self, source: Source, graph_case_id: str) -> list[Fact]:
        facts: list[Fact] = []
        entities = extract_all_entities(source.raw_text)
        sentences = split_sentences(source.raw_text)

        for ent in entities:
            label = _LABEL_MAP.get(ent["label"], ent["label"])
            conf = 0.9 if ent["label"] in ("TAX_CODE", "IBAN", "IP_ADDRESS") else 0.7
            fact = Fact(
                id=self.new_id(),
                case_id=graph_case_id,
                type=label,
                value=ent["text"],
                confidence=conf,
                source_ids=[source.id],
                evidence_ids=[],
                metadata={
                    "start": ent["start"],
                    "end": ent["end"],
                    "sentence": ent.get("sentence", "")[:500],
                },
            )
            facts.append(fact)

        # Deduplicate overlapping duplicate entities of same type.
        facts = self._deduplicate(facts)
        logger.info("Extracted %d facts from source %s", len(facts), source.id)
        return facts

    def _deduplicate(self, facts: list[Fact]) -> list[Fact]:
        seen: dict[tuple[str, str], Fact] = {}
        for f in facts:
            key = (f.type, f.value.lower().strip())
            if key not in seen:
                seen[key] = f
            else:
                if f.confidence > seen[key].confidence:
                    seen[key] = f
        return list(seen.values())

    def extract_batch(self, sources: list[Source], graph_case_id: str) -> list[Fact]:
        all_facts: list[Fact] = []
        for s in sources:
            if s.raw_text:
                all_facts.extend(self.extract(s, graph_case_id))
        return all_facts

    def run(self, *args, **kwargs):
        return {"status": "ok", "data": {}}
