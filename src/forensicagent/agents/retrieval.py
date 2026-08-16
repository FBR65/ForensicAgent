from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from forensicagent.agents.base import BaseAgent
from forensicagent.utils.bm25 import BM25Index

logger = logging.getLogger(__name__)


class KnowledgeRetrievalAgent(BaseAgent):
    """RAG over a *persistent* domain knowledge base (statutes, procedures,
    templates, precedents).  The KB is separate from the volatile case graph.

    The KB is tokenised and indexed with BM25 at init.  Queries are
    answered by BM25 ranking.
    """

    name = "knowledge_retrieval"

    def __init__(self, case_id: str, kb_dirs: list[str | Path] | None = None) -> None:
        super().__init__(case_id)
        self._kb_dirs = [Path(d) for d in (kb_dirs or [])]
        self._documents: list[dict[str, Any]] = []
        self._bm25: BM25Index | None = None
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
