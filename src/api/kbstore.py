"""Where uploaded knowledge bases live.

THE SPLIT, and the axis it falls on: **data lifetime, not speed.**

  * The committed corpus is a FILE. It ships inside the image, loads at boot with zero
    network, and nobody else's quota or outage can break it. 482 vectors, 0.74 MB,
    0.008 ms exact cosine. Putting it in a vector database would be infrastructure cosplay.
  * An uploaded KB arrives AFTER the image was built, onto a disk the platform wipes.
    It therefore needs a database -- not because it is big, but because it must outlive
    the container.

One Retriever protocol, two backends, both on live traffic, chosen by kb_id. That is the
answer to "so why is the other one in the repo?": they hold different data with different
lifecycles, and each is wrong for the other's job.

THE HONEST STATE OF THIS DEPLOYMENT: with no PINECONE_API_KEY, uploads are IN-MEMORY and
die on restart. That is stated in the UI at upload time -- before the user spends effort --
rather than discovered afterwards. A demo that appears to lose your data is worse than one
that never offered to keep it.

MEMORY IS THE BINDING CONSTRAINT, and the caps below are not decoration. The box has
512 MB and the baseline already occupies ~435 MB. An unbounded in-memory KB is an OOM, and
an OOM on a free tier is not a degraded upload -- it is a dead URL for the reviewer who was
clicking the public demo. So the caps protect the demo from the feature.
"""

from __future__ import annotations

import numpy as np

from src.api.settings import settings
from src.api.uploads import KnowledgeBase, UploadBackendUnavailable
from src.core.embeddings import EMBED_DIM, EMBED_MODEL_ID, embed_passages, embed_query
from src.core.models import Chunk
from src.core.retrieval import DEFAULT_TOP_K, reciprocal_rank_fusion, tokenise


class InMemoryKbRetriever:
    """Ephemeral. Vectors and BM25 held in RAM, bounded, gone on restart."""

    def __init__(self, kb: KnowledgeBase):
        self.kb = kb
        self._vectors: np.ndarray | None = None
        self._bm25 = None

    def reindex(self) -> None:
        if not self.kb.chunks:
            self._vectors, self._bm25 = None, None
            return
        from rank_bm25 import BM25Okapi

        self._vectors = embed_passages([c.text for c in self.kb.chunks])
        # Per-namespace BM25, rebuilt in memory at upload -- milliseconds for a few hundred
        # chunks. An earlier draft gave uploads a dense-only path and called it "an honest
        # asymmetry"; it is not honest to hand someone a demonstrably worse pipeline built
        # from the components you spend the interview arguing for. It costs milliseconds.
        self._bm25 = BM25Okapi([tokenise(c.text) for c in self.kb.chunks])

    def search(self, query: str, k: int = DEFAULT_TOP_K) -> list[tuple[Chunk, float]]:
        if self._vectors is None or self._bm25 is None:
            return []
        dense = self._vectors @ embed_query(query)
        dense_rank = np.argsort(-dense)[: k * 4].tolist()
        lexical = self._bm25.get_scores(tokenise(query))
        lexical_rank = np.argsort(-lexical)[: k * 4].tolist()
        fused = reciprocal_rank_fusion([dense_rank, lexical_rank])
        top = sorted(fused.items(), key=lambda kv: -kv[1])[:k]
        return [(self.kb.chunks[i], s) for i, s in top]

    def get_section(self, section_no: int) -> list[Chunk]:
        return []  # an arbitrary document has no section grammar to key on

    def all_chunks(self) -> list[Chunk]:
        return self.kb.chunks


