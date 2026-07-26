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

import html as html_lib
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


def _esc(s: str) -> str:
    return html_lib.escape(s, quote=True)


def _email_shell(preheader: str, body_html: str) -> str:
    """Shared HTML wrapper. Inline styles only -- email clients don't load stylesheets, and
    several (Outlook, some webmail) strip <style> blocks entirely. Kept deliberately simple:
    email rendering is inconsistent across clients, so a plain card beats anything fancy
    that might collapse in Outlook's Word-based renderer."""
    return f"""\
<!DOCTYPE html>
<html><head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#f4f4f7;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;">
<span style="display:none;max-height:0;overflow:hidden;">{_esc(preheader)}</span>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f4f4f7;padding:32px 16px;">
<tr><td align="center">
<table role="presentation" width="100%" style="max-width:520px;background:#ffffff;border-radius:12px;overflow:hidden;border:1px solid #e5e7eb;">
<tr><td style="background:linear-gradient(135deg,#8b5cf6,#22d3ee);padding:20px 28px;">
<span style="color:#ffffff;font-size:18px;font-weight:700;">Ask Reshad</span>
</td></tr>
<tr><td style="padding:28px;">
{body_html}
</td></tr>
<tr><td style="padding:16px 28px;background:#fafafa;border-top:1px solid #eee;">
<span style="color:#9ca3af;font-size:12px;">Sent from the AI assistant on reshadulkarim.me</span>
</td></tr>
</table>
</td></tr>
</table>
</body></html>"""


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
        page_row_html = ""
        if body.page and body.page.title:
            page_line = f"\nPage: {body.page.title} ({body.page.kind})"
            page_row_html = (
                f'<tr><td style="padding:6px 0;color:#6b7280;font-size:13px;">Page</td>'
                f'<td style="padding:6px 0;color:#111827;font-size:13px;">'
                f"{_esc(body.page.title)} ({_esc(body.page.kind)})</td></tr>"  # type: ignore[union-attr]
            )
        history_block = ""
        history_html = ""
        if body.recent_history:
            turns = "\n\n".join(f"Q: {t.question}\nA: {t.answer}" for t in body.recent_history)
            history_block = f"\n\n--- Last few turns of their conversation ---\n{turns}"
            turn_rows = "".join(
                f'<div style="margin-bottom:10px;"><div style="color:#6b7280;font-size:13px;">'
                f"Q: {_esc(t.question)}</div><div style=\"color:#111827;font-size:13px;\">"
                f"A: {_esc(t.answer)}</div></div>"
                for t in body.recent_history
            )
            history_html = (
                '<div style="margin-top:20px;padding-top:16px;border-top:1px solid #eee;">'
                '<div style="color:#6b7280;font-size:12px;text-transform:uppercase;'
                f'letter-spacing:.05em;margin-bottom:10px;">Recent conversation</div>{turn_rows}</div>'
            )

        owner_html = _email_shell(
            f"New booking request from {body.name}",
            f"""\
<h2 style="margin:0 0 16px;color:#111827;font-size:18px;">New booking request</h2>
<table role="presentation" width="100%" style="border-collapse:collapse;">
<tr><td style="padding:6px 0;color:#6b7280;font-size:13px;width:100px;">From</td>
<td style="padding:6px 0;color:#111827;font-size:13px;">{_esc(body.name)} &lt;{_esc(body.email)}&gt;</td></tr>
<tr><td style="padding:6px 0;color:#6b7280;font-size:13px;">Purpose</td>
<td style="padding:6px 0;color:#111827;font-size:13px;">{_esc(body.purpose)}</td></tr>
<tr><td style="padding:6px 0;color:#6b7280;font-size:13px;">Preferred times</td>
<td style="padding:6px 0;color:#111827;font-size:13px;">{_esc(body.preferred_times) or '(not specified)'}</td></tr>
{page_row_html}
</table>
{history_html}
""",
        )
        mailer.send(
            to=settings.owner_email,  # type: ignore[arg-type]
            subject=f"Portfolio booking request from {body.name}",
            text=(
                f"New booking request from {body.name} <{body.email}>\n"
                f"Purpose: {body.purpose}\n"
                f"Preferred times: {body.preferred_times or '(not specified)'}"
                f"{page_line}{history_block}"
            ),
            html=owner_html,
            reply_to=body.email,
        )

        visitor_html = _email_shell(
            f"Thanks for reaching out to {settings.owner_name}",
            f"""\
<p style="margin:0 0 12px;color:#111827;font-size:15px;">Hi {_esc(body.name)},</p>
<p style="margin:0 0 12px;color:#374151;font-size:14px;line-height:1.5;">
Thanks for reaching out to {_esc(settings.owner_name)} through his portfolio assistant.
He's received your request and will follow up by email soon.</p>
<div style="margin:16px 0;padding:14px 16px;background:#f9fafb;border-radius:8px;border:1px solid #eee;">
<div style="color:#6b7280;font-size:12px;text-transform:uppercase;letter-spacing:.05em;margin-bottom:6px;">
You wrote</div>
<div style="color:#111827;font-size:14px;">{_esc(body.purpose)}</div>
</div>
""",
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
            html=visitor_html,
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
