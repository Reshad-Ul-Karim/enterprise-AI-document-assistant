"""API contract. Runs with NO API key and NO network -- that is the point of the Protocol.

A reviewer who has signed up for nothing must be able to clone this and get a green suite.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

REPO = Path(__file__).resolve().parents[1]
INDEX = REPO / "index"

pytestmark = pytest.mark.skipif(
    not (INDEX / "chunks.jsonl").exists(), reason="index not built; run python -m src.ingest.build_index"
)


@pytest.fixture(scope="module")
def client():
    from src.api import main

    with TestClient(main.app) as test_client:
        yield test_client


def test_health_reports_the_index_and_never_lies_about_it(client):
    body = client.get("/health").json()
    assert body["index_loaded"] is True
    assert body["chunk_count"] > 0
    assert body["model_id"] == "mistral-large-2512"  # pinned, never '-latest'
    # pinecone_reachable is a SEPARATE field from index_loaded: Pinecone serves uploads
    # only, so it must never imply the baseline demo is down.
    assert "pinecone_reachable" in body


def test_documents_endpoint_uses_the_curated_manifest_not_filenames(client):
    docs = client.get("/api/documents").json()["documents"]
    titles = {d["doc_title"] for d in docs}
    assert "Employee Handbook (Partex Star Group)" in titles
    # The file is called Partex-Star-Group.pdf. Its metadata title is
    # 'Employee Handbook-Final'. Neither is what a user should be shown.
    assert not any("Partex-Star-Group.pdf" == t for t in titles)
    statute = next(d for d in docs if d["doc_id"] == "statute")
    assert statute["modality"] == "ocr"
    assert "2013" in statute["note"] and "2018" in statute["note"]  # staleness is disclosed


def test_ask_without_a_key_fails_typed_never_with_a_stack_trace(client, monkeypatch):
    """A 200 with a stack trace in the body scores 5/10 on API design.

    The unconfigured-generator path is forced explicitly rather than inferred from whether
    the developer happens to have a .env file: a test that passes only on an unconfigured
    machine silently stops testing anything the moment a key is added.
    """
    from src.api import main

    monkeypatch.setitem(main.state, "generator", None)
    response = client.post("/api/ask", json={"question": "How many casual leave days?"})

    assert response.status_code == 503
    body = response.json()
    assert body["error"]["code"] == "GENERATION_UNCONFIGURED"
    assert body["error"]["request_id"]
    assert "Traceback" not in response.text


def test_validation_is_a_422_not_a_500(client):
    assert client.post("/api/ask", json={"question": "x"}).status_code == 422  # min_length
    assert client.post("/api/ask", json={"question": "ok?", "section_no": 9999}).status_code == 422


def test_refusal_is_200_not_an_error():
    """THE FR#5 TEST, on the measured unanswerable question -- not a generic one.

    'paternity leave?' is the adversarial case: it scores HIGHER on similarity than
    answerable questions because it collides with the casual-leave chunk. A refusal is a
    designed product state, so it is 200 + insufficient_information: true. Returning 422
    here would make the eval harness score every correct refusal as a transport failure.
    """
    from src.api.service import Corpus, answer
    from src.core.generator import FakeGenerator

    corpus = Corpus(INDEX)
    # The model, asked about paternity leave, correctly declines to cite anything.
    generator = FakeGenerator("The provided documents do not address paternity leave.")
    response = answer("How many days of paternity leave do I get?", corpus, generator)

    assert response.insufficient_information is True
    assert response.citations == []
    assert response.route == "NO_ANSWER"


def test_a_hallucinated_citation_cannot_escape_the_pipeline():
    """End-to-end: a model that invents a quote produces an abstention, not a wrong answer."""
    from src.api.service import Corpus, answer
    from src.core.generator import FakeGenerator

    corpus = Corpus(INDEX)
    generator = FakeGenerator("[[chunk:statute:s115|workers get forty days of casual leave]]")
    response = answer("How many casual leave days?", corpus, generator)

    assert response.insufficient_information is True
    assert "forty days" not in response.answer
