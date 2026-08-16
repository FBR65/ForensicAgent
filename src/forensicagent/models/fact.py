from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class FactStatus(str, Enum):
    CONFIRMED = "confirmed"
    APPROVED = "approved"
    CANDIDATE = "candidate"
    INCOMPLETE = "incomplete"
    REJECTED = "rejected"
    REVIEW = "requires_review"


@dataclass
class Fact:
    id: str
    case_id: str
    type: str
    value: Any
    unit: str = ""
    status: FactStatus = FactStatus.CANDIDATE
    confidence: float = 0.0
    source_ids: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def is_usable(self) -> bool:
        return self.status in (FactStatus.CONFIRMED, FactStatus.APPROVED)

    def __hash__(self) -> int:
        return hash(self.id)


@dataclass
class FactTableEntry:
    id: str
    type: str
    value: str
    status: FactStatus
    confidence: float
    source_id: Optional[str] = None
    evidence_id: Optional[str] = None
    snippet: str = ""
