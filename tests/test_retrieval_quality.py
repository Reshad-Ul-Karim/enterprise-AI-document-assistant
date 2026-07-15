"""Retrieval behaviour, and the measurement that shaped the abstention design."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[1]
INDEX = REPO / "index"

pytestmark = pytest.mark.skipif(
    not (INDEX / "chunks.jsonl").exists(), reason="index not built; run python -m src.ingest.build_index"
)


@pytest.fixture(scope="module")
def retriever():
    from src.core.models import Chunk
    from src.core.retrieval import NumpyRetriever

    chunks = [Chunk(**json.loads(line)) for line in (INDEX / "chunks.jsonl").open()]
    vectors = np.load(INDEX / "index.npz")["vectors"]
    return NumpyRetriever(chunks, vectors)


@pytest.mark.parametrize(
    "question,expected_section",
    [
        ("How many days of casual leave am I entitled to?", 115),
        ("maternity benefit for women workers", 46),
        ("How much overtime pay is required?", 108),
        ("festival holidays", 118),
        # The one that killed a headline claim. An early draft asserted "BM25 misses s.116
        # because the Act writes 'fourteen days' and users type '14'". Measured at the PAGE
        # level, inferred at the SECTION level -- and wrong. Once you chunk on section
        # boundaries the title carries the query: df('sick') is ~2/342, a decisive high-IDF
        # anchor, and the digit free-rides. It ranks FIRST. The fine-tune this was meant to
        # justify was cut on this measurement.
        ("14 sick days?", 116),
    ],
)
def test_governing_section_is_retrieved_top_1(retriever, question, expected_section):
    hits = retriever.search(question, k=8)
    sections = [c.section_no for c, _ in hits]
    assert sections[0] == expected_section, f"{question!r} -> {sections[:5]}"


def test_get_section_is_an_exact_lookup_not_a_similarity_guess(retriever):
    """A statute has a natural primary key. Approximating an exact key is silly."""
    for number, page in ((46, 39), (108, 57), (115, 59), (117, 59), (118, 60)):
        chunks = retriever.get_section(number)
        assert chunks, f"s.{number} missing"
        assert chunks[0].printed_page == page


def test_similarity_threshold_is_an_antisignal_for_abstention():
    """THE finding that makes FR#5 an architecture problem, not a prompt problem.

    A good adversarial question is PLAUSIBLE, and plausible means semantically adjacent. So
    the unanswerable question outscores answerable ones and the distributions INVERT: any
    threshold that refuses paternity leave also refuses 'who is the Chairperson?'.

    This test asserts the inversion EXISTS -- i.e. that thresholding is unsafe here. If it
    ever starts passing, thresholding became viable and the design should be revisited.
    """
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity

    from src.core.models import Chunk

    chunks = [Chunk(**json.loads(line)) for line in (INDEX / "chunks.jsonl").open()]
    texts = [c.text for c in chunks]
    vectoriser = TfidfVectorizer(stop_words="english", sublinear_tf=True).fit(texts)
    matrix = vectoriser.transform(texts)

    def top1(question: str) -> float:
        return float(cosine_similarity(vectoriser.transform([question]), matrix)[0].max())

    answerable = min(top1("Who is the Chairperson?"), top1("How much overtime pay is required?"))
    unanswerable = top1("How many days of paternity leave do I get?")

    assert unanswerable > answerable, (
        "The distributions no longer invert. Thresholding may now be safe here; "
        "re-examine the abstention design."
    )
