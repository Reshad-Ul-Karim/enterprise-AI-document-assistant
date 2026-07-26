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
import re
import time
import uuid
from functools import lru_cache
from pathlib import Path

import numpy as np

from src.core.generator import Generator
from src.core.models import AskResponse, Chunk, PageContext, Turn
from src.core.retrieval import DEFAULT_TOP_K, NumpyRetriever, assemble_context
from src.core.verification import derive_route, verify_answer

REPO = Path(__file__).resolve().parents[2]
PROMPTS = REPO / "prompts"


@lru_cache(maxsize=4)
def load_prompt(name: str = "synthesis") -> str:
    """Prompts are versioned .md loaded at runtime -- never inline f-strings. The assessment
    requires explaining them at interview, so the git history of prompts/ IS the tuning
    curve, and each revision can carry its eval delta in the commit message."""
    return (PROMPTS / f"{name}.md").read_text()


class Corpus:
    """The committed corpus: loaded from files at boot, zero network."""

    def __init__(self, index_dir: Path, embedder=None):
        if embedder is None:
            from src.providers.pinecone_embed import PineconeEmbedder

            embedder = PineconeEmbedder()
        self.embedder = embedder
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
        # Guarded exactly like portfolio_retriever below: BM25Okapi([]) raises
        # ZeroDivisionError on an empty corpus (avgdl = num_doc / corpus_size), and this
        # branch IS empty when this instance is loading the persona index instead of the HR
        # one -- caught by actually loading the persona index locally, not by inspection.
        self.statute_retriever = (
            NumpyRetriever([self.chunks[i] for i in statute_mask], vectors[statute_mask], embedder)
            if statute_mask
            else None
        )
        # The full retriever exists so recall@k is measurable across BOTH documents --
        # otherwise Retrieval Accuracy is measured over 97% of the corpus while the
        # document the business scenario is about stays invisible to the metric. Also
        # guarded: an empty chunks.jsonl would hit the same BM25 division by zero, though
        # that case is already caught earlier by _assert_boot_invariant's shape check.
        self.full_retriever = NumpyRetriever(self.chunks, vectors, embedder) if self.chunks else None

        # PERSONA CORPUS -- same asymmetric-pin argument, applied a second time: the resume
        # is small enough to pin in full (see manifest.py), so its silence is provable the
        # same way the handbook's is. This Corpus instance is loaded from ONE index dir at a
        # time (see main.py's lifespan -- one for the HR index, one for the persona index),
        # so exactly one of {self.handbook, self.resume} is ever non-empty; the other stays
        # an empty list rather than raising, which is what lets prompt_floor_tokens and
        # answer() branch on "which pinned set is populated" instead of needing a separate
        # corpus-kind flag threaded through the constructor.
        self.resume = [c for c in self.chunks if c.doc_kind == "resume"]
        portfolio_mask = [i for i, c in enumerate(self.chunks) if c.doc_kind == "portfolio"]
        self.portfolio_retriever = (
            NumpyRetriever([self.chunks[i] for i in portfolio_mask], vectors[portfolio_mask], embedder)
            if portfolio_mask
            else None
        )

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
    def prompt_floor_tokens(self) -> int:
        """Every token a request costs BEFORE the question itself: system prompt + the pinned
        handbook + an allowance for the retrieved statute sections.

        This exists because the first version counted only the handbook and reserved 5,643
        tokens against a real prompt of 9,653 -- a 42% under-count. The gate believed it was
        spending 5.6k while spending 9.7k, so it let through ~1.7x its own budget and 429'd
        anyway. **A budget that mis-measures the thing it is budgeting is not a budget**, and
        this is the third time this project metered the wrong quantity (requests instead of
        tokens; retries outside the gate; now an incomplete prompt).

        Measured at boot from the real artifacts rather than guessed, and the retrieval
        allowance is rounded UP: over-reserving costs a little throughput, under-reserving
        costs a 429 the user sees.
        """
        if not hasattr(self, "_floor"):
            from src.api.rategate import estimate_tokens
            from src.api.service import load_prompt

            retrieval_allowance = 4000  # 8 whole sections measured at ~2.7k; rounded up
            if self.resume:
                # Persona corpus. Re-measured, not assumed: the merged resume is larger than
                # the 3,081-token handbook it replaces (see docs/AI_ASSISTANT_PLAN.md's
                # token-floor warning), so this branch cannot just reuse the handbook number.
                system = estimate_tokens(load_prompt("persona"))
                pinned = estimate_tokens("".join(c.text for c in self.resume))
            else:
                system = estimate_tokens(load_prompt("synthesis"))
                pinned = estimate_tokens("".join(c.text for c in self.handbook))
            self._floor = system + pinned + retrieval_allowance
        return self._floor

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


def build_persona_block(resume: list[Chunk], portfolio: list[Chunk]) -> str:
    """Mirrors build_context_block's shape: pinned resume in full, retrieved portfolio after.

    `portfolio` here already includes any page-pinned chunks the caller merged in (see
    answer()'s page-context handling) -- this function does not know or care whether a
    portfolio chunk was pinned-by-page or retrieved-by-search, since that distinction only
    matters for *which* chunks get selected, not for how they render.
    """

    def render(chunk: Chunk) -> str:
        head = f"[[chunk:{chunk.chunk_id}]] {chunk.doc_title}"
        if chunk.section_title:
            head += f" — {chunk.section_title}"
        return f"{head}\n{chunk.text}"

    return (
        "# RESUME (complete — every section of it is here; an absent skill, employer, or "
        "qualification means Reshad does not claim it)\n\n"
        + "\n\n".join(render(c) for c in resume)
        + "\n\n# PORTFOLIO (project docs, publications, and site content — retrieved passages)\n\n"
        + "\n\n".join(render(c) for c in portfolio)
    )


def _page_context_block(page: PageContext | None) -> str:
    """The visitor's current page, so 'this'/'here'/'it' in the question has an antecedent.

    Rendered as its own labelled block (same pattern as _history_block) rather than a
    template variable inside persona.md, because load_prompt() serves plain, unparsed text
    -- there is no templating engine in this codebase to fill a {{page_title}} placeholder,
    and adding one for a single call site would be more machinery than the problem needs.
    """
    if page is None or page.kind in ("index", "home"):
        return ""
    return (
        f"\n\n# CURRENTLY VIEWING\nThe visitor is on: {page.title or page.slug} ({page.kind}). "
        "Its full content is pinned above under PORTFOLIO. Resolve 'this'/'here'/'it' to this "
        "page, but answer beyond it whenever the question is broader.\n"
    )


def build_uploaded_block(chunks: list[Chunk]) -> str:
    def render(chunk: Chunk) -> str:
        return (
            f"[[chunk:{chunk.chunk_id}]] {chunk.doc_title} (page {chunk.printed_page})\n{chunk.text}"
        )

    return "# UPLOADED DOCUMENTS (retrieved passages)\n\n" + "\n\n".join(render(c) for c in chunks)


def _history_block(history: list[Turn]) -> str:
    """Prior turns, supplied by the client on every request.

    Stateless by design: a server-side session store would die with the container on a free
    tier that sleeps and restarts, and a 262,144-token window makes resending a few turns
    free. The trade is that the client can lie about the history -- which does not matter
    here, because every CLAIM is still verified against retrieved source text regardless of
    what the conversation says.
    """
    if not history:
        return ""
    turns = "\n\n".join(f"Q: {t.question}\nA: {t.answer}" for t in history[-5:])
    return (
        "\n\n# EARLIER IN THIS CONVERSATION (context only -- never cite this, cite the "
        f"documents)\n\n{turns}\n"
    )


