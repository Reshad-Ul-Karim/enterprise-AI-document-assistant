"""Regressions against the real persona corpus (reshadulkarim.me). Same philosophy as
test_corpus_regression.py: every one of these guards a SILENT failure -- plausible wrong
output, no exception raised. Two of these (HTML leakage, glued skill-table labels) are
regressions for real bugs found by actually running the pipeline against a live question,
not by reading the code; see build_persona_index.py's _strip_html and
_fix_skill_table_spacing docstrings for the incidents.

Skipped when the persona index has not been built (`python -m src.ingest.build_persona_index`),
so a reviewer who has only cloned the repo still gets a green suite.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
INDEX = REPO / "index_persona"

pytestmark = pytest.mark.skipif(
    not (INDEX / "chunks.jsonl").exists(),
    reason="persona index not built; run python -m src.ingest.build_persona_index",
)


@pytest.fixture(scope="module")
def chunks():
    from src.core.models import Chunk

    return [Chunk(**json.loads(line)) for line in (INDEX / "chunks.jsonl").open()]


def test_resume_covers_education_skills_and_experience(chunks):
    """The build gate, as a test -- same reasoning as test_required_sections_are_all_present:
    an empty or truncated pinned resume is the worst failure here, since the assistant would
    answer everything with 'he doesn't list that.'"""
    resume = [c for c in chunks if c.doc_kind == "resume"]
    assert resume, "resume produced no chunks"
    titles = {(c.section_title or "").upper() for c in resume}
    assert {"EDUCATION", "TECHNICAL SKILLS", "WORK EXPERIENCE"} <= titles


def test_no_chunk_id_collides_across_the_whole_corpus(chunks):
    """chunk_markdown() disambiguates same-slug headings with a heading index specifically
    because this collided in an early build (two headings slugifying to the same string
    would silently overwrite each other in verification.py's `by_id` lookup)."""
    ids = [c.chunk_id for c in chunks]
    assert len(ids) == len(set(ids))


def test_no_raw_html_tags_leak_into_pinned_or_retrieved_text(chunks):
    """data/projects.json and data/publications.json embed presentation markup
    ('<strong>planner/router</strong>') for the SITE's own rendering. Measured leaking into
    an early build's chunks and into the model's citations verbatim -- stripped by
    build_persona_index.py's _strip_html, guarded here so it cannot silently return."""
    tag_re = re.compile(r"<(strong|em|b|i|span|div|a|br)\b", re.I)
    offenders = [c.chunk_id for c in chunks if tag_re.search(c.text)]
    assert not offenders, f"HTML tags leaked into: {offenders[:5]}"


def test_skill_table_labels_are_not_glued_to_their_first_value(chunks):
    """Regression for the bug that force-refused 'what programming languages does he know?'
    -- pypdf's default extraction ran 'Languages' straight into 'Python' with no space,
    making the model's correct, verbatim quote unverifiable against a source where the two
    words were one token. See build_persona_index.py's _fix_skill_table_spacing."""
    glued_re = re.compile(
        r"(Languages|Generative AI & LLMs|Agentic AI & NLP|ML & Computer Vision|"
        r"Deep Learning|MLOps & Deployment|Backend & Tools|Hardware & Robotics)[A-Za-z]"
    )
    resume = [c for c in chunks if c.doc_kind == "resume"]
    offenders = [c.chunk_id for c in resume if glued_re.search(c.text)]
    assert not offenders, f"glued skill-table label(s) in: {offenders}"


def test_known_project_slugs_are_present_as_their_own_doc_ids(chunks):
    """Page-context pinning (see service.py's answer()) matches page.slug against
    Chunk.doc_id directly -- if a project's chunks were ever grouped under one shared
    'projects' doc_id instead of the project's own slug, pinning-by-page would silently pin
    nothing instead of raising."""
    doc_ids = {c.doc_id for c in chunks if c.doc_kind == "portfolio"}
    assert {"lumenaa", "camdet", "weheal"} <= doc_ids


def test_paper_chunks_use_real_page_numbers_not_a_fake_page_one(chunks):
    """Papers get TWO kinds of chunk under the same doc_id: chunk_markdown() metadata
    (venue/contribution/citation, WITH a section_title, printed_page fixed at 1) from
    build_publication_metadata_chunks(), and chunk_paper_pdf() full-text pages (no
    section_title, real varying printed_page) from build_paper_chunks() -- deliberately
    sharing a doc_id so both pin together on that paper's page (see
    build_publication_metadata_chunks's docstring). This checks the PAGE chunks
    specifically, identified by having no section_title."""
    paper_pages = [
        c for c in chunks if c.doc_id == "stroke-xai-ieee-access" and c.section_title is None
    ]
    assert paper_pages, "IEEE Access paper produced no full-text page chunks"
    assert max(c.printed_page for c in paper_pages) > 1


def test_index_meta_matches_the_runtime_embedder(chunks):
    from src.core.embeddings import EMBED_DIM, EMBED_MODEL_ID

    meta = json.loads((INDEX / "index_meta.json").read_text())
    assert meta["embed_model_id"] == EMBED_MODEL_ID
    assert meta["embed_dim"] == EMBED_DIM
    assert meta["chunk_count"] == len(chunks)
