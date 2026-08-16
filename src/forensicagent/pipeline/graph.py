from __future__ import annotations

import logging
import os
import tempfile
from dataclasses import asdict
from enum import Enum
from typing import Any, Iterator, Optional

import networkx as nx
from networkx import DiGraph

from forensicagent.models import (
    Evidence,
    Fact,
    FactStatus,
    Finding,
    Requirement,
    RequirementStatus,
    Source,
    Relationship,
)
from forensicagent.pipeline.lmdb_store import LMDBStore

logger = logging.getLogger(__name__)


def _serialize_node(node_id: str, node_type: str, data: Any) -> dict[str, Any]:
    """Convert a model object into a JSON-serialisable dict."""
    if hasattr(data, "__dataclass_fields__"):
        raw = asdict(data)
    elif hasattr(data, "__dict__"):
        raw = data.__dict__.copy()
    elif isinstance(data, dict):
        raw = data.copy()
    else:
        raw = {"value": str(data)}
    for k, v in list(raw.items()):
        if isinstance(v, Enum):
            raw[k] = v.value
        elif isinstance(v, dict):
            for dk, dv in list(v.items()):
                if isinstance(dv, Enum):
                    raw[k][dk] = dv.value
    raw["_id"] = node_id
    raw["_type"] = node_type
    return raw


def _deserialize_node(raw: dict[str, Any]):
    """Recreate a model object from its serialised form."""
    node_type = raw.get("_type", "unknown")
    payload = {k: v for k, v in raw.items() if not k.startswith("_")}
    from forensicagent.models import (
        Evidence, Fact, Finding, Requirement, Source, Relationship,
        DocumentClass, FactStatus, SourceStatus, RequirementStatus, FindingStatus,
    )
    if node_type == "source":
        payload["status"] = SourceStatus(payload.get("status", "usable"))
        if "classification" in payload and isinstance(payload["classification"], dict):
            payload["classification"] = DocumentClass(**payload["classification"])
        return node_type, Source(**payload)
    if node_type == "fact":
        payload["status"] = FactStatus(payload.get("status", "candidate"))
        return node_type, Fact(**payload)
    if node_type == "evidence":
        return node_type, Evidence(**payload)
    if node_type == "relationship":
        return node_type, Relationship(**payload)
    if node_type == "requirement":
        payload["status"] = RequirementStatus(payload.get("status", "unsatisfied"))
        return node_type, Requirement(**payload)
    if node_type == "finding":
        payload["status"] = FindingStatus(payload.get("status", "unsupported"))
        return node_type, Finding(**payload)
    return node_type, raw


