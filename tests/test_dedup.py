"""Tests for Entity Deduplication (S-DEDUP)."""

import pytest
from forensicagent.pipeline.semantica_backend import is_available, SemanticaBackend
from forensicagent.pipeline.dedup import EntityDeduplicator
from forensicagent.models import Fact, FactStatus


def _make_fact(fid, value, source_ids=None):
    return Fact(id=fid, case_id="DEDUP-CASE", type="PERSON", value=value,
                status=FactStatus.CONFIRMED, confidence=0.9,
                source_ids=source_ids or ["SRC-1"])


@pytest.mark.skipif(not is_available(), reason="semantica not installed")
class TestEntityDedup:

    def test_same_person_two_sources_merges(self):
        """Two facts with same person name from different sources get merged."""
        backend = SemanticaBackend("DEDUP-TEST-1")
        dedup = EntityDeduplicator(backend.duplicate_detector, backend.entity_merger)
        facts = [
            _make_fact("F1", "Thomas Becker", ["SRC-A"]),
            _make_fact("F2", "Thomas Becker", ["SRC-B"]),
        ]
        merged = dedup.deduplicate_facts(facts)
        # Should merge into 1 fact with 2 source_ids
        assert len(merged) == 1
        assert set(merged[0].source_ids) == {"SRC-A", "SRC-B"}
        backend.destroy()

    def test_different_facts_not_merged(self):
        """Different person names are not merged."""
        backend = SemanticaBackend("DEDUP-TEST-2")
        dedup = EntityDeduplicator(backend.duplicate_detector, backend.entity_merger)
        facts = [
            _make_fact("F1", "Thomas Becker", ["SRC-A"]),
            _make_fact("F2", "Petra Hoffmann", ["SRC-B"]),
        ]
        merged = dedup.deduplicate_facts(facts)
        assert len(merged) == 2
        backend.destroy()

    def test_exact_iban_match_merges(self):
        """Same IBAN from different sources gets merged."""
        backend = SemanticaBackend("DEDUP-TEST-3")
        dedup = EntityDeduplicator(backend.duplicate_detector, backend.entity_merger)
        facts = [
            Fact(id="F1", case_id="C", type="IBAN", value="DE71500105179423614829",
                 status=FactStatus.CONFIRMED, confidence=0.9, source_ids=["SRC-A"]),
            Fact(id="F2", case_id="C", type="IBAN", value="DE71500105179423614829",
                 status=FactStatus.CONFIRMED, confidence=0.9, source_ids=["SRC-B"]),
        ]
        merged = dedup.deduplicate_facts(facts)
        assert len(merged) == 1
        assert set(merged[0].source_ids) == {"SRC-A", "SRC-B"}
        backend.destroy()

    def test_dedup_without_backend_is_noop(self):
        """Without backend, deduplicate_facts returns input unchanged."""
        dedup = EntityDeduplicator(None, None)
        facts = [
            _make_fact("F1", "Thomas Becker", ["SRC-A"]),
            _make_fact("F2", "Thomas Becker", ["SRC-B"]),
        ]
        merged = dedup.deduplicate_facts(facts)
        assert len(merged) == 2  # unchanged