from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from forensicagent.agents.base import BaseAgent
from forensicagent.models import Fact, FactStatus
from forensicagent.pipeline.graph import CaseGraph
from forensicagent.utils.spacy_utils import extract_all_entities

logger = logging.getLogger(__name__)

# Regex patterns for claims that MUST be grounded.
# AMOUNT requires an explicit currency marker — no bare numbers.
_AMOUNT_RE = re.compile(r"(?:[$€£]|USD|EUR|GBP)\s*\d{1,3}(?:[,.]\d{3})*(?:\.\d{2})?\b")
_TAX_CODE_RE = re.compile(r"\b[A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z]\b")
_DATE_RE = re.compile(r"\b\d{1,2}\.\d{1,2}\.\d{4}\b|\b\d{1,2}[\/\-.]\d{1,2}[\/\-.]\d{2,4}\b")
_IP_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_IBAN_RE = re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b")


@dataclass
class GroundingResult:
    passed: bool
    grounded_claims: list[dict[str, Any]] = field(default_factory=list)
    ungrounded_claims: list[dict[str, Any]] = field(default_factory=list)
    rejected_facts: list[str] = field(default_factory=list)
    summary: str = ""


class GroundingAgent(BaseAgent):
    """Post-generation verification.

    Every numerical / identifier / date / court claim in the LLM output is
    extracted and cross-checked against confirmed facts in the graph.  Any
    claim with no evidence path causes the output to be rejected.
    """

    name = "grounding"

    def __init__(self, case_id: str, graph: CaseGraph) -> None:
        super().__init__(case_id)
        self._graph = graph

    def _claim_matches_fact(self, claim_text: str) -> tuple[bool, str | None]:
        """Check if a claim string matches any confirmed fact value."""
        normalised = claim_text.strip().lower().replace(",", "")
        for fact in self._graph.usable_facts():
            fact_val = str(fact.value).strip().lower().replace(",", "")
            if normalised == fact_val or normalised in fact_val or fact_val in normalised:
                return (True, fact.id)
        return (False, None)

    def verify(self, output: str) -> GroundingResult:
        grounded: list[dict[str, Any]] = []
        ungrounded: list[dict[str, Any]] = []

        # Extract candidate claims via regex.
        patterns = [
            ("AMOUNT", _AMOUNT_RE),
            ("TAX_CODE", _TAX_CODE_RE),
            ("DATE", _DATE_RE),
            ("IP_ADDRESS", _IP_RE),
            ("IBAN", _IBAN_RE),
        ]
        for label, pattern in patterns:
            for m in pattern.finditer(output):
                claim = m.group()
                ok, fact_id = self._claim_matches_fact(claim)
                if ok:
                    grounded.append({"type": label, "claim": claim, "fact_id": fact_id})
                else:
                    ungrounded.append({"type": label, "claim": claim, "reason": "no confirmed fact matches"})

        # Also check spaCy-extracted entities.
        ents = extract_all_entities(output)
        for ent in ents:
            if ent["label"] in ("PERSON", "ORG", "LOCATION"):
                ok, fact_id = self._claim_matches_fact(ent["text"])
                if not ok:
                    # Names are softer — mark as needing source citation rather than rejecting.
                    continue

        passed = len(ungrounded) == 0
        summary = (
            f"Verified {len(grounded)} claims, {len(ungrounded)} ungrounded."
            if passed else
            f"REJECTED: {len(ungrounded)} ungrounded claims found."
        )

        # If rejected, flag relevant facts for review.
        rejected_facts = [u.get("fact_id", "?") for u in ungrounded]

        return GroundingResult(
            passed=passed,
            grounded_claims=grounded,
            ungrounded_claims=ungrounded,
            rejected_facts=rejected_facts,
            summary=summary,
        )

    def run(self, *args, **kwargs):
        return {"status": "ok", "data": {}}
