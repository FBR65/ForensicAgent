from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class FindingStatus(str, Enum):
    SUPPORTED = "supported"
    PARTIAL = "partial"
    UNSUPPORTED = "unsupported"


@dataclass
class Finding:
    id: str
    case_id: str
    statement: str
    confidence: float = 0.0
    status: FindingStatus = FindingStatus.UNSUPPORTED
    evidence_path: list[str] = field(default_factory=list)
    fact_ids: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __hash__(self) -> int:
        return hash(self.id)
