"""Tests for Conflict Detection (S-CONFLICT)."""

import pytest
from forensicagent.pipeline.semantica_backend import is_available, SemanticaBackend
from forensicagent.pipeline.conflicts import ConflictScanner
from forensicagent.models import Fact, FactStatus, Finding, FindingStatus


def _amt(fid, val, src="SRC-A"):
    return Fact(id=fid, case_id="C", type="AMOUNT", value=val,
                status=FactStatus.CONFIRMED, confidence=0.9, source_ids=[src])


@pytest.mark.skipif(not is_available(), reason="semantica not installed")
class TestConflictDetection:

    def test_conflicting_amounts_detected(self):
        """Two AMOUNT facts with same entity group but different values -> conflict."""
        backend = SemanticaBackend("CONF-TEST-1")
        scanner = ConflictScanner(backend.conflict_detector)
        facts = [
            _amt("F1", "EUR 50.000,00", "klage.txt"),
            _amt("F2", "EUR 60.000,00", "gutachten.pdf"),
        ]
        findings = scanner.scan_conflicts(facts, group_key="AMOUNT")
        assert len(findings) >= 1
        assert findings[0].metadata.get("conflict_type") == "value_mismatch"
        backend.destroy()

    def test_no_conflict_same_values(self):
        """Same value from different sources is not a conflict."""
        backend = SemanticaBackend("CONF-TEST-2")
        scanner = ConflictScanner(backend.conflict_detector)
        facts = [
            _amt("F1", "EUR 50.000,00", "klage.txt"),
            _amt("F2", "EUR 50.000,00", "gutachten.pdf"),
        ]
        findings = scanner.scan_conflicts(facts, group_key="AMOUNT")
        assert len(findings) == 0
        backend.destroy()

    def test_no_backend_is_noop(self):
        """Without backend, scan_conflicts returns empty list."""
        scanner = ConflictScanner(None)
        facts = [_amt("F1", "EUR 50"), _amt("F2", "EUR 60")]
        findings = scanner.scan_conflicts(facts)
        assert findings == []