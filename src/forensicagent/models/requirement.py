from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class RequirementStatus(str, Enum):
    SATISFIED = "satisfied"
    PARTIAL = "partial"
    UNSATISFIED = "unsatisfied"


@dataclass
class Requirement:
    id: str
    case_id: str
    domain: str
    description: str
    required_fact_types: list[str]
    status: RequirementStatus = RequirementStatus.UNSATISFIED
    missing_fact_types: list[str] = field(default_factory=list)

    def __hash__(self) -> int:
        return hash(self.id)
