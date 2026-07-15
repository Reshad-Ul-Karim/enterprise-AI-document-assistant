"""Authentication for the upload surface.

SCOPE, and the reason for it: the demo corpus is PUBLIC and stays public. A reviewer must
be able to open the URL and click the compliance questions with no login -- an assessment
demo behind a password is a demo nobody sees, and the rubric's live-URL requirement is not
satisfied by a login screen.

Auth exists only for the part that needs it: uploading documents. That is the surface that
consumes quota, writes to a vector store, and would otherwise let anyone on the internet
push arbitrary PDFs through a rate-limited free tier on someone else's key.

The credential is a DEMO credential and is published in the README, because the assessment
requires test credentials to be supplied. It therefore protects nothing valuable and must
never be a password used anywhere else.

What is stored: an email and a bcrypt hash, both from the environment. The repo is public,
so no plaintext and no hash are committed. There is no user table -- one account, checked
against two env vars, is the honest amount of machinery for one demo account. A database
of one row would be architecture theatre.
"""

from __future__ import annotations

import hmac
import time
from typing import Annotated

import bcrypt
from fastapi import Depends, Request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from src.api.errors import AppError
from src.api.settings import settings

SESSION_COOKIE = "eda_session"
SESSION_MAX_AGE = 60 * 60 * 12  # 12h -- long enough for a demo session, short enough to expire


class AuthRequired(AppError):
    status_code = 401
    code = "AUTH_REQUIRED"  # type: ignore[assignment]


class AuthUnconfigured(AppError):
    status_code = 503
    code = "AUTH_UNCONFIGURED"  # type: ignore[assignment]


def _serializer() -> URLSafeTimedSerializer:
    if not settings.session_secret:
        raise AuthUnconfigured(
            "SESSION_SECRET is not set, so sessions cannot be signed. Upload is disabled; "
            "the public demo corpus is unaffected."
        )
    return URLSafeTimedSerializer(settings.session_secret, salt="eda-session")


def verify_credentials(email: str, password: str) -> bool:
    """Constant-time email compare + bcrypt password check.

    `hmac.compare_digest` on the email rather than `==`: string comparison short-circuits on
    the first differing byte, which leaks the email a character at a time to anyone willing
    to time it. bcrypt is already constant-time internally.

    bcrypt (not sha256) because it is deliberately slow and salted -- a fast hash of a
    published demo password is pointless anyway, but the habit is the point: the next person
    to copy this file may not be hashing something worthless.
    """
    if not settings.auth_email or not settings.auth_password_hash:
        raise AuthUnconfigured(
            "AUTH_EMAIL / AUTH_PASSWORD_HASH are not set. Upload is disabled; the public "
            "demo corpus is unaffected."
        )
    email_ok = hmac.compare_digest(email.strip().lower(), settings.auth_email.strip().lower())
    try:
        password_ok = bcrypt.checkpw(password.encode(), settings.auth_password_hash.encode())
    except ValueError:
        # A malformed hash in the env is a deployment error, not a failed login. Say so
        # rather than returning "wrong password" and sending someone hunting for a typo.
        raise AuthUnconfigured("AUTH_PASSWORD_HASH is not a valid bcrypt hash.")
    # Evaluate both regardless of the first result: an early return on a bad email skips the
    # bcrypt work and makes "wrong email" measurably faster than "wrong password".
    return email_ok and password_ok


def issue_session(email: str) -> str:
    return _serializer().dumps({"sub": email, "iat": int(time.time())})


def read_session(request: Request) -> str | None:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    try:
        data = _serializer().loads(token, max_age=SESSION_MAX_AGE)
    except (BadSignature, SignatureExpired, AuthUnconfigured):
        return None
    return data.get("sub")


async def require_auth(request: Request) -> str:
    """FastAPI dependency. Gates the upload surface only."""
    email = read_session(request)
    if not email:
        raise AuthRequired("Sign in to upload documents. The demo corpus needs no sign-in.")
    return email


CurrentUser = Annotated[str, Depends(require_auth)]
