"""FastAPI app."""

from __future__ import annotations

import json
import logging
import sys
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from src.api.auth import AuthRequired, read_session
from src.api.errors import AppError, GenerationUnconfigured, IndexNotLoaded, app_error_handler
from src.api.uploads import KbNotFound
from src.api.kbstore import KbRegistry
from src.api.memguard import MEMORY_LIMIT_MB, current_rss_mb
from src.api.rategate import RateGate, estimate_tokens
from src.api.routes_book import router as book_router
from src.api.routes_kb import router as kb_router
from src.api.settings import settings
from src.core.generator import Generator
from src.core.models import AskRequest, AskResponse
from src.core.manifest import MANIFEST

REPO = Path(__file__).resolve().parents[2]
STATIC = REPO / "static"

logging.basicConfig(level=settings.log_level, stream=sys.stdout, format="%(message)s")
log = logging.getLogger("app")


def _log(event: str, **fields: object) -> None:
    log.info(json.dumps({"event": event, **fields}))


state: dict[str, object] = {
    "corpus": None,
    "corpus_persona": None,
    "generator": None,
    "gate": None,
    "error": None,
    "error_persona": None,
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    from src.api.service import Corpus

    try:
        state["corpus"] = Corpus(REPO / settings.index_dir)
        _log("index_loaded", chunks=len(state["corpus"].chunks))  # type: ignore[union-attr]
    except Exception as exc:
        # /health reports this rather than the app crash-looping: a reviewer gets a
        # diagnosis, not a blank page.
        state["error"] = f"{type(exc).__name__}: {exc}"
        _log("index_load_failed", error=state["error"])

    persona_dir = REPO / settings.persona_index_dir
    if persona_dir.exists():
        try:
            state["corpus_persona"] = Corpus(persona_dir)
            _log("persona_index_loaded", chunks=len(state["corpus_persona"].chunks))  # type: ignore[union-attr]
        except Exception as exc:
            # Best-effort and SEPARATE from the HR error: a broken persona build must never
            # take the HR demo down with it, and vice versa -- they are two independent
            # corpora sharing one process, not one corpus with two names.
            state["error_persona"] = f"{type(exc).__name__}: {exc}"
            _log("persona_index_load_failed", error=state["error_persona"])
    else:
        _log("persona_index_absent", path=str(persona_dir))

    app.state.registry = KbRegistry()
    # Restore uploaded notebooks from Pinecone. Persisting vectors while forgetting the
    # notebook means the data survives and the user still sees an empty list -- which is
    # indistinguishable from having lost it. Best-effort: a Pinecone outage must never stop
    # the app booting, because the public demo corpus is a local file and is unaffected.
    restored = app.state.registry.rehydrate()
    if restored:
        _log("kbs_rehydrated", count=restored)
    state["gate"] = RateGate(settings.max_concurrent_requests, settings.tokens_per_minute)
    if settings.generation_available:
        from src.api.providers.mistral import MistralGenerator

        state["generator"] = MistralGenerator(settings.mistral_api_key, settings.mistral_model)
    yield


app = FastAPI(
    title="Enterprise AI Document Assistant",
    description=(
        "HR policy compliance assistant over the Partex Star Group Employee Handbook and "
        "the Bangladesh Labour Act 2006."
    ),
    version="1.0.0",
    lifespan=lifespan,
)
app.add_exception_handler(AppError, app_error_handler)  # type: ignore[arg-type]
app.include_router(kb_router)
app.include_router(book_router)

if settings.cors_origins:
    # Same-origin-only until now: static/app.js has always been served from this app's own
    # origin (app.mount("/static", ...) below), so no CORSMiddleware existed. The persona
    # widget on reshadulkarim.me is a genuinely different origin calling this API, hence a
    # real (not copy-pasted) CORS config -- gated behind an env var so the HR demo's origin
    # policy is unchanged for anyone who never sets CORS_ALLOW_ORIGINS.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["POST", "GET"],
        allow_headers=["Content-Type"],
        allow_credentials=False,  # the persona corpus is public; no cookies cross this boundary
    )


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    request.state.request_id = str(uuid.uuid4())[:8]
    response = await call_next(request)
    response.headers["X-Request-ID"] = request.state.request_id
    return response


def _corpus():
    if state["corpus"] is None:
        raise IndexNotLoaded(state["error"] or "Index not loaded.")
    return state["corpus"]


def _corpus_persona():
    if state["corpus_persona"] is None:
        raise IndexNotLoaded(
            state["error_persona"] or "Persona index not loaded (has it been built yet?)."
        )
    return state["corpus_persona"]


def _generator() -> Generator:
    if state["generator"] is None:
        raise GenerationUnconfigured(
            "MISTRAL_API_KEY is not set on this deployment. Retrieval and /health work; "
            "answer generation does not."
        )
    return state["generator"]  # type: ignore[return-value]


