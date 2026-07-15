"""Upload surface: triage, idempotency, caps, and the honest asymmetry.

Network-free by default -- the tests that need Mistral/Pinecone are marked and skipped
unless keys are present, so a reviewer who has signed up for nothing still gets a green run.
"""

from __future__ import annotations

import importlib.util
import pathlib

import pytest

from src.api.uploads import KnowledgeBase, assess_extractability, chunk_uploaded

REPO = pathlib.Path(__file__).resolve().parents[1]
HANDBOOK = REPO / "Assets" / "Partex-Star-Group.pdf"
ACT = REPO / "Assets" / "A Handbook on the Bangladesh Labour Act 2006.pdf"

pytestmark = pytest.mark.skipif(not HANDBOOK.exists(), reason="assets not present")

# langchain_text_splitters' import ABORTS at the C++ level (`libc++abi: mutex lock failed`)
# when `transformers` is importable -- it reaches for it, which on a box that also has
# tensorflow/pyarrow deadlocks. A C++ abort is NOT catchable by try/except: it kills the
# whole process, so it takes pytest down rather than failing a test.
#
# This is NOT a defect in this code. The runtime image has no transformers; CI asserts the
# closure is clean AND proves this exact import path works there. The skip fires only on a
# dev machine that carries transformers for unrelated work -- which is how it was found.
_SPLITTER_ABORTS_HERE = importlib.util.find_spec("transformers") is not None
needs_splitter = pytest.mark.skipif(
    _SPLITTER_ABORTS_HERE,
    reason="langchain_text_splitters aborts at C++ level when transformers is importable; "
           "the runtime image has neither, and CI proves this path there",
)


def test_triage_sends_only_scanned_pdfs_to_the_ocr_api():
    """The cost model depends on this. A text-native PDF extracts locally for free and
    instantly; paying an OCR API for it would be waste. Only pages with no text layer go
    to the API."""
    pages, needs_ocr = assess_extractability(HANDBOOK.read_bytes())
    assert pages == 6 and needs_ocr is False, "the handbook is text-native"

    pages, needs_ocr = assess_extractability(ACT.read_bytes())
    assert pages == 181 and needs_ocr is True, "the Act is 100% scanned images"


@needs_splitter
def test_uploaded_chunks_carry_a_page_number_but_no_section_anchor():
    """The honest asymmetry, asserted rather than described.

    The statute gets a chunker built on its own section grammar because we know it. An
    arbitrary upload gets a generic recursive split because we don't -- so its citations
    carry a page number (FR#4) and no section number. Claiming otherwise would be inventing
    structure we never parsed.
    """
    chunks = chunk_uploaded([(1, "word " * 400), (2, "other " * 400)], "doc1", "My Doc", "kb1", "text")
    assert chunks, "expected chunks"
    assert all(c.section_no is None for c in chunks)
    assert all(c.doc_kind == "uploaded" for c in chunks)
    assert {c.printed_page for c in chunks} == {1, 2}
    # Chunked per page, so every citation has an exact page. Splitting across pages would
    # buy a little coherence and lose the page number, which the spec requires.
    for c in chunks:
        assert c.zero_based_pdf_index == c.printed_page - 1


@needs_splitter
def test_ingest_is_idempotent_on_content_hash():
    """This is what makes an ephemeral job store survivable: recovery is a re-upload, never
    a duplicate and never a corruption."""
    from src.api.uploads import Job, ingest

    kb = KnowledgeBase(kb_id="k", name="k")
    data = HANDBOOK.read_bytes()

    j1 = Job(job_id="1", kb_id="k", filename="h.pdf")
    ingest(data, "h.pdf", kb, j1)
    first = len(kb.chunks)
    assert first > 0

    j2 = Job(job_id="2", kb_id="k", filename="h.pdf")
    ingest(data, "h.pdf", kb, j2)
    assert len(kb.chunks) == first, "re-uploading the same bytes must not duplicate"
    assert j2.state == "done" and "Already ingested" in j2.progress


def test_oversized_upload_is_rejected_before_any_work():
    """The box has 512 MB and the baseline uses ~435 MB. An unbounded upload is an OOM, and
    an OOM is a dead URL for whoever was clicking the PUBLIC demo. The cap protects the demo
    from the feature."""
    from src.api.settings import settings
    from src.api.uploads import Job, PayloadTooLarge, ingest

    kb = KnowledgeBase(kb_id="k", name="k")
    huge = b"x" * (settings.max_upload_mb * 1_000_000 + 1)
    with pytest.raises(PayloadTooLarge):
        ingest(huge, "big.pdf", kb, Job(job_id="1", kb_id="k", filename="big.pdf"))


def test_create_is_atomic_and_leaves_no_half_made_notebook():
    """The bug behind two unrelated-looking reports.

    create() registered the KB and THEN built the retriever, so when the retriever raised
    (the dimension guard, correctly, on a 384-dim index vs a 1024-dim embedder) the notebook
    was left in self.kbs with no retriever. The user saw "Failed to fetch", refreshed, and it
    was THERE -- then uploading died with `KeyError: 'newdox'` from self.retrievers[kb_id].

    A partially-applied mutation is worse than a failure: the failure is visible, the partial
    state is not.
    """
    from unittest.mock import patch

    import pytest

    from src.api.kbstore import KbRegistry
    from src.core.embeddings import FakeEmbedder

    registry = KbRegistry(embedder=FakeEmbedder())

    with patch("src.api.kbstore.settings") as fake_settings:
        fake_settings.uploads_persist = True
        fake_settings.pinecone_api_key = "x"
        fake_settings.pinecone_index = "y"
        fake_settings.max_inmemory_kbs = 3
        with patch("src.api.kbstore.PineconeKbRetriever", side_effect=RuntimeError("boom")):
            with pytest.raises(RuntimeError):
                registry.create("halfmade", "Half made")

    assert "halfmade" not in registry.kbs, "a failed create must leave NO notebook behind"
    assert "halfmade" not in registry.retrievers
