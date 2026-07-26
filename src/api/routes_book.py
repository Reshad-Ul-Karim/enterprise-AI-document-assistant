"""POST /api/book -- a visitor asking to talk to Reshad directly.

Public and unauthenticated, like /api/ask's default corpus -- this is the whole point of the
booking flow (see docs/AI_ASSISTANT_PLAN.md sec.6), not an oversight. Protected instead by:
  * a honeypot field (silently discarded, not rejected -- see body.website below)
  * a basic email-format check (ValidationFailed, 422)
  * DailyIPGate (3/IP/day, BookingRateLimited, 429)

Two emails go out on success -- one to Reshad with the ask and recent conversation context,
one to the visitor as an acknowledgement -- as a BackgroundTask, so the response returns as
soon as the request is validated rather than waiting on two sequential calls to Resend's API.
"""

from __future__ import annotations

import re

from fastapi import APIRouter, BackgroundTasks, Request

from src.api.bookgate import DailyIPGate
from src.api.errors import BookingRateLimited, ValidationFailed
from src.api.settings import settings
from src.core.models import BookRequest

router = APIRouter(prefix="/api")

# Module-level, not per-request: the whole point is that state persists ACROSS requests for
# the lifetime of the process (same reasoning as KbRegistry's in-memory store).
_gate = DailyIPGate(max_per_day=3)

# Deliberately crude (no RFC-5322 parser, no new dependency) -- this rejects the typos and
# empty-field submissions that matter, not every theoretically-malformed address, and the
# visitor finds out about anything subtler when Resend itself bounces it.
_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _send_booking_emails(body: BookRequest) -> None:
    """Runs in a BackgroundTask. A failed send must never surface to the visitor as a 500
    for a request that already returned 202 -- so exceptions are swallowed here, same
    tolerance routes_kb.py's _run_ingest applies to a background job."""
    if not settings.booking_available:
        return
    try:
        from src.api.providers.resend import ResendMailer

        mailer = ResendMailer(settings.resend_api_key)  # type: ignore[arg-type]

        page_line = ""
        if body.page and body.page.title:
            page_line = f"\nPage: {body.page.title} ({body.page.kind})"
        history_block = ""
        if body.recent_history:
            turns = "\n\n".join(f"Q: {t.question}\nA: {t.answer}" for t in body.recent_history)
            history_block = f"\n\n--- Last few turns of their conversation ---\n{turns}"

        mailer.send(
            to=settings.owner_email,  # type: ignore[arg-type]
            subject=f"Portfolio booking request from {body.name}",
            text=(
                f"New booking request from {body.name} <{body.email}>\n"
                f"Purpose: {body.purpose}\n"
                f"Preferred times: {body.preferred_times or '(not specified)'}"
                f"{page_line}{history_block}"
            ),
            reply_to=body.email,
        )
        mailer.send(
            to=body.email,
            subject=f"You reached {settings.owner_name}",
            text=(
                f"Hi {body.name},\n\n"
                f"Thanks for reaching out to {settings.owner_name} through his portfolio "
                "assistant. He's received your request and will follow up by email soon.\n\n"
                f"For reference, here's what you sent:\n\"{body.purpose}\"\n\n"
                "— Ask Reshad"
            ),
        )
    except Exception:
        pass  # best-effort; the visitor already got a 202 and has no way to retry this call


@router.post("/book", status_code=202)
async def book(body: BookRequest, request: Request, background: BackgroundTasks) -> dict[str, str]:
    if body.website.strip():
        # Honeypot tripped. Report the SAME success shape a real submission gets -- telling
        # a bot it was caught only teaches it to leave the field blank next time. No email
        # is sent and the rate-limit counter is not spent on it.
        return {"status": "queued"}

    if not _EMAIL_RE.match(body.email):
        raise ValidationFailed("That doesn't look like a valid email address.")

    ip = _client_ip(request)
    if not _gate.allow(ip):
        raise BookingRateLimited(
            "You've reached the limit of booking requests for today. Try again tomorrow, "
            "or email Reshad directly."
        )

    background.add_task(_send_booking_emails, body)
    return {"status": "queued"}
