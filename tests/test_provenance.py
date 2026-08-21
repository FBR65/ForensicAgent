"""Tests for Provenance integration (S-PROV)."""

import pytest
from forensicagent.pipeline.semantica_backend import is_available, SemanticaBackend
from forensicagent.pipeline.provenance import ProvenanceTracker
from forensicagent.models import Source, SourceStatus, Fact, FactStatus, Evidence


@pytest.fixture
def source():
    return Source(id="SRC-PROV-1", path="/tmp/evidence.txt", mime="text/plain",
                  status=SourceStatus.USABLE, raw_text="Kläger: Thomas Becker")


@pytest.fixture
def fact():
    return Fact(id="FACT-PROV-1", case_id="PROV-CASE", type="PERSON",
                value="Thomas Becker", status=FactStatus.CONFIRMED,
                confidence=0.9, source_ids=["SRC-PROV-1"])


@pytest.fixture
def evidence():
    return Evidence(id="EV-PROV-1", source_id="SRC-PROV-1", fact_id="FACT-PROV-1",
                    snippet="Kläger: Thomas Becker", start_char=0, end_char=20)


@pytest.mark.skipif(not is_available(), reason="semantica not installed")
class TestProvenanceTracker:

    def test_track_fact_creates_provenance(self, source, fact, evidence):
        """Tracking a fact creates a PROV-O provenance entry."""
        backend = SemanticaBackend("PROV-TEST-1")
        tracker = ProvenanceTracker(backend.provenance)
        tracker.track_fact(fact, source, evidence)
        # Provenance entry should exist for the fact
        prov = backend.provenance.get_provenance(fact.id)
        assert prov is not None
        backend.destroy()

    def test_track_source_creates_provenance(self, source):
        """Tracking a source creates a provenance entry."""
        backend = SemanticaBackend("PROV-TEST-2")
        tracker = ProvenanceTracker(backend.provenance)
        tracker.track_source(source)
        prov = backend.provenance.get_provenance(source.id)
        assert prov is not None
        backend.destroy()

    def test_get_lineage(self, source, fact, evidence):
        """get_lineage returns the provenance chain for a fact."""
        backend = SemanticaBackend("PROV-TEST-3")
        tracker = ProvenanceTracker(backend.provenance)
        tracker.track_source(source)
        tracker.track_fact(fact, source, evidence)
        lineage = tracker.get_lineage(fact.id)
        assert lineage is not None
        backend.destroy()

    def test_tracker_without_backend(self):
        """ProvenanceTracker with None backend is a no-op."""
        tracker = ProvenanceTracker(None)
        # Should not raise
        tracker.track_source(Source(id="X", path="/x", mime="text/plain"))
        tracker.track_fact(Fact(id="F", case_id="C", type="PERSON", value="X"), None, None)
        assert tracker.get_lineage("X") is None