class CaseGraph:
    """Volatile evidentiary knowledge graph (per session).

    The primary working set is an in-memory NetworkX DiGraph for fast
    traversal.  Optionally, every mutation is mirrored to an LMDB
    environment so the session can be checkpointed or restored.  The LMDB
    directory is **destroyed** on ``close_session`` / ``destroy`` — client
    data never becomes permanent system memory.
    """

    def __init__(
        self,
        case_id: str,
        lmdb_path: Optional[str] = None,
        restore: bool = False,
    ) -> None:
        self.case_id = case_id
        self._graph: DiGraph = nx.DiGraph()
        self._lmdb: Optional[LMDBStore] = None
        self._lmdb_path: Optional[str] = lmdb_path or tempfile.mkdtemp(prefix=f"case-{case_id[:8]}-")
        if restore and os.path.exists(self._lmdb_path):
            self._lmdb = LMDBStore(self._lmdb_path)
            self._restore_from_lmdb()
        else:
            self._lmdb = LMDBStore(self._lmdb_path)
        self._graph.add_node(self.case_id, type="case", data={"id": case_id})

    # ---- persistence ----

    def _persist_node(self, node_id: str, node_type: str, data: dict) -> None:
        if self._lmdb:
            self._lmdb.put_node(node_id, {"_type": node_type, **data})

    def _persist_edge(self, src: str, dst: str, label: str | None, key: str) -> None:
        if self._lmdb:
            self._lmdb.put_edge(key, {"_src": src, "_dst": dst, "_label": label or ""})

    def _restore_from_lmdb(self) -> None:
        for node_id, raw in self._lmdb.iter_nodes():
            ntype, obj = _deserialize_node(raw)
            self._graph.add_node(node_id, type=ntype, data=obj)
        for edge_key, edata in self._lmdb.iter_edges():
            self._graph.add_edge(
                edata["_src"], edata["_dst"],
                label=edata["_label"], key=edge_key,
            )
        logger.info("Restored %d nodes from LMDB", self._lmdb.stats()["nodes"])

    def checkpoint(self) -> int:
        """Re-sync current in-memory graph to LMDB (full rebuild)."""
        if not self._lmdb:
            return 0
        for node_id, data in self._graph.nodes(data=True):
            ntype = data.get("type", "unknown")
            obj = data.get("data", {})
            raw = _serialize_node(node_id, ntype, obj)
            if ntype != "case":
                self._lmdb.put_node(node_id, raw)
        for u, v, edata in self._graph.edges(data=True):
            if edata.get("label"):
                key = f"{u}->{v}"
                self._lmdb.put_edge(key, {"_src": u, "_dst": v, "_label": edata["label"]})
        self._lmdb.put_meta("case", {"id": self.case_id, "nodes": len(self._graph)})
        return len(self._graph)

    def destroy(self) -> None:
        if self._lmdb:
            self._lmdb.destroy()

    def close(self) -> None:
        if self._lmdb:
            self._lmdb.close()

    # ---- node management ----

    def add_source(self, source: Source) -> None:
        self._graph.add_node(source.id, type="source", data=source)
        self._graph.add_edge(self.case_id, source.id, label="HAS_SOURCE")
        self._persist_node(source.id, "source", source.__dict__)
        self._persist_edge(self.case_id, source.id, "HAS_SOURCE", f"{self.case_id}->{source.id}")

    def add_fact(self, fact: Fact) -> None:
        self._graph.add_node(fact.id, type="fact", data=fact)
        self._graph.add_edge(self.case_id, fact.id, label="HAS_FACT")
        self._persist_node(fact.id, "fact", fact.__dict__)
        self._persist_edge(self.case_id, fact.id, "HAS_FACT", f"{self.case_id}->{fact.id}")
        for sid in fact.source_ids:
            if sid in self._graph:
                self._graph.add_edge(sid, fact.id, label="SUPPORTS")
                self._persist_edge(sid, fact.id, "SUPPORTS", f"{sid}->{fact.id}")

    def add_evidence(self, evidence: Evidence) -> None:
        self._graph.add_node(evidence.id, type="evidence", data=evidence)
        self._graph.add_edge(self.case_id, evidence.id, label="HAS_EVIDENCE")
        self._persist_node(evidence.id, "evidence", evidence.__dict__)
        self._persist_edge(self.case_id, evidence.id, "HAS_EVIDENCE", f"{self.case_id}->{evidence.id}")
        self._graph.add_edge(evidence.source_id, evidence.id, label="CONTAINS")
        self._persist_edge(evidence.source_id, evidence.id, "CONTAINS", f"{evidence.source_id}->{evidence.id}")
        if evidence.fact_id:
            self._graph.add_edge(evidence.fact_id, evidence.id, label="HAS_EVIDENCE")
            self._persist_edge(evidence.fact_id, evidence.id, "HAS_EVIDENCE", f"{evidence.fact_id}->{evidence.id}")

    def add_relationship(self, rel: Relationship) -> None:
        self._graph.add_node(rel.id, type="relationship", data=rel)
        self._graph.add_edge(rel.subject_fact_id, rel.object_fact_id, label=rel.predicate)
        self._graph.add_edge(rel.subject_fact_id, rel.object_fact_id, label=rel.predicate)
        self._persist_node(rel.id, "relationship", rel.__dict__)
        self._persist_edge(rel.subject_fact_id, rel.object_fact_id, rel.predicate, f"{rel.subject_fact_id}->{rel.object_fact_id}")

    def add_requirement(self, req: Requirement) -> None:
        self._graph.add_node(req.id, type="requirement", data=req)
        self._graph.add_edge(self.case_id, req.id, label="REQUIRES")
        self._persist_node(req.id, "requirement", req.__dict__)
        self._persist_edge(self.case_id, req.id, "REQUIRES", f"{self.case_id}->{req.id}")

    def add_finding(self, finding: Finding) -> None:
        self._graph.add_node(finding.id, type="finding", data=finding)
        self._graph.add_edge(self.case_id, finding.id, label="HAS_FINDING")
        self._persist_node(finding.id, "finding", finding.__dict__)
        for fid in finding.fact_ids:
            if fid in self._graph:
                self._graph.add_edge(fid, finding.id, label="SUPPORTS")

    # ---- queries ----

    def get_node(self, node_id: str) -> dict[str, Any] | None:
        return self._graph.nodes.get(node_id) if node_id in self._graph else None

    def _node(self, node_id: str) -> tuple[str, Any] | None:
        if node_id not in self._graph:
            return None
        data = self._graph.nodes[node_id]
        return (data.get("type", "?"), data.get("data"))

    def get_source(self, source_id: str) -> Source | None:
        n = self._node(source_id)
        return n[1] if n and n[0] == "source" else None

    def get_fact(self, fact_id: str) -> Fact | None:
        n = self._node(fact_id)
        return n[1] if n and n[0] == "fact" else None

    def get_evidence(self, evidence_id: str) -> Evidence | None:
        n = self._node(evidence_id)
        return n[1] if n and n[0] == "evidence" else None

    def facts_by_type(self, fact_type: str) -> list[Fact]:
        results = []
        for _, data in self._graph.nodes(data=True):
            if data.get("type") == "fact":
                fact: Fact = data["data"]
                if fact.type == fact_type:
                    results.append(fact)
        return results

    def facts_by_status(self, statuses: list[str]) -> list[Fact]:
        results = []
        status_set = {s.value for s in statuses}
        for _, data in self._graph.nodes(data=True):
            if data.get("type") == "fact":
                fact: Fact = data["data"]
                if fact.status.value in status_set:
                    results.append(fact)
        return results

    def usable_facts(self) -> list[Fact]:
        results = []
        for _, data in self._graph.nodes(data=True):
            if data.get("type") == "fact":
                fact: Fact = data["data"]
                if fact.is_usable():
                    results.append(fact)
        return results

    def evidence_for_fact(self, fact_id: str) -> list[Evidence]:
        results = []
        if fact_id in self._graph:
            for _, ev_id in self._graph.out_edges(fact_id):
                node = self.get_node(ev_id)
                if node and node.get("type") == "evidence":
                    results.append(node["data"])
        return results

    def sources_for_fact(self, fact_id: str) -> list[str]:
        evs = self.evidence_for_fact(fact_id)
        return list({ev.source_id for ev in evs})

    def get_source_evidence(self, source_id: str) -> list[Evidence]:
        results = []
        if source_id in self._graph:
            for _, ev_id in self._graph.out_edges(source_id):
                node = self.get_node(ev_id)
                if node and node.get("type") == "evidence":
                    results.append(node["data"])
        return results

    def all_sources(self) -> list[Source]:
        return [data["data"] for _, data in self._graph.nodes(data=True) if data.get("type") == "source"]

    def all_facts(self) -> list[Fact]:
        return [data["data"] for _, data in self._graph.nodes(data=True) if data.get("type") == "fact"]

    def all_evidence(self) -> list[Evidence]:
        return [data["data"] for _, data in self._graph.nodes(data=True) if data.get("type") == "evidence"]

    def all_requirements(self) -> list[Requirement]:
        return [data["data"] for _, data in self._graph.nodes(data=True) if data.get("type") == "requirement"]

    def all_findings(self) -> list[Finding]:
        return [data["data"] for _, data in self._graph.nodes(data=True) if data.get("type") == "finding"]

    def all_relationships(self) -> list[Relationship]:
        return [data["data"] for _, data in self._graph.nodes(data=True) if data.get("type") == "relationship"]

    # ---- validation & requirements ----

    def evaluate_requirement(self, req: Requirement) -> tuple[str, list[str]]:
        existing_types = {f.type for f in self.usable_facts()}
        missing = [t for t in req.required_fact_types if t not in existing_types]
        if not missing:
            return ("satisfied", [])
        if existing_types.intersection(req.required_fact_types):
            return ("partial", missing)
        return ("unsatisfied", missing)

    def update_requirement_status(self, req: Requirement) -> Requirement:
        status, missing = self.evaluate_requirement(req)
        from forensicagent.models import RequirementStatus as RS
        req.status = RS(status)
        req.missing_fact_types = missing
        node = self.get_node(req.id)
        if node:
            node["data"] = req
        return req

    # ---- export ----

    def fact_table(self) -> list[dict[str, Any]]:
        table = []
        for fact in self.all_facts():
            sources = self.sources_for_fact(fact.id)
            evs = self.evidence_for_fact(fact.id)
            snippet = evs[0].snippet[:200] if evs else ""
            table.append({
                "id": fact.id,
                "type": fact.type,
                "value": str(fact.value),
                "unit": fact.unit,
                "status": fact.status.value,
                "confidence": round(fact.confidence, 3),
                "sources": sources,
                "snippet": snippet,
            })
        return table

    def evidence_audit(self) -> list[dict[str, Any]]:
        audit = []
        for ev in self.all_evidence():
            fact = self.get_fact(ev.fact_id)
            src = self.get_source(ev.source_id)
            audit.append({
                "evidence_id": ev.id,
                "fact_id": ev.fact_id,
                "fact_type": fact.type if fact else "?",
                "source_id": ev.source_id,
                "source_path": src.path if src else "?",
                "page": ev.page,
                "snippet": ev.snippet[:300],
            })
        return audit

    def drafting_matrix(self, domain_requirements: list[Requirement]) -> list[dict[str, Any]]:
        matrix = []
        for req in domain_requirements:
            req = self.update_requirement_status(req)
            facts = self.facts_by_type("")
            covered_types = {f.type for f in self.usable_facts()}
            matrix.append({
                "requirement": req.description,
                "domain": req.domain,
                "required_facts": req.required_fact_types,
                "status": req.status.value,
                "covered": [t for t in req.required_fact_types if t in covered_types],
                "missing": req.missing_fact_types,
            })
        return matrix

    def export_session(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "sources": [s.__dict__ for s in self.all_sources()],
            "facts": [f.__dict__ for f in self.all_facts()],
            "evidence": [e.__dict__ for e in self.all_evidence()],
        }
