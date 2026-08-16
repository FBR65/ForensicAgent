from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Evidence:
    id: str
    source_id: str
    fact_id: str
    snippet: str
    page: int | None = None
    start_char: int | None = None
    end_char: int | None = None
    confidence: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def __hash__(self) -> int:
        return hash(self.id)
