"""Retrieval: hybrid BM25 + dense, fused with RRF, over a flat exact index.

No ANN index. At 399 vectors, exact cosine search costs ~0.008 ms -- vector search is a
rounding error against a ~2s model call. HNSW (m=16, ef_construction=200, ef_search=64)
would earn its place at roughly 50k vectors, where the exact scan crosses ~10 ms.
Reaching for a distributed vector database to serve 0.6 MB is infrastructure cosplay.

Why hybrid HERE, specifically -- not the generic reason:
  1. IDF. 'gratuity' appears 10x in 61k body word-tokens, 'retrenchment' 14x, 'lay-off'
     7x -- rare high-IDF terms of art where BM25 is near-perfectly precise and dense
     embeddings blur them into 'compensation' (120x). Conversely "can my boss make me
     work overtime?" has zero lexical overlap with the governing sections: dense wins.
  2. OCR noise is asymmetric. Only 2 corrupted tokens in 61,098 body word-tokens, so the
     "OCR is noisy therefore BM25 breaks" argument is measured FALSE. But real prose noise
     ('taw' for law, 'CUOAPTER') breaks lexical matching on PROSE, while section numbers
     and terms of art OCR cleanly and demand exact match. You need both scorers.

RRF rather than a weighted blend: no alpha to justify at interview.
"""

from __future__ import annotations

import re
from typing import Protocol

import numpy as np

from src.core.embeddings import embed_query
from src.core.models import Chunk

RRF_K = 60
DEFAULT_TOP_K = 8


class Retriever(Protocol):
    """Two implementations, both on live traffic, split on ONE axis: data lifetime.

    What ships inside the image is a file (NumpyRetriever). What arrives after the image
    is built needs a database (PineconeRetriever), because the disk is ephemeral.
    """

    def search(self, query: str, k: int = DEFAULT_TOP_K) -> list[tuple[Chunk, float]]: ...
    def get_section(self, section_no: int) -> list[Chunk]: ...
    def all_chunks(self) -> list[Chunk]: ...


def tokenise(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def reciprocal_rank_fusion(
    rankings: list[list[int]], k: int = RRF_K
) -> dict[int, float]:
    scores: dict[int, float] = {}
    for ranking in rankings:
        for rank, doc_index in enumerate(ranking):
            scores[doc_index] = scores.get(doc_index, 0.0) + 1.0 / (k + rank + 1)
    return scores


class NumpyRetriever:
    """The committed corpus: a file that loads at boot with zero network.

    Nobody but us can pause it, rate-limit it, or reap it for inactivity.
    """

    def __init__(self, chunks: list[Chunk], vectors: np.ndarray):
        if len(chunks) != vectors.shape[0]:
            raise ValueError(f"{len(chunks)} chunks vs {vectors.shape[0]} vectors")
        self.chunks = chunks
        self.vectors = vectors
        self._bm25 = self._build_bm25(chunks)
        self._by_section: dict[int, list[Chunk]] = {}
        for chunk in chunks:
            if chunk.section_no is not None:
                self._by_section.setdefault(chunk.section_no, []).append(chunk)

    @staticmethod
    def _build_bm25(chunks: list[Chunk]):
        from rank_bm25 import BM25Okapi

        return BM25Okapi([tokenise(c.text) for c in chunks])

    def search(self, query: str, k: int = DEFAULT_TOP_K) -> list[tuple[Chunk, float]]:
        dense_scores = self.vectors @ embed_query(query)
        dense_rank = np.argsort(-dense_scores)[: k * 4].tolist()

        lexical_scores = self._bm25.get_scores(tokenise(query))
        lexical_rank = np.argsort(-lexical_scores)[: k * 4].tolist()

        fused = reciprocal_rank_fusion([dense_rank, lexical_rank])
        top = sorted(fused.items(), key=lambda kv: -kv[1])[:k]
        return [(self.chunks[i], score) for i, score in top]

    def get_section(self, section_no: int) -> list[Chunk]:
        """A statute has a natural primary key. Approximating an exact key is silly --
        this is a WHERE section_no = N, not agentic retrieval.

        (Statutes cite by number and never self-name in the third person, so a section
        header and a cross-reference to it are different strings. That is why the section
        number is a metadata field, not a similarity target.)
        """
        return self._by_section.get(section_no, [])

    def all_chunks(self) -> list[Chunk]:
        return self.chunks


def assemble_context(hits: list[tuple[Chunk, float]]) -> list[Chunk]:
    """Statutes read sequentially: assemble in section-number order, not relevance order."""
    chunks = [c for c, _ in hits]
    return sorted(
        chunks,
        key=lambda c: (c.section_no if c.section_no is not None else 10_000, c.chunk_id),
    )
