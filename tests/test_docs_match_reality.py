"""The docs must describe the system that exists.

THIS TEST EXISTS BECAUSE THE ONE-NUMBER RULE WAS BROKEN BY ITS OWN AUTHOR, TWICE.

The rule -- "one committed script emits corpus_stats.json; every number in the README, the
diagram and the interview prep reads from it" -- was written after an expert council produced
seven contradictory values for one fact. Then:

  * The roadmap kept the council's PROTOTYPE numbers while the README carried the BUILT
    system's. Two documents in one repo, disagreeing about the same fact.
  * Embeddings moved from local bge-small/384 to Pinecone Inference/1024, and the README,
    the roadmap AND the interview handbook were left describing an architecture that no
    longer existed. The handbook literally scripted "local embeddings, 2.4ms, zero API spend"
    -- it would have coached a confident, checkable falsehood into an interview.

A stale doc is not untidiness. The README is what the reviewer reads first, and a claim they
can falsify in one click discredits every other measured claim in the repo.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
STATS = json.loads((REPO / "corpus_stats.json").read_text())
README = (REPO / "README.md").read_text()
HANDBOOK = (REPO / "docs" / "INTERVIEW_HANDBOOK.md").read_text()


def test_readme_quotes_the_real_embedding_model():
    model = STATS["index"]["embed_model_id"]
    assert model in README, f"README must name the actual embedder ({model})"


def test_readme_quotes_the_real_index_size_and_dimension():
    """Catch DRIFT (384 vs 1024, 0.74 MB vs 1.97 MB), not rounding.

    An earlier version demanded the literal "1.974" and failed on prose that said "1.97 MB".
    That is the test dictating style rather than guarding truth -- and a test that forces
    ugly precision into a sentence will get deleted by the next person, taking the real
    guard with it. Sensible rounding is allowed; a stale number is not.
    """
    mb = STATS["index"]["index_mb"]
    assert any(f"{mb:.{p}f}" in README for p in (1, 2, 3)), f"README must quote the real index size (~{mb} MB)"
    assert str(STATS["index"]["embed_dim"]) in README, "README must quote the real embedding dimension"
    assert "384" not in README.replace("3,84", ""), "384 is the OLD embedder's dimension"


def test_readme_quotes_the_real_chunk_and_token_counts():
    assert str(STATS["index"]["chunk_count"]) in README
    assert f"{STATS['tokens']['corpus_full']:,}" in README


def test_the_handbooks_cheat_sheet_is_not_stale():
    """Part 11 is the ten-second cheat sheet -- the numbers he would say out loud under
    pressure. If any of them is from a superseded architecture, this test is the only thing
    standing between him and a checkable falsehood in the room."""
    cheat = HANDBOOK[HANDBOOK.index("## Part 11"):]
    assert STATS["index"]["embed_model_id"] in cheat, "cheat sheet names a dead embedder"
    assert "384" not in cheat, "384-dim is the OLD embedder; vectors are 1024-dim now"
    assert str(STATS["index"]["embed_dim"]) in cheat


def test_no_doc_claims_retrieval_is_network_free():
    """It WAS true with local embeddings and is not any more: the query embedding is an API
    call. The claim may appear only as history (describing what changed), never as a live
    promise -- so any surviving mention must sit near an explicit correction."""
    for name, text in (("README.md", README), ("INTERVIEW_HANDBOOK.md", HANDBOOK)):
        for m in re.finditer(r"zero network", text, re.I):
            window = text[max(0, m.start() - 400) : m.end() + 400].lower()
            corrected = any(
                phrase in window
                for phrase in ("no longer true", "was correct", "used to", "api call", "were correct")
            )
            assert corrected, (
                f"{name} claims 'zero network' at char {m.start()} without noting that the "
                "query embedding is now an API call. That is a live falsehood a reviewer can "
                "check in one click."
            )


def test_the_roadmap_admits_it_is_superseded():
    """The roadmap is the PLAN. It is kept for its reasoning, not its rulings -- two of which
    reality overturned. It must say so at the top rather than quietly misinform."""
    roadmap = (REPO / "IMPLEMENTATION_ROADMAP.md").read_text()
    head = roadmap[:2500]
    assert "SUPERSEDED" in head.upper()
    assert "Render" in head, "must say the deploy target is not HF Spaces"
    assert "Pinecone Inference" in head, "must say embeddings are not local any more"
