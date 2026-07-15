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


# Quotation marks the model wraps around its quote. It is quoting, so quoting punctuation is
# the natural thing to write -- `[[chunk:x|"the text."]]` -- but those characters are NOT part
# of the span, and matching them literally makes a true quote fail. Observed in production:
# a correct answer about overtime was refused because the span started with a `"`.
_WRAPPING_QUOTES = "\"'“”‘’«»"


def _strip_wrapping_quotes(quote: str) -> str:
    """Drop paired quote marks around the span. Only the OUTSIDE -- an apostrophe inside
    ("worker's") is part of the text and must survive."""
    text = quote.strip()
    while len(text) >= 2 and text[0] in _WRAPPING_QUOTES:
        text = text[1:].strip()
    while len(text) >= 1 and text[-1] in _WRAPPING_QUOTES:
        text = text[:-1].strip()
    return text


_WORD_RE = re.compile(r"\S+")

# Fuzzy tolerance, and the exact reason for it. MEASURED: asked for the festival-holiday
# entitlement, the model quoted
#     "Every worker shall be allowed in a calendar year eleven days of paid festival holidays"
# and the source -- an OCR of a printed statute -- says "calender year". The typo is the
# DOCUMENT'S; the model silently corrected it while quoting, which is what a careful writer
# does. Exact matching then refused a correct answer. On a corpus that is 97% OCR'd, that is
# systemic, not a one-off: byte-exactness punishes the model for the scan's errors.
#
# So one character of drift is allowed per LONG word, and short tokens must match EXACTLY.
# That is deliberately tight enough to keep the guarantee intact:
#     calender -> calendar   distance 1, len 8   ALLOWED  (an OCR/print typo)
#     eleven   -> seven      distance 3          REJECTED (a different quantity)
#     ten      -> two        len 3, exact only   REJECTED (a different quantity)
#     14       -> 4          len < 4, exact only REJECTED
# The numbers -- which is what these answers turn on -- cannot drift.
_MAX_EDITS = 1
_FUZZY_MIN_LEN = 4


def _within_one_edit(a: str, b: str) -> bool:
    """Levenshtein <= 1, short-circuited. Hand-rolled to avoid a dependency for ~15 lines."""
    if a == b:
        return True
    la, lb = len(a), len(b)
    if abs(la - lb) > _MAX_EDITS:
        return False
    i = j = edits = 0
    while i < la and j < lb:
        if a[i] == b[j]:
            i += 1
            j += 1
            continue
        edits += 1
        if edits > _MAX_EDITS:
            return False
        if la > lb:
            i += 1
        elif lb > la:
            j += 1
        else:
            i += 1
            j += 1
    return edits + (la - i) + (lb - j) <= _MAX_EDITS


def _token_matches(quote_token: str, source_token: str) -> bool:
    if quote_token == source_token:
        return True
    # Short tokens carry the numbers and the negations. They must be exact.
    if len(quote_token) < _FUZZY_MIN_LEN or len(source_token) < _FUZZY_MIN_LEN:
        return False
    if any(ch.isdigit() for ch in quote_token) or any(ch.isdigit() for ch in source_token):
        return False  # never fuzz a figure
    return _within_one_edit(quote_token, source_token)


def find_span(quote: str, text: str) -> tuple[int, int] | None:
    """Locate the quote in `text`, tolerating OCR-level noise. Returns (start, end) or None.

    Token-wise with a sliding window rather than a regex, because the tolerance is per-token
    and a regex cannot express "this word, or one character away from it".

    What is still NOT tolerated -- and must not be: an ellipsis or any reordering.
    `"the employer... may... fix"` is the model splicing distant fragments into one quote,
    which is the fabrication this check exists to catch. Forgiving the scan's typos is not
    the same as forgiving invention.
    """
    q = _canonical(_strip_wrapping_quotes(quote)).split()
    if not q:
        return None
    spans = [(m.group(0).lower().strip(".,;:()[]\"'"), m.start(), m.end())
             for m in _WORD_RE.finditer(unicodedata.normalize("NFKC", text))]
    if len(spans) < len(q):
        return None
    for i in range(len(spans) - len(q) + 1):
        if all(_token_matches(q[k], spans[i + k][0]) for k in range(len(q))):
            return spans[i][1], spans[i + len(q) - 1][2]
    return None


def verify_span(quote: str, chunk: Chunk) -> bool:
    """Does the quoted span actually appear in the chunk it cites?"""
    return find_span(quote, chunk.text) is not None


def slice_snippet(chunk: Chunk, quote: str) -> str:
    """Slice the span out of the chunk. THIS is the anti-hallucination guarantee: the snippet
    the reviewer reads is SOURCE text, not model output.

    It matters that this returns the source's version rather than the model's. When the model
    tidied "calender year" to "calendar year", the reviewer sees what the document actually
    says -- typo and all -- because that is what they would find if they opened the PDF.
    """
    found = find_span(quote, chunk.text)
    return chunk.text[found[0]:found[1]] if found else quote.strip()


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


# ONLY real headings: a markdown '#' line, or a line that is nothing but bold text
# (**Sensors:**). Deliberately NOT "any sentence ending in a colon" -- that first attempt
# matched "Here is what I found:" and deleted the genuine heading above it. A rule that
# removes real content to tidy up is worse than the untidiness.
_HEADING_RE = re.compile(r"^\s*(?:#{1,6}\s+\S|\*\*[^*\n]+\*\*\s*:?\s*$)")


