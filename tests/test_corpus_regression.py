"""Regressions against the real corpus. Every one of these guards a SILENT failure.

This corpus's signature failure mode is plausible wrong output with no exception raised.
None of these bugs throw. All of them would ship.

Skipped when the index has not been built (`python -m src.ingest.build_index`), so a
reviewer who has only cloned the repo still gets a green suite.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
INDEX = REPO / "index"

pytestmark = pytest.mark.skipif(
    not (INDEX / "chunks.jsonl").exists(), reason="index not built; run python -m src.ingest.build_index"
)


@pytest.fixture(scope="module")
def chunks():
    from src.core.models import Chunk

    return [Chunk(**json.loads(line)) for line in (INDEX / "chunks.jsonl").open()]


def test_required_sections_are_all_present(chunks):
    """The build gate, as a test. s.46's title WRAPS A LINE -- a regex whose title class
    forbids newlines cannot match it, so s.46 silently merges into s.45 CARRYING S.45'S
    METADATA. You would ship a clean recall number and a fabricated citation on the one
    question the reviewer remembers."""
    from src.core.sections import REQUIRED_SECTIONS

    found = {c.section_no for c in chunks if c.section_no is not None}
    assert REQUIRED_SECTIONS <= found, f"missing: {sorted(REQUIRED_SECTIONS - found)}"


def test_s46_is_its_own_section_with_its_own_metadata(chunks):
    s46 = [c for c in chunks if c.section_no == 46]
    assert s46, "s.46 (maternity benefit) is the flagship demo and it is missing"
    assert "maternity" in s46[0].section_title.lower()
    assert s46[0].printed_page == 39


def test_handbook_is_deinterleaved(chunks):
    """Partex is a landscape 2-up spread. Naive extraction interleaves two folios into one
    chunk, line by line, with no error. Verified on the real file: naive idx 3 emits
    '6 / employee handbook / 5 / employee handbook / Sales Office...' -- two folios, out of
    order. The Leave Policy and the Confidentiality Policy must never share a chunk."""
    handbook = [c for c in chunks if c.doc_kind == "handbook"]
    assert handbook, "no handbook chunks"
    for chunk in handbook:
        text = chunk.text.lower()
        assert not ("leave" in text and "confidential" in text and "code of conduct" in text), (
            f"{chunk.chunk_id} looks interleaved: multiple unrelated policies in one chunk"
        )
    # Every chunk is one half of one spread, and folios are 1..10 with no cover.
    assert {c.half for c in handbook} == {"left", "right"}
    assert min(c.printed_page for c in handbook) >= 1
    assert max(c.printed_page for c in handbook) <= 10


def test_the_compliance_gaps_are_real(chunks):
    """The differentiator rests on these being facts, not narrative. If the handbook ever
    turns out to mention maternity, the flagship demo is wrong and must be retired."""
    handbook_text = " ".join(c.text.lower() for c in chunks if c.doc_kind == "handbook")
    for absent in ("maternity", "overtime", "paternity"):
        assert absent not in handbook_text, f"handbook mentions {absent!r}; the gap claim is dead"
    # ...and the handbook does claim compliance, which is what makes the gap interesting.
    assert "compliance" in handbook_text


def test_statute_pages_are_never_front_matter(chunks):
    """A statute chunk whose printed_page is <= 0 means the offset is wrong."""
    for chunk in chunks:
        if chunk.doc_kind == "statute":
            assert chunk.printed_page >= 1, f"{chunk.chunk_id} -> printed p.{chunk.printed_page}"


def test_index_meta_matches_the_runtime_embedder(chunks):
    """Query and passage vectors must come from the same model or the results are silently
    incomparable -- wrong in the way that never throws."""
    from src.core.embeddings import EMBED_DIM, EMBED_MODEL_ID

    meta = json.loads((INDEX / "index_meta.json").read_text())
    assert meta["embed_model_id"] == EMBED_MODEL_ID
    assert meta["embed_dim"] == EMBED_DIM
    assert meta["chunk_count"] == len(chunks)