class PineconeKbRetriever:
    """Persistent. One namespace per KB.

    Namespace-per-KB rather than a metadata filter, and the reason is failure mode:
    a metadata filter you forget LEAKS across tenants; a namespace you forget RETURNS
    NOTHING. When the entire feature is separation, fail-closed beats fail-open.

    Namespaces, not indexes: the free tier caps at 5 indexes but 100 namespaces per index.
    Index-per-KB is the mistake that shows you did not read the limits page -- wrong by 20x.

    CHUNK TEXT RIDES IN THE METADATA. Vectors alone would be useless after the restart this
    exists to survive: you would retrieve a vector and have no text to cite. Chunks are
    0.6-2 KB against a 40 KB metadata cap -- roughly 20x headroom -- so the text comes home
    with the vector and an upload survives a restart COMPLETELY.
    """

    def __init__(self, kb: KnowledgeBase, api_key: str, index_name: str):
        from pinecone import Pinecone, ServerlessSpec

        self.kb = kb
        self.namespace = f"kb_{kb.kb_id}"
        pc = Pinecone(api_key=api_key)
        existing = {i["name"] for i in pc.list_indexes()}
        if index_name not in existing:
            pc.create_index(
                name=index_name,
                dimension=EMBED_DIM,  # MUST match bge-small: same model both sides, or the
                metric="cosine",       # two vector spaces are silently incomparable.
                # Starter is region-locked to us-east-1; hardcoding anything else fails at
                # create time with an error that does not say so.
                spec=ServerlessSpec(cloud="aws", region="us-east-1"),
            )
        self.index = pc.Index(index_name)
        stats = self.index.describe_index_stats()
        if stats.get("dimension") != EMBED_DIM:
            raise UploadBackendUnavailable(
                f"Pinecone index '{index_name}' has dimension {stats.get('dimension')}, but "
                f"{EMBED_MODEL_ID} produces {EMBED_DIM}. Query and passage vectors would be "
                "incomparable -- wrong in the way that never throws."
            )
        self._bm25 = None

    def upsert(self, chunks: list[Chunk]) -> None:
        import json

        vectors = embed_passages([c.text for c in chunks])
        payload = []
        for chunk, vector in zip(chunks, vectors):
            metadata = {
                "text": chunk.text,
                "doc_id": chunk.doc_id,
                "doc_title": chunk.doc_title,
                "printed_page": chunk.printed_page,
                "zero_based_pdf_index": chunk.zero_based_pdf_index,
                "source_modality": chunk.source_modality,
            }
            # Fail the INGEST, never the query: a chunk that cannot round-trip must be
            # rejected while the user is watching, not discovered as a missing citation.
            if len(json.dumps(metadata)) >= 40_000:
                raise UploadBackendUnavailable(
                    f"Chunk {chunk.chunk_id} exceeds Pinecone's 40 KB metadata cap."
                )
            payload.append({"id": chunk.chunk_id, "values": vector.tolist(), "metadata": metadata})
        for i in range(0, len(payload), 100):
            self.index.upsert(vectors=payload[i : i + 100], namespace=self.namespace)
        self._rebuild_bm25()

    def _rebuild_bm25(self) -> None:
        from rank_bm25 import BM25Okapi

        if self.kb.chunks:
            self._bm25 = BM25Okapi([tokenise(c.text) for c in self.kb.chunks])

    def search(self, query: str, k: int = DEFAULT_TOP_K) -> list[tuple[Chunk, float]]:
        result = self.index.query(
            vector=embed_query(query).tolist(),
            top_k=k,
            namespace=self.namespace,
            include_metadata=True,
        )
        out: list[tuple[Chunk, float]] = []
        for match in result.get("matches", []):
            md = match["metadata"]
            out.append(
                (
                    Chunk(
                        chunk_id=match["id"],
                        kb_id=self.kb.kb_id,
                        doc_id=md["doc_id"],
                        doc_title=md["doc_title"],
                        doc_kind="uploaded",
                        text=md["text"],
                        zero_based_pdf_index=int(md["zero_based_pdf_index"]),
                        printed_page=int(md["printed_page"]),
                        source_modality=md["source_modality"],
                    ),
                    float(match["score"]),
                )
            )
        return out

    def get_section(self, section_no: int) -> list[Chunk]:
        return []

    def all_chunks(self) -> list[Chunk]:
        return self.kb.chunks


class KbRegistry:
    """The knowledge bases this process knows about, and the jobs feeding them."""

    def __init__(self) -> None:
        self.kbs: dict[str, KnowledgeBase] = {}
        self.retrievers: dict[str, object] = {}
        self.jobs: dict[str, object] = {}

    def create(self, kb_id: str, name: str) -> KnowledgeBase:
        if not settings.uploads_persist and len(self.kbs) >= settings.max_inmemory_kbs:
            raise UploadBackendUnavailable(
                f"This deployment holds uploaded knowledge bases in memory (no "
                f"PINECONE_API_KEY), and is capped at {settings.max_inmemory_kbs} to protect "
                f"the public demo from an out-of-memory kill on a 512 MB box. Delete one first."
            )
        kb = KnowledgeBase(kb_id=kb_id, name=name)
        self.kbs[kb_id] = kb
        if settings.uploads_persist:
            self.retrievers[kb_id] = PineconeKbRetriever(
                kb, settings.pinecone_api_key, settings.pinecone_index  # type: ignore[arg-type]
            )
        else:
            self.retrievers[kb_id] = InMemoryKbRetriever(kb)
        return kb

    def index_after_upload(self, kb_id: str, new_chunks: list[Chunk]) -> None:
        retriever = self.retrievers[kb_id]
        if isinstance(retriever, PineconeKbRetriever):
            retriever.upsert(new_chunks)
        else:
            retriever.reindex()  # type: ignore[union-attr]

    def delete(self, kb_id: str) -> None:
        self.kbs.pop(kb_id, None)
        self.retrievers.pop(kb_id, None)