# GET *and* HEAD. FastAPI's APIRoute does NOT auto-add HEAD to a GET route the way plain
# Starlette's Route does, so `@app.get` alone answers HEAD with 405 Method Not Allowed.
# Uptime monitors send HEAD by default -- it is the cheapest possible liveness probe, since
# the server sends headers and no body. A health endpoint that rejects the standard health
# check is a real defect, and an external monitor found it in production within minutes.
@app.api_route("/health", methods=["GET", "HEAD"])
async def health() -> JSONResponse:
    corpus = state["corpus"]
    persona = state["corpus_persona"]
    body = {
        "status": "ok" if corpus else "degraded",
        "index_loaded": corpus is not None,
        "chunk_count": len(corpus.chunks) if corpus else 0,  # type: ignore[union-attr]
        "index_version": corpus.meta["index_version"] if corpus else None,  # type: ignore[union-attr]
        # Deliberately not folded into the fields above: the HR demo's health is the
        # long-standing contract an uptime monitor already parses, and the persona corpus is
        # optional/additive, so it gets its own namespaced sub-object instead of changing
        # the meaning of an existing field.
        "persona": {
            "index_loaded": persona is not None,
            "chunk_count": len(persona.chunks) if persona else 0,  # type: ignore[union-attr]
            "error": state["error_persona"],
        },
        "model_id": settings.mistral_model,
        "generation_configured": settings.generation_available,
        # Deliberately a SEPARATE field from index_loaded: Pinecone serves uploads only, so
        # it being unreachable must not imply the baseline demo is down.
        "pinecone_reachable": bool(settings.pinecone_api_key),
        "auth_configured": settings.auth_available,
        "memory_mb": round(current_rss_mb()),
        "memory_limit_mb": MEMORY_LIMIT_MB,
        "uploads_persist": settings.uploads_persist,
        "error": state["error"],
    }
    return JSONResponse(body, status_code=200 if corpus else 503)


@app.get("/api/documents")
async def documents() -> dict[str, object]:
    """The curated manifest. Never the filename -- 'Partex-Star-Group.pdf' is misleadingly
    named; its own PDF metadata title is 'Employee Handbook-Final'."""
    return {"documents": list(MANIFEST.values())}


@app.post("/api/ask", response_model=AskResponse)
async def ask(request: AskRequest, http_request: Request) -> AskResponse:
    from src.api.service import answer

    # 'corpus' picks WHICH pinned/retrieved pair this request answers against -- "hr" (the
    # original handbook+statute demo) or "persona" (reshadulkarim.me's resume+portfolio).
    # kb_id below is an orthogonal axis (an uploaded KB within whichever corpus is active);
    # it is only meaningful for "hr" today, since the persona corpus has no upload surface.
    corpus = _corpus_persona() if request.corpus == "persona" else _corpus()
    generator = _generator()
    registry = http_request.app.state.registry

    # kb_id picks the retriever. 'default' is the public committed corpus (a file, no
    # network, no auth); anything else is an uploaded KB. Asking an uploaded KB requires a
    # session, because it is not public data.
    kb_retriever = None
    if request.kb_id != "default":
        if not read_session(http_request):
            raise AuthRequired("Sign in to query an uploaded knowledge base.")
        if request.kb_id not in registry.kbs:
            raise KbNotFound(f"No knowledge base {request.kb_id!r}.")
        kb_retriever = registry.retrievers[request.kb_id]

    # run_in_threadpool, and this one is not a nicety -- it was taking the site down.
    #
    # answer() is synchronous and makes two network calls: embed the query (~500 ms) and
    # generate (~3 s). Called directly from an `async def`, that freezes the ENTIRE event
    # loop for ~4 seconds. So /health cannot respond while anyone is asking a question,
    # Render's health check times out, Render restarts the container -- and the asker's
    # connection is reset mid-request. Observed in production as `HTTP 000 in 2s` on
    # /api/ask with /health failing alongside it, while /  and /api/documents (which touch
    # nothing blocking) stayed green.
    #
    # I wrote this exact diagnosis in create_kb's docstring and fixed it there, without
    # checking whether the same pattern existed anywhere else. It did, on the busiest route
    # in the app.
    # Reserve the request's TOKEN cost before sending it, because tokens are the unit the
    # free tier actually meters. prompt_floor_tokens is the fixed part measured at boot --
    # system prompt + pinned handbook + a rounded-up retrieval allowance -- because the first
    # version counted only the handbook and under-reserved by 42%, so the gate spent 1.7x its
    # own budget and 429'd anyway.
    prompt_tokens = estimate_tokens(request.question) + corpus.prompt_floor_tokens
    async with state["gate"].reserve(prompt_tokens):  # type: ignore[union-attr]
        response = await run_in_threadpool(
            answer,
            request.question,
            corpus,
            generator,
            section_no=request.section_no,
            history=request.history,
            kb_retriever=kb_retriever,
            page=request.page,
        )
    _log(
        "ask",
        request_id=getattr(http_request.state, "request_id", None),
        route=response.route,
        insufficient=response.insufficient_information,
        citations=len(response.citations),
        latency_ms=response.latency_ms,
    )
    return response


if STATIC.exists():
    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(STATIC / "index.html")
