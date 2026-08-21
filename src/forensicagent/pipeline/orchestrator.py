from __future__ import annotations

import logging
import os
import tempfile
from typing import Any

from forensicagent.agents import (
    AssessmentAgent,
    ClassificationAgent,
    ContextBuilderAgent,
    EvidenceLinkingAgent,
    FactExtractionAgent,
    GroundingAgent,
    IngestionAgent,
    KnowledgeBaseAgent,
    KnowledgeRetrievalAgent,
    QualityControlAgent,
    ReportingAgent,
    ReviewAgent,
    ValidationAgent,
    KeywordIndexAgent,
)
from forensicagent.domains.config import load_domain
from forensicagent.models import (
    Fact,
    Finding,
    Requirement,
    Source,
)
from forensicagent.pipeline.graph import CaseGraph
from forensicagent.pipeline.semantica_backend import is_available, SemanticaBackend
from forensicagent.pipeline.semantica_retrieval import SemanticaRetrieval
from forensicagent.pipeline.semantica_assessment import SemanticaDecisionKit
from forensicagent.pipeline.semantica_query import SemanticaKGQuery
from forensicagent.pipeline.provenance import ProvenanceTracker
from forensicagent.pipeline.dedup import EntityDeduplicator
from forensicagent.pipeline.conflicts import ConflictScanner
from forensicagent.pipeline.datalog_rules import DatalogValidator
from forensicagent.pipeline.prov_export import export_provenance
from forensicagent.utils.bm25 import BM25Index

logger = logging.getLogger(__name__)


