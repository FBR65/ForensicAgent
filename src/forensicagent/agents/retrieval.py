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

        Results are then passed through an explainable reranker that
        combines semantic relevance with source authority, recency and
        diversity (PDF §9).
        """
        # --- S-RETRIEVE: GraphRAG primary path ---
        if self._semantica_retrieval is not None and self._semantica_retrieval.is_available():
            try:
                graph_results = self._semantica_retrieval.retrieve(query, max_results=top_k)
                if graph_results:
                    results = [
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
                    return self._rerank(query, results, top_k)
            except Exception as exc:
                logger.warning("GraphRAG retrieval failed, falling back to BM25: %s", exc)

        # --- BM25 fallback ---
        if not self._bm25:
            return []
        results = self._bm25.search(query, top_k)
        docs_by_id = {d["id"]: d for d in self._documents}
        docs = [
            {"score": score, **docs_by_id.get(doc_id, {"id": doc_id, "body": ""})}
            for doc_id, score in results
        ]
        return self._rerank(query, docs, top_k)

    def _rerank(
        self, query: str, results: list[dict[str, Any]], top_k: int
    ) -> list[dict[str, Any]]:
        """Explainable reranking (PDF §9).

        Combines the raw retrieval score with:
        - semantic relevance (query-term overlap in title/body),
        - source authority (tags such as ``statute``/``official``),
        - recency (a ``date`` field, if present),
        - diversity (penalise near-duplicate bodies).

        Each result carries a ``rerank`` dict explaining the score so the
        ranking is auditable rather than a black box.
        """
        if not results:
            return results

        q_terms = {
            t.strip(".,?;:!'\"").lower()
            for t in query.split()
            if len(t.strip(".,?;:!'\"")) >= 3
        }

        scored: list[tuple[float, dict[str, Any]]] = []
        for r in results:
            base = float(r.get("score", 0.0))
            text = f"{r.get('title', '')} {r.get('body', '')}".lower()
            overlap = sum(1 for t in q_terms if t in text)
            semantic = min(1.0, overlap / max(1, len(q_terms)))

            tags = [t.lower() for t in r.get("tags", [])]
            authority = 0.0
            if any(t in tags for t in ("statute", "official", "gesetz", "amtlich")):
                authority = 0.2
            elif any(t in tags for t in ("template", "checklist", "practice")):
                authority = 0.1

            recency = 0.0
            date = r.get("date")
            if date:
                try:
                    from datetime import datetime
                    year = int(str(date)[:4])
                    recency = 0.1 if year >= 2020 else 0.0
                except (ValueError, TypeError):
                    recency = 0.0

            final = base + semantic + authority + recency
            scored.append((final, r))

        # Diversity: penalise results whose body is near-duplicate of a
        # higher-ranked result already kept.
        scored.sort(key=lambda x: x[0], reverse=True)
        kept: list[dict[str, Any]] = []
        seen_bodies: list[str] = []
        for score, r in scored:
            body = (r.get("body", "") or "").lower()[:200]
            if body and any(body in seen or seen in body for seen in seen_bodies):
                score -= 0.15
            seen_bodies.append(body)
            r["rerank"] = {
                "base_score": round(float(r.get("score", 0.0)), 3),
                "semantic": round(semantic, 3),
                "authority": round(authority, 3),
                "recency": round(recency, 3),
                "final_score": round(score, 3),
            }
            kept.append(r)

        return kept[:top_k]

    def retrieve_by_tags(self, tags: list[str], top_k: int = 10) -> list[dict[str, Any]]:
        matched = [d for d in self._documents if any(t in d.get("tags", []) for t in tags)]
        matched.sort(key=lambda d: len(d["body"]), reverse=True)
        return matched[:top_k]

    def run(self, *args, **kwargs):
        return {"status": "ok", "data": {"kb_documents": len(self._documents)}}
