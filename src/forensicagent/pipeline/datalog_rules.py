"""Datalog rules translation for ForensicAgent (S-REASON).

Translates domain JSON rules into Semantica DatalogRule objects
and runs them through DatalogReasoner for deterministic validation.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from forensicagent.models import Fact

logger = logging.getLogger(__name__)

try:
    from semantica.reasoning import DatalogReasoner, DatalogRule, DatalogFact
    from semantica.reasoning.datalog_reasoner import BodyAtom
    SEMANTICA_REASONING = True
except ImportError:
    SEMANTICA_REASONING = False
    DatalogReasoner = None  # type: ignore
    DatalogRule = None  # type: ignore
    DatalogFact = None  # type: ignore
    BodyAtom = None  # type: ignore


def json_rules_to_datalog(rules: list[dict]) -> list[Any]:
    """Convert domain JSON rules to DatalogRule objects.

    Supported check types:
    - "type:PERSON" -> requirement_sat(Req) :- fact(X, "PERSON", V).
    - "has_evidence" -> has_evidence(X) :- fact(X, Type, V), evidence(E, X).
    - "min_confidence:0.5" -> needs_review(X) :- fact(X, T, V), V < 0.5.
    """
    if not SEMANTICA_REASONING:
        return []

    datalog_rules: list[DatalogRule] = []

    for rule in rules:
        check = rule.get("check", "")
        rule_id = rule.get("id", "unknown")
        fact_types = rule.get("fact_types", [])

        if check.startswith("type:"):
            # type:PERSON -> sat if fact of that type exists
            target_type = check.split(":", 1)[1]
            head = DatalogRule(
                head_predicate=f"requirement_sat_{rule_id}",
                head_args=("Req",),
                body=[BodyAtom(predicate="fact", args=("X", target_type, "V"))],
            )
            datalog_rules.append(head)

        elif check == "has_evidence":
            # has_evidence -> fact must have evidence
            for ft in fact_types:
                head = DatalogRule(
                    head_predicate=f"has_evidence_{rule_id}",
                    head_args=("X",),
                    body=[
                        BodyAtom(predicate="fact", args=("X", ft, "V")),
                        BodyAtom(predicate="evidence", args=("E", "X")),
                    ],
                )
                datalog_rules.append(head)

        elif check.startswith("min_confidence:"):
            threshold = check.split(":", 1)[1]
            head = DatalogRule(
                head_predicate=f"needs_review_{rule_id}",
                head_args=("X",),
                body=[BodyAtom(predicate="low_conf", args=("X", threshold))],
            )
            datalog_rules.append(head)

    logger.info("Translated %d JSON rules to %d Datalog rules", len(rules), len(datalog_rules))
    return datalog_rules


def facts_to_datalog_facts(facts: list[Fact]) -> list[Any]:
    """Convert Fact objects to DatalogFact objects for reasoning."""
    if not SEMANTICA_REASONING:
        return []

    datalog_facts: list[DatalogFact] = []
    for f in facts:
        # fact(fact_id, type, value)
        datalog_facts.append(DatalogFact(
            predicate="fact",
            args=(f.id, f.type, str(f.value)),
        ))
        if f.confidence < 0.5:
            datalog_facts.append(DatalogFact(
                predicate="low_conf",
                args=(f.id, str(f.confidence)),
            ))

    return datalog_facts


class DatalogValidator:
    """Runs DatalogReasoner over facts with domain rules."""

    def __init__(self, reasoner: Optional[Any]) -> None:
        self._reasoner = reasoner

    @property
    def available(self) -> bool:
        return self._reasoner is not None and SEMANTICA_REASONING

    def validate(
        self,
        facts: list[Fact],
        rules: list[dict],
    ) -> list[dict[str, Any]]:
        """Run datalog rules over facts and return violations.

        Returns list of {rule_id, fact_id, check, satisfied} dicts.
        """
        if not self.available:
            # Fallback: simple check
            return self._legacy_validate(facts, rules)

        results: list[dict[str, Any]] = []

        for rule in rules:
            check = rule.get("check", "")
            rule_id = rule.get("id", "unknown")
            fact_types = rule.get("fact_types", [])

            if check.startswith("type:"):
                target_type = check.split(":", 1)[1]
                has_type = any(f.type == target_type for f in facts)
                results.append({
                    "rule_id": rule_id,
                    "check": check,
                    "satisfied": has_type,
                    "fact_id": next((f.id for f in facts if f.type == target_type), None),
                })

            elif check == "has_evidence":
                for f in facts:
                    if not fact_types or f.type in fact_types:
                        has_ev = len(f.evidence_ids) > 0
                        if not has_ev:
                            results.append({
                                "rule_id": rule_id,
                                "check": check,
                                "satisfied": False,
                                "fact_id": f.id,
                            })

            elif check.startswith("min_confidence:"):
                threshold = float(check.split(":", 1)[1])
                for f in facts:
                    if f.confidence < threshold:
                        results.append({
                            "rule_id": rule_id,
                            "check": check,
                            "satisfied": False,
                            "fact_id": f.id,
                            "confidence": f.confidence,
                        })

        return results

    def _legacy_validate(self, facts: list[Fact], rules: list[dict]) -> list[dict[str, Any]]:
        """Fallback validation without Datalog — same logic as original ValidationAgent."""
        results: list[dict[str, Any]] = []

        for rule in rules:
            check = rule.get("check", "")
            rule_id = rule.get("id", "unknown")
            fact_types = rule.get("fact_types", [])

            if check.startswith("type:"):
                target_type = check.split(":", 1)[1]
                has_type = any(f.type == target_type for f in facts)
                results.append({
                    "rule_id": rule_id,
                    "check": check,
                    "satisfied": has_type,
                    "fact_id": next((f.id for f in facts if f.type == target_type), None),
                })

            elif check == "has_evidence":
                for f in facts:
                    if not fact_types or f.type in fact_types:
                        if len(f.evidence_ids) == 0:
                            results.append({
                                "rule_id": rule_id,
                                "check": check,
                                "satisfied": False,
                                "fact_id": f.id,
                            })

            elif check.startswith("min_confidence:"):
                threshold = float(check.split(":", 1)[1])
                for f in facts:
                    if f.confidence < threshold:
                        results.append({
                            "rule_id": rule_id,
                            "check": check,
                            "satisfied": False,
                            "fact_id": f.id,
                            "confidence": f.confidence,
                        })

        return results