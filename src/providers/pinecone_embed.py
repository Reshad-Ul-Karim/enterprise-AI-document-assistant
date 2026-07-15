"""Pinecone Inference embeddings. The ONLY module that imports `pinecone` for embedding.

WHY THIS FILE EXISTS AT ALL -- the short version of an expensive lesson.

Embeddings used to be local: fastembed / BAAI-bge-small / onnxruntime. That was the right
call for Hugging Face Spaces (16 GB), where onnxruntime's ~280 MB is a rounding error, and
the argument was sound: a remote embedder puts a network call in the query path, and on a
rate-limited free tier requests are scarce while local compute is free.

Then HF made Docker Spaces PRO-only, we moved to Render's 512 MB, and the premise died
without the decision being revisited. Measured, current RSS, fresh process each:

    with onnxruntime      370 MB baseline  ->  142 MB left for an upload needing ~190  ->  OOM
    without onnxruntime    81 MB baseline  ->  431 MB left                             ->  fine

Uploads OOM-killed the container and the reviewer got a 502 on the PUBLIC demo, which shares
nothing with uploads except a process. Local compute is not free when memory is the scarce
resource. **Same shape as the LLM router**: a trade that was correct when written, and wrong
once its premise moved. Neither was re-examined. That is the actual lesson.

WHY PINECONE INFERENCE. The expert council explicitly rejected it -- for a good reason that
no longer applies. Its objection: using it for uploads while the committed corpus used local
bge would create TWO EMBEDDING SPACES, so the same query embeds differently depending on
which store it hits and the result sets are silently incomparable. That dies if EVERYTHING
uses it. One model, one space, both stores. Free (5M tokens/month vs a corpus indexed once at
~100k), no card, and already a dependency for upload persistence -- no new vendor.
"""

from __future__ import annotations

import os

import numpy as np

from src.core.embeddings import (
    EMBED_BATCH_SIZE_DEFAULT,
    EMBED_MODEL_ID,
    INPUT_TYPE_PASSAGE,
    INPUT_TYPE_QUERY,
    EmbeddingUnavailable,
    l2_normalise,
)


class PineconeEmbedder:
    """Bounds a REQUEST, not memory -- unlike the old onnxruntime batch size, which bounded
    an allocation. The vectors are 4 KB each; the batch limit is Pinecone's API cap."""

    def __init__(self, api_key: str | None = None, batch_size: int | None = None):
        self.api_key = api_key or os.environ.get("PINECONE_API_KEY")
        if not self.api_key:
            raise EmbeddingUnavailable(
                "PINECONE_API_KEY is required for embeddings. Retrieval cannot run without it; "
                "/health reports this rather than the app crash-looping."
            )
        self.batch_size = batch_size or EMBED_BATCH_SIZE_DEFAULT
        self._pc = None

    def _client(self):
        if self._pc is None:
            from pinecone import Pinecone

            self._pc = Pinecone(api_key=self.api_key)
        return self._pc

    def _embed(self, texts: list[str], input_type: str) -> np.ndarray:
        out: list[list[float]] = []
        for start in range(0, len(texts), self.batch_size):
            batch = texts[start : start + self.batch_size]
            try:
                response = self._client().inference.embed(
                    model=EMBED_MODEL_ID,
                    inputs=batch,
                    parameters={"input_type": input_type, "truncate": "END"},
                )
            except Exception as exc:
                # Never return a wrong vector. A degraded embedding does not throw -- it just
                # retrieves the wrong thing, convincingly.
                raise EmbeddingUnavailable(f"Pinecone Inference failed: {exc}") from exc
            out.extend(d["values"] for d in response.data)
        return l2_normalise(np.array(out, dtype=np.float32))

    def embed_passages(self, texts: list[str]) -> np.ndarray:
        return self._embed(texts, INPUT_TYPE_PASSAGE)

    def embed_query(self, text: str) -> np.ndarray:
        return self._embed([text], INPUT_TYPE_QUERY)[0]
