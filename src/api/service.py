"""The ask pipeline. ONE model call per query.

The shape is deliberate and each deletion has a reason:

    pin handbook (3,081 tok) + retrieve top-8 statute sections   [local, ~8 ms]
      -> ONE mistral-large-2512 call                              [the only network hop]
      -> code-verified citations, code-forced abstention          [local, no model]
      -> route label derived in code                              [local, no model]

There is no router model: that was a COST optimisation, and on a free tier requests are
scarce while dollars are not, so it inverted. There is no live entailment judge: at ~1 rps,
five claims would cost five extra seconds, and asyncio.gather does not create quota.
"""

from __future__ import annotations

import json
import time
import uuid
from functools import lru_cache
from pathlib import Path

import numpy as np

from src.core.generator import Generator
from src.core.models import AskResponse, Chunk
from src.core.retrieval import DEFAULT_TOP_K, NumpyRetriever, assemble_context
from src.core.verification import derive_route, verify_answer

REPO = Path(__file__).resolve().parents[2]
PROMPTS = REPO / "prompts"


@lru_cache(maxsize=1)
def load_prompt() -> str:
    return (PROMPTS / "synthesis.md").read_text()


class Corpus:
    """The committed corpus: loaded from files at boot, zero network."""

    def __init__(self, index_dir: Path):
        self.chunks = [Chunk(**json.loads(line)) for line in (index_dir / "chunks.jsonl").open()]
        vectors = np.load(index_dir / "index.npz")["vectors"]
        self.meta = json.loads((index_dir / "index_meta.json").read_text())
        self._assert_boot_invariant(vectors)

        # ASYMMETRIC RETRIEVAL. The handbook is 3,081 tokens -- retrieval over a document
        # that already fits can only lose information. So it is pinned in full and only the
        # statute is retrieved over. This eliminates the 37:1 base-rate problem BY
        # CONSTRUCTION rather than by tuning a per-doc quota you would have to defend, and
        # it is what makes "the handbook is silent on maternity" a SOUND claim rather than
        # an inference from a failed top-k.
        self.handbook = [c for c in self.chunks if c.doc_kind == "handbook"]
        statute_mask = [i for i, c in enumerate(self.chunks) if c.doc_kind == "statute"]
        self.statute_retriever = NumpyRetriever(
            [self.chunks[i] for i in statute_mask], vectors[statute_mask]
        )
        # The full retriever exists so recall@k is measurable across BOTH documents --
        # otherwise Retrieval Accuracy is measured over 97% of the corpus while the
        # document the business scenario is about stays invisible to the metric.
        self.full_retriever = NumpyRetriever(self.chunks, vectors)

    def _assert_boot_invariant(self, vectors: np.ndarray) -> None:
        from src.core.embeddings import EMBED_DIM, EMBED_MODEL_ID

        if self.meta["embed_model_id"] != EMBED_MODEL_ID:
            raise RuntimeError(
                f"index built with {self.meta['embed_model_id']} but runtime uses "
                f"{EMBED_MODEL_ID}. Query and passage vectors would be incomparable."
            )
        if vectors.shape[1] != EMBED_DIM or vectors.shape[0] != len(self.chunks):
            raise RuntimeError(f"index shape {vectors.shape} vs {len(self.chunks)} chunks")

    @property
    def handbook_text(self) -> str:
        return "\n\n".join(f"[[chunk:{c.chunk_id}]] (printed p.{c.printed_page})\n{c.text}" for c in self.handbook)


def build_context_block(handbook: list[Chunk], statute: list[Chunk]) -> str:
    def render(chunk: Chunk) -> str:
        head = f"[[chunk:{chunk.chunk_id}]]"
        if chunk.section_no is not None:
            head += f" Bangladesh Labour Act 2006, s.{chunk.section_no} {chunk.section_title} (printed p.{chunk.printed_page})"
        else:
            head += f" Employee Handbook, printed p.{chunk.printed_page}"
        return f"{head}\n{chunk.text}"

    return (
        "# EMPLOYEE HANDBOOK (complete — every page of it is here)\n\n"
        + "\n\n".join(render(c) for c in handbook)
        + "\n\n# BANGLADESH LABOUR ACT 2006 (retrieved sections)\n\n"
        + "\n\n".join(render(c) for c in statute)
    )


def answer(
    question: str,
    corpus: Corpus,
    generator: Generator,
    top_k: int = DEFAULT_TOP_K,
    section_no: int | None = None,
) -> AskResponse:
    started = time.perf_counter()
    request_id = str(uuid.uuid4())[:8]

    if section_no is not None:
        statute = corpus.statute_retriever.get_section(section_no)
    else:
        statute = assemble_context(corpus.statute_retriever.search(question, k=top_k))

    context = build_context_block(corpus.handbook, statute)
    raw = generator.generate(load_prompt(), f"{context}\n\n# QUESTION\n{question}")

    # The model's output is not trusted. Every quoted span is checked against the chunk it
    # claims to come from; unverifiable claims are stripped; if nothing survives,
    # insufficient_information is set BY CODE rather than chosen by the model.
    available = corpus.handbook + statute
    text, citations, insufficient = verify_answer(raw, available)

    return AskResponse(
        answer=text or "Not found in the provided documents.",
        citations=citations,
        insufficient_information=insufficient,
        route=derive_route(citations),
        latency_ms=int((time.perf_counter() - started) * 1000),
        request_id=request_id,
        index_version=corpus.meta["index_version"],
    )