def _drop_orphaned_headings(marked: list[tuple[str, bool]]) -> str:
    """Remove headings whose OWN content was dropped.

    Dropping a claim's line is right; leaving its heading behind is not. Asked what hardware
    a robot used, the answer came back as:

        The robot uses the following sensors and components:
        **Sensors:**
        **Components:**

    -- every bullet dropped for a failed quote, every heading kept. The refusal was correct;
    it just looked broken instead of honest, which costs the same trust as being wrong.

    `marked` is (line, kept) over the ORIGINAL lines, and it has to be: a first attempt
    checked the surviving lines instead, so a heading whose bullet had been dropped simply
    ADOPTED the next unrelated paragraph as its body and survived anyway. The question is not
    "is there anything after this heading" but "did anything that belonged to it survive" --
    and only the original structure knows which lines belonged to it.
    """
    keep_flags = [kept for _, kept in marked]
    for i, (line, kept) in enumerate(marked):
        if not (kept and line.strip() and _HEADING_RE.match(line)):
            continue
        owns_surviving_content = False
        for j in range(i + 1, len(marked)):
            following, following_kept = marked[j]
            if not following.strip():
                continue
            if _HEADING_RE.match(following):
                break  # the next heading: this one's section is over
            if following_kept:
                owns_surviving_content = True
                break
        if not owns_surviving_content:
            keep_flags[i] = False
    return "\n".join(line for (line, _), keep in zip(marked, keep_flags) if keep)


def _resolve(chunk_id: str, quote: str, by_id: dict[str, Chunk], context: list[Chunk]) -> Chunk | None:
    """Find the chunk this quote genuinely came from, or None.

    THE FIX FOR MOST FALSE REFUSALS -- and the guarantee is untouched.

    Measured: the model frequently quotes text that IS in the retrieved context, and
    attributes it to the WRONG chunk id. Asked who the Chairperson was, it quoted the
    handbook correctly and cited `handbook:p3:right`, which is the Employee Record folio.
    Asked about casual leave, it quoted s.115's real text against a handbook chunk. The
    QUOTE was true; the POINTER was wrong. v1 stripped the claim, and a correct answer
    became "not found" -- 36% of answerable questions, measured.

    That is the wrong thing to punish. The invariant that matters is **"this text exists in
    the source we retrieved"** -- that is what makes fabrication impossible. Which of the
    eight retrieved chunks it sits in is bookkeeping the MODEL should not be trusted with
    anyway; code can determine it exactly, and does.

    So: try the cited chunk first (the common, correct case). If the span is not there,
    search the other retrieved chunks for it. If it is found, the citation is BUILT FROM THE
    CHUNK IT WAS ACTUALLY FOUND IN -- so the page number the reviewer sees is the real one,
    not the model's guess.

    NOTHING IS LOOSENED. The span must still exist, verbatim (modulo the OCR tolerance), in a
    chunk that was actually retrieved for THIS question. An invented quote still matches
    nothing and is still stripped. We stopped requiring the model to be right about which
    drawer the fact was in -- not about whether the fact is there.
    """
    cited = by_id.get(chunk_id)
    if cited is not None and verify_span(quote, cited):
        return cited
    # The pointer was wrong. Is the QUOTE real?
    for candidate in context:
        if candidate is cited:
            continue
        if verify_span(quote, candidate):
            return candidate
    return None


def verify_answer(raw: str, context: list[Chunk]) -> tuple[str, list[Citation], bool]:
    """Strip unverifiable claims; force abstention if nothing survives.

    Returns (answer_text, citations, insufficient_information).
    """
    by_id = {c.chunk_id: c for c in context}
    citations: list[Citation] = []
    stripped = 0
    total = 0
    model_declared = bool(INSUFFICIENT_RE.search(raw))

    # LINE BY LINE, because stripping a marker removes the CITATION, not the SENTENCE.
    #
    # Observed live: the model answered "Chairperson: Sultana Hashem" with a marker that
    # verified, and "Head office: Shanta Western Tower..." with one that did not. Deleting
    # only the failed marker left the address asserted with nothing behind it -- carried past
    # the gate by a DIFFERENT claim that happened to verify. An unsupported fact rendered as
    # though it were sourced is precisely what this system exists to make impossible.
    #
    # So: a line whose markers ALL failed loses its evidence and is dropped whole. A line
    # with no markers is prose or structure (headings, connectives) and is kept. This is
    # blunt -- it can drop a line the model got right -- and that trade is deliberate:
    # completeness is worth less than the guarantee.
    marked: list[tuple[str, bool]] = []  # (rendered line, survived) over the ORIGINAL lines
    for line in INSUFFICIENT_RE.sub("", raw).split("\n"):
        markers = list(CLAIM_RE.finditer(line))
        if not markers:
            marked.append((line, True))
            continue

        line_ok = 0
        for m in markers:
            total += 1
            quote = m.group("quote")
            chunk = _resolve(m.group("chunk_id"), quote, by_id, context)
            if chunk is None:
                stripped += 1
                continue
            line_ok += 1
            citation = build_citation(chunk, quote)
            if citation not in citations:
                citations.append(citation)

        # Remove the marker; do NOT inline the quote. The verbatim text is rendered once, in
        # Sources, sliced from the chunk by code. Inlining it printed the quote twice.
        marked.append((CLAIM_RE.sub("", line), bool(line_ok)))

    answer = _drop_orphaned_headings(marked)
    answer = re.sub(r"[ \t]{2,}", " ", answer)
    answer = re.sub(r"\n{3,}", "\n\n", answer).strip()

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
