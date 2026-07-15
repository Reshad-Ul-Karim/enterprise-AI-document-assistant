"""Embeddings: Pinecone Inference, `llama-text-embed-v2`, 1024-dim. Free tier, no card.

THIS WAS LOCAL (fastembed / BAAI-bge-small / onnxruntime) AND HAD TO CHANGE. The reasoning
is worth keeping, because the mistake is more interesting than the fix.

The original argument was sound: a remote embedder puts a network call in the query path, and
on a rate-limited free tier requests are the scarce resource while local compute is free and
unlimited. That is TRUE -- when RAM is not the binding constraint. It was written for Hugging
Face Spaces: 16 GB, where onnxruntime's ~280 MB is a rounding error.

Then HF made Docker Spaces PRO-only, we moved to Render's free tier, and the premise silently
died. MEASURED, current RSS, fresh process each:

    with onnxruntime      baseline 370 MB of 512  ->  142 MB for everything else
    without onnxruntime   baseline  81 MB of 512  ->  431 MB

An upload needs ~190 MB (pypdf + splitter + embedding). 190 > 142, so uploads OOM'd, Render
killed the container, and the reviewer got a 502 -- on the PUBLIC demo, which was working
fine. No amount of batching fixes a baseline that is 72% of the ceiling; that is arithmetic,
not tuning. Local compute is not free when memory is what you are short of.

**This is the same failure as the LLM router.** That was a cost optimisation that inverted
when the scarce resource became requests instead of dollars. This was a memory-for-requests
trade that inverted when the platform's RAM fell 32x. Both were right when written. Neither
was re-examined when its premise changed. That is the lesson worth carrying.

WHY PINECONE INFERENCE and not another API: the expert council explicitly REJECTED it -- for a
good reason that no longer applies. Its objection was that using Pinecone Inference for
uploads while the committed corpus used local bge would create TWO EMBEDDING SPACES: the same
query embeds differently depending on which store it hits, and the two result sets are
silently incomparable. Not slower -- WRONG, and wrong in the way that never throws.

That objection dies if EVERYTHING uses it. One model, one space, both stores. It is free
(5M tokens/month against a corpus of ~100k tokens indexed once), it needs no card, and it is
a dependency we already carry for upload persistence -- no new vendor.

WHAT THIS COSTS, honestly:
  * The query path gains one network call (~150-250 ms). The generation call is 1-3 s, so it
    is ~10% of the request, not a doubling.
  * "The committed corpus answers with zero network calls" is no longer true. It is now "the
    index is a committed file; embedding the question is an API call." Retrieval now depends
    on Pinecone being up -- though generation already depends on Mistral being up, so the
    request path was never network-free end to end.
  * Query embeddings are ~10 tokens each. The free allowance is not a real constraint.
"""

from __future__ import annotations

from typing import Protocol

import numpy as np

EMBED_MODEL_ID = "llama-text-embed-v2"
EMBED_DIM = 1024

# llama-text-embed-v2 is asymmetric: passages and queries use different input_types. That is
# the model's contract, not a preference -- getting it backwards degrades recall silently.
INPUT_TYPE_PASSAGE = "passage"
INPUT_TYPE_QUERY = "query"

# Bounds a REQUEST (Pinecone caps inputs per call), not memory.
EMBED_BATCH_SIZE_DEFAULT = 90


class EmbeddingUnavailable(RuntimeError):
    """Raised rather than returning a wrong vector. A silently bad embedding is worse than an
    outage: it returns plausible neighbours for the wrong reason and nothing throws."""


class Embedder(Protocol):
    """The provider boundary for embeddings, exactly like Generator is for generation.

    core/ may not import `pinecone` -- .importlinter enforces it. When embeddings moved from
    local onnxruntime to Pinecone Inference, the obvious shortcut was to delete `pinecone`
    from core's forbidden list. That would have been weakening the guard BECAUSE it caught
    something, which is the opposite of what a guard is for. A vendor client is a vendor
    client whether it embeds or generates; both get injected.

    What this buys, concretely: the suite runs with no key and no network (FakeEmbedder),
    and swapping Pinecone Inference for a self-hosted model is one file.
    """

    def embed_passages(self, texts: list[str]) -> np.ndarray: ...
    def embed_query(self, text: str) -> np.ndarray: ...


def l2_normalise(vectors: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(vectors, axis=-1, keepdims=True)
    return vectors / np.clip(norms, 1e-12, None)


class FakeEmbedder:
    """Deterministic, offline, no key. Hash-based, so the same text always gives the same
    vector -- tests can assert on retrieval order without a network call."""

    def __init__(self, dim: int = EMBED_DIM):
        self.dim = dim

    def _vec(self, text: str) -> np.ndarray:
        rng = np.random.default_rng(abs(hash(text)) % (2**32))
        return rng.standard_normal(self.dim).astype(np.float32)

    def embed_passages(self, texts: list[str]) -> np.ndarray:
        return l2_normalise(np.array([self._vec(t) for t in texts], dtype=np.float32))

    def embed_query(self, text: str) -> np.ndarray:
        return l2_normalise(self._vec(text).reshape(1, -1))[0]
