from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Relationship:
    id: str
    subject_fact_id: str
    predicate: str
    object_fact_id: str
    evidence_id: Optional[str] = None
    confidence: float = 1.0

    def __hash__(self) -> int:
        return hash(self.id)
