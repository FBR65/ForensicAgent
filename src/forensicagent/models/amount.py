from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class AmountSourceType(str, Enum):
    """How an amount relates to its documentary source (PDF §6)."""
    DIRECT = "direct"          # has an individual documentary source
    DERIVED = "derived"        # computed from documented addends
    UNPROVEN = "unproven"      # link to source missing
    NON_ADDITIVE = "non_additive"  # must not be summed automatically
    OVERLAPPING = "overlapping"    # may duplicate another value


@dataclass
class Amount:
    """A monetary fact with provenance and addend tracking.

    A total is only accepted when its addends are known and documented.
    ``non_additive`` and ``overlapping`` flags prevent improper sums.
    """
    value: float
    currency: str = "EUR"
    source_type: AmountSourceType = AmountSourceType.DIRECT
    addend_ids: list[str] = field(default_factory=list)
    fact_id: str = ""
    source_ids: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_total(self) -> bool:
        return bool(self.addend_ids)

    def is_usable(self) -> bool:
        return self.source_type in (
            AmountSourceType.DIRECT,
            AmountSourceType.DERIVED,
        )

    def __hash__(self) -> int:
        return hash(self.fact_id)
