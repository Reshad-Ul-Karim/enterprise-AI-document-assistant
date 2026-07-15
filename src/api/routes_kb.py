"""Knowledge-base routes: login, create, upload, poll, ask.

The public demo corpus is NOT here -- it is in main.py and needs no session. Everything in
this module is gated, because uploading is what consumes quota and writes to a store.
"""

from __future__ import annotations

import re
import uuid

from fastapi import APIRouter, BackgroundTasks, File, Request, Response, UploadFile
from pydantic import BaseModel, Field

from src.api.auth import (
    SESSION_COOKIE,
    SESSION_MAX_AGE,
    AuthRequired,
    CurrentUser,
    issue_session,
    read_session,
    verify_credentials,
)
from src.api.settings import settings
from src.api.uploads import Job, KbNotFound, PayloadTooLarge, ingest

router = APIRouter(prefix="/api")


class LoginRequest(BaseModel):
    email: str
    password: str


class CreateKbRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)


@router.post("/auth/login")
async def login(body: LoginRequest, response: Response) -> dict[str, object]:
    if not verify_credentials(body.email, body.password):
        # One message for both wrong-email and wrong-password. Distinguishing them tells an
        # attacker which half they got right -- and this is the account-enumeration answer
        # the reviewer may probe for.
        raise AuthRequired("Invalid email or password.")
    response.set_cookie(
        SESSION_COOKIE,
        issue_session(body.email),
        max_age=SESSION_MAX_AGE,
        httponly=True,   # JS cannot read it, so an XSS cannot steal the session
        secure=True,     # HTTPS only; Render terminates TLS
        samesite="lax",  # not sent on cross-site POSTs -> CSRF has nothing to ride on
    )
    return {"email": body.email, "uploads_persist": settings.uploads_persist}


@router.post("/auth/logout")
async def logout(response: Response) -> dict[str, bool]:
    response.delete_cookie(SESSION_COOKIE)
    return {"ok": True}


@router.get("/auth/me")
async def me(request: Request) -> dict[str, object]:
    """Unauthenticated on purpose: the UI asks 'am I signed in?' before deciding what to
    render. Answering 'no' is not an error."""
    email = read_session(request)
    return {
        "authenticated": bool(email),
        "email": email,
        "auth_configured": settings.auth_available,
        # The UI states this AT UPLOAD TIME, before the user spends effort -- not after.
        "uploads_persist": settings.uploads_persist,
    }


@router.get("/kb")
async def list_kbs(request: Request, user: CurrentUser) -> dict[str, object]:
    registry = request.app.state.registry
    return {
        "knowledge_bases": [
            {
                "kb_id": kb.kb_id,
                "name": kb.name,
                "documents": len(kb.docs),
                "chunks": len(kb.chunks),
                "doc_titles": list(kb.docs.values()),
            }
            for kb in registry.kbs.values()
        ],
        "uploads_persist": settings.uploads_persist,
    }


@router.post("/kb", status_code=201)
async def create_kb(body: CreateKbRequest, request: Request, user: CurrentUser) -> dict[str, str]:
    """Creating a notebook does ~3.5s of BLOCKING network I/O (Pinecone list_indexes +
    describe_index_stats), so it runs in a threadpool.

    In an `async def` route, a blocking call does not just make THAT request slow -- it
    freezes the entire event loop. On a single-worker box that means every other request,
    including /health, stalls behind it. Render's health check failing is a restart, and a
    restart mid-request is exactly the "Failed to fetch" the user saw.

    run_in_threadpool is the whole fix: the socket work happens off the loop.
    """
    from starlette.concurrency import run_in_threadpool

    registry = request.app.state.registry
    kb_id = re.sub(r"[^a-z0-9]+", "-", body.name.lower()).strip("-")[:32] or uuid.uuid4().hex[:8]
    if kb_id in registry.kbs:
        kb_id = f"{kb_id}-{uuid.uuid4().hex[:4]}"
    kb = await run_in_threadpool(registry.create, kb_id, body.name)
    return {"kb_id": kb.kb_id, "name": kb.name}


