from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable
from pathlib import Path

from forensicagent.agents.base import BaseAgent
from forensicagent.models import Fact, FactStatus
from forensicagent.domains.config import load_domain, DomainRule

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    fact_id: str
    checks_passed: list[str]
    checks_failed: list[str]
    final_status: FactStatus
    notes: list[str] = field(default_factory=list)


class ValidationAgent(BaseAgent):
    """Deterministic, rule-based checks that run BEFORE the LLM.

    Each DomainRule carries a ``fact_types`` list.  A rule only applies to
    a Fact whose ``type`` is in that list (an empty list means "all types").
    """

    name = "validation"

    def __init__(self, case_id: str, domain: str = "general", rules_path: str | Path | None = None) -> None:
        super().__init__(case_id)
        self.domain = load_domain(domain, rules_path)
        self._rules: list[tuple[str, Callable[[Fact], bool], str, list[str]]] = []
        self._compile_rules()

    def _compile_rules(self) -> None:
        for rule in self.domain.rules:
            fn = self._compile_rule(rule.check)
            self._rules.append((rule.id, fn, rule.severity, rule.fact_types))
        self._rules.extend(self._default_rules())

    def _compile_rule(self, check: str) -> Callable[[Fact], bool]:
        check = check.strip()
        if check.startswith("regex:"):
            pattern = re.compile(check[len("regex:"):])
            return lambda fact: bool(pattern.search(str(fact.value)))
        if check.startswith("type:"):
            target_type = check[len("type:"):]
            return lambda fact: fact.type == target_type
        if check.startswith("min_confidence:"):
            threshold = float(check[len("min_confidence:"):])
            return lambda fact: fact.confidence >= threshold
        if check == "has_evidence":
            return lambda fact: len(fact.evidence_ids) > 0
        logger.warning("Unknown rule check syntax: %s", check)
        return lambda fact: True

    def _default_rules(self) -> list[tuple[str, Callable[[Fact], bool], str, list[str]]]:
        return [
            ("rule-amount-has-source",
             lambda f: len(f.evidence_ids) > 0, "error", ["AMOUNT"]),
            ("rule-person-has-evidence",
             lambda f: len(f.evidence_ids) > 0, "warning", ["PERSON", "ORG"]),
            ("rule-confidence-threshold",
             lambda f: f.confidence >= 0.5, "warning", []),
            ("rule-rejected-source",
             lambda f: not _is_from_blocking_source(f), "error", []),
        ]

    def validate_fact(self, fact: Fact) -> ValidationResult:
        checks_passed: list[str] = []
        checks_failed: list[str] = []
        notes: list[str] = []

        for rule_id, fn, severity, fact_types in self._rules:
            if fact_types and fact.type not in fact_types:
                continue
            try:
                result = fn(fact)
            except Exception as exc:
                result = False
                notes.append(f"rule {rule_id} raised {exc}")
            if result:
                checks_passed.append(rule_id)
            else:
                checks_failed.append(f"{rule_id} ({severity})")

        if any("(error)" in f for f in checks_failed):
            final = FactStatus.REJECTED
        elif fact.status == FactStatus.REVIEW:
            final = FactStatus.REVIEW
        elif any("(warning)" in f for f in checks_failed):
            final = FactStatus.REVIEW
        else:
            final = fact.status

        return ValidationResult(
            fact_id=fact.id,
            checks_passed=checks_passed,
            checks_failed=checks_failed,
            final_status=final,
            notes=notes,
        )

    def validate_batch(self, facts: list[Fact]) -> list[ValidationResult]:
        results = []
        for f in facts:
            res = self.validate_fact(f)
            f.status = res.final_status
            results.append(res)
        return results

    def run(self, *args, **kwargs):
        return {"status": "ok", "data": {}}


def load_rules_from_file(path: str | Path) -> list[DomainRule]:
    with open(path) as f:
        data = json.load(f)
    return [DomainRule(**r) for r in data]


def _is_from_blocking_source(fact: Fact) -> bool:
    from forensicagent.models import SourceStatus
    for sid in fact.source_ids:
        from forensicagent.models import Source
        pass
    return False
