"""POST /api/book -- unit-level, no network, no dependency on the HR/persona index.

Uses a minimal app with just book_router mounted (not src.api.main.app) precisely so these
tests never need an index built or a Mistral key -- booking is independent of both, and
gating these tests behind "index built" (like test_api.py does) would be testing the wrong
dependency.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.bookgate import DailyIPGate
from src.api.errors import app_error_handler, AppError
from src.api.routes_book import router


def _make_client(monkeypatch, sent=None):
    """Fresh app + fresh rate-gate per test, so tests don't share the module-level _gate."""
    import src.api.routes_book as routes_book

    fresh_gate = DailyIPGate(max_per_day=3)
    monkeypatch.setattr(routes_book, "_gate", fresh_gate)

    if sent is not None:
        def fake_send(self, to, subject, text, reply_to=None):
            sent.append({"to": to, "subject": subject, "text": text, "reply_to": reply_to})

        monkeypatch.setattr("src.api.providers.resend.ResendMailer.send", fake_send)

    app = FastAPI()
    app.add_exception_handler(AppError, app_error_handler)
    app.include_router(router)
    return TestClient(app)


VALID_BODY = {
    "name": "Test Recruiter",
    "email": "recruiter@example.com",
    "purpose": "Discuss an ML engineering role",
    "preferred_times": "Tuesday afternoon",
    "website": "",
}


def test_valid_booking_is_accepted(monkeypatch):
    client = _make_client(monkeypatch)
    res = client.post("/api/book", json=VALID_BODY)
    assert res.status_code == 202
    assert res.json() == {"status": "queued"}


def test_honeypot_field_is_silently_discarded_not_rejected(monkeypatch):
    """A bot filling every field (including the hidden one) must see the SAME success shape
    a real visitor gets -- telling it "caught you" only teaches it to leave the field blank
    next time (see routes_book.py's docstring)."""
    sent = []
    client = _make_client(monkeypatch, sent=sent)
    body = dict(VALID_BODY, website="http://spam.example")
    res = client.post("/api/book", json=body)
    assert res.status_code == 202
    assert res.json() == {"status": "queued"}
    assert sent == []  # no mail actually sent for the honeypot case


def test_malformed_email_is_rejected_with_422(monkeypatch):
    client = _make_client(monkeypatch)
    res = client.post("/api/book", json=dict(VALID_BODY, email="not-an-email"))
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "VALIDATION_FAILED"


def test_fourth_booking_from_the_same_ip_in_one_day_is_rate_limited(monkeypatch):
    client = _make_client(monkeypatch)
    for _ in range(3):
        assert client.post("/api/book", json=VALID_BODY).status_code == 202
    res = client.post("/api/book", json=VALID_BODY)
    assert res.status_code == 429
    assert res.json()["error"]["code"] == "BOOKING_RATE_LIMITED"


def test_without_resend_configured_the_request_still_succeeds(monkeypatch):
    """settings.booking_available is False in the test environment (no RESEND_API_KEY/
    OWNER_EMAIL) -- the endpoint must still validate and rate-limit correctly and return
    202, not crash trying to reach a mailer that was never configured."""
    from src.api.settings import settings

    monkeypatch.setattr(settings, "resend_api_key", None)
    monkeypatch.setattr(settings, "owner_email", None)
    client = _make_client(monkeypatch)
    res = client.post("/api/book", json=VALID_BODY)
    assert res.status_code == 202


def test_successful_booking_emails_both_owner_and_visitor(monkeypatch):
    from src.api.settings import settings

    monkeypatch.setattr(settings, "resend_api_key", "fake-key")
    monkeypatch.setattr(settings, "owner_email", "reshad@example.com")
    sent = []
    client = _make_client(monkeypatch, sent=sent)
    res = client.post("/api/book", json=VALID_BODY)
    assert res.status_code == 202
    recipients = {m["to"] for m in sent}
    assert recipients == {"reshad@example.com", "recruiter@example.com"}
    owner_mail = next(m for m in sent if m["to"] == "reshad@example.com")
    assert owner_mail["reply_to"] == "recruiter@example.com"
    assert "Discuss an ML engineering role" in owner_mail["text"]
