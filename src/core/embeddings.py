"""Embeddings: fastembed BAAI/bge-small-en-v1.5, 384d, local.

Local, not remote, and the reason is specific to a rate-limited free tier: a remote
embedder puts a network call in the QUERY path, spending the scarcest resource in the
system (requests/second, shared with generation) on something local hardware does in
~2.4 ms for free. Under a rate-limited free tier, local compute is free and unlimited
while API requests are scarce -- so move everything you can OFF the API.

No quantization step: fastembed's default artifact for this model ID already resolves to
the int8 ONNX build. Writing a quantization step would re-do what the library did.
"""

from __future__ import annotations

from functools import lru_cache

import numpy as np

EMBED_MODEL_ID = "BAAI/bge-small-en-v1.5"
EMBED_DIM = 384

# bge is trained asymmetrically: this prefix goes on QUERIES ONLY, never on passages.
# Applied because that is how the model was trained and it is one line -- NOT because it
# measurably buys recall here. Measured on this corpus: recall@5 = 1.00 with and without.
# Do not claim a benefit you cannot measure.
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


@lru_cache(maxsize=1)
def _model():
    from fastembed import TextEmbedding

    return TextEmbedding(model_name=EMBED_MODEL_ID)


def embed_passages(texts: list[str]) -> np.ndarray:
    vectors = np.array(list(_model().embed(texts)), dtype=np.float32)
    return _l2_normalise(vectors)


def embed_query(text: str) -> np.ndarray:
    vector = np.array(list(_model().embed([QUERY_PREFIX + text]))[0], dtype=np.float32)
    return _l2_normalise(vector.reshape(1, -1))[0]


def _l2_normalise(vectors: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(vectors, axis=-1, keepdims=True)
    return vectors / np.clip(norms, 1e-12, None)
