"""Tests for Semantica assessment integration (S-ASSESS, S-DECISION).

Verifies that AgnoDecisionKit (ContextGraph.record_decision / trace_decision_chain /
find_precedents / get_causal_chain) registers decisions with causal chains.
"""

import pytest

from forensicagent.pipeline.semantica_backend import is_available, SemanticaBackend
from forensicagent.pipeline.semantica_assessment import SemanticaDecisionKit
from forensicagent.models import Fact, FactStatus


@pytest.fixture
def backend():
    b = SemanticaBackend("TEST-ASSESS-1")
    yield b
    b.destroy()


@pytest.fixture
def populated_backend(backend):
    """Populate ContextGraph with facts for assessment."""
    cg = backend.context_graph
    cg.add_node("fact-1", "fact", content="Thomas Becker", value="Thomas Becker", type="PERSON")
    cg.add_node("fact-2", "fact", content="50000", value="50000", type="AMOUNT")
    cg.add_edge("fact-1", "fact-2", edge_type="owes")
    return backend


@pytest.mark.skipif(not is_available(), reason="semantica not installed")
class TestSemanticaDecisionKit:
    """S-ASSESS, S-DECISION: AgnoDecisionKit decision recording and tracing."""

    def test_decision_kit_initializes(self, backend):
        """SemanticaDecisionKit can be created from a SemanticaBackend."""
        kit = SemanticaDecisionKit(backend)
        assert kit is not None
        assert kit.is_available()

    def test_record_decision_returns_id(self, populated_backend):
        """record_decision() returns a non-empty decision ID."""
        kit = SemanticaDecisionKit(populated_backend)
        dec_id = kit.record_decision(
            category="assessment",
            scenario="liability assessment",
            reasoning="Person owes amount confirmed by evidence",
            outcome="liable",
            confidence=0.9,
            entities=["fact-1", "fact-2"],
            decision_maker="AssessmentAgent",
        )
        assert dec_id is not None
        assert isinstance(dec_id, str)
        assert len(dec_id) > 0

    def test_record_decision_with_causal_chain(self, populated_backend):
        """record_decision + add_causal_relationship produces a traceable chain."""
        kit = SemanticaDecisionKit(populated_backend)

        # First decision: evidence review
        dec1 = kit.record_decision(
            category="evidence_review",
            scenario="fact extraction complete",
            reasoning="PERSON and AMOUNT extracted",
            outcome="confirmed",
            confidence=0.85,
            entities=["fact-1", "fact-2"],
            decision_maker="FactExtractionAgent",
        )

        # Second decision: assessment (caused by first)
        dec2 = kit.record_decision(
            category="assessment",
            scenario="liability assessment",
            reasoning="Person confirmed, amount confirmed",
            outcome="liable",
            confidence=0.9,
            entities=["fact-1", "fact-2"],
            decision_maker="AssessmentAgent",
        )

        # Link them causally
        kit.add_causal_link(dec1, dec2, "CAUSED")

        # Trace the chain
        chain = kit.trace_decision_chain(dec2)
        assert isinstance(chain, list)
        assert len(chain) > 0

    def test_find_precedents(self, populated_backend):
        """find_precedents() returns prior similar decisions."""
        kit = SemanticaDecisionKit(populated_backend)

        # Record a precedent decision
        dec1 = kit.record_decision(
            category="assessment",
            scenario="liability assessment",
            reasoning="Prior case with similar facts",
            outcome="liable",
            confidence=0.8,
            entities=["fact-1", "fact-2"],
            decision_maker="AssessmentAgent",
        )

        # Record a new decision
        dec2 = kit.record_decision(
            category="assessment",
            scenario="liability assessment",
            reasoning="Current case",
            outcome="liable",
            confidence=0.9,
            entities=["fact-1", "fact-2"],
            decision_maker="AssessmentAgent",
        )

        # Link as precedent
        kit.add_causal_link(dec1, dec2, "PRECEDENT_FOR")

        precedents = kit.find_precedents(dec2)
        assert isinstance(precedents, list)

    def test_get_causal_chain_upstream(self, populated_backend):
        """get_causal_chain() returns upstream decisions."""
        kit = SemanticaDecisionKit(populated_backend)

        dec1 = kit.record_decision(
            category="evidence_review",
            scenario="fact extraction",
            reasoning="Facts extracted",
            outcome="confirmed",
            confidence=0.85,
            entities=["fact-1"],
            decision_maker="FactExtractionAgent",
        )
        dec2 = kit.record_decision(
            category="assessment",
            scenario="assessment",
            reasoning="Based on confirmed facts",
            outcome="liable",
            confidence=0.9,
            entities=["fact-1"],
            decision_maker="AssessmentAgent",
        )
        kit.add_causal_link(dec1, dec2, "CAUSED")

        chain = kit.get_causal_chain(dec2, direction="upstream")
        assert isinstance(chain, list)
        assert len(chain) >= 1

    def test_fallback_when_no_backend(self):
        """SemanticaDecisionKit with None backend is not available."""
        kit = SemanticaDecisionKit(None)
        assert not kit.is_available()
        result = kit.record_decision(
            category="test", scenario="test", reasoning="test",
            outcome="test", confidence=0.5, entities=[],
        )
        assert result is None