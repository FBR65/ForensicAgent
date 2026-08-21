from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional

from forensicagent.agents.base import BaseAgent
from forensicagent.utils.bm25 import BM25Index

logger = logging.getLogger(__name__)


class KnowledgeRetrievalAgent(BaseAgent):
    """RAG over a *persistent* domain knowledge base (statutes, procedures,
    templates, precedents).  The KB is separate from the volatile case graph.

    When a :class:`~forensicagent.pipeline.semantica_retrieval.SemanticaRetrieval`
    instance is supplied via *semantica_retrieval*, queries first go through
    Multi-hop GraphRAG over the Semantica ContextGraph.  If GraphRAG yields
    no results, the query falls back to BM25 ranking (S-RETRIEVE).
    """

    name = "knowledge_retrieval"

    def __init__(
        self,
        case_id: str,
        kb_dirs: list[str | Path] | None = None,
        semantica_retrieval: Optional[Any] = None,
    ) -> None:
        super().__init__(case_id)
        self._kb_dirs = [Path(d) for d in (kb_dirs or [])]
        self._documents: list[dict[str, Any]] = []
        self._bm25: BM25Index | None = None
        self._semantica_retrieval = semantica_retrieval
        if self._kb_dirs:
            self._load_kb(self._kb_dirs)

    def reindex(self) -> None:
        """Reload and re-index the KB from disk (after documents were added)."""
        self._documents = []
        if self._kb_dirs:
            self._load_kb(self._kb_dirs)

    def _load_kb(self, kb_dirs: list[str | Path]) -> None:
        for d in kb_dirs:
            d = Path(d)
            if not d.exists():
                logger.warning("KB directory not found: %s", d)
                continue
            for file in d.rglob("*"):
                if file.suffix in (".json", ".txt", ".md"):
                    try:
                        if file.suffix == ".json":
                            with open(file) as f:
                                data = json.load(f)
                            items = data if isinstance(data, list) else data.get("items", [])
                            for item in items:
                                self._documents.append({
                                    "id": item.get("id", f"{file.stem}-{len(self._documents)}"),
                                    "title": item.get("title", file.stem),
                                    "body": item.get("body", item.get("text", "")),
                                    "source": str(file),
                                    "tags": item.get("tags", []),
                                })
                        else:
                            text = file.read_text(encoding="utf-8", errors="replace")
                            self._documents.append({
                                "id": file.stem,
                                "title": file.stem,
                                "body": text,
                                "source": str(file),
                                "tags": [],
                            })
                    except Exception as exc:
                        logger.warning("Failed to load KB file %s: %s", file, exc)
        self._index_kb()

    def _index_kb(self) -> None:
        self._bm25 = BM25Index()
        for doc in self._documents:
            self._bm25.add(doc["id"], doc["title"] + "\n" + doc["body"])
        logger.info("Knowledge base indexed: %d documents", len(self._documents))

    def retrieve(self, query: str, top_k: int = 10) -> list[dict[str, Any]]:
        """Retrieve documents for *query*.

        S-RETRIEVE: When Semantica retrieval is available, first try
        Multi-hop GraphRAG.  If it returns results, they are returned as-is
        (content + score + source).  If GraphRAG yields nothing, fall back
        to BM25 ranking over the local KB documents.
        """
        # --- S-RETRIEVE: GraphRAG primary path ---
        if self._semantica_retrieval is not None and self._semantica_retrieval.is_available():
            try:
                graph_results = self._semantica_retrieval.retrieve(query, max_results=top_k)
                if graph_results:
                    return [
                        {
                            "id": r.metadata.get("node_id", r.source or ""),
                            "title": r.content[:80],
                            "body": r.content,
                            "source": r.source or "graph",
                            "score": r.score,
                            "tags": [],
                        }
                        for r in graph_results
                    ]
            except Exception as exc:
                logger.warning("GraphRAG retrieval failed, falling back to BM25: %s", exc)

        # --- BM25 fallback ---
        if not self._bm25:
            return []
        results = self._bm25.search(query, top_k)
        docs_by_id = {d["id"]: d for d in self._documents}
        return [
            {"score": score, **docs_by_id.get(doc_id, {"id": doc_id, "body": ""})}
            for doc_id, score in results
        ]

    def retrieve_by_tags(self, tags: list[str], top_k: int = 10) -> list[dict[str, Any]]:
        matched = [d for d in self._documents if any(t in d.get("tags", []) for t in tags)]
        matched.sort(key=lambda d: len(d["body"]), reverse=True)
        return matched[:top_k]

    def run(self, *args, **kwargs):
        return {"status": "ok", "data": {"kb_documents": len(self._documents)}}
