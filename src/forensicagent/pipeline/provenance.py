"""Provenance tracking wrapper for ForensicAgent.

Wraps Semantica's ProvenanceManager so that every fact and source gets
a W3C PROV-O provenance entry tracking its origin (source document,
extraction activity, agent).

When no backend is available, all methods are no-ops.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from forensicagent.models import Evidence, Fact, Source

logger = logging.getLogger(__name__)


class ProvenanceTracker:
    """Thin wrapper around semantica.provenance.ProvenanceManager."""

    def __init__(self, provenance_manager: Optional[Any]) -> None:
        self._prov = provenance_manager

    @property
    def available(self) -> bool:
        return self._prov is not None

    def track_source(self, source: Source) -> None:
        """Record provenance for a source document."""
        if self._prov is None:
            return
        try:
            self._prov.track_entity(
                entity_id=source.id,
                source=source.path,
                metadata={
                    "mime": source.mime,
                    "ocr_used": source.ocr_used,
                    "quality_score": source.quality_score,
                },
            )
        except Exception as exc:
            logger.debug("Provenance track_source skipped: %s", exc)

    def track_fact(
        self,
        fact: Fact,
        source: Optional[Source],
        evidence: Optional[Evidence],
    ) -> None:
        """Record provenance for a fact, linking it to its source and evidence."""
        if self._prov is None:
            return
        try:
            source_ref = source.path if source else "unknown"
            metadata: dict[str, Any] = {
                "fact_type": fact.type,
                "fact_value": str(fact.value),
                "confidence": fact.confidence,
                "case_id": fact.case_id,
            }
            if evidence:
                metadata["evidence_id"] = evidence.id
                metadata["snippet"] = evidence.snippet[:200]
                metadata["start_char"] = evidence.start_char
                metadata["end_char"] = evidence.end_char
            self._prov.track_entity(
                entity_id=fact.id,
                source=source_ref,
                metadata=metadata,
            )
        except Exception as exc:
            logger.debug("Provenance track_fact skipped: %s", exc)

    def get_lineage(self, entity_id: str) -> Optional[Any]:
        """Return the provenance lineage for an entity."""
        if self._prov is None:
            return None
        try:
            return self._prov.get_lineage(entity_id)
        except Exception as exc:
            logger.debug("Provenance get_lineage skipped: %s", exc)
            return None

    def get_all_sources(self) -> list[Any]:
        """Return all tracked sources."""
        if self._prov is None:
            return []
        try:
            return self._prov.get_all_sources()
        except Exception:
            return []