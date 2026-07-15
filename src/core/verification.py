"""FR#5: abstention, enforced structurally in code. Zero extra LLM calls.

THE FINDING THIS IS BUILT ON -- similarity thresholding is measurably broken on this
corpus. Measured, and reproduced independently with different chunking:

    ANSWERABLE    "Who is the Chairperson?"            top-1 = 0.179
    ANSWERABLE    "How much overtime pay is required?" top-1 = 0.224
    UNANSWERABLE  "How many days of paternity leave?"  top-1 = 0.413   <-- HIGHER

The unanswerable question scores higher than two answerable ones because it collides with
the casual-leave chunk. The distributions OVERLAP AND INVERT: any threshold that refuses
paternity also refuses the Chairperson. This is not bad luck -- a good adversarial
question is PLAUSIBLE, and plausible means semantically adjacent. Retrieval score is an
ANTI-SIGNAL for abstention. (Regenerate these numbers from the committed script; do not
quote them from this docstring.)

So refusal is decided by structure, not by a score and not by asking the model nicely:

  1. Handbook silence is PROVABLE -- it is pinned in full context (3,166 tokens), so
     absence is a fact rather than an inference from a failed top-k. This falls out of the
     asymmetric retrieval design for free.
  2. Every claim must cite a retrieved chunk.
  3. Every quoted span must actually appear in the chunk it cites. Claims whose span does
     not verify are STRIPPED. If all are stripped, insufficient_information is set BY
     CODE, not chosen by the model.
  4. Statute silence is BOUNDED, not proved -- and we say so. Only top-8 of 399 chunks are
     in context, so "the Act does not address X" is "I did not find it in what I
     retrieved". The full-context oracle in evals/ is what turns that concession into a
     number. Choosing RAG re-introduces exactly the unprovability FR#5 needs; the honest
     concession is stronger than a fake guarantee.
"""

from __future__ import annotations

import re
import unicodedata

from src.core.models import Chunk, Citation

# The model emits claims tagged with the chunk they came from. Citations are then BUILT by
# code from that chunk's metadata -- the model never writes a citation string, so it
# structurally cannot fabricate a page number.
CLAIM_RE = re.compile(r"\[\[chunk:(?P<chunk_id>[^\]|]+)\|(?P<quote>[^\]]+)\]\]")

# The model's way of SAYING it cannot answer. Note the asymmetry, which is the whole design:
# the model may REQUEST a refusal, and code may FORCE one, but the model can never overrule
# code into answering. Refusal is code-forced when nothing verifies; this marker only adds
# the case where the model knows it has nothing and says so while still offering related
# material. Without it, "the documents don't cover X, but here is related material [cite]"
# would score as an ANSWER purely because the related citation verified.
INSUFFICIENT_RE = re.compile(r"\[\[insufficient\]\]", re.I)


def _canonical(text: str) -> str:
    """NFKC + whitespace collapse. OCR line-wrapping means a true quote rarely matches
    byte-for-byte; it must still match once whitespace is normalised."""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", text)).strip().lower()


def _span_pattern(quote: str) -> re.Pattern[str]:
    """A pattern matching the quote in ORIGINAL text with any whitespace between tokens.

    The statute is OCR'd from a scan, so line wrapping means a true quote almost never
    matches byte-for-byte. Matching token-wise against flexible whitespace is what lets us
    slice the real span out of the real text.
    """
    tokens = _canonical(quote).split()
    return re.compile(r"\s+".join(re.escape(t) for t in tokens), re.I)


def verify_span(quote: str, chunk: Chunk) -> bool:
    """Does the quoted span actually appear in the chunk it cites?"""
    if not _canonical(quote):
        return False
    return _span_pattern(quote).search(chunk.text) is not None


def slice_snippet(chunk: Chunk, quote: str) -> str:
    """Slice the verbatim span out of the chunk. THIS is the anti-hallucination guarantee:
    the snippet the reviewer reads is source text, not model output."""
    match = _span_pattern(quote).search(chunk.text)
    return match.group(0) if match else quote.strip()


def build_citation(chunk: Chunk, quote: str) -> Citation:
    """The snippet is SLICED FROM THE CHUNK BY CODE, never generated."""
    return Citation(
        doc_id=chunk.doc_id,
        doc_title=chunk.doc_title,
        doc_kind=chunk.doc_kind,
        section_no=chunk.section_no,
        section_title=chunk.section_title,
        printed_page=chunk.printed_page,
        pdf_page=chunk.zero_based_pdf_index,
        half=chunk.half,
        snippet=slice_snippet(chunk, quote),
        source_modality=chunk.source_modality,
        ocr_confidence=chunk.ocr_mean_conf,
    )


def verify_answer(raw: str, context: list[Chunk]) -> tuple[str, list[Citation], bool]:
    """Strip unverifiable claims; force abstention if nothing survives.

    Returns (answer_text, citations, insufficient_information).
    """
    by_id = {c.chunk_id: c for c in context}
    citations: list[Citation] = []
    stripped = 0
    total = 0

    def _replace(match: re.Match[str]) -> str:
        nonlocal stripped, total
        total += 1
        chunk = by_id.get(match.group("chunk_id"))
        quote = match.group("quote")
        if chunk is None or not verify_span(quote, chunk):
            stripped += 1
            return ""  # the claim is removed, not softened
        citation = build_citation(chunk, quote)
        if citation not in citations:
            citations.append(citation)
        return quote

    answer = CLAIM_RE.sub(_replace, raw)

    # The model declared it cannot answer. Its related citations survive as "related
    # sources" beside an honest refusal rather than masquerading as an answer.
    model_declared = bool(INSUFFICIENT_RE.search(answer))
    answer = INSUFFICIENT_RE.sub("", answer)
    answer = re.sub(r"[ \t]{2,}", " ", answer).strip()

    # Code-forced refusal: nothing the model claimed could be verified against the source.
    # This is the branch the model cannot talk its way out of.
    code_forced = (total > 0 and stripped == total) or not answer or not citations

    return answer, citations, (code_forced or model_declared)


def derive_route(citations: list[Citation]) -> str:
    """The route label, derived in CODE from which documents were actually cited.

    v1 spent an LLM call on a router to produce this. That was a COST optimisation --
    a cheap model triaging so the expensive one did less work. On a free tier dollars are
    not scarce; REQUESTS are, at roughly one per second. A router doubles requests per
    query to save retrieval that costs 8 microseconds locally, so the optimisation
    inverted and the router was deleted. The label survives, for free.
    """
    kinds = {c.doc_kind for c in citations}
    if not kinds:
        return "NO_ANSWER"
    if kinds == {"handbook"}:
        return "HANDBOOK_ONLY"
    if kinds == {"statute"}:
        return "STATUTE_ONLY"
    if {"handbook", "statute"} <= kinds:
        return "COMPARE"
    return "UPLOADED_KB"
