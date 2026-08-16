from __future__ import annotations

import logging

from forensicagent.agents.base import BaseAgent
from forensicagent.models import Source
from forensicagent.utils.bm25 import BM25Index

logger = logging.getLogger(__name__)


class KeywordIndexAgent(BaseAgent):
    """Builds a BM25 index over all source documents and extracts
    the top-k BM25-weighted keywords per source."""

    name = "keyword_index"

    def __init__(self, case_id: str) -> None:
        super().__init__(case_id)
        self.bm25: BM25Index = BM25Index()
        self._doc_keywords: dict[str, list[str]] = {}

    def index_sources(self, sources: list[Source]) -> BM25Index:
        self.bm25 = BM25Index()
        for s in sources:
            if s.raw_text:
                self.bm25.add(s.id, s.raw_text)
        logger.info("BM25 index built over %d sources", self.bm25.num_docs)
        return self.bm25

    def extract_keywords(self, source: Source, top_k: int = 20) -> list[str]:
        idx = self.bm25.doc_ids.index(source.id) if source.id in self.bm25.doc_ids else -1
        if idx < 0:
            return []
        ranked = self.bm25.keyword_scores(idx, top_k)
        keywords = [tok for tok, _ in ranked]
        source.keywords = keywords
        self._doc_keywords[source.id] = keywords
        return keywords

    def search(self, query: str, top_k: int = 10) -> list[tuple[str, float]]:
        return self.bm25.search(query, top_k)

    def run(self, *args, **kwargs):
        return {"status": "ok", "data": {"index_size": self.bm25.num_docs}}
