"""Typed error envelope. Never a 200 with a stack trace in the body.

THE RULE THAT MATTERS MOST HERE: a refusal is NOT an error.

"I couldn't find this in the documents" returns 200 with insufficient_information: true.
It is a designed product state -- it is literally functional requirement #5 -- and a
product state is not a transport failure. 4xx means the CALLER did something wrong.
Returning 422 for a refusal would make the eval harness score every CORRECT refusal as a
transport failure, which is how a system gets "fixed" into refusing nothing.
"""

from __future__ import annotations

from typing import Literal, get_args

from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

ErrorCode = Literal[
    "VALIDATION_FAILED",
    "SCANNED_PDF_REQUIRES_OCR",
    "KB_NOT_FOUND",
    "PAYLOAD_TOO_LARGE",
    "UPSTREAM_RATE_LIMITED",
    "UPSTREAM_UNAVAILABLE",
    "UPLOAD_BACKEND_UNAVAILABLE",
    "INDEX_NOT_LOADED",
    "GENERATION_UNCONFIGURED",
    "AUTH_REQUIRED",
    "AUTH_UNCONFIGURED",
]


class ErrorDetail(BaseModel):
    code: ErrorCode
    message: str
    request_id: str
    retry_after_s: float | None = None


class ErrorEnvelope(BaseModel):
    error: ErrorDetail


class AppError(Exception):
    status_code = 500
    code: ErrorCode = "UPSTREAM_UNAVAILABLE"

    def __init__(self, message: str, retry_after_s: float | None = None):
        super().__init__(message)
        self.message = message
        self.retry_after_s = retry_after_s


class IndexNotLoaded(AppError):
    status_code = 503
    code: ErrorCode = "INDEX_NOT_LOADED"


class GenerationUnconfigured(AppError):
    status_code = 503
    code: ErrorCode = "GENERATION_UNCONFIGURED"


class UpstreamRateLimited(AppError):
    status_code = 429
    code: ErrorCode = "UPSTREAM_RATE_LIMITED"


class UpstreamUnavailable(AppError):
    status_code = 503
    code: ErrorCode = "UPSTREAM_UNAVAILABLE"


class UploadBackendUnavailable(AppError):
    status_code = 503
    code: ErrorCode = "UPLOAD_BACKEND_UNAVAILABLE"


class KbNotFound(AppError):
    status_code = 404
    code: ErrorCode = "KB_NOT_FOUND"


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    """Build the envelope defensively.

    An earlier version trusted `exc.code` to be in the Literal. It was not -- AuthRequired
    was added with a code nobody added to ErrorCode -- so ErrorDetail raised a
    ValidationError INSIDE the handler and FastAPI returned a 500. The error envelope built
    to prevent 500s produced one. An unknown code is a bug to fix, not a reason to hand the
    caller a stack trace, so it degrades to a typed envelope and the mismatch is caught by
    test_every_app_error_code_is_declared instead.
    """
    request_id = getattr(request.state, "request_id", "unknown")
    code = exc.code if exc.code in get_args(ErrorCode) else "UPSTREAM_UNAVAILABLE"
    envelope = ErrorEnvelope(
        error=ErrorDetail(
            code=code,
            message=exc.message,
            request_id=request_id,
            retry_after_s=exc.retry_after_s,
        )
    )
    headers = {}
    if exc.retry_after_s is not None:
        # Echo upstream's Retry-After into the header AND the body: the header is for
        # clients, the body is for the human reading the response in a browser.
        headers["Retry-After"] = str(int(exc.retry_after_s) or 1)
    return JSONResponse(status_code=exc.status_code, content=envelope.model_dump(), headers=headers)
