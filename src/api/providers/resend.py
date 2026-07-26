"""The Resend adapter. The ONLY module that imports `httpx` for outbound mail.

Mirrors mistral.py's shape: a real implementation the route injects, so routes_book.py never
imports `httpx` directly and a test can inject a fake sender with zero network calls -- same
reasoning as core/'s injected Generator/Embedder Protocols, just one layer up (this is
api/-only, never imported by core/ or ingest/, since sending mail is a serving-time concern
with no build-time analogue).
"""

from __future__ import annotations

from typing import Protocol


class Mailer(Protocol):
    def send(
        self, to: str, subject: str, text: str, html: str | None = None, reply_to: str | None = None
    ) -> None: ...


class ResendMailer:
    """Resend's HTTP API directly (no SDK dependency -- one POST, not worth a client library).

    Sending from Resend's shared onboarding domain (no DNS work) with `reply_to` set to the
    visitor's or Reshad's address, per docs/AI_ASSISTANT_PLAN.md sec.6 -- moving to a
    `@reshadulkarim.me` from-address needs SPF/DKIM records and is a later, optional step.
    """

    API_URL = "https://api.resend.com/emails"
    FROM = "Ask Reshad <onboarding@resend.dev>"

    def __init__(self, api_key: str):
        self._api_key = api_key

    def send(
        self, to: str, subject: str, text: str, html: str | None = None, reply_to: str | None = None
    ) -> None:
        import httpx

        payload: dict[str, object] = {
            "from": self.FROM,
            "to": [to],
            "subject": subject,
            "text": text,
        }
        if html:
            payload["html"] = html
        if reply_to:
            payload["reply_to"] = reply_to
        response = httpx.post(
            self.API_URL,
            headers={"Authorization": f"Bearer {self._api_key}"},
            json=payload,
            timeout=10.0,
        )
        response.raise_for_status()
