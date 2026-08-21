"""Semantica backend factory for ForensicAgent.

Initialises the shared Semantica infrastructure (ContextGraph, ProvenanceManager,
ConflictDetector, DuplicateDetector, EntityMerger, DatalogReasoner) and exposes
them through a single ``SemanticaBackend`` facade.

When ``semantica`` is not installed, ``SEMANTICA_AVAILABLE`` is ``False`` and
the caller falls back to the legacy NetworkX + LMDB path.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

try:
    from semantica.context import ContextGraph
    from semantica.provenance import ProvenanceManager
    from semantica.conflicts import ConflictDetector
    from semantica.deduplication import DuplicateDetector, EntityMerger, MergeStrategy
    from semantica.reasoning import DatalogReasoner
    from semantica.export import RDFExporter

    SEMANTICA_AVAILABLE = True
except ImportError:
    SEMANTICA_AVAILABLE = False
    ContextGraph = None  # type: ignore[assignment, misc]
    ProvenanceManager = None  # type: ignore[assignment, misc]
    ConflictDetector = None  # type: ignore[assignment, misc]
    DuplicateDetector = None  # type: ignore[assignment, misc]
    EntityMerger = None  # type: ignore[assignment, misc]
    MergeStrategy = None  # type: ignore[assignment, misc]
    DatalogReasoner = None  # type: ignore[assignment, misc]
    RDFExporter = None  # type: ignore[assignment, misc]


class SemanticaBackend:
    """Holds all Semantica components for one forensic case session.

    Created by :class:`~forensicagent.pipeline.orchestrator.ForensicPipeline`
    when ``SEMANTICA_AVAILABLE`` is ``True``.  Each component is initialised
    lazily so importing this module never triggers heavy Semantica imports
    unless a backend is actually constructed.
    """

    def __init__(self, case_id: str) -> None:
        if not SEMANTICA_AVAILABLE:
            raise RuntimeError("semantica is not installed — use legacy path")

        self.case_id = case_id

        # --- ContextGraph (S-GRAPH) ---
        self.context_graph: ContextGraph = ContextGraph(
            advanced_analytics=True,
            centrality_analysis=True,
            community_detection=False,  # not needed for forensic cases
            node_embeddings=False,       # not needed — no vector search
        )

        # --- Provenance (S-PROV) ---
        self.provenance: ProvenanceManager = ProvenanceManager()

        # --- Conflict Detection (S-CONFLICT) ---
        self.conflict_detector: ConflictDetector = ConflictDetector()

        # --- Entity Deduplication (S-DEDUP) ---
        self.duplicate_detector: DuplicateDetector = DuplicateDetector(
            similarity_threshold=0.85,   # conservative — forensic data
            confidence_threshold=0.6,
            use_clustering=True,
        )
        self.entity_merger: EntityMerger = EntityMerger(
            preserve_provenance=True,
        )

        # --- Datalog Reasoning (S-REASON) ---
        self.datalog_reasoner: DatalogReasoner = DatalogReasoner()

        # --- RDF Export (S-EXPORT) ---
        self._rdf_exporter: Optional[RDFExporter] = None

        logger.info(
            "SemanticaBackend initialised for case %s "
            "(ContextGraph, Provenance, Conflicts, Dedup, Datalog, Export)",
            case_id,
        )

    @property
    def rdf_exporter(self) -> RDFExporter:
        if self._rdf_exporter is None:
            self._rdf_exporter = RDFExporter()
        return self._rdf_exporter

    def destroy(self) -> None:
        """Release all resources held by this backend."""
        # ContextGraph is in-memory — just drop references.
        self.context_graph = None  # type: ignore[assignment]
        self.provenance = None  # type: ignore[assignment]
        self.conflict_detector = None  # type: ignore[assignment]
        self.duplicate_detector = None  # type: ignore[assignment]
        self.entity_merger = None  # type: ignore[assignment]
        self.datalog_reasoner = None  # type: ignore[assignment]
        self._rdf_exporter = None
        logger.info("SemanticaBackend destroyed for case %s", self.case_id)


def is_available() -> bool:
    """Return ``True`` if semantica is installed and importable."""
    return SEMANTICA_AVAILABLE