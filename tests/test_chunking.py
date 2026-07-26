"""chunk_markdown() and chunk_paper_pdf() -- the two persona-corpus chunkers.

chunk_statute()/chunk_handbook() already have implicit coverage via test_corpus_regression's
real-index assertions; these two are new and have no committed index to regress against in a
fresh clone (index_persona/ is a local build artifact, same as index/), so they get direct
unit tests instead.
"""

from __future__ import annotations

from src.core.chunking import chunk_markdown, chunk_paper_pdf


def test_splits_on_each_heading_and_carries_it_as_section_title():
    text = (
        "## Overview\nFirst paragraph.\n\n"
        "## Approach\nSecond paragraph.\n"
    )
    chunks = chunk_markdown(text, doc_id="lumenaa", doc_title="LUMENAA", kind="portfolio")
    assert [c.section_title for c in chunks] == ["Overview", "Approach"]
    assert chunks[0].text == "First paragraph."
    assert chunks[1].text == "Second paragraph."


def test_preamble_before_the_first_heading_is_dropped():
    """This is deliberate, not an oversight -- see build_persona_index.py's
    _mark_resume_headings docstring: the resume's contact info (phone, email) sits before
    its first '## OBJECTIVE' heading, and a chatbot should not be able to quote a phone
    number back at a visitor just because it happened to share a PDF page with a heading."""
    text = "Reshad Ul Karim\n+8801795580506\n\n## OBJECTIVE\nAI/ML engineer.\n"
    chunks = chunk_markdown(text, doc_id="resume", doc_title="Resume", kind="resume")
    assert len(chunks) == 1
    assert "8801795580506" not in chunks[0].text
    assert chunks[0].section_title == "OBJECTIVE"


def test_markdown_chunks_have_no_real_pagination():
    """zero_based_pdf_index/printed_page are fixed at 0/1 -- Citation.render()'s persona
    branch prefers section_title over page number specifically so this never surfaces as a
    fake 'page 1' in the UI (see models.py)."""
    chunks = chunk_markdown("## X\nbody text here.\n", doc_id="d", doc_title="D", kind="portfolio")
    assert chunks[0].zero_based_pdf_index == 0
    assert chunks[0].printed_page == 1


def test_long_section_is_sub_split_but_keeps_its_heading():
    body = "word " * 500  # well over SUBSPLIT_WINDOW
    chunks = chunk_markdown(f"## Long Section\n{body}", doc_id="d", doc_title="D", kind="portfolio")
    assert len(chunks) > 1
    assert all(c.section_title == "Long Section" for c in chunks)
    ids = [c.chunk_id for c in chunks]
    assert len(ids) == len(set(ids)), "sub-split windows must still get distinct chunk_ids"


def test_chunk_ids_do_not_collide_across_two_headings_with_the_same_slug():
    text = "## Overview\nA.\n\n## overview\nB.\n"  # same slug, different case
    chunks = chunk_markdown(text, doc_id="d", doc_title="D", kind="portfolio")
    ids = [c.chunk_id for c in chunks]
    assert len(ids) == len(set(ids))


def test_paper_pdf_chunker_uses_real_page_numbers_not_headings():
    pages = ["Page one text.", "Page two text, quite a bit longer than the first one here."]
    chunks = chunk_paper_pdf(pages, doc_id="stroke-xai-ieee-access", doc_title="IEEE Access paper")
    assert chunks[0].zero_based_pdf_index == 0
    assert chunks[0].printed_page == 1
    assert chunks[0].section_title is None
    assert chunks[0].doc_kind == "portfolio"
    assert chunks[0].source_modality == "text"


def test_paper_pdf_chunker_skips_blank_pages():
    pages = ["Real content here.", "   \n\n  ", ""]
    chunks = chunk_paper_pdf(pages, doc_id="d", doc_title="D")
    assert len(chunks) == 1
    assert chunks[0].zero_based_pdf_index == 0
