"""Domain types.

Citations are typed objects the whole way out -- never markdown strings. A markdown
citation is unassertable: you cannot write `assert c.printed_page == 59` against
'-- printed p.59 (PDF page 76)' without a regex. Rendering happens in the UI layer from a
typed object, so the model never emits a citation string and structurally cannot
fabricate one.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

DocKind = Literal["handbook", "statute", "uploaded", "resume", "portfolio"]
Modality = Literal["text", "ocr"]


class Chunk(BaseModel):
    """One retrievable unit. Carries its own provenance so a citation is by construction."""

    model_config = ConfigDict(frozen=True)

    chunk_id: str
    kb_id: str = "default"
    doc_id: str
    doc_title: str  # from the curated manifest, NEVER the filename
    doc_kind: DocKind
    text: str

    layer: str | None = None  # statute | commentary | handbook
    section_no: int | None = None
    section_title: str | None = None
    is_definition: bool = False

    zero_based_pdf_index: int
    printed_page: int
    half: Literal["left", "right"] | None = None

    source_modality: Modality
    ocr_mean_conf: float | None = None


class Citation(BaseModel):
    model_config = ConfigDict(frozen=True)

    doc_id: str
    doc_title: str
    doc_kind: DocKind
    section_no: int | None = None
    section_title: str | None = None
    printed_page: int
    pdf_page: int
    half: Literal["left", "right"] | None = None
    snippet: str  # sliced from the chunk by code, never generated
    source_modality: Modality
    ocr_confidence: float | None = None

    def render(self) -> str:
        """The one f-string that ends the printed-vs-physical argument.

        Print both: printed matches what the document says about itself, PDF matches the
        reviewer's scrollbar. The section number is the anchor the eval asserts on -- it is
        the statute's actual primary key, stable regardless of pagination, and it OCRs
        cleanly where footers do not ('ll' for 11, 'Az' for 47).
        """
        if self.doc_kind == "statute" and self.section_no is not None:
            return (
                f"{self.doc_title}, s.{self.section_no} {self.section_title} "
                f"— printed p.{self.printed_page} (PDF page {self.pdf_page} of 181)"
            )
        if self.doc_kind in ("resume", "portfolio"):
            # Markdown-sourced persona chunks have no real pagination (see chunk_markdown,
            # zero_based_pdf_index/printed_page are both 1) -- the section heading is the
            # only stable, human-readable anchor. PDF-sourced ones (papers) do have a real
            # printed page, so fall back to it when there's no heading.
            if self.section_title:
                return f"{self.doc_title} — {self.section_title}"
            return f"{self.doc_title} — p.{self.printed_page}"
        if self.half:
            return (
                f"{self.doc_title}, printed p.{self.printed_page} "
                f"(PDF page {self.pdf_page}, {self.half} half)"
            )
        return f"{self.doc_title}, printed p.{self.printed_page} (PDF page {self.pdf_page})"


class Turn(BaseModel):
    """One prior exchange. History is sent BY THE CLIENT on every request.

    Server-side sessions would die with the container on a free tier that restarts and
    sleeps. Client-held history is stateless, survives every restart, and costs nothing --
    and against a 262,144-token window, resending a few turns is free.
    """

    model_config = ConfigDict(frozen=True)
    question: str = Field(max_length=1000)
    answer: str = Field(max_length=8000)


class PageContext(BaseModel):
    """Which page the visitor is standing on, for the persona corpus (see prompts/persona.md).

    The site's routes map 1:1 onto corpus doc_ids (gen_pages.py builds every page from
    `slug`), so `slug` is looked up directly against Chunk.doc_id to pin the current page's
    chunks alongside the resume -- bias, don't confine (see persona.md's page-context rule).
    """

    model_config = ConfigDict(frozen=True)
    kind: Literal["project", "publication", "index", "home"] = "home"
    slug: str | None = None
    title: str | None = None


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=1000)
    kb_id: str = "default"
    corpus: Literal["hr", "persona"] = "hr"
    doc_filter: Literal["handbook", "statute"] | None = None
    section_no: int | None = Field(default=None, ge=1, le=354)  # a free 422 on nonsense
    history: list[Turn] = Field(default_factory=list, max_length=10)
    page: PageContext | None = None  # persona corpus only; ignored otherwise


class BookRequest(BaseModel):
    """A visitor asking to talk to Reshad directly (see prompts/persona.md's <<BOOK>> marker
    and docs/AI_ASSISTANT_PLAN.md sec.6). `website` is a honeypot: a real visitor never sees
    or fills this field (CSS-hidden in the widget), so a non-empty value is a bot signal --
    routes_book.py accepts the request but silently discards it rather than sending mail."""

    name: str = Field(min_length=1, max_length=120)
    email: str = Field(min_length=3, max_length=254)
    purpose: str = Field(min_length=1, max_length=2000)
    preferred_times: str = Field(default="", max_length=300)
    website: str = Field(default="", max_length=200)  # honeypot
    page: PageContext | None = None
    recent_history: list[Turn] = Field(default_factory=list, max_length=3)


class AskResponse(BaseModel):
    answer: str
    citations: list[Citation]
    insufficient_information: bool
    route: str  # derived in code from which docs the cited chunks came from
    latency_ms: int
    request_id: str
    index_version: str
