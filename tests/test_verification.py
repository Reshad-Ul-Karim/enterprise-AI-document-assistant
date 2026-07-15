"""FR#5: refusal is forced by code, not chosen by the model.

The spec's highest-signal requirement: "If the answer cannot be found, clearly state that
sufficient information is unavailable instead of generating unsupported information."

Most implementations satisfy this with a prompt line and a similarity threshold, and never
test it. On this corpus a threshold is measurably WORSE than nothing -- see
test_similarity_threshold_is_an_antisignal in tests/test_retrieval_quality.py.
"""

from __future__ import annotations

from src.core.models import Chunk
from src.core.verification import derive_route, verify_answer, verify_span

CHUNK = Chunk(
    chunk_id="statute:s115",
    doc_id="statute",
    doc_title="Bangladesh Labour Act 2006",
    doc_kind="statute",
    text="115. Casual leave : Every worker shall be entitled to casual leave with full wages "
    "for ten days in a calendar year.",
    section_no=115,
    section_title="Casual leave",
    zero_based_pdf_index=75,
    printed_page=59,
    source_modality="ocr",
)


def test_verified_claim_survives_and_produces_a_typed_citation():
    raw = "You get [[chunk:statute:s115|casual leave with full wages for ten days]] per year."
    text, citations, insufficient = verify_answer(raw, [CHUNK])

    assert not insufficient
    assert "ten days" in text
    assert "[[chunk:" not in text  # the marker is consumed, never shown to the user
    assert len(citations) == 1
    assert citations[0].section_no == 115
    assert citations[0].printed_page == 59  # assertable BECAUSE it is a typed object


def test_fabricated_quote_is_stripped_and_forces_abstention():
    """A quote that is not in the source does not become a wrong answer. It becomes NO answer."""
    raw = "You get [[chunk:statute:s115|casual leave for twenty-five days]] per year."
    text, citations, insufficient = verify_answer(raw, [CHUNK])

    assert insufficient is True
    assert citations == []
    assert "twenty-five" not in text


def test_citation_to_a_chunk_that_was_never_retrieved_is_stripped():
    raw = "The Act says [[chunk:statute:s999|anything at all]]."
    _, citations, insufficient = verify_answer(raw, [CHUNK])
    assert insufficient is True
    assert citations == []


def test_span_verification_tolerates_ocr_line_wrapping():
    """The statute is OCR'd from a scan: a true quote rarely matches byte-for-byte."""
    wrapped = Chunk(**{**CHUNK.model_dump(), "text": "Every worker shall be entitled\nto casual   leave"})
    assert verify_span("entitled to casual leave", wrapped)


def test_snippet_is_sliced_from_the_source_not_echoed_from_the_model():
    raw = "[[chunk:statute:s115|EVERY   WORKER shall be ENTITLED to casual leave]]"
    _, citations, _ = verify_answer(raw, [CHUNK])
    # The model shouted; the snippet comes back in the source's own casing because code cut
    # it out of the chunk rather than trusting the model's rendering.
    assert citations[0].snippet == "Every worker shall be entitled to casual leave"


def test_answer_with_no_citations_at_all_is_insufficient():
    text, citations, insufficient = verify_answer("Employees get about 20 days off.", [CHUNK])
    assert insufficient is True
    assert citations == []


def test_route_is_derived_in_code_not_by_a_model():
    """v1 spent an LLM call on this label. On a free tier requests are the scarce resource,
    so the router was deleted and the label derived for free."""
    _, citations, _ = verify_answer(
        "[[chunk:statute:s115|Every worker shall be entitled to casual leave]]", [CHUNK]
    )
    assert derive_route(citations) == "STATUTE_ONLY"
    assert derive_route([]) == "NO_ANSWER"


def test_model_can_declare_insufficiency_while_keeping_related_sources():
    """"The docs don't cover X, but here's related material" is a REFUSAL, not an answer.

    Without this, one verified related citation would flip a correct refusal into a
    confident-looking answer -- which is how the 'parental leave' demo silently broke.
    """
    raw = (
        "The documents do not address parental leave. [[insufficient]] The Act covers "
        "[[chunk:statute:s115|casual leave with full wages]] but not parental leave."
    )
    text, citations, insufficient = verify_answer(raw, [CHUNK])

    assert insufficient is True          # refusal wins...
    assert len(citations) == 1           # ...and related sources still render
    assert "[[insufficient]]" not in text


def test_the_model_cannot_talk_its_way_out_of_a_code_forced_refusal():
    """The asymmetry that makes FR#5 an invariant: the model may REQUEST a refusal, and
    code may FORCE one, but the model can never overrule code into answering."""
    raw = "Definitely 40 days [[chunk:statute:s115|workers get forty days of casual leave]]"
    _, citations, insufficient = verify_answer(raw, [CHUNK])
    assert insufficient is True
    assert citations == []


def test_stitched_noncontiguous_quote_is_rejected():
    """The real failure that caused a false refusal on 'who is the Chairperson?'.

    The model spliced a letter's opening to its sign-off -- both fragments real, the
    contiguous span fabricated. Rejecting it is correct; the prompt now forbids stitching.
    """
    assert verify_span("Every worker shall be entitled", CHUNK)          # contiguous: real
    assert not verify_span("Every worker for ten days in a calendar", CHUNK)  # stitched: fake


def test_quotes_wrapped_in_quotation_marks_still_verify():
    """The model is QUOTING, so it writes quotation marks -- [[chunk:x|"the text."]].

    Those characters are punctuation the model put AROUND the span, not part of it. Matching
    them literally made a correct answer about overtime pay get refused in production: the
    span started with a `"` that does not exist in the source.
    """
    assert verify_span('"Every worker shall be entitled to casual leave"', CHUNK)
    assert verify_span("“Every worker shall be entitled”", CHUNK)   # curly quotes too
    assert verify_span("Every worker shall be entitled", CHUNK)     # and bare


def test_an_apostrophe_inside_the_span_is_not_stripped():
    """Only the OUTSIDE is punctuation. An apostrophe inside a word is the text."""
    c = Chunk(**{**CHUNK.model_dump(), "text": "the worker's right to leave"})
    assert verify_span("worker's right", c)


def test_an_ellipsis_quote_is_still_rejected():
    """Tolerating wrapping punctuation must NOT become tolerating elision.

    '"the employer... may... fix time rates"' is the model splicing distant fragments into
    one quote -- the exact fabrication the span check exists to catch. Observed in
    production alongside the quotation-mark bug; this one SHOULD fail.
    """
    assert not verify_span('"Every worker... casual leave"', CHUNK)