class ForensicPipeline:
    """The master orchestrator.

    Usage::

        pipeline = ForensicPipeline(case_id="CASE-2026-001")
        pipeline.ingest(["evidence/doc1.pdf", "evidence/log.txt"])
        result = pipeline.query("What is the total liability?")
        report = pipeline.build_report()
        pipeline.close()
    """

    def __init__(
        self,
        case_id: str,
        domain: str = "general",
        kb_dirs: list[str] | None = None,
        session_dir: str | None = None,
        use_semantica: bool = True,
    ) -> None:
        self.case_id = case_id
        self.domain = load_domain(domain)
        self._session_dir = session_dir or tempfile.mkdtemp(prefix=f"forensic-session-{case_id[:8]}-")

        # --- Semantica backend (optional) ---
        self._semantica: SemanticaBackend | None = None
        if use_semantica and is_available():
            self._semantica = SemanticaBackend(case_id)
            logger.info("[%s] Using Semantica backend", case_id)
        else:
            logger.info("[%s] Using legacy backend (NetworkX + LMDB)", case_id)

        self._graph = CaseGraph(
            case_id,
            lmdb_path=self._session_dir,
            restore=True,
            backend=self._semantica,
        )

        # --- Wrappers ---
        self._provenance = ProvenanceTracker(
            self._semantica.provenance if self._semantica else None
        )
        self._dedup = EntityDeduplicator(
            self._semantica.duplicate_detector if self._semantica else None,
            self._semantica.entity_merger if self._semantica else None,
        )
        self._conflict_scanner = ConflictScanner(
            self._semantica.conflict_detector if self._semantica else None
        )
        self._datalog = DatalogValidator(
            self._semantica.datalog_reasoner if self._semantica else None
        )

        # --- S-RETRIEVE / S-ASSESS / S-QUERY wrappers ---
        self._semantica_retrieval: SemanticaRetrieval | None = None
        self._decision_kit: SemanticaDecisionKit | None = None
        self._kg_query: SemanticaKGQuery | None = None
        if self._semantica:
            self._semantica_retrieval = SemanticaRetrieval(self._semantica)
            self._decision_kit = SemanticaDecisionKit(self._semantica)
            self._kg_query = SemanticaKGQuery(self._semantica)

        # --- Agents (unchanged except Semantica injection) ---
        self._ingestor = IngestionAgent(case_id)
        self._qc = QualityControlAgent(case_id)
        self._classifier = ClassificationAgent(case_id)
        self._keyword_agent = KeywordIndexAgent(case_id)
        self._fact_extractor = FactExtractionAgent(case_id)
        self._evidence_linker = EvidenceLinkingAgent(case_id)
        self._validator = ValidationAgent(case_id, domain=domain)
        self._knowledge = KnowledgeRetrievalAgent(
            case_id, kb_dirs=kb_dirs,
            semantica_retrieval=self._semantica_retrieval,
        ) if kb_dirs else None
        self._kb_assistant = KnowledgeBaseAgent(case_id, kb_dirs=kb_dirs) if kb_dirs else None
        self._context_builder = ContextBuilderAgent(case_id, kg_query=self._kg_query)
        self._assessor = AssessmentAgent(case_id, self._graph, decision_kit=self._decision_kit)
        self._grounder = GroundingAgent(case_id, self._graph)
        self._reporter = ReportingAgent(case_id, self._graph)
        self._reviewer = ReviewAgent(case_id, self._graph)

        self._sources_by_id: dict[str, Source] = {}
        self._ingested = False

    # ---- phase methods ----

    def ingest(self, paths: list[str]) -> list[Source]:
        logger.info("[%s] Phase 1-2: Ingestion & Quality Control", self.case_id)
        sources = self._ingestor.ingest_files(paths)
        self._qc.assess_batch(sources)
        self._classifier.classify_batch(sources)
        for s in sources:
            self._graph.add_source(s)
            self._sources_by_id[s.id] = s
            # S-PROV: track source provenance
            self._provenance.track_source(s)
        self._ingested = True
        logger.info("Ingested %d sources (%d usable, %d review, %d blocking)",
                    len(sources),
                    sum(1 for s in sources if s.status.value == "usable"),
                    sum(1 for s in sources if s.status.value == "requires_review"),
                    sum(1 for s in sources if s.status.value == "blocking"))
        return sources

    def index_keywords(self) -> BM25Index | None:
        logger.info("[%s] Phase 3: BM25 Keyword Indexing", self.case_id)
        usable_sources = [s for s in self._sources_by_id.values() if s.raw_text]
        self._keyword_agent.index_sources(usable_sources)
        for s in usable_sources:
            self._keyword_agent.extract_keywords(s, top_k=15)
        return self._keyword_agent.bm25

    def extract_and_link(self) -> tuple[list[Fact], list]:
        logger.info("[%s] Phase 4-5: Fact Extraction & Evidence Linking", self.case_id)
        sources = [s for s in self._sources_by_id.values() if s.raw_text]
        facts = self._fact_extractor.extract_batch(sources, self.case_id)
        evidence_items = self._evidence_linker.link_batch(facts, self._sources_by_id)

        # Apply deterministic classification of fact status.
        for fact in facts:
            status = self._evidence_linker.classify_fact(fact, self._sources_by_id.get(fact.source_ids[0], Fact(id="", case_id="", type="", value="")))
            fact.status = status

        # Run validation rules (S-REASON: use Datalog if available, else legacy).
        domain_rules = []
        for r in (self.domain.rules if hasattr(self.domain, 'rules') else []):
            if hasattr(r, '__dict__'):
                domain_rules.append({
                    "id": r.id, "name": r.name, "description": r.description,
                    "fact_types": r.fact_types, "check": r.check, "severity": r.severity,
                })
            else:
                domain_rules.append(r)
        if self._semantica:
            violations = self._datalog.validate(facts, domain_rules)
            for v in violations:
                if not v["satisfied"]:
                    logger.warning("Datalog violation: %s on fact %s", v["rule_id"], v["fact_id"])
        else:
            self._validator.validate_batch(facts)

        # S-DEDUP: deduplicate facts across sources.
        facts = self._dedup.deduplicate_facts(facts)

        # S-PROV: track fact provenance.
        for fact in facts:
            src = self._sources_by_id.get(fact.source_ids[0]) if fact.source_ids else None
            ev = next((e for e in evidence_items if e.fact_id == fact.id), None)
            self._provenance.track_fact(fact, src, ev)

        # Add to graph.
        for fact in facts:
            self._graph.add_fact(fact)
        for ev in evidence_items:
            self._graph.add_evidence(ev)

        logger.info("Extracted %d facts, %d evidence items", len(facts), len(evidence_items))
        return facts, evidence_items

    def build_graph(self, requirements: list[Requirement] | None = None) -> CaseGraph:
        logger.info("[%s] Phase 6: Graph Build & Requirements", self.case_id)
        if requirements is None:
            requirements = [
                Requirement(
                    id=f"REQ-{self.case_id[:8]}-{i}",
                    case_id=self.case_id,
                    domain=self.domain.name,
                    description=req["description"],
                    required_fact_types=req["required_fact_types"],
                )
                for i, req in enumerate(self.domain.requirements)
            ]
        for req in requirements:
            self._graph.add_requirement(req)
            self._graph.update_requirement_status(req)

        # S-CONFLICT: scan for contradictory facts.
        if self._semantica:
            findings = self._conflict_scanner.scan_conflicts(self._graph.all_facts())
            for finding in findings:
                self._graph.add_finding(finding)
                logger.warning("Conflict detected: %s", finding.statement)

        self._graph.checkpoint()
        logger.info("Graph: %d facts, %d evidence, %d requirements, %d findings",
                    len(self._graph.all_facts()),
                    len(self._graph.all_evidence()),
                    len(self._graph.all_requirements()),
                    len(self._graph.all_findings()))
        return self._graph

    def query(self, question: str) -> dict[str, Any]:
        """Run a single query through the full evidence-constrained pipeline."""
        if not self._ingested:
            raise RuntimeError("Call ingest() before query()")

        logger.info("[%s] Phase 7-12: Query -> %s", self.case_id, question)
        context = self._context_builder.build_context(
            self._graph, question, knowledge_agent=self._knowledge
        )
        assessment = self._assessor.assess(question, context)
        grounding = self._grounder.verify(assessment["answer"])

        if not grounding.passed:
            logger.warning("Grounding failed: %s", grounding.summary)
            for claim in grounding.ungrounded_claims:
                logger.warning("  Ungrounded %s: %s", claim["type"], claim["claim"])

        return {
            "question": question,
            "answer": assessment["answer"],
            "mode": assessment["mode"],
            "grounding": {
                "passed": grounding.passed,
                "summary": grounding.summary,
                "grounded_claims": grounding.grounded_claims,
                "ungrounded_claims": grounding.ungrounded_claims,
            },
        }

    def build_report(self, title: str = "Forensic Case Report") -> dict[str, Any]:
        logger.info("[%s] Phase 13: Reporting", self.case_id)
        return self._reporter.build_report(title=title)

    def export_markdown_report(self) -> str:
        report = self.build_report()
        return self._reporter.export_markdown(report)

    # ---- S-EXPORT: PROV-O export ----

    def export_provenance(self, format: str = "turtle") -> str:
        """Export case provenance as W3C PROV-O (Turtle/JSON-LD/XML)."""
        if self._semantica is None:
            return ""
        return export_provenance(
            self._semantica.context_graph,
            self._semantica.rdf_exporter,
            format=format,
        )

    # ---- S-CONFLICT: get conflicts ----

    def get_conflicts(self) -> list[Finding]:
        """Return all conflict findings detected in the case."""
        return [f for f in self._graph.all_findings()
                if f.metadata.get("conflict_type") == "value_mismatch"]

    # ---- S-DECISION: trace decision chain ----

    def trace_decision(self, decision_id: str) -> dict[str, Any]:
        """Trace the causal chain for a recorded decision.

        Returns a dict with the chain steps and upstream causal decisions.
        Returns an empty dict when Semantica is not available.
        """
        if self._decision_kit is None or not self._decision_kit.is_available():
            return {}
        chain = self._decision_kit.trace_decision_chain(decision_id)
        causal = self._decision_kit.get_causal_chain(decision_id, direction="upstream")
        return {
            "decision_id": decision_id,
            "chain_steps": chain,
            "upstream_causal": [
                {"category": getattr(d, "category", "?"),
                 "outcome": getattr(d, "outcome", "?"),
                 "scenario": getattr(d, "scenario", "?")}
                for d in causal
            ],
        }

    # ---- review / corrections ----

    def correct_fact_status(self, fact_id: str, new_status: str) -> Fact | None:
        return self._reviewer.correct_fact_status(fact_id, new_status)

    def re_evaluate_requirements(self) -> list[dict[str, Any]]:
        return self._reviewer.re_evaluate_requirements()

    # ---- knowledge-base authoring ----

    def build_kb_document(self, description: str, domain: str | None = None) -> dict[str, Any]:
        if self._kb_assistant is None:
            raise RuntimeError("No kb_dirs configured -- pass kb_dirs to ForensicPipeline.")
        doc, path = self._kb_assistant.add_document_from_description(
            description, domain or self.domain.name
        )
        if self._knowledge is not None:
            self._knowledge.reindex()
        return {"document": doc, "path": str(path)}

    # ---- teardown ----

    def close(self) -> None:
        """Destroy the volatile session (LMDB store is wiped, backend destroyed)."""
        self._graph.destroy()
        logger.info("[%s] Session destroyed -- case data purged.", self.case_id)

    def __enter__(self) -> "ForensicPipeline":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    @property
    def graph(self) -> CaseGraph:
        return self._graph

    @property
    def keyword_agent(self) -> KeywordIndexAgent:
        return self._keyword_agent

    @property
    def semantica_backend(self) -> SemanticaBackend | None:
        return self._semantica

    @property
    def semantica_retrieval(self) -> SemanticaRetrieval | None:
        return self._semantica_retrieval

    @property
    def decision_kit(self) -> SemanticaDecisionKit | None:
        return self._decision_kit

    @property
    def kg_query(self) -> SemanticaKGQuery | None:
        return self._kg_query