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
    """The intended shape: the FACT is the model's prose, the marker is its EVIDENCE.

    (An earlier version of this test put the fact inside the marker and asserted the quote
    was inlined. That was testing a bug: it printed the quote twice, once in the prose and
    once in Sources. The prompt now tells the model to state the claim and cite it.)
    """
    raw = "You are entitled to 10 days [[chunk:statute:s115|casual leave with full wages for ten days]]."
    text, citations, insufficient = verify_answer(raw, [CHUNK])

    assert not insufficient
    assert "10 days" in text                       # the model's own words survive
    assert "[[chunk:" not in text                  # the marker is consumed, never shown
    assert "full wages for ten days" not in text   # the quote lives in Sources, not the prose
    assert len(citations) == 1
    assert citations[0].section_no == 115
    assert citations[0].printed_page == 59         # assertable BECAUSE it is a typed object


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


def test_the_verified_quote_is_not_inlined_into_the_prose():
    """Observed live: the answer read
         Chairperson: Sultana Hashem
         Sultana Hashem Chairperson
    because a verified marker was replaced with its own quote text, printing it twice. The
    verbatim text belongs in Sources exactly once, sliced from the chunk by code."""
    raw = "You get 10 days [[chunk:statute:s115|casual leave with full wages for ten days]]."
    text, citations, insufficient = verify_answer(raw, [CHUNK])

    assert not insufficient
    assert len(citations) == 1
    assert citations[0].snippet == "casual leave with full wages for ten days"
    assert "casual leave with full wages" not in text, "the quote must not be inlined"
    assert text.startswith("You get 10 days")


def test_a_claim_whose_evidence_failed_is_dropped_WHOLE():
    """The hole this closes: stripping a marker removes the CITATION, not the SENTENCE.

    Live, the model answered the Chairperson (verified) and the head-office address (its
    quote failed). Deleting only the failed marker left the address asserted with nothing
    behind it, carried past the gate by the Chairperson's citation. An unsupported fact
    rendered as though sourced is exactly what this system exists to prevent.
    """
    raw = (
        "Chairperson: Sultana Hashem [[chunk:statute:s115|Every worker shall be entitled]]\n"
        "Head office: Shanta Western Tower [[chunk:statute:s115|the head office is in Dhaka]]"
    )
    text, citations, insufficient = verify_answer(raw, [CHUNK])

    assert not insufficient                       # the first claim verified
    assert "Sultana Hashem" in text               # ...so its line survives
    assert "Shanta Western Tower" not in text, (
        "a line whose only evidence failed must be dropped whole, not left uncited"
    )
    assert len(citations) == 1


def test_prose_and_headings_without_markers_survive():
    """Dropping unsupported CLAIMS must not shred the answer's structure."""
    raw = "### Key findings\n\nHere is what I found:\n\nYou get 10 days [[chunk:statute:s115|for ten days]]."
    text, _, insufficient = verify_answer(raw, [CHUNK])
    assert not insufficient
    assert "### Key findings" in text
    assert "Here is what I found" in text


def test_ocr_typos_in_the_SOURCE_do_not_refuse_a_correct_quote():
    """MEASURED failure. s.118 of the Act reads "in a calender year" -- the typo is the
    document's, faithfully OCR'd. The model quoted "calendar year", silently correcting it,
    and exact matching refused a correct answer about festival holidays. On a corpus that is
    97% OCR'd this is systemic: byte-exactness punishes the model for the scan's errors."""
    c = Chunk(**{**CHUNK.model_dump(),
                 "text": "118. Festival holidays : Every worker shall be allowed in a calender year "
                         "eleven days of paid festival holidays."})
    assert verify_span("allowed in a calendar year eleven days of paid festival holidays", c)


def test_the_snippet_shows_the_SOURCES_spelling_not_the_models():
    """The reviewer must see what the PDF actually says -- typo included -- because that is
    what they will find when they check it."""
    c = Chunk(**{**CHUNK.model_dump(), "text": "allowed in a calender year eleven days"})
    _, citations, _ = verify_answer("Eleven days [[chunk:statute:s115|in a calendar year eleven days]].", [c])
    assert citations and "calender" in citations[0].snippet, "snippet must be sliced from source"


def test_fuzziness_can_never_change_a_NUMBER():
    """The whole tolerance is worthless if it lets a quantity drift -- these answers turn on
    quantities. One char of slack on long words; short tokens and anything with a digit are
    exact-only."""
    c = Chunk(**{**CHUNK.model_dump(), "text": "entitled to ten days of casual leave in 14 months"})
    assert verify_span("entitled to ten days", c)
    assert not verify_span("entitled to two days", c), "ten -> two must NOT match"
    assert not verify_span("entitled to tan days", c), "short tokens are exact-only"
    assert not verify_span("casual leave in 4 months", c), "digits must never fuzz"


def test_eleven_cannot_become_seven():
    c = Chunk(**{**CHUNK.model_dump(), "text": "eleven days of paid festival holidays"})
    assert verify_span("eleven days of paid festival", c)
    assert not verify_span("seven days of paid festival", c)


def test_a_real_quote_cited_to_the_WRONG_chunk_is_recovered():
    """THE false-refusal fix, and the guarantee is untouched.

    Measured: the model quotes text that IS in the retrieved context but attributes it to the
    wrong chunk id. Asked who the Chairperson was, it quoted the handbook correctly and cited
    the Employee Record folio. The QUOTE was true; the POINTER was wrong. v1 stripped it, and
    a correct answer became "not found" -- ~36% of answerable questions.

    Which of eight retrieved chunks a fact sits in is bookkeeping the model should not be
    trusted with; code can determine it exactly. The invariant that matters -- "this text
    exists in what we retrieved" -- is unchanged.
    """
    other = Chunk(**{**CHUNK.model_dump(), "chunk_id": "statute:s999", "section_no": 999,
                     "section_title": "Something else", "text": "Entirely unrelated text."})
    raw = "You get 10 days [[chunk:statute:s999|casual leave with full wages for ten days]]."
    text, citations, insufficient = verify_answer(raw, [other, CHUNK])

    assert not insufficient, "a real quote must not be refused for a wrong pointer"
    assert len(citations) == 1
    # The citation is built from where the text ACTUALLY is -- so the page is real, not the
    # model's guess.
    assert citations[0].section_no == 115
    assert citations[0].printed_page == 59


def test_recovery_does_NOT_rescue_an_invented_quote():
    """The loosening must stop exactly at 'wrong drawer, right fact'. A fabricated span
    matches nothing in ANY retrieved chunk and is still stripped."""
    other = Chunk(**{**CHUNK.model_dump(), "chunk_id": "statute:s999", "text": "Unrelated."})
    raw = "You get [[chunk:statute:s999|forty days of casual leave]] a year."
    _, citations, insufficient = verify_answer(raw, [other, CHUNK])
    assert insufficient is True
    assert citations == []


def test_orphaned_headings_are_dropped_with_their_content():
    """The REAL failure, from the CSE-350 upload test. The answer came back as:

        The robot uses the following sensors and components:
        **Sensors:**
        **Components:**

    Every bullet was dropped for a failed quote and every heading was kept, leaving a
    skeleton. The refusal was correct; it just looked broken instead of honest, which costs
    the same trust as being wrong.

    (An earlier version of this test appended unrelated trailing prose and expected
    **Components:** to be dropped anyway. That expectation was wrong: by markdown semantics a
    heading's section runs to the NEXT heading, so the trailing line genuinely was its
    content. The code was right and the test was badly written -- this is the shape that
    actually occurred.)
    """
    raw = (
        "The robot uses the following sensors and components:\n"
        "**Sensors:**\n"
        "- an IR sensor [[chunk:statute:s115|this quote is fabricated entirely]]\n"
        "**Components:**\n"
        "- a motor [[chunk:statute:s115|also completely made up]]\n"
    )
    text, citations, insufficient = verify_answer(raw, [CHUNK])

    assert insufficient is True, "every claim failed, so this must be a refusal"
    assert citations == []
    assert "**Sensors:**" not in text, "a heading whose only content was dropped must go too"
    assert "**Components:**" not in text


def test_a_heading_keeps_its_surviving_content():
    """The cut must not be greedy: a heading with ANY verified line under it stays."""
    raw = (
        "**Leave:**\n"
        "- casual is ten days [[chunk:statute:s115|casual leave with full wages for ten days]]\n"
        "- sick is fabricated [[chunk:statute:s115|sick leave for ninety days]]\n"
    )
    text, citations, insufficient = verify_answer(raw, [CHUNK])
    assert not insufficient
    assert "**Leave:**" in text, "one surviving claim keeps the heading"
    assert "casual is ten days" in text
    assert "sick is fabricated" not in text, "the unverified line still goes"
    assert len(citations) == 1
