from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class SourceStatus(str, Enum):
    USABLE = "usable"
    REVIEW = "requires_review"
    BLOCKING = "blocking"


@dataclass
class DocumentClass:
    category: str = "unknown"
    function: str = "unknown"
    weight: int = 1
    confidence: float = 0.0


@dataclass
class Source:
    id: str
    path: str
    mime: str
    status: SourceStatus = SourceStatus.USABLE
    quality_score: float = 1.0
    raw_text: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    keywords: list[str] = field(default_factory=list)
    classification: Optional[DocumentClass] = None
    ocr_used: bool = False

    def __hash__(self) -> int:
        return hash(self.id)
