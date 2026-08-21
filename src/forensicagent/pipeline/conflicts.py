"""Conflict detection wrapper for ForensicAgent.

Uses Semantica's ConflictDetector to find contradictory facts
(e.g. different amounts for the same claim across sources).

When no backend is available, scan_conflicts returns an empty list.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from forensicagent.models import Fact, Finding, FindingStatus

logger = logging.getLogger(__name__)


class ConflictScanner:
    """Wraps Semantica's ConflictDetector for Fact objects."""

    def __init__(self, conflict_detector: Optional[Any]) -> None:
        self._detector = conflict_detector

    @property
    def available(self) -> bool:
        return self._detector is not None

    def scan_conflicts(
        self,
        facts: list[Fact],
        group_key: str = "AMOUNT",
    ) -> list[Finding]:
        """Detect conflicting facts and return them as Findings.

        Args:
            facts: All facts to check for conflicts.
            group_key: The fact type to group by for conflict detection.

        Returns:
            List of Finding objects for each detected conflict.
        """
        if not self.available or len(facts) <= 1:
            return []

        # Group facts by type
        type_groups: dict[str, list[Fact]] = {}
        for fact in facts:
            type_groups.setdefault(fact.type, []).append(fact)

        findings: list[Finding] = []

        for ftype, group in type_groups.items():
            if len(group) < 2:
                continue

            # Group by value to find contradictions
            value_groups: dict[str, list[Fact]] = {}
            for f in group:
                value_groups.setdefault(str(f.value).strip(), []).append(f)

            # If there are 2+ distinct values for the same type, it's a conflict
            if len(value_groups) < 2:
                continue

            # Build entity dicts for ConflictDetector
            entities = []
            for value, facts_with_value in value_groups.items():
                for f in facts_with_value:
                    entities.append({
                        "entity_id": f"CONFLICT-{ftype}",
                        "entity_type": ftype,
                        "value": str(f.value),
                        "source": ",".join(f.source_ids),
                        "fact_id": f.id,
                    })

            try:
                conflicts = self._detector.detect_conflicts(
                    entities,
                    method="value",
                    property_name="value",
                )
            except Exception as exc:
                logger.debug("ConflictDetector skipped for %s: %s", ftype, exc)
                conflicts = []

            # If ConflictDetector found something OR we detected manually
            if conflicts or len(value_groups) >= 2:
                values = list(value_groups.keys())
                all_fact_ids = [f.id for f in group]
                all_sources = []
                for v_facts in value_groups.values():
                    for f in v_facts:
                        all_sources.extend(f.source_ids)

                findings.append(Finding(
                    id=f"CONFLICT-{ftype}-{len(findings)}",
                    case_id=group[0].case_id,
                    statement=f"Widerspruechliche Werte fuer {ftype}: {', '.join(values[:3])}",
                    confidence=0.9,
                    status=FindingStatus.UNSUPPORTED,
                    evidence_path=list(set(all_sources)),
                    fact_ids=all_fact_ids,
                    metadata={
                        "conflict_type": "value_mismatch",
                        "values": values,
                        "detector_found": len(conflicts) > 0,
                    },
                ))

        logger.info("Conflict scan: %d findings from %d facts", len(findings), len(facts))
        return findings