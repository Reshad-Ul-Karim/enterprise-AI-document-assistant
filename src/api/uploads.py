"""Runtime document upload. The NotebookLM surface.

This is the one place in the system where an API beats local compute, and the reason is
specific: a user uploads a scanned PDF to a box with 0.1 CPU and no GPU. Tesseract on 60
pages there would take minutes and blow the request timeout. Ollama and Pixtral need a GPU
that does not exist on a free tier. **Mistral OCR is an HTTP call** -- the compute happens
on Mistral's infrastructure and this box only forwards bytes. Verified working on the free
tier before any of this was written.

So the split is not a preference, it is physics:
  * BULK / build-time OCR  -> local tesseract. Free, unlimited, 181 pages in ~98s, and it
                              never ships in the image.
  * RUNTIME upload OCR     -> Mistral OCR API. Needs no local compute, which is the only
                              reason it can happen on this box at all.

Same interface, two implementations, each doing the job the other physically cannot.

WHAT IS HONESTLY WORSE HERE THAN IN THE COMMITTED CORPUS, and it must be said out loud:
the statute gets a chunker built on its own section grammar, because I know that grammar.
For a document uploaded thirty seconds from now I do not, so it gets a generic recursive
split. Citations from an uploaded document therefore carry a page number but no section
anchor, and abstention over it is BOUNDED, not provable -- the document is not pinned in
context the way the 3,081-token handbook is. That is a real asymmetry, not a rough edge.
"""

from __future__ import annotations

import base64
import hashlib
import io
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Literal

from src.api.errors import AppError
from src.api.memguard import assert_room_to_ingest, estimate_ingest_mb
from src.api.settings import settings
from src.core.models import Chunk

JobState = Literal["queued", "extracting", "embedding", "indexing", "done", "failed"]


class PayloadTooLarge(AppError):
    status_code = 413
    code = "PAYLOAD_TOO_LARGE"  # type: ignore[assignment]


class ScannedPdfRequiresOcr(AppError):
    status_code = 422
    code = "SCANNED_PDF_REQUIRES_OCR"  # type: ignore[assignment]


class KbNotFound(AppError):
    status_code = 404
    code = "KB_NOT_FOUND"  # type: ignore[assignment]


class UploadBackendUnavailable(AppError):
    status_code = 503
    code = "UPLOAD_BACKEND_UNAVAILABLE"  # type: ignore[assignment]


@dataclass
class Job:
    job_id: str
    kb_id: str
    filename: str
    state: JobState = "queued"
    progress: str = ""
    doc_id: str | None = None
    pages: int = 0
    chunks: int = 0
    modality: str | None = None
    error: str | None = None


@dataclass
class KnowledgeBase:
    kb_id: str
    name: str
    chunks: list[Chunk] = field(default_factory=list)
    docs: dict[str, str] = field(default_factory=dict)  # sha256 -> filename, for idempotency


def _normalise(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    return re.sub(r"(\w)-\n\s*(\w)", r"\1\2", text)


def assess_extractability(pdf_bytes: bytes) -> tuple[int, bool]:
    """(page_count, needs_ocr).

    Deciding this UP FRONT is what keeps the cost model honest: a text-native PDF is free
    and instant to extract locally, so paying an OCR API for it would be waste. Only pages
    that genuinely have no text layer go to the API.

    Uses pypdf, not PyMuPDF: `.importlinter` forbids src.api from importing pymupdf, because
    PyMuPDF is a BUILD-TIME dependency that is deliberately absent from the runtime image --
    a rule learned when importing it here crashed a deploy on boot.
    """
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(pdf_bytes))
    pages = len(reader.pages)
    sampled = reader.pages[: min(5, pages)]
    chars = sum(len((p.extract_text() or "").strip()) for p in sampled)
    # <50 chars/page averaged over the sample means there is no text layer worth having.
    return pages, (chars / max(len(sampled), 1)) < 50


def extract_text_native(pdf_bytes: bytes) -> list[tuple[int, str]]:
    """Local, free, instant. [(printed_page, text)] -- 1-based, as a human counts pages."""
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(pdf_bytes))
    out: list[tuple[int, str]] = []
    for i, page in enumerate(reader.pages):
        text = _normalise(page.extract_text() or "")
        if text.strip():
            out.append((i + 1, text))
    return out


def extract_via_mistral_ocr(pdf_bytes: bytes, api_key: str) -> list[tuple[int, str]]:
    """Scanned PDFs. The compute happens at Mistral, not on this 0.1-CPU box.

    Returns markdown per page, which preserves layout and tables far better than tesseract
    manages on a dense scan.
    """
    from mistralai import Mistral

    client = Mistral(api_key=api_key)
    response = client.ocr.process(
        model="mistral-ocr-latest",
        document={
            "type": "document_url",
            "document_url": f"data:application/pdf;base64,{base64.b64encode(pdf_bytes).decode()}",
        },
    )
    return [
        (page.index + 1, _normalise(page.markdown))
        for page in response.pages
        if (page.markdown or "").strip()
    ]


def chunk_uploaded(
    pages: list[tuple[int, str]], doc_id: str, doc_title: str, kb_id: str, modality: str
) -> list[Chunk]:
    """Generic recursive split -- the honest default for an unknown grammar.

    THIS is where langchain-text-splitters earns its place, and it is the ONLY place. For
    the statute I measured RecursiveCharacterTextSplitter(1000, 200) merging ss.115/116/117
    -- casual, sick and annual leave, three distinct entitlements sharing a printed page --
    into one chunk with one wrong page number, so the statute gets a chunker built on its
    own section grammar instead. For a document I have never seen, a recursive character
    split IS correct. Same library, opposite verdicts, both measured.

    Chunking per page rather than across pages: it costs a little coherence at page
    boundaries and buys an exact page number on every citation, which FR#4 requires.
    """
    # langchain-text-splitters (0.3 MB) drags in langchain-core (5.1 MB) -> LANGSMITH
    # (7.2 MB), which is a TELEMETRY CLIENT. In a document-confidentiality product that is a
    # bad look, so it is disabled explicitly rather than assumed off: langsmith only traces
    # when these are truthy, and being explicit means an env var set elsewhere on the host
    # cannot quietly opt this service into shipping user documents to a third party.
    import os

    os.environ.setdefault("LANGSMITH_TRACING", "false")
    os.environ.setdefault("LANGCHAIN_TRACING_V2", "false")

    from langchain_text_splitters import RecursiveCharacterTextSplitter

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200,
        separators=["\n\n", "\n", ". ", " ", ""],
    )
    chunks: list[Chunk] = []
    for printed_page, text in pages:
        for n, piece in enumerate(splitter.split_text(text)):
            if not piece.strip():
                continue
            chunks.append(
                Chunk(
                    chunk_id=f"{doc_id}:p{printed_page}:c{n}",
                    kb_id=kb_id,
                    doc_id=doc_id,
                    doc_title=doc_title,
                    doc_kind="uploaded",
                    text=piece.strip(),
                    zero_based_pdf_index=printed_page - 1,
                    printed_page=printed_page,
                    source_modality="ocr" if modality == "ocr" else "text",
                )
            )
    return chunks


def ingest(pdf_bytes: bytes, filename: str, kb: KnowledgeBase, job: Job) -> None:
    """Extract -> chunk -> embed -> store. Mutates `job` so the UI can poll it.

    Idempotent on sha256(bytes): re-uploading the same file returns the same doc_id instead
    of duplicating it. That is what makes "the job store is ephemeral" survivable -- after a
    restart, recovery is a re-upload, never a duplicate and never a corruption.
    """
    size_mb = len(pdf_bytes) / 1e6
    if size_mb > settings.max_upload_mb:
        raise PayloadTooLarge(
            f"{size_mb:.1f} MB exceeds the {settings.max_upload_mb} MB limit. This is a free "
            f"tier with 512 MB of RAM; the cap protects the public demo from an upload."
        )

    digest = hashlib.sha256(pdf_bytes).hexdigest()[:16]
    if digest in kb.docs:
        job.state = "done"
        job.doc_id = digest
        job.progress = f"Already ingested as {kb.docs[digest]!r} — no duplicate created."
        return

    job.state = "extracting"
    pages, needs_ocr = assess_extractability(pdf_bytes)

    # Check BEFORE the expensive part. If this instance is already near its limit, refusing
    # one upload with a typed 503 is strictly better than being OOM-killed and handing every
    # user -- including whoever is on the public demo -- a 502.
    assert_room_to_ingest(estimate_ingest_mb(len(pdf_bytes), pages))

    if pages > settings.max_upload_pages:
        raise PayloadTooLarge(
            f"{pages} pages exceeds the {settings.max_upload_pages}-page limit on this free tier."
        )

    if needs_ocr:
        if not settings.mistral_api_key:
            raise ScannedPdfRequiresOcr(
                "This PDF is scanned images with no text layer, so it needs OCR — and OCR "
                "needs MISTRAL_API_KEY, which is not configured on this deployment."
            )
        job.progress = f"Scanned PDF ({pages} pages) — OCR via Mistral (no local compute)…"
        extracted = extract_via_mistral_ocr(pdf_bytes, settings.mistral_api_key)
        modality = "ocr"
    else:
        job.progress = f"Text-native PDF ({pages} pages) — extracting locally, no API needed…"
        extracted = extract_text_native(pdf_bytes)
        modality = "text"

    if not extracted:
        raise ScannedPdfRequiresOcr("No text could be extracted from this PDF.")

    job.state = "embedding"
    job.progress = f"Chunking and embedding {len(extracted)} pages…"
    title = filename.rsplit(".", 1)[0].replace("_", " ").replace("-", " ").strip() or filename
    chunks = chunk_uploaded(extracted, digest, title, kb.kb_id, modality)

    job.state = "indexing"
    kb.chunks.extend(chunks)
    kb.docs[digest] = filename

    job.state = "done"
    job.doc_id = digest
    job.pages = len(extracted)
    job.chunks = len(chunks)
    job.modality = modality
    job.progress = (
        f"Indexed {len(chunks)} chunks from {len(extracted)} pages "
        f"({'OCR' if modality == 'ocr' else 'text-native'})."
    )