# PERSONA CORPUS ONLY: a code-level backstop, not a style preference. persona.md's own
# "Scope" section already tells the model to decline off-topic/instruction-override
# requests -- but a prompt is not a security boundary, and the widget is public on the open
# internet where every answered question spends Reshad's own Mistral quota (see
# docs/AI_ASSISTANT_PLAN.md sec.9: "Public endpoint = real traffic"). Caught live: asked
# "write me a two-sum function", the model happily wrote Python, because the question also
# cited a real skill from the resume ("Python") -- verification.py only checks CITED claims,
# never the uncited prose padded around them, so an off-topic request wrapped around one
# legitimate citation sails through untouched. This pattern matches the clearest, lowest-
# false-positive category of abuse -- prompt-injection/role-override attempts -- and short-
# circuits BEFORE any embedding search or Mistral call, so it costs nothing, unlike the
# prompt-only defense.
_INJECTION_RE = re.compile(
    r"ignore\s+(all|the|your|any|above|previous|prior)\b.{0,20}\binstructions?\b"
    r"|disregard\s+(the|all|your|above|previous)\b.{0,20}\b(instructions?|prompt)\b"
    r"|you\s+are\s+now\b"
    r"|act\s+as\s+(a|an|if)\b"
    r"|pretend\s+(you('re| are)|to\s+be)\b"
    r"|system\s+prompt\b"
    r"|\bjailbreak\b",
    re.I,
)

_OFF_TOPIC_DECLINE = (
    "I'm just here to answer questions about Reshad's background and work — I can't help "
    "with that. Want to know what he's built instead?"
)


def _looks_like_injection(question: str) -> bool:
    return bool(_INJECTION_RE.search(question))


def answer(
    question: str,
    corpus: Corpus,
    generator: Generator,
    top_k: int = DEFAULT_TOP_K,
    section_no: int | None = None,
    history: list[Turn] | None = None,
    kb_retriever: object | None = None,
    page: PageContext | None = None,
) -> AskResponse:
    started = time.perf_counter()
    request_id = str(uuid.uuid4())[:8]
    history = history or []
    page_block = ""

    if kb_retriever is None and corpus.resume and _looks_like_injection(question):
        return AskResponse(
            answer=_OFF_TOPIC_DECLINE,
            citations=[],
            insufficient_information=True,
            route="NO_ANSWER",
            latency_ms=int((time.perf_counter() - started) * 1000),
            request_id=request_id,
            index_version=corpus.meta["index_version"],
        )

    if kb_retriever is not None:
        # An UPLOADED knowledge base. Nothing is pinned -- an arbitrary document may be far
        # larger than the 3,081-token handbook, so it must be retrieved over. That means
        # absence here is BOUNDED, not provable: "I didn't find it in what I retrieved"
        # rather than "it isn't there". The asymmetry is real and the README says so.
        hits = kb_retriever.search(question, k=top_k)  # type: ignore[attr-defined]
        available = [c for c, _ in hits]
        context = build_uploaded_block(available)
        prompt = load_prompt("uploaded")
    elif corpus.resume:
        # PERSONA corpus (reshadulkarim.me). Same asymmetric-pin argument as the handbook,
        # applied a third time (see docs/AI_ASSISTANT_PLAN.md sec.1 and sec.5.1): the resume
        # is pinned whole, and the portfolio is retrieved -- except the one portfolio
        # document the visitor is CURRENTLY looking at, which is pinned too rather than left
        # to a possibly-missed top-k, because a single project's chunks are only a few
        # hundred tokens and pinning them is nearly free.
        portfolio = (
            assemble_context(corpus.portfolio_retriever.search(question, k=top_k))
            if corpus.portfolio_retriever is not None
            else []
        )
        pinned_extra: list[Chunk] = []
        if page is not None and page.slug:
            pinned_extra = [c for c in corpus.chunks if c.doc_id == page.slug and c not in portfolio]
        portfolio = pinned_extra + portfolio
        available = corpus.resume + portfolio
        context = build_persona_block(corpus.resume, portfolio)
        page_block = _page_context_block(page)
        prompt = load_prompt("persona")
    else:
        if section_no is not None:
            statute = corpus.statute_retriever.get_section(section_no)
        else:
            statute = assemble_context(corpus.statute_retriever.search(question, k=top_k))
        # ASYMMETRIC: the handbook is pinned in full, so its silence is PROVABLE.
        available = corpus.handbook + statute
        context = build_context_block(corpus.handbook, statute)
        prompt = load_prompt("synthesis")

    raw = generator.generate(
        prompt, f"{context}{page_block}{_history_block(history)}\n\n# QUESTION\n{question}"
    )

    # The model's output is not trusted. Every quoted span is checked against the chunk it
    # claims to come from; unverifiable claims are stripped; if nothing survives,
    # insufficient_information is set BY CODE rather than chosen by the model.
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
