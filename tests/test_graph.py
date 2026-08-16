"""Tests for the evidentiary knowledge graph and LMDB persistence."""
import tempfile

import networkx as nx
import pytest

from forensicagent.models import (
    Evidence, Fact, FactStatus, Finding, Requirement, RequirementStatus,
    Source, SourceStatus,
)
from forensicagent.pipeline.graph import CaseGraph


@pytest.fixture
def case_graph():
    with tempfile.TemporaryDirectory() as tmpdir:
        graph = CaseGraph("TEST-CASE", lmdb_path=tmpdir, restore=False)
        yield graph
        graph.close()


def _make_source(path="test.txt", text="Max Mustermann lives in Berlin."):
    return Source(id="S-1", path=path, mime="text/plain", raw_text=text,
                  status=SourceStatus.USABLE, quality_score=1.0)


def _make_fact(type="PERSON", value="Max Mustermann", status=FactStatus.CONFIRMED, source_ids=None):
    return Fact(
        id=f"F-{type}",
        case_id="TEST-CASE",
        type=type,
        value=value,
        status=status,
        confidence=0.9,
        source_ids=source_ids or ["S-1"],
    )


def test_add_and_retrieve_source(case_graph):
    src = _make_source()
    case_graph.add_source(src)
    assert case_graph.get_source("S-1").path == "test.txt"


def test_add_and_retrieve_fact(case_graph):
    src = _make_source()
    fact = _make_fact(source_ids=["S-1"])
    case_graph.add_source(src)
    case_graph.add_fact(fact)
    retrieved = case_graph.get_fact("F-PERSON")
    assert retrieved is not None
    assert retrieved.value == "Max Mustermann"


def test_evidence_linking_in_graph(case_graph):
    src = _make_source()
    fact = _make_fact()
    ev = Evidence(
        id="E-1", source_id="S-1", fact_id="F-PERSON",
        snippet="Max Mustermann lives in Berlin.",
    )
    case_graph.add_source(src)
    case_graph.add_fact(fact)
    case_graph.add_evidence(ev)
    evs = case_graph.evidence_for_fact("F-PERSON")
    assert len(evs) == 1
    assert evs[0].snippet == "Max Mustermann lives in Berlin."


def test_usable_facts_filter(case_graph):
    case_graph.add_source(_make_source())
    confirmed = _make_fact(type="A", status=FactStatus.CONFIRMED)
    rejected = _make_fact(type="B", status=FactStatus.REJECTED, source_ids=["S-1"])
    review = _make_fact(type="C", status=FactStatus.REVIEW, source_ids=["S-1"])
    case_graph.add_fact(confirmed)
    case_graph.add_fact(rejected)
    case_graph.add_fact(review)
    usable = case_graph.usable_facts()
    types = {f.type for f in usable}
    assert types == {"A"}  # only CONFIRMED/APPROVED


def test_requirement_evaluation(case_graph):
    req = Requirement(
        id="REQ-1", case_id="TEST-CASE", domain="general",
        description="Need a person", required_fact_types=["PERSON"],
    )
    case_graph.add_requirement(req)
    updated = case_graph.update_requirement_status(req)
    assert updated.status == RequirementStatus.UNSATISFIED

    fact = _make_fact(type="PERSON")
    case_graph.add_fact(fact)
    updated = case_graph.update_requirement_status(req)
    assert updated.status == RequirementStatus.SATISFIED


def test_lmdb_persistence(case_graph):
    case_graph.add_source(_make_source())
    fact = _make_fact()
    case_graph.add_fact(fact)
    case_graph.checkpoint()
    # Destroy and restore.
    case_graph.destroy()
    import tempfile as tf
    with tempfile.TemporaryDirectory() as tmpdir:
        new_graph = CaseGraph("TEST-CASE", lmdb_path=tmpdir, restore=False)
        # Fresh, no data.
        assert len(new_graph.all_facts()) == 0


def test_fact_table_export(case_graph):
    case_graph.add_source(_make_source())
    case_graph.add_fact(_make_fact())
    table = case_graph.fact_table()
    assert len(table) == 1
    assert table[0]["type"] == "PERSON"
    assert table[0]["status"] == "confirmed"
