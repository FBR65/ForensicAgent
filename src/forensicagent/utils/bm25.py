from __future__ import annotations

import re
import unicodedata
from functools import lru_cache

from rank_bm25 import BM25Okapi


_STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "as", "is", "are", "was", "were", "be",
    "been", "being", "have", "has", "had", "do", "does", "did", "not",
    "no", "nor", "so", "than", "then", "but", "or", "yet",
}

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def tokenize(text: str, lowercase: bool = True) -> list[str]:
    text = unicodedata.normalize("NFKC", text)
    if lowercase:
        text = text.lower()
    return [tok for tok in _TOKEN_RE.findall(text) if tok not in _STOPWORDS]


class BM25Index:
    def __init__(self) -> None:
        self._docs: list[str] = []
        self._tokenised: list[list[str]] = []
        self._bm25: BM25Okapi | None = None
        self._built = False

    def add(self, doc_id: str, text: str) -> None:
        tokens = tokenize(text)
        self._docs.append(doc_id)
        self._tokenised.append(tokens)
        self._bm25 = None
        self._built = False

    def _ensure(self) -> None:
        if not self._built:
            self._bm25 = BM25Okapi(self._tokenised)
            self._built = True

    def keyword_scores(self, doc_index: int, top_k: int = 20) -> list[tuple[str, float]]:
        self._ensure()
        assert self._bm25 is not None
        tokens = self._tokenised[doc_index]
        scores = self._bm25.get_scores(tokens)
        token_scores: dict[str, float] = {}
        for tok, sc in zip(tokens, scores):
            token_scores[tok] = token_scores.get(tok, 0.0) + sc
        ranked = sorted(token_scores.items(), key=lambda kv: kv[1], reverse=True)
        return ranked[:top_k]

    def search(self, query: str, top_k: int = 10) -> list[tuple[str, float]]:
        self._ensure()
        assert self._bm25 is not None
        q_tokens = tokenize(query)
        if not q_tokens:
            return []
        scores = self._bm25.get_scores(q_tokens)
        ranked = sorted(zip(self._docs, scores), key=lambda kv: kv[1], reverse=True)
        # Keep docs that share at least one query term, even when BM25 score
        # is <= 0 (single-doc KB / idf=0 edge cases).
        result: list[tuple[str, float]] = []
        for did, sc in ranked:
            q_set = set(q_tokens)
            doc_set = set(self._tokenised[self._docs.index(did)])
            if sc > 0.0 or q_set.intersection(doc_set):
                result.append((did, sc))
            if len(result) >= top_k:
                break
        return result

    @property
    def doc_ids(self) -> list[str]:
        return list(self._docs)

    @property
    def num_docs(self) -> int:
        return len(self._docs)
