from __future__ import annotations

import logging
import time
import uuid
from typing import Any, Protocol, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class AgentResult(Protocol):
    status: str
    data: dict[str, Any]


class BaseAgent:
    name: str = "base"

    def __init__(self, case_id: str) -> None:
        self.case_id = case_id
        self.logger = logging.getLogger(f"forensicagent.agents.{self.name}")

    def new_id(self) -> str:
        return f"{self.case_id[:8]}-{uuid.uuid4().hex[:8]}"

    def run(self, *args: Any, **kwargs: Any) -> AgentResult:
        raise NotImplementedError


def time_block(label: str):
    def decorator(func):
        def wrapper(*args, **kwargs):
            start = time.perf_counter()
            result = func(*args, **kwargs)
            elapsed = time.perf_counter() - start
            logger.info("[%s] %s completed in %.2fs", label, func.__name__, elapsed)
            return result
        return wrapper
    return decorator
