"""Deterministic amount validation (PDF §6).

Amounts are the most delicate area of a forensic pipeline.  An LLM can
easily add amounts that should not be added, duplicate items, confuse
procedural expenses with liabilities, or treat a settled amount as a
current debt.  This module enforces the "ban on improper sums":

- A total is accepted only when its addends are known and documented.
- ``non_additive`` amounts must never be summed automatically.
- ``overlapping`` amounts may duplicate another value and must be flagged.
- ``unproven`` amounts (no source link) are not usable for drafting.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from forensicagent.models import Amount, AmountSourceType, Fact, FactStatus

logger = logging.getLogger(__name__)


@dataclass
class AmountValidationResult:
    amount: Amount
    valid: bool
    issues: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


class AmountValidator:
    """Deterministic, rule-based checks for monetary facts."""

    def validate(self, amount: Amount) -> AmountValidationResult:
        issues: list[str] = []
        notes: list[str] = []

        if amount.source_type == AmountSourceType.UNPROVEN:
            issues.append("unproven: no documentary source link")

        if amount.source_type == AmountSourceType.NON_ADDITIVE:
            notes.append("non_additive: must not be summed automatically")

        if amount.source_type == AmountSourceType.OVERLAPPING:
            notes.append("overlapping: may duplicate another value")

        if amount.source_type == AmountSourceType.DERIVED:
            if not amount.addend_ids:
                issues.append("derived amount without documented addends")
            else:
                notes.append(f"derived from {len(amount.addend_ids)} documented addends")
        elif amount.is_total and not amount.addend_ids:
            issues.append("total without documented addends")

        if amount.value < 0:
            issues.append("negative amount")

        valid = not issues
        return AmountValidationResult(
            amount=amount,
            valid=valid,
            issues=issues,
            notes=notes,
        )

    def validate_facts(self, facts: list[Fact]) -> list[AmountValidationResult]:
        """Validate all AMOUNT facts, attaching the Amount to the fact's
        metadata and downgrading unusable amounts to CANDIDATE/REJECTED."""
        results: list[AmountValidationResult] = []
        for fact in facts:
            if fact.type != "AMOUNT":
                continue
            amount = self._to_amount(fact)
            res = self.validate(amount)
            fact.metadata["amount"] = amount
            if not res.valid:
                if fact.is_usable():
                    fact.status = FactStatus.REVIEW
            results.append(res)
        return results

    @staticmethod
    def _to_amount(fact: Fact) -> Amount:
        """Build an Amount from a Fact, honouring any explicit flags in the
        fact's metadata (e.g. ``non_additive``, ``overlapping``)."""
        meta = fact.metadata or {}
        source_type = AmountSourceType(meta.get("amount_source_type", "direct"))
        # Copy metadata so the Amount does not reference the fact's own
        # metadata dict (which would create a cyclic reference once the
        # Amount is stored back into fact.metadata["amount"]).
        amount_meta = {k: v for k, v in meta.items() if k != "amount"}
        return Amount(
            value=AmountValidator._parse_number(fact.value),
            currency=meta.get("currency", "EUR"),
            source_type=source_type,
            addend_ids=list(meta.get("addend_ids", [])),
            fact_id=fact.id,
            source_ids=list(fact.source_ids),
            evidence_ids=list(fact.evidence_ids),
            metadata=amount_meta,
        )

    @staticmethod
    def _parse_number(value: Any) -> float:
        """Parse a monetary string that may carry a currency prefix/suffix
        and German (1.234,56) or English (1,234.56) separators."""
        if isinstance(value, (int, float)):
            return float(value)
        s = str(value).strip()
        # Strip currency tokens.
        for tok in ("EUR", "USD", "GBP", "€", "$", "£"):
            s = s.replace(tok, "")
        s = s.strip()
        if not s:
            return 0.0
        # German format: thousands '.', decimal ','.
        if "," in s and "." in s:
            if s.rfind(",") > s.rfind("."):
                s = s.replace(".", "").replace(",", ".")
            else:
                s = s.replace(",", "")
        elif "," in s:
            s = s.replace(",", ".")
        return float(s)