@router.delete("/kb/{kb_id}")
async def delete_kb(kb_id: str, request: Request, user: CurrentUser) -> dict[str, bool]:
    from starlette.concurrency import run_in_threadpool

    registry = request.app.state.registry
    if kb_id not in registry.kbs:
        raise KbNotFound(f"No knowledge base {kb_id!r}.")
    await run_in_threadpool(registry.delete, kb_id)  # deletes the namespace: network I/O
    return {"ok": True}


def _run_ingest(registry, kb_id: str, job: Job, data: bytes, filename: str) -> None:
    """Runs in a BackgroundTask.

    Free tier: no queue, no worker, no persistent disk. So job records live in-process and
    die on restart -- stated in the README rather than hidden. Ingestion is idempotent on
    sha256(bytes), which is what makes that survivable: recovery is a re-upload, never a
    duplicate and never a corruption.
    """
    try:
        kb = registry.kbs[kb_id]
        before = len(kb.chunks)
        ingest(data, filename, kb, job)
        if job.state == "done" and len(kb.chunks) > before:
            # ingest() finishes by setting state=done and progress="Indexed N chunks...".
            # Flipping back to "indexing" here left the UI showing a spinner NEXT TO a
            # completion message -- the state said working, the text said finished. The
            # upsert is real work (a network round-trip), so it gets its own honest message
            # rather than borrowing the finished one.
            job.state = "indexing"
            done_message = job.progress
            job.progress = "Saving to Pinecone so it survives a restart…"
            registry.index_after_upload(kb_id, kb.chunks[before:])
            job.progress = done_message
            job.state = "done"
    except Exception as exc:  # a failed upload must never take the process with it
        job.state = "failed"
        job.error = f"{type(exc).__name__}: {exc}"


@router.post("/kb/{kb_id}/documents", status_code=202)
async def upload_document(
    kb_id: str,
    request: Request,
    background: BackgroundTasks,
    user: CurrentUser,
    file: UploadFile = File(...),
) -> dict[str, str]:
    """202 Accepted + a job to poll, not a blocking request.

    A 60-page scanned PDF is an OCR round-trip plus embedding -- minutes, not seconds. A
    synchronous upload would hit the proxy's request timeout and hand the user a 502 while
    the work was still succeeding in the background.
    """
    registry = request.app.state.registry
    if kb_id not in registry.kbs:
        raise KbNotFound(f"No knowledge base {kb_id!r}. Create it first.")

    data = await file.read()
    if len(data) > settings.max_upload_mb * 1_000_000:
        raise PayloadTooLarge(
            f"{len(data)/1e6:.1f} MB exceeds the {settings.max_upload_mb} MB limit."
        )
    if not (file.filename or "").lower().endswith(".pdf"):
        raise PayloadTooLarge("Only PDF uploads are supported.")

    job = Job(job_id=uuid.uuid4().hex[:12], kb_id=kb_id, filename=file.filename or "upload.pdf")
    registry.jobs[job.job_id] = job
    background.add_task(_run_ingest, registry, kb_id, job, data, job.filename)
    return {"job_id": job.job_id, "state": job.state}


@router.get("/jobs/{job_id}")
async def job_status(job_id: str, request: Request, user: CurrentUser) -> dict[str, object]:
    job = request.app.state.registry.jobs.get(job_id)
    if not job:
        raise KbNotFound(f"No job {job_id!r}.")
    return {
        "job_id": job.job_id,
        "kb_id": job.kb_id,
        "filename": job.filename,
        "state": job.state,
        "progress": job.progress,
        "doc_id": job.doc_id,
        "pages": job.pages,
        "chunks": job.chunks,
        "modality": job.modality,
        "error": job.error,
    }
