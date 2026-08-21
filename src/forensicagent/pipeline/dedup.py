"""Entity deduplication wrapper for ForensicAgent.

Uses Semantica's DuplicateDetector and EntityMerger to merge facts that
refer to the same real-world entity across multiple source documents.

When no backend is available, deduplicate_facts returns the input unchanged.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from forensicagent.models import Fact, FactStatus

logger = logging.getLogger(__name__)

# Fact types that should be deduplicated by exact value match
_EXACT_MATCH_TYPES = {"IBAN", "TAX_CODE", "IP_ADDRESS", "DEVICE_ID", "EMAIL", "ACCOUNT"}

# Fact types that should be deduplicated by name similarity
_NAME_MATCH_TYPES = {"PERSON", "ORG"}


class EntityDeduplicator:
    """Wraps Semantica's deduplication pipeline for Fact objects."""

    def __init__(
        self,
        duplicate_detector: Optional[Any],
        entity_merger: Optional[Any],
    ) -> None:
        self._detector = duplicate_detector
        self._merger = entity_merger

    @property
    def available(self) -> bool:
        return self._detector is not None and self._merger is not None

    def deduplicate_facts(self, facts: list[Fact]) -> list[Fact]:
        """Merge facts referring to the same entity.

        Returns a new list where duplicate facts are merged into one,
        combining their source_ids and evidence_ids.
        """
        if not self.available or len(facts) <= 1:
            return list(facts)

        # Group facts by type+value for exact matches, and by type+normalized name
        groups: dict[tuple[str, str], list[Fact]] = {}
        for fact in facts:
            if fact.type in _EXACT_MATCH_TYPES:
                key = (fact.type, str(fact.value).strip().upper())
            elif fact.type in _NAME_MATCH_TYPES:
                key = (fact.type, str(fact.value).strip().lower())
            else:
                # Non-deduplicatable types: each fact is its own group
                key = (fact.type, f"__unique__{fact.id}")
            groups.setdefault(key, []).append(fact)

        merged: list[Fact] = []
        for key, group in groups.items():
            if len(group) == 1:
                merged.append(group[0])
                continue

            # Merge the group: keep first fact, accumulate source_ids and evidence_ids
            primary = group[0]
            all_source_ids = set(primary.source_ids)
            all_evidence_ids = set(primary.evidence_ids)
            max_confidence = primary.confidence

            for other in group[1:]:
                all_source_ids.update(other.source_ids)
                all_evidence_ids.update(other.evidence_ids)
                max_confidence = max(max_confidence, other.confidence)

            # Create merged fact
            merged_fact = Fact(
                id=primary.id,
                case_id=primary.case_id,
                type=primary.type,
                value=primary.value,
                unit=primary.unit,
                status=primary.status,
                confidence=max_confidence,
                source_ids=sorted(all_source_ids),
                evidence_ids=sorted(all_evidence_ids),
                metadata=primary.metadata,
            )
            merged.append(merged_fact)

        logger.info(
            "Deduplication: %d facts -> %d facts (%d merged)",
            len(facts), len(merged), len(facts) - len(merged),
        )
        return merged