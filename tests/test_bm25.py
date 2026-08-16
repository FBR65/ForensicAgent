"""Tests for BM25 indexing and keyword extraction."""
from forensicagent.utils.bm25 import BM25Index, tokenize


def test_tokenize():
    tokens = tokenize("Hello, world! This is a test.")
    assert "hello" in tokens
    assert "world" in tokens
    assert "test" in tokens
    assert "is" not in tokens  # stopword


def test_bm25_index_and_search():
    idx = BM25Index()
    idx.add("doc1", "The defendant committed fraud in Berlin")
    idx.add("doc2", "The patient was treated at the hospital")
    idx.add("doc3", "The defendant fled to Munich")
    results = idx.search("defendant fraud", top_k=2)
    assert len(results) == 2
    assert results[0][0] == "doc1"  # most relevant


def test_bm25_keyword_scores():
    idx = BM25Index()
    idx.add("d1", "fraud fraud fraud Berlin Berlin fraud")
    idx.add("d2", "hospital patient treatment")
    keywords = idx.keyword_scores(0, top_k=5)
    words = [w for w, _ in keywords]
    assert "fraud" in words  # highest BM25 weight